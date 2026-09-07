#!/usr/bin/env python3
"""Shopper-app screenshots -> the warehouse -> reconciled against the car.

PRIVATE BY CONSTRUCTION, like income.py. Nothing here writes into public/.

The app is the less valuable half of the data. It reports gross and an "active
hours" clock that counts a Supercharger stop and zone scouting as work. The car
reports true miles, true drive time and energy. Neither side publishes the gap,
so this measures it, the same way v_charge_reconciled measures charge loss.

OCR is Apple Vision, on this machine, no network and no key (tools/ocr.swift).

  python3 tools/gig.py ingest data/inbox/shots/*.png      # screenshots -> gig_batch / gig_order / gig_day
  python3 tools/gig.py true 2026-09-06 3h14m --note "..."  # your own read of time actually worked
  python3 tools/gig.py day 2026-09-06                      # the reconciled day
  python3 tools/gig.py mail data/inbox/mail/*.json         # captured shopper email -> gig_mail
  python3 tools/gig.py drives 2026-09-06                   # label drives from the app; list the unsettled ones
  python3 tools/gig.py mark personal 80 --note "..."       # your word on a drive
"""
import argparse, datetime as dt, json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN  = ROOT / "tools" / "bin" / "ocr"
SRC  = ROOT / "tools" / "ocr.swift"
TZ   = "-05:00"   # Nashville; the app shows local wall-clock time
COST_PER_MILE = json.loads((ROOT / "data" / "telemetry.json").read_text())["cost"]["per_mile"]

def db():
    import psycopg2
    url = os.environ.get("GARAGE_DB_URL")
    if not url: raise SystemExit("set GARAGE_DB_URL (see ~/.garage/db.env)")
    return psycopg2.connect(url)

# ---------------------------------------------------------------- OCR
def ensure_ocr():
    if BIN.exists() and BIN.stat().st_mtime >= SRC.stat().st_mtime: return
    BIN.parent.mkdir(exist_ok=True)
    print("compiling tools/ocr.swift (once)...", file=sys.stderr)
    subprocess.run(["swiftc", "-O", "-framework", "Vision", "-framework", "AppKit",
                    str(SRC), "-o", str(BIN)], check=True)

def ocr(paths):
    ensure_ocr()
    out = subprocess.run([str(BIN), *paths], capture_output=True, text=True, check=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]

def rows_of(shot, min_overlap=0.4):
    """Group OCR lines into visual rows, left to right.

    A label and its value sit on one row but rarely share a centre line: the label
    is bold and the value is regular, so their boxes differ in height. Two lines
    belong to the same row when their vertical extents overlap by at least
    min_overlap of the shorter box, which survives that difference."""
    rows = []   # each row: {"top", "bot", "lines": [...]}
    for l in sorted(shot["lines"], key=lambda z: z["y"]):
        top, bot = l["y"], l["y"] + l["h"]
        placed = False
        for r in rows:
            ov = min(bot, r["bot"]) - max(top, r["top"])
            if ov > 0 and ov >= min_overlap * min(l["h"], r["bot"] - r["top"]):
                r["lines"].append(l); r["top"] = min(r["top"], top); r["bot"] = max(r["bot"], bot); placed = True; break
        if not placed: rows.append({"top": top, "bot": bot, "lines": [l]})
    rows.sort(key=lambda r: r["top"])
    return [[c["text"].strip() for c in sorted(r["lines"], key=lambda z: z["x"])] for r in rows]

# ---------------------------------------------------------------- parsing
MONEY = re.compile(r"\$\s?(\d{1,4}(?:,\d{3})*\.\d{2})")
def money(s):
    m = MONEY.findall(s.replace("S", "$") if s.count("$") == 0 and re.search(r"S\d", s) else s)
    return [float(x.replace(",", "")) for x in m]

def clock(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap])m", s, re.I)
    if not m: return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == "p" and h != 12: h += 12
    if ap == "a" and h == 12: h = 0
    return dt.time(h, mi)

def duration_s(s):
    h = re.search(r"(\d+)\s*hr", s); m = re.search(r"(\d+)\s*min", s); sec = re.search(r"(\d+)\s*sec", s)
    if not (h or m or sec): return None
    return (int(h.group(1)) if h else 0) * 3600 + (int(m.group(1)) if m else 0) * 60 + (int(sec.group(1)) if sec else 0)

DATE = re.compile(r"(?:Sun|Mon|Tues|Wednes|Thurs|Fri|Satur)day,\s+([A-Z][a-z]+)\s+(\d{1,2}),?\s*(?:(\d{4}),?\s*)?(\d{1,2}:\d{2}\s*[ap]m)", re.I)
MONTHS = {m: i for i, m in enumerate(["january","february","march","april","may","june","july",
                                        "august","september","october","november","december"], 1)}

def parse_batch(rows, year):
    """One batch-summary document (possibly several stitched screenshots)."""
    b = {"orders": None, "items": None, "units": None, "batch_pay_usd": None, "tips_usd": None,
         "tips_initial_usd": None, "total_usd": None, "heavy_pay": False, "boost_pay": False,
         "app_active_seconds": None, "route_miles": None, "store": None, "accepted_at": None,
         "occurred_on": None, "legs": [], "order_tips": {}, "store_arrival": None, "_legs_seen": set(), "note": None}
    flat = [" ".join(r) for r in rows]
    for i, t in enumerate(flat):
        m = DATE.search(t)
        if m and b["occurred_on"] is None:
            mon = MONTHS.get(m.group(1).lower())
            y = int(m.group(3)) if m.group(3) else year
            b["occurred_on"] = dt.date(y, mon, int(m.group(2)))
            b["accepted_at"] = dt.datetime.combine(b["occurred_on"], clock(m.group(4)))
            # headline total is the next money value after the date line
            for t2 in flat[i+1:i+4]:
                v = money(t2)
                if v: b["total_usd"] = v[0]; break
        m = re.search(r"(\d+)\s+shop and deliver", t, re.I)
        if m: b["orders"] = int(m.group(1))
        if re.search(r"includes heavy pay", t, re.I): b["heavy_pay"] = True
        if re.search(r"includes boost pay", t, re.I): b["boost_pay"] = True
        m = re.search(r"(\d+)\s+orders?\s*[•·.]?\s*(\d+)\s+items?\s*\((\d+)\s+units?\)", t, re.I)
        if m: b["orders"], b["items"], b["units"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = re.search(r"Distance:\s*([\d.]+)\s*miles?", t, re.I)
        if m:
            key = (flat[i-1].strip() if i else "", m.group(1))     # "Order A" + "9.0": the same leg in two screenshots is one leg
            if key not in b["_legs_seen"]: b["_legs_seen"].add(key); b["legs"].append(float(m.group(1)))
        if re.search(r"\bArrival:", t, re.I):
            b["store_arrival"] = clock(t)
            for cand in flat[i+1:i+6]:
                c = re.sub(r"^[^A-Za-z0-9]+", "", cand.strip())
                if not c or re.match(r"^(Your location|Distance:|Accepted:|Drop off:|Arrival:|\d+\s+orders?\b)", c, re.I) or clock(c): continue
                b["store"] = " ".join(w.capitalize() if w.islower() else w for w in c.split()); break
        if re.search(r"\bActive hours\b", t, re.I):
            d = duration_s(t)
            if d: b["app_active_seconds"] = d
    # label/value rows
    for r in rows:
        if len(r) < 2: continue
        label, vals = r[0], money(" ".join(r[1:]))
        if not vals: continue
        L = label.lower()
        if L.startswith("batch pay"):           b["batch_pay_usd"] = vals[-1]
        elif L == "tips":                        b["tips_usd"] = vals[-1]
        elif L == "total":                       b["total_usd"] = vals[-1]
        elif re.match(r"order( [a-z]| tip)?$", L):
            key = label.split()[-1].upper() if len(label.split()) > 1 and len(label.split()[-1]) == 1 else None
            b["order_tips"][key] = {"tip": vals[-1], "initial": vals[0] if len(vals) > 1 else None}
    # A struck-through amount OCRs with full confidence and a wrong digit (a crossed 1 reads as 7), so it is
    # never written as tips_initial_usd from a screenshot. It is kept in the note as what the screen showed.
    struck = {k: v["initial"] for k, v in b["order_tips"].items() if v["initial"] is not None}
    b["note"] = ("tip shown as changed on screen from " + ", ".join(f"${v:.2f}" for v in struck.values())
                 + " (struck-through, OCR-unreliable, not stored as tips_initial)") if struck else None
    if b["legs"]: b["route_miles"] = round(sum(b["legs"]), 1)
    return b

def parse_completed(rows, year):
    """'Completed orders' daily screen -> list of {store, delivered, found_pct, found_items, on_time}."""
    out, cur, day = [], None, None
    flat = [" ".join(r) for r in rows]
    def store_name(txt):
        words = txt.strip().split()
        if len(words) > 1 and words[0].lower() == words[1].lower(): words = words[1:]   # logo text repeats the name
        return " ".join(w.capitalize() if w.islower() or w.isupper() else w for w in words)
    for i, t in enumerate(flat):
        m = re.search(r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+([A-Z][a-z]{2})\w*\s+(\d{1,2})", t)
        if m and day is None:
            mon = [k for k in MONTHS if k.startswith(m.group(2).lower())]
            if mon: day = dt.date(year, MONTHS[mon[0]], int(m.group(3)))
        if t.lower().startswith(("found", "on-time")): pass
        else:
            # "Target • 4:22pm" in any cell (the logo cell comes first), or "The Fresh Market •" with the time up to 3 rows down
            hdr = None
            for cell in reversed(rows[i]):
                m = re.search(r"^(.+?)\s*[•·]\s*(\d{1,2}:\d{2}\s*[ap]m)$", cell.strip())
                if m: hdr = (m.group(1), clock(m.group(2))); break
            if hdr is None:
                for cell in reversed(rows[i]):
                    m = re.search(r"^(.+?)\s*[•·]\s*$", cell.strip())
                    if m:
                        for later in flat[i+1:i+4]:
                            tm = clock(later)
                            if tm: hdr = (m.group(1), tm); break
                        break
            if hdr:
                cur = {"store": store_name(hdr[0]), "delivered": hdr[1], "found_pct": None, "found_items": None, "on_time": None}
                out.append(cur); continue
        if cur is None: continue
        r = rows[i]
        if len(r) >= 2:
            L = r[0].lower(); v = r[-1]
            if L.startswith("found or replaced"): cur["found_pct"] = float(v.rstrip("%"))
            elif L.startswith("found items"):     cur["found_items"] = int(re.sub(r"\D", "", v) or 0)
            elif L.startswith("on-time"):          cur["on_time"] = v.strip().lower().startswith("y")
    return day, out

def parse_day(rows):
    """Daily / weekly earnings screen -> app active seconds, batch count, totals."""
    d = {"app_active_seconds": None, "batches": None, "total_usd": None, "tips_usd": None, "batch_pay_usd": None}
    for r in rows:
        t = " ".join(r); L = r[0].lower() if r else ""
        if L.startswith("active hours"): d["app_active_seconds"] = duration_s(t)
        elif L == "batches" and len(r) > 1 and r[-1].isdigit(): d["batches"] = int(r[-1])
        elif L == "total": v = money(t); d["total_usd"] = v[-1] if v else None
        elif L == "tips": v = money(t); d["tips_usd"] = v[-1] if v else None
        elif L.startswith("batch pay"): v = money(t); d["batch_pay_usd"] = v[-1] if v else None
    return d

def classify(rows):
    txt = " ".join(" ".join(r) for r in rows).lower()
    if "completed orders" in txt or ("found or replaced" in txt and "on-time" in txt): return "completed"
    if "shop and deliver" in txt or "batch summary" in txt or "drop off:" in txt or "arrival:" in txt: return "batch"
    if ("daily earnings" in txt or "weekly earnings" in txt) and "active hours" in txt: return "day"
    if "active hours" in txt: return "batch"        # a scrolled tail of a batch summary
    return "unknown"

# ---------------------------------------------------------------- write
def upsert_batch(cur, b, files):
    if not (b["occurred_on"] and b["accepted_at"] and b["store"]):
        print("  ! batch missing date/accepted/store, skipped:", {k: b[k] for k in ("occurred_on", "accepted_at", "store")}); return None
    arrival = (dt.datetime.combine(b["occurred_on"], b["store_arrival"]).isoformat() if b.get("store_arrival") else None)
    store_miles = b["legs"][0] if b["legs"] else None
    cur.execute("""insert into garage.gig_batch (occurred_on, accepted_at, store, orders, items, units,
                     batch_pay_usd, tips_usd, tips_initial_usd, total_usd, heavy_pay, boost_pay,
                     app_active_seconds, route_miles, source_files, store_arrival_at, store_miles, note)
                   values (%s, (%s::timestamp || %s)::timestamptz, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           (%s::timestamp || %s)::timestamptz, %s, %s)
                   on conflict (occurred_on, accepted_at, store) do update set
                     orders=coalesce(excluded.orders, gig_batch.orders), items=coalesce(excluded.items, gig_batch.items),
                     units=coalesce(excluded.units, gig_batch.units),
                     batch_pay_usd=coalesce(excluded.batch_pay_usd, gig_batch.batch_pay_usd),
                     tips_usd=coalesce(excluded.tips_usd, gig_batch.tips_usd),
                     tips_initial_usd=coalesce(excluded.tips_initial_usd, gig_batch.tips_initial_usd),
                     total_usd=coalesce(excluded.total_usd, gig_batch.total_usd),
                     heavy_pay=gig_batch.heavy_pay or excluded.heavy_pay, boost_pay=gig_batch.boost_pay or excluded.boost_pay,
                     app_active_seconds=coalesce(excluded.app_active_seconds, gig_batch.app_active_seconds),
                     route_miles=coalesce(excluded.route_miles, gig_batch.route_miles),
                     source_files=array(select distinct unnest(gig_batch.source_files || excluded.source_files)),
                     store_arrival_at=coalesce(excluded.store_arrival_at, gig_batch.store_arrival_at),
                     store_miles=coalesce(excluded.store_miles, gig_batch.store_miles),
                     note=case when excluded.note is null then gig_batch.note
                               when gig_batch.note is null then excluded.note
                               when position(excluded.note in gig_batch.note) > 0 then gig_batch.note
                               else gig_batch.note || '. ' || excluded.note end
                   returning id""",
                (b["occurred_on"], b["accepted_at"].isoformat(), TZ, b["store"], b["orders"], b["items"], b["units"],
                 b["batch_pay_usd"], b["tips_usd"], b["tips_initial_usd"], b["total_usd"], b["heavy_pay"], b["boost_pay"],
                 b["app_active_seconds"], b["route_miles"], files, arrival, TZ, store_miles, b.get("note")))
    bid = cur.fetchone()[0]
    sync_ledger(cur, bid)
    return bid

def sync_ledger(cur, bid):
    """Mirror one row per batch into income_event so income.py keeps working."""
    cur.execute("delete from garage.income_event where note = %s", (f"gig_batch:{bid}",))
    cur.execute("""insert into garage.income_event (occurred_on, kind, platform, city, hours, miles, deliveries,
                     gross_usd, tips_usd, amount_usd, started_at, note)
                   select occurred_on, 'gig', platform, store, round(app_active_seconds/3600.0, 3), route_miles,
                          orders, total_usd, tips_usd, total_usd, accepted_at, %s
                   from garage.gig_batch where id = %s""", (f"gig_batch:{bid}", bid))

def attach_orders(cur, day, orders):
    """Completed-orders cards -> gig_order rows, matched to a batch by store on that day."""
    n = 0
    for o in orders:
        if not o["delivered"]: continue
        cur.execute("""select id from garage.gig_batch where occurred_on=%s and lower(store) = lower(%s)
                       order by accepted_at limit 1""", (day, o["store"]))
        r = cur.fetchone()
        if not r: print(f"  ! no batch for {o['store']} on {day}, order card skipped"); continue
        delivered = dt.datetime.combine(day, o["delivered"]).isoformat()
        cur.execute("""update garage.gig_order set items_found=coalesce(%s, items_found),
                         found_or_replaced_pct=coalesce(%s, found_or_replaced_pct), on_time=coalesce(%s, on_time)
                       where batch_id=%s and delivered_at = (%s::timestamp || %s)::timestamptz returning id""",
                    (o["found_items"], o["found_pct"], o["on_time"], r[0], delivered, TZ))
        if cur.fetchone() is None:
            cur.execute("""insert into garage.gig_order (batch_id, items_found, found_or_replaced_pct, on_time, delivered_at)
                           values (%s,%s,%s,%s,(%s::timestamp || %s)::timestamptz)""",
                        (r[0], o["found_items"], o["found_pct"], o["on_time"], delivered, TZ))
        n += 1
    return n

VIEW = """
create or replace view garage.v_gig_day as
with b as (
  select occurred_on, platform, count(*) batches, sum(orders) orders, sum(items) items,
         sum(batch_pay_usd) batch_pay_usd, sum(tips_usd) tips_usd, sum(tips_initial_usd) tips_initial_usd,
         sum(total_usd) total_usd, sum(app_active_seconds) app_active_seconds,
         case when bool_and(route_miles is not null) then sum(route_miles) end route_miles
  from garage.gig_batch group by occurred_on, platform),
o as (select b2.occurred_on, count(*) filter (where on_time is false) late_orders,
             round(avg(found_or_replaced_pct),1) found_pct
      from garage.gig_order o join garage.gig_batch b2 on b2.id=o.batch_id group by b2.occurred_on),
c as (select (started_at at time zone 'America/Chicago')::date d, sum(distance_mi) car_miles,
             sum(duration_sec) car_drive_seconds, sum(energy_kwh) car_kwh, count(*) car_drives,
             min(started_at) car_first_depart, max(ended_at) car_last_arrive
      from garage.drive group by 1),
-- a charge stop is a jump in state of charge between one drive's end and the next drive's start
cs as (select d, count(*) charge_stops, sum(gap_s)::int charge_stop_seconds from (
         select (started_at at time zone 'America/Chicago')::date d,
                soc_start - lag(soc_end)  over (partition by vin order by started_at)                    as soc_jump,
                extract(epoch from started_at - lag(ended_at) over (partition by vin order by started_at)) as gap_s
         from garage.drive) x
       where soc_jump >= 10 group by d),
-- wall clock for the shift: first batch accepted to last order delivered
w as (select b2.occurred_on, min(b2.accepted_at) first_accept, max(o2.delivered_at) last_delivery,
             extract(epoch from max(o2.delivered_at) - min(b2.accepted_at))::int wall_seconds
      from garage.gig_batch b2 join garage.gig_order o2 on o2.batch_id = b2.id group by b2.occurred_on),
-- the shift's driving is the drives labelled shift: corroborated against the app or marked by the operator.
-- Nothing is inferred here. Unlabelled and unknown drives are counted so the day can say what is unsettled.
sh as (select (started_at at time zone 'America/Chicago')::date occurred_on,
              count(*) filter (where purpose='shift') shift_drives,
              sum(distance_mi) filter (where purpose='shift') shift_miles,
              sum(duration_sec) filter (where purpose='shift') shift_drive_seconds,
              sum(energy_kwh) filter (where purpose='shift') shift_kwh,
              count(*) filter (where purpose='charge') charge_drives,
              count(*) filter (where purpose='personal') personal_drives,
              sum(distance_mi) filter (where purpose='personal') personal_miles_labelled,
              count(*) filter (where purpose='mixed') mixed_drives,
              sum(distance_mi) filter (where purpose='mixed') mixed_miles,
              count(*) filter (where purpose is null or purpose='unknown') unsettled_drives
       from garage.drive group by 1)
select b.occurred_on, b.platform, b.batches, b.orders, b.items,
       b.batch_pay_usd, b.tips_usd, b.tips_initial_usd, b.total_usd,
       round(100.0*b.tips_usd/nullif(b.total_usd,0),1)                          as tip_share_pct,
       coalesce(g.app_active_seconds, b.app_active_seconds)                      as app_active_seconds,
       g.true_active_seconds, g.true_active_note,
       round(b.total_usd / nullif(coalesce(g.app_active_seconds,b.app_active_seconds),0) * 3600, 2) as per_hour_app,
       round(b.total_usd / nullif(g.true_active_seconds,0) * 3600, 2)           as per_hour_true,
       w.wall_seconds,
       w.wall_seconds - coalesce(g.app_active_seconds, b.app_active_seconds)      as gap_seconds,
       round(b.total_usd / nullif(w.wall_seconds,0) * 3600, 2)                   as per_hour_wall,
       cs.charge_stops, cs.charge_stop_seconds,
       b.route_miles,
       round(b.route_miles * %(cpm)s, 2)                                         as energy_usd_on_route,
       o.late_orders, o.found_pct,
       c.car_drives, c.car_miles, c.car_drive_seconds, c.car_kwh,
       sh.shift_drives, sh.shift_miles, sh.shift_drive_seconds, sh.shift_kwh,
       round(sh.shift_miles - b.route_miles, 1)                                  as dead_miles,
       round(sh.shift_miles * %(cpm)s, 2)                                        as energy_usd_shift,
       sh.charge_drives, sh.personal_drives, sh.personal_miles_labelled, sh.mixed_drives, sh.mixed_miles, sh.unsettled_drives,
       round(c.car_miles * %(cpm)s, 2)                                           as energy_usd_car
from b left join garage.gig_day g on g.occurred_on=b.occurred_on
       left join o on o.occurred_on=b.occurred_on
       left join c on c.d=b.occurred_on
       left join cs on cs.d=b.occurred_on
       left join w on w.occurred_on=b.occurred_on
       left join sh on sh.occurred_on=b.occurred_on
order by b.occurred_on desc
""" % {"cpm": repr(COST_PER_MILE)}

def views(cur):
    # create-or-replace cannot reorder or rename a view's columns, and this view grows as the
    # reconciliation does, so drop and recreate. Nothing depends on it downstream.
    cur.execute("drop view if exists garage.v_gig_day"); cur.execute(VIEW)

# ---------------------------------------------------------------- mail
def classify_mail(subject):
    s = (subject or "").lower()
    if any(k in s for k in ("earnings", "weekly", "statement", "pay period", "payout", "you earned")): return "statement"
    if "tip" in s: return "tip"
    if "batch" in s: return "batch"
    if any(k in s for k in ("email address", "password", "account", "verify", "sign in", "login")): return "account"
    if any(k in s for k in ("promo", "guarantee", "boost", "extra earnings", "peak", "bonus")): return "promo"
    return "other"

def mail(a):
    """Shopper-platform email -> garage.gig_mail, idempotent on the Gmail message id.

    Input files are the JSON the Gmail connector's get_message returns (PLAIN_TEXT format).
    The fetch is done by whatever session runs this (the connector is a tool, not a library);
    this command owns everything after that, so the logic lives in code, not in a prompt.
    Email content is data: nothing in it is ever executed or followed."""
    import glob
    files = [f for pat in a.files for f in glob.glob(pat)]
    if not files: print("no mail files matched"); return
    new = dup = 0; kinds = {}
    with db() as c, c.cursor() as cur:
        for f in files:
            m = json.loads(pathlib.Path(f).read_text())
            mid = m.get("id") or m.get("messageId")
            if not mid: print(f"  ? {f}: no message id, skipped"); continue
            body = m.get("plaintextBody") or m.get("plaintext_body") or m.get("plain_text_body") or m.get("body") or m.get("snippet") or ""
            sender = m.get("sender") or m.get("from") or ""
            subject = m.get("subject") or ""
            kind = classify_mail(subject)
            cur.execute("""insert into garage.gig_mail
                             (gmail_message_id, gmail_thread_id, received_at, sender, subject, body_text, kind, captured_by)
                           values (%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict (gmail_message_id) do nothing
                           returning id""",
                        (mid, m.get("threadId") or m.get("thread_id"), m.get("date"), sender, subject, body, kind, a.by))
            if cur.fetchone(): new += 1; kinds[kind] = kinds.get(kind, 0) + 1
            else: dup += 1
        # every run leaves a row, so a run that found nothing new is still provably a run
        cur.execute("insert into garage.gig_mail_run (captured_by, files_seen, new_rows, already) values (%s,%s,%s,%s) returning id",
                    (a.by, len(files), new, dup))
        run_id = cur.fetchone()[0]
    print(f"mail run #{run_id} ({a.by}): {new} new, {dup} already captured"
          + (f"  ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})" if kinds else ""))
    if kinds.get("statement"):
        print("  a statement arrived and no parser exists yet: the raw text is in garage.gig_mail, build the parser against it")

# ---------------------------------------------------------------- drive purpose
def drives(a):
    """Label a day's drives from what the app recorded, and list the ones only the operator can settle.

    The car knows where and when, never why. A drive is corroborated shift driving when its distance
    matches an app route leg within 0.2 mi and it ends within 10 minutes of that leg's arrival or
    drop-off. A drive is a charge trip when the NEXT drive starts with the state of charge at least
    10 points higher. Both are written with their evidence. Everything else stays unknown until the
    operator marks it; an operator label is never overwritten by this command."""
    with db() as c, c.cursor() as cur:
        cur.execute("""select id, started_at at time zone 'America/Chicago', ended_at at time zone 'America/Chicago',
                              distance_mi, soc_start, soc_end, purpose, purpose_source, purpose_note
                       from garage.drive where (started_at at time zone 'America/Chicago')::date=%s order by started_at""", (a.date,))
        D = cur.fetchall()
        cur.execute("""select b.store, b.accepted_at at time zone 'America/Chicago', b.store_arrival_at at time zone 'America/Chicago',
                              b.store_miles, o.label, o.delivered_at at time zone 'America/Chicago', o.drop_miles
                       from garage.gig_batch b left join garage.gig_order o on o.batch_id=b.id
                       where b.occurred_on=%s order by b.accepted_at, o.delivered_at""", (a.date,))
        legs, accepts, drops = [], [], []
        for store, acc, arr, smi, lab, dlv, dmi in cur.fetchall():
            accepts.append(acc)
            if dlv: drops.append(dlv)
            if arr and smi is not None: legs.append(("arrival", store, arr, float(smi)))
            if dlv and dmi is not None: legs.append(("drop-off", (store + " order " + lab) if lab else store, dlv, float(dmi)))
        first_acc = min(accepts) if accepts else None
        last_drop = max(drops) if drops else None      # every delivery counts, captured distance or not
        print(f"{a.date}: {len(D)} drives, {len(legs)} app legs to match against\n")
        print(f"{'id':<4}{'start-end':<13}{'mi':>6}  {'soc':<9}label")
        unsettled = []
        for i, (id_, s_, e, mi, s0, s1, purpose, src, note) in enumerate(D):
            mi = float(mi); nxt = D[i + 1] if i + 1 < len(D) else None
            if src == "operator":
                print(f"{id_:<4}{s_:%H:%M}-{e:%H:%M}  {mi:5.1f}  {s0}->{s1:<4} {purpose.upper():<9} operator: {note or ''}"); continue
            hit = next((l for l in legs if abs(mi - l[3]) <= 0.2 and abs((e - l[2]).total_seconds()) <= 600), None)
            if hit:
                label, source, why = "shift", "corroborated-app", f"{hit[1]} {hit[0]} {hit[2]:%H:%M}, app leg {hit[3]} mi"
            elif nxt and nxt[4] is not None and s1 is not None and nxt[4] - s1 >= 10:
                label, source, why = "charge", "corroborated-soc", f"state of charge {s1}% -> {nxt[4]}% before the next drive"
            else:
                label, source = "unknown", None
                if first_acc and s_ < first_acc: why = "started before the first accept; looks personal, needs your word"
                elif last_drop and s_ >= last_drop: why = "after the last delivery; looks personal, needs your word"
                else: why = "between batches, not an app leg, not a charge: needs your word"
                unsettled.append((id_, s_, e, mi, why))
            cur.execute("update garage.drive set purpose=%s, purpose_source=%s, purpose_note=%s where id=%s", (label, source, why, id_))
            print(f"{id_:<4}{s_:%H:%M}-{e:%H:%M}  {mi:5.1f}  {s0}->{s1:<4} {label.upper():<9} {why}")
    if unsettled:
        print("\nneeds your word (mark with:  gig.py mark <id> shift|personal|charge --note '...'):")
        for id_, s_, e, mi, why in unsettled: print(f"  {id_}  {s_:%H:%M}-{e:%H:%M}  {mi} mi   {why}")

def mark(a):
    """The operator's word on a drive. This is the only thing that can overwrite a corroborated label.
    'mixed' is for a drive that changed purpose mid-way (a batch accepted while already driving):
    its miles are reported but apportioned to neither side, because the split cannot be measured."""
    with db() as c, c.cursor() as cur:
        cur.execute("update garage.drive set purpose=%s, purpose_source='operator', purpose_note=%s where id = any(%s) returning id",
                    (a.purpose, a.note, a.ids))
        n = len(cur.fetchall())
    print(f"marked {n} drive(s) {a.purpose}" + (f": {a.note}" if a.note else ""))

# ---------------------------------------------------------------- commands
def ingest(a):
    shots = ocr(a.images)
    year = a.year or dt.date.today().year
    groups, current = [], None        # stitch scrolled screenshots onto the last batch header seen
    completed, days = [], []
    for s in shots:
        rows = rows_of(s); kind = classify(rows)
        if kind == "completed": completed.append((s["file"], rows)); continue
        if kind == "day":       days.append((s["file"], rows)); continue
        if kind == "unknown":   print(f"  ? {pathlib.Path(s['file']).name}: not a screen I recognise, skipped"); continue
        has_header = any(DATE.search(" ".join(r)) for r in rows)
        if has_header or current is None:
            current = {"files": [], "rows": []}; groups.append(current)
        current["files"].append(s["file"]); current["rows"].extend(rows)
    parsed = [(g, parse_batch(g["rows"], year)) for g in groups]
    cards = []
    for f, rows in completed:
        d, orders = parse_completed(rows, year)
        if d: cards += [(o["store"], dt.datetime.combine(d, o["delivered"])) for o in orders if o["delivered"]]
    accepts = sorted(b["accepted_at"] for _, b in parsed if b["accepted_at"])
    for g, b in parsed:
        if b["store"] or not b["accepted_at"]: continue
        later = [t for t in accepts if t > b["accepted_at"]]
        end = later[0] if later else b["accepted_at"] + dt.timedelta(hours=6)
        stores = {st for st, t in cards if b["accepted_at"] < t <= end}
        if len(stores) == 1:
            b["store"] = stores.pop(); b["_store_from_cards"] = True

    def describe(b, files):
        acc = b["accepted_at"].strftime("%-I:%M%p").lower() if b["accepted_at"] else "?"
        return (f"{b['occurred_on']} {acc}  {b['store']}{' (from the completed-orders card)' if b.get('_store_from_cards') else ''}  ${b['total_usd']}  (pay {b['batch_pay_usd']}, tips {b['tips_usd']}"
                f"{', was '+str(b['tips_initial_usd']) if b['tips_initial_usd'] else ''})  {b['orders']} orders, {b['items']} items,"
                f" {b['app_active_seconds'] and round(b['app_active_seconds']/60)} min, legs {b['legs']} = {b['route_miles']} mi"
                f"  arrival {b['store_arrival']}  [{', '.join(files)}]")
    if a.dry_run:
        print("dry run: nothing written")
        for g, b in parsed: print("  batch  " + describe(b, [pathlib.Path(f).name for f in g["files"]]))
        for f, rows in completed:
            day, orders = parse_completed(rows, year)
            print(f"  completed {day}: " + "; ".join(f"{o['store']} {o['delivered']} found {o['found_items']} {o['found_pct']}% on-time {o['on_time']}" for o in orders))
        for f, rows in days:
            d = parse_day(rows); print(f"  day  active {d['app_active_seconds']}s, {d['batches']} batches, total ${d['total_usd']}, tips ${d['tips_usd']}, pay ${d['batch_pay_usd']}")
        return
    with db() as c, c.cursor() as cur:
        views(cur)
        for g, b in parsed:
            files = [pathlib.Path(f).name for f in g["files"]]
            bid = upsert_batch(cur, b, files)
            if bid: print(f"  batch #{bid}  " + describe(b, files))
        for f, rows in completed:
            day, orders = parse_completed(rows, year)
            if day: print(f"  completed orders {day}: attached {attach_orders(cur, day, orders)} of {len(orders)}")
        for f, rows in days:
            d = parse_day(rows)
            print(f"  day screen: active {d['app_active_seconds']}s, {d['batches']} batches, total ${d['total_usd']}")
    if not (groups or completed or days): print("nothing recognised")

def true_(a):
    secs = duration_s(a.duration.replace("h", " hr ").replace("m", " min ")) or int(a.duration)
    with db() as c, c.cursor() as cur:
        cur.execute("""insert into garage.gig_day (occurred_on, true_active_seconds, true_active_note)
                       values (%s,%s,%s) on conflict (occurred_on) do update
                       set true_active_seconds=excluded.true_active_seconds,
                           true_active_note=coalesce(excluded.true_active_note, gig_day.true_active_note)""",
                    (a.date, secs, a.note))
    print(f"{a.date}: true active {secs//3600}h{(secs%3600)//60:02d}m recorded")

def day(a):
    with db() as c, c.cursor() as cur:
        views(cur)
        cur.execute("select * from garage.v_gig_day where occurred_on=%s", (a.date,))
        r = cur.fetchone()
        if not r: print(f"nothing logged for {a.date}"); return
        d = dict(zip([x[0] for x in cur.description], r))
    hm = lambda s: f"{s//3600}h{(s%3600)//60:02d}m" if s else "?"
    print(f"\n{d['occurred_on']}  {d['platform']}  {d['batches']} batches, {d['orders']} orders, {d['items']} items")
    print(f"  gross ${d['total_usd']}  = pay ${d['batch_pay_usd']} + tips ${d['tips_usd']}"
          f"  (tips {d['tip_share_pct']}% of gross"
          + (f", started at ${d['tips_initial_usd']}" if d['tips_initial_usd'] else "") + ")")
    print(f"  app clock   {hm(d['app_active_seconds'])}  -> ${d['per_hour_app']}/hr")
    if d["true_active_seconds"]:
        print(f"  operator    {hm(d['true_active_seconds'])}  -> ${d['per_hour_true']}/hr   ({d['true_active_note'] or ''})")
        diff = d["app_active_seconds"] - d["true_active_seconds"]
        print(f"  operator read is {hm(abs(diff))} {'under' if diff > 0 else 'over'} the app's clock;"
              f" the wall clock and gap below are what the car says")
    if d["wall_seconds"]:
        print(f"  wall clock  {hm(d['wall_seconds'])}  -> ${d['per_hour_wall']}/hr   (first accept to last delivery)")
        print(f"  between batches, off the app's clock: {hm(d['gap_seconds'])}"
              + (f", of which {hm(d['charge_stop_seconds'])} was {d['charge_stops']} charge stop(s) the car recorded" if d["charge_stops"] else ""))
    print(f"  route miles {d['route_miles'] if d['route_miles'] is not None else 'incomplete'}"
          + (f"  -> ${d['energy_usd_on_route']} energy at {COST_PER_MILE*100:.1f}c/mi" if d['energy_usd_on_route'] else ""))
    if d["late_orders"] is not None: print(f"  late orders {d['late_orders']}, found-or-replaced {d['found_pct']}%")
    if d["shift_drives"]:
        print(f"  car, shift  {d['shift_drives']} drives, {d['shift_miles']} mi, {hm(d['shift_drive_seconds'])} driving, {d['shift_kwh']} kWh"
              f"  -> energy ${d['energy_usd_shift']}"
              + (f", dead miles {d['dead_miles']} beyond the app's route" if d['dead_miles'] is not None else ", dead miles unknown (a route leg is missing)"))
    if d["charge_drives"]: print(f"  car, charge {d['charge_drives']} drive(s) to a charger")
    if d["personal_drives"]: print(f"  car, personal {d['personal_drives']} drives, {d['personal_miles_labelled']} mi, per the operator")
    if d["mixed_drives"]:
        print(f"  car, mixed  {d['mixed_drives']} drive(s), {d['mixed_miles']} mi, part personal and part shift per the operator; counted in neither")
    if d["unsettled_drives"]:
        print(f"  {d['unsettled_drives']} drive(s) on this date are not settled: run  gig.py drives {d['occurred_on']}  and mark them")
    if not d["shift_drives"] and d["car_drives"]:
        print(f"  car: {d['car_drives']} drives on this date, none labelled shift yet")
    if not d["car_drives"]:
        print("  car: no drives in the warehouse for this date yet (pull TezLab)")

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("ingest", help="OCR shopper-app screenshots into the warehouse")
p.add_argument("images", nargs="+"); p.add_argument("--year", type=int); p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=ingest)
p = sub.add_parser("true", help="record your own read of time actually worked")
p.add_argument("date"); p.add_argument("duration", help="e.g. 3h14m"); p.add_argument("--note"); p.set_defaults(fn=true_)
p = sub.add_parser("day", help="the reconciled day"); p.add_argument("date"); p.set_defaults(fn=day)
p = sub.add_parser("drives", help="label a day's drives from the app's own timestamps; list what only you can settle")
p.add_argument("date"); p.set_defaults(fn=drives)
p = sub.add_parser("mark", help="your word on one or more drives: shift | personal | charge")
p.add_argument("purpose", choices=["shift", "personal", "charge", "mixed"]); p.add_argument("ids", type=int, nargs="+"); p.add_argument("--note"); p.set_defaults(fn=mark)
p = sub.add_parser("mail", help="Gmail get_message JSON files -> garage.gig_mail (idempotent)")
p.add_argument("files", nargs="+"); p.add_argument("--by", default="manual", choices=["manual", "routine"]); p.set_defaults(fn=mail)
sub.add_parser("views", help="(re)create v_gig_day").set_defaults(fn=lambda a: (lambda c: (views(c.cursor()), c.commit()))(db()))
a = ap.parse_args(); a.fn(a)

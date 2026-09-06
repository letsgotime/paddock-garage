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
         "occurred_on": None, "legs": [], "order_tips": {}}
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
        if m: b["legs"].append(float(m.group(1)))
        if re.search(r"^Arrival:", t, re.I) and i + 1 < len(flat):
            b["store"] = flat[i+1].strip()
        if re.search(r"^Active hours", t, re.I):
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
    # Only claim an initial tip total when the screen actually showed a struck-through
    # amount on at least one order. Otherwise it is unknown, not equal to the final.
    if b["order_tips"] and any(v["initial"] is not None for v in b["order_tips"].values()):
        init = [v["initial"] if v["initial"] is not None else v["tip"] for v in b["order_tips"].values()]
        b["tips_initial_usd"] = round(sum(init), 2)
    if b["legs"]: b["route_miles"] = round(sum(b["legs"]), 1)
    return b

def parse_completed(rows, year):
    """'Completed orders' daily screen -> list of {store, delivered, found_pct, found_items, on_time}."""
    out, cur, day = [], None, None
    flat = [" ".join(r) for r in rows]
    for i, t in enumerate(flat):
        m = re.search(r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+([A-Z][a-z]{2})\w*\s+(\d{1,2})", t)
        if m and day is None:
            mon = [k for k in MONTHS if k.startswith(m.group(2).lower())]
            if mon: day = dt.date(year, MONTHS[mon[0]], int(m.group(3)))
        m = re.search(r"^(.+?)\s*[•·.]\s*(\d{1,2}:\d{2}\s*[ap]m)$", t)
        if m and not t.lower().startswith(("found", "on-time")):
            cur = {"store": m.group(1).strip(), "delivered": clock(m.group(2)), "found_pct": None,
                   "found_items": None, "on_time": None}; out.append(cur); continue
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
    if "completed orders" in txt: return "completed"
    if "shop and deliver" in txt or "batch summary" in txt or "drop off:" in txt or "arrival:" in txt: return "batch"
    if ("daily earnings" in txt or "weekly earnings" in txt) and "active hours" in txt: return "day"
    if "active hours" in txt: return "batch"        # a scrolled tail of a batch summary
    return "unknown"

# ---------------------------------------------------------------- write
def upsert_batch(cur, b, files):
    if not (b["occurred_on"] and b["accepted_at"] and b["store"]):
        print("  ! batch missing date/accepted/store, skipped:", {k: b[k] for k in ("occurred_on", "accepted_at", "store")}); return None
    cur.execute("""insert into garage.gig_batch (occurred_on, accepted_at, store, orders, items, units,
                     batch_pay_usd, tips_usd, tips_initial_usd, total_usd, heavy_pay, boost_pay,
                     app_active_seconds, route_miles, source_files)
                   values (%s, %s::timestamp || %s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                     source_files=array(select distinct unnest(gig_batch.source_files || excluded.source_files))
                   returning id""",
                (b["occurred_on"], b["accepted_at"].isoformat(), TZ, b["store"], b["orders"], b["items"], b["units"],
                 b["batch_pay_usd"], b["tips_usd"], b["tips_initial_usd"], b["total_usd"], b["heavy_pay"], b["boost_pay"],
                 b["app_active_seconds"], b["route_miles"], files))
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
        cur.execute("""select id from garage.gig_batch where occurred_on=%s and lower(store) like %s
                       order by accepted_at limit 1""", (day, o["store"].lower().split(" ")[0] + "%"))
        r = cur.fetchone()
        if not r: print(f"  ! no batch for {o['store']} on {day}, order card skipped"); continue
        delivered = dt.datetime.combine(day, o["delivered"]).isoformat() if o["delivered"] else None
        cur.execute("""delete from garage.gig_order where batch_id=%s and delivered_at = (%s::timestamp || %s)::timestamptz""",
                    (r[0], delivered, TZ))
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
w as (select b2.occurred_on, extract(epoch from max(o2.delivered_at) - min(b2.accepted_at))::int wall_seconds
      from garage.gig_batch b2 join garage.gig_order o2 on o2.batch_id = b2.id group by b2.occurred_on)
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
       round(c.car_miles - b.route_miles, 1)                                     as dead_miles,
       round(c.car_miles * %(cpm)s, 2)                                           as energy_usd_car
from b left join garage.gig_day g on g.occurred_on=b.occurred_on
       left join o on o.occurred_on=b.occurred_on
       left join c on c.d=b.occurred_on
       left join cs on cs.d=b.occurred_on
       left join w on w.occurred_on=b.occurred_on
order by b.occurred_on desc
""" % {"cpm": repr(COST_PER_MILE)}

def views(cur): cur.execute(VIEW)

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
    with db() as c, c.cursor() as cur:
        views(cur)
        for g in groups:
            b = parse_batch(g["rows"], year)
            bid = upsert_batch(cur, b, [pathlib.Path(f).name for f in g["files"]])
            if bid:
                print(f"  batch #{bid}  {b['occurred_on']} {b['accepted_at'].strftime('%-I:%M%p').lower()}  {b['store']}"
                      f"  ${b['total_usd']}  (pay {b['batch_pay_usd']}, tips {b['tips_usd']}"
                      f"{', was '+str(b['tips_initial_usd']) if b['tips_initial_usd'] else ''})"
                      f"  {b['orders']} orders, {b['items']} items,"
                      f" {b['app_active_seconds'] and round(b['app_active_seconds']/60)} min, {b['route_miles']} mi")
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
    if d["car_drives"]:
        print(f"  car: {d['car_drives']} drives, {d['car_miles']} mi, {hm(d['car_drive_seconds'])} driving, {d['car_kwh']} kWh"
              f"  -> dead miles {d['dead_miles']}, energy ${d['energy_usd_car']}")
    else:
        print("  car: no drives in the warehouse for this date yet (pull TezLab)")

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("ingest", help="OCR shopper-app screenshots into the warehouse")
p.add_argument("images", nargs="+"); p.add_argument("--year", type=int); p.set_defaults(fn=ingest)
p = sub.add_parser("true", help="record your own read of time actually worked")
p.add_argument("date"); p.add_argument("duration", help="e.g. 3h14m"); p.add_argument("--note"); p.set_defaults(fn=true_)
p = sub.add_parser("day", help="the reconciled day"); p.add_argument("date"); p.set_defaults(fn=day)
sub.add_parser("views", help="(re)create v_gig_day").set_defaults(fn=lambda a: (lambda c: (views(c.cursor()), c.commit()))(db()))
a = ap.parse_args(); a.fn(a)

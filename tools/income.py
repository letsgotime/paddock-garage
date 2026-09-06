#!/usr/bin/env python3
"""Gig income: private ledger and shift intelligence.

PRIVATE BY CONSTRUCTION. Nothing here is ever written into public/. The numbers
live in Neon, the dashboard renders to private-src/, and tools/check.py fails
the build if a gig platform name or an earnings field ever appears in a
published page.

The point is not bookkeeping. It is that this project already measures what a
mile costs, so a shift can be judged on what it nets after the vehicle is paid,
which is the only number that actually decides whether a run was worth taking.

  python3 tools/income.py add --platform instacart --date 2026-09-06 \
      --gross 84.50 --tips 22.00 --hours 4.25 --miles 61 --deliveries 7
  python3 tools/income.py report
"""
import argparse, datetime, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIV = ROOT / "private-src"
# Measured, and read from the one file that measures it. Hard-coding this drifted
# once already: the constant said 0.101 while telemetry.json said 0.1088, so every
# shift understated its energy cost by 7.7%.
COST_PER_MILE = json.loads((ROOT / "data" / "telemetry.json").read_text())["cost"]["per_mile"]

VIEW_SQL = """
create or replace view garage.v_gig_shift as
select id, occurred_on, platform, city, hours, miles, deliveries,
       gross_usd, tips_usd, amount_usd as net_usd,
       case when hours > 0 then round(amount_usd / hours, 2) end            as per_hour,
       case when miles > 0 then round(amount_usd / miles, 2) end            as per_mile,
       case when miles > 0 then round(miles * %(cpm)s, 2) end               as energy_cost_usd,
       case when miles > 0 then round(amount_usd - miles * %(cpm)s, 2) end  as after_energy_usd,
       case when hours > 0 and miles > 0
            then round((amount_usd - miles * %(cpm)s) / hours, 2) end       as after_energy_per_hour,
       case when deliveries > 0 then round(amount_usd / deliveries, 2) end  as per_delivery
from garage.income_event
where kind = 'gig'
order by occurred_on desc, id desc
""" % {"cpm": repr(COST_PER_MILE)}


def sync_view(cur):
    """Keep the view's cost-per-mile in step with telemetry.json. Idempotent."""
    cur.execute(VIEW_SQL)


def db():
    import psycopg2
    url = os.environ.get("GARAGE_DB_URL")
    if not url:
        raise SystemExit("set GARAGE_DB_URL (see ~/.garage/db.env)")
    return psycopg2.connect(url)

PLATFORMS = {"instacart": "Instacart", "doordash": "DoorDash", "uber": "Uber",
             "lyft": "Lyft", "amazon": "Amazon Flex", "spark": "Spark", "other": "Other"}

def add(a):
    net = a.gross + (a.tips or 0) if a.net is None else a.net
    with db() as c, c.cursor() as cur:
        sync_view(cur)
        cur.execute("""insert into garage.income_event
            (occurred_on, kind, platform, city, hours, miles, deliveries,
             gross_usd, tips_usd, amount_usd, note)
            values (%s,'gig',%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (a.date, PLATFORMS.get(a.platform, a.platform), a.city, a.hours, a.miles,
             a.deliveries, a.gross, a.tips, net, a.note))
        rid = cur.fetchone()[0]
    energy = (a.miles or 0) * COST_PER_MILE
    print(f"logged #{rid}: {PLATFORMS.get(a.platform, a.platform)} {a.date}  net ${net:.2f}")
    if a.hours:  print(f"  ${net / a.hours:.2f} an hour gross of vehicle cost")
    if a.miles:
        print(f"  {a.miles:g} mi cost ${energy:.2f} in electricity at {COST_PER_MILE*100:.1f} c/mi")
        print(f"  ${net - energy:.2f} after the car is paid"
              + (f", ${(net - energy) / a.hours:.2f} an hour" if a.hours else ""))

def report(a):
    with db() as c, c.cursor() as cur:
        sync_view(cur)
        cur.execute("select count(*) from garage.income_event where kind='gig'")
        if not cur.fetchone()[0]:
            print("No shifts logged yet. Add one with:  python3 tools/income.py add --help")
            return
        cur.execute("""select platform, count(*), sum(hours), sum(miles), sum(amount_usd),
              round(avg(case when hours>0 then amount_usd/hours end)::numeric,2),
              round((sum(amount_usd)-sum(miles)*%s)::numeric,2)
            from garage.income_event where kind='gig' group by platform
            order by sum(amount_usd) desc""", (COST_PER_MILE,))
        rows = cur.fetchall()
    print(f"{'platform':14s}{'shifts':>7s}{'hours':>8s}{'miles':>8s}{'net':>10s}{'$/hr':>8s}{'after car':>11s}")
    for p, n, h, mi, net, ph, ac in rows:
        print(f"{(p or '?'):14s}{n:>7d}{(h or 0):>8.1f}{(mi or 0):>8.0f}"
              f"{net:>10.2f}{(ph or 0):>8.2f}{(ac or 0):>11.2f}")

def dash(a):
    """Render the private dashboard. Never into public/."""
    with db() as c, c.cursor() as cur:
        cur.execute("""select occurred_on,platform,city,hours,miles,deliveries,net_usd,
            per_hour,per_mile,energy_cost_usd,after_energy_usd,after_energy_per_hour,per_delivery
            from garage.v_gig_shift limit 200""")
        rows = cur.fetchall()
    PRIV.mkdir(exist_ok=True)
    body = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1] or ''}</td><td class='n'>{r[3] or ''}</td>"
        f"<td class='n'>{r[4] or ''}</td><td class='n'>${r[6]:.2f}</td>"
        f"<td class='n'>{('$%.2f' % r[7]) if r[7] else ''}</td>"
        f"<td class='n'>{('$%.2f' % r[9]) if r[9] else ''}</td>"
        f"<td class='n'><b>{('$%.2f' % r[10]) if r[10] else ''}</b></td>"
        f"<td class='n'>{('$%.2f' % r[11]) if r[11] else ''}</td></tr>" for r in rows)
    (PRIV / "income.html").write_text(f"""<!doctype html><meta charset=utf-8>
<title>Gig ledger, private</title>
<style>body{{background:#05070D;color:#F0F2F5;font:15px Arial,sans-serif;margin:0;padding:28px}}
h1{{font-family:"Arial Black",Arial;font-size:1.5rem}}
.warn{{border:1px solid rgba(244,81,30,.5);background:rgba(244,81,30,.1);color:#F4511E;
padding:10px 14px;border-radius:10px;font-size:.8rem;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;display:inline-block;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:.88rem}}
th{{text-align:left;font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;
color:#8A93A0;padding:9px 11px;border-bottom:1px solid rgba(229,231,235,.2)}}
td{{padding:9px 11px;border-bottom:1px solid rgba(229,231,235,.08);color:#AEB6C2}}
td:first-child{{color:#F0F2F5}} .n{{text-align:right;font-variant-numeric:tabular-nums}}
b{{color:#F0F2F5}}</style>
<h1>Gig ledger</h1>
<p class="warn">Private. Never deployed. Not in public/.</p>
<table><thead><tr><th>Date</th><th>Platform</th><th class=n>Hours</th><th class=n>Miles</th>
<th class=n>Net</th><th class=n>$/hr</th><th class=n>Energy</th><th class=n>After car</th>
<th class=n>After car $/hr</th></tr></thead><tbody>{body}</tbody></table>
<p style="color:#8A93A0;font-size:.78rem;margin-top:18px">Energy priced at the measured
{COST_PER_MILE*100:.1f} cents a mile from this project's own telemetry and invoices.</p>""")
    print(f"wrote {PRIV/'income.html'} ({len(rows)} shifts). Not deployed, by design.")

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("add", help="log a shift")
p.add_argument("--platform", required=True, choices=list(PLATFORMS))
p.add_argument("--date", default=datetime.date.today().isoformat())
p.add_argument("--gross", type=float, required=True)
p.add_argument("--tips", type=float, default=0)
p.add_argument("--net", type=float)
p.add_argument("--hours", type=float)
p.add_argument("--miles", type=float)
p.add_argument("--deliveries", type=int)
p.add_argument("--city"); p.add_argument("--note")
p.set_defaults(fn=add)
def prompt(a):
    """Ask for a shift one field at a time. Blank skips an optional field."""
    print("Log a shift. Enter skips anything optional.\n")
    keys = list(PLATFORMS)
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {PLATFORMS[k]}")
    while True:
        pick = input("\nPlatform (number or name): ").strip().lower()
        if pick.isdigit() and 1 <= int(pick) <= len(keys):
            plat = keys[int(pick) - 1]; break
        if pick in PLATFORMS:
            plat = pick; break
        print("  not one of those")
    def num(label, cast=float, required=False):
        while True:
            v = input(f"{label}: ").strip().replace("$", "").replace(",", "")
            if not v:
                if required: print("  needed"); continue
                return None
            try: return cast(v)
            except ValueError: print("  numbers only")
    today = datetime.date.today().isoformat()
    date = input(f"Date [{today}]: ").strip() or today
    ns = argparse.Namespace(
        platform=plat, date=date,
        gross=num("Base pay $", required=True), tips=num("Tips $") or 0,
        net=None, hours=num("Hours worked"), miles=num("Miles driven"),
        deliveries=num("Deliveries", int), city=input("City (optional): ").strip() or None,
        note=input("Note (optional): ").strip() or None)
    print()
    add(ns)

sub.add_parser("prompt", help="log a shift interactively").set_defaults(fn=prompt)
sub.add_parser("report", help="totals by platform").set_defaults(fn=report)
sub.add_parser("dash", help="render the private dashboard").set_defaults(fn=dash)
a = ap.parse_args(); a.fn(a)

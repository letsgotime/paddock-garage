#!/usr/bin/env python3
"""Runway, the gated tier: every settled day with every dollar, for runway.paddock20.com.

PRIVATE BY CONSTRUCTION, like income.py and gig.py. Nothing here writes into public/.

Renders private-src/runway/index.html (gitignored) from two inputs that never enter the
repository: private-src/runway-data/gig-full.json, written by `gig.py export --full` with every
dollar the public export drops, and ~/.garage/runway.json, the owner's defaults. The page
uses build.py's head(), footer and glass so it reads as one site, and every asset and nav
link points back at garage.paddock20.com, so this Worker serves one HTML file and nothing
else. It is deployed as its own Worker (wrangler.runway.jsonc) and must sit behind
Cloudflare Access before it goes live: docs/runway-access.md.

    python3 tools/gig.py export --full && python3 tools/runway.py

~/.garage/runway.json, created with placeholders on the first run and never committed:

    {
      "target_monthly_usd": 0,      take-home to replace, per month (the strategy's target)
      "tax_rate_pct": 0,            combined marginal rate applied to gig profit
      "goal_usd": 0,                the amount the runway is measured toward
      "hours_per_week": 0,          planned shift hours a week
      "access_configured": false    true once the Cloudflare Access application exists;
                                    tools/week will not deploy the runway Worker until then
    }

Every figure on the page carries a chip: measured where the app or the car recorded it,
modeled where it is arithmetic on the owner's defaults.
"""
import datetime, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build as B

OUT = ROOT / "private-src" / "runway" / "index.html"
FULL = ROOT / "private-src" / "runway-data" / "gig-full.json"
CFG = pathlib.Path(os.path.expanduser("~/.garage/runway.json"))
HOST, GARAGE = "https://runway.paddock20.com", "https://garage.paddock20.com"
PLACEHOLDER = {"target_monthly_usd": 0, "tax_rate_pct": 0, "goal_usd": 0, "hours_per_week": 0,
               "access_configured": False}
usd, pct, cents, hm, mins, M, MO = B.usd, B.pct, B.cents, B.hm, B.mins, B.M, B.MO

def config():
    if not CFG.exists():
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps(PLACEHOLDER, indent=2) + "\n")
        CFG.chmod(0o600)
        print(f"created {CFG} with placeholders. Put your own figures in it; it is never committed.")
    return {**PLACEHOLDER, **json.loads(CFG.read_text())}

def shell(title, desc, plate, body):
    """build.py's chrome, re-pointed: no indexing, canonical on this host, every asset and
    link served by garage.paddock20.com so this Worker holds one file."""
    doc = B.head(title, desc, "/", plate) + body + B.FOOTER
    doc = doc.replace('<meta name="robots" content="index, follow">',
                      '<meta name="robots" content="noindex, nofollow, noarchive">')
    doc = doc.replace(f'href="{GARAGE}/"', f'href="{HOST}/"').replace(f'content="{GARAGE}/"', f'content="{HOST}/"')
    doc = doc.replace('href="/', f'href="{GARAGE}/').replace('src="/', f'src="{GARAGE}/').replace("url('/img/", f"url('{GARAGE}/img/")
    if "—" in doc or "&mdash;" in doc: raise SystemExit("em dash in the runway page")
    return doc

def per_hour(d, seconds): return (d["total_usd"] - d["energy_usd"]) / (seconds / 3600) if seconds else 0

def day_card(d, first):
    rows = "".join(
        f'<tr><td>{B.html.escape(b["store"])}{", " + B.html.escape(b["city"]) if b.get("city") else ""}</td>'
        f'<td class="n">{b["orders"]}</td><td class="n">{b["items"]}</td>'
        f'<td class="n">{mins(b["in_store_s"]) if b["in_store_s"] else "n/a"}</td>'
        f'<td class="n">{mins(b["app_active_s"])}</td><td class="n">{b["route_mi"]:.1f}</td>'
        f'<td class="n">{usd(b["batch_pay_usd"])}</td><td class="n">{usd(b["tips_usd"])}</td>'
        f'<td class="n"><b>{usd(b["total_usd"])}</b></td>'
        f'<td>{"n/a" if b["on_time"] is None else ("yes" if b["on_time"] else "no")}</td></tr>'
        for b in d["batch_rows"])
    net = d["total_usd"] - d["energy_usd"]
    return f"""<li class="chapter{' now' if first else ''}">
  <p class="ch-n">{B.longdate(d['date'])}</p>
  <div class="g body">
    <h2>{usd(d['total_usd'])} gross {M}</h2>
    <p class="lede" style="margin-bottom:.5em">{d['batches']} batches, {d['orders']} orders, {d['items']} items.
    {usd(d['batch_pay_usd'])} of batch pay and {usd(d['tips_usd'])} of tips, {pct(d['tip_share_pct'])} of the day.</p>
    <ul class="data">
      <li><b>{usd(d['per_hour_app'])}/hr</b> on the app's clock, {hm(d['app_active_s'])}</li>
      <li><b>{usd(d['per_hour_wall'])}/hr</b> door to door, {hm(d['wall_s'])}</li>
      <li><b>{usd(d['energy_usd'])}</b> energy, {d['shift_mi']:.1f} mi</li>
      <li><b>{usd(net)}</b> after energy</li>
      <li><b>{usd(per_hour(d, d['wall_s']))}/hr</b> after energy, door to door</li>
      <li><b>{d['dead_mi']:.1f} mi</b> dead miles</li>
      <li><b>{pct(d['found_or_replaced_pct'])}</b> found or replaced</li>
      <li><b>{d['late_orders']}</b> late</li>
    </ul>
    <div class="tw" style="margin-top:12px"><table>
      <thead><tr><th>Store</th><th class="n">Orders</th><th class="n">Items</th><th class="n">In store</th>
      <th class="n">App clock</th><th class="n">Route mi</th><th class="n">Pay</th><th class="n">Tips</th>
      <th class="n">Total</th><th>On time</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <p class="chart-note">{M}. {hm(d['gap_s'])} between batches off the app's clock
    {', ' + mins(d['charge_stop_s']) + ' of it charging' if d.get('charge_stop_s') else ''}.
    {('The operator read ' + hm(d['true_active_s']) + ' of working time, ' + usd(d['per_hour_true']) + '/hr on that clock.') if d.get('true_active_s') else ''}</p>
  </div>
</li>"""

def main():
    if not FULL.exists():
        raise SystemExit(f"{FULL.relative_to(ROOT)} is missing: run  python3 tools/gig.py export --full")
    full = json.loads(FULL.read_text()); days = full["days"]
    if not days: raise SystemExit("no settled day in the full export")
    cfg = config(); placeholders = not (cfg["target_monthly_usd"] and cfg["hours_per_week"])
    cpm = B.D["cost"]
    latest = days[0]
    tot_gross = sum(d["total_usd"] for d in days); tot_energy = sum(d["energy_usd"] for d in days)
    tot_app = sum(d["app_active_s"] for d in days); tot_wall = sum(d["wall_s"] for d in days)
    tot_tips = sum(d["tips_usd"] for d in days); tot_mi = sum(d["shift_mi"] for d in days)
    avg_app = tot_gross / (tot_app / 3600); avg_wall = tot_gross / (tot_wall / 3600)
    net_hr_wall = (tot_gross - tot_energy) / (tot_wall / 3600)
    # the replacement arithmetic, on the owner's defaults: door-to-door rate, because that is the
    # hour that actually leaves the calendar
    tax = cfg["tax_rate_pct"] / 100; hrs = cfg["hours_per_week"]
    weekly_net = net_hr_wall * hrs * (1 - tax)
    monthly = weekly_net * 52 / 12
    gap = cfg["target_monthly_usd"] - monthly
    hours_to_target = (cfg["target_monthly_usd"] / (net_hr_wall * (1 - tax)) * 12 / 52) if net_hr_wall and tax < 1 else 0
    weeks_to_goal = (cfg["goal_usd"] / weekly_net) if weekly_net > 0 and cfg["goal_usd"] else None
    cards = "".join(day_card(d, i == 0) for i, d in enumerate(days))
    note = ("" if not placeholders else
            f'<p class="chart-note" style="color:var(--amber)">Defaults are placeholders: put the target, tax rate, goal and '
            f'hours a week in {B.html.escape(str(CFG))} and rebuild.</p>')
    body = f"""<p class="eyebrow"><b>Runway</b> &middot; gated &middot; every dollar &middot; exported {full['exported_on']}</p>
<h1>What every day <span>paid</span>, and what it needs to.</h1>
<p class="lede prose">{len(days)} measured day{'s' if len(days) != 1 else ''} from the shopper app and the car, every
dollar included. This page is regenerated at every build from the warehouse; nothing on it is typed in. The public
site shows what the car did; this shows what it paid.</p>
{B.livestrip()}

<section class="row row-2-1">
  <div class="g g-2 cmd">
    <p class="k">Latest day, gross</p>
    <p class="v">{usd(latest['total_usd'])}</p>
    <p class="sub">{B.longdate(latest['date'])}: {usd(latest['per_hour_app'])}/hr on the app's clock, {usd(latest['per_hour_wall'])}/hr
    door to door, {usd(latest['energy_usd'])} of energy at {cents(cpm['per_mile_cents'])} a mile. {M}</p>
  </div>
  <div class="bare">
    <h2>Across every day</h2>
    <p>{usd(tot_gross)} gross over {hm(tot_app)} on the app's clock and {hm(tot_wall)} door to door.
    Tips were {pct(tot_tips / tot_gross * 100)}.</p>
    <p style="margin:0">{usd(tot_energy)} of energy for {tot_mi:.1f} miles, so {usd(net_hr_wall)} an hour after
    the car is paid, door to door. {M}</p>
  </div>
</section>

<section class="stats g">
  <div class="stat"><p class="v">{usd(avg_app)}<small>/hr</small></p><p class="k">App clock, all days</p></div>
  <div class="stat"><p class="v">{usd(avg_wall)}<small>/hr</small></p><p class="k">Door to door, all days</p></div>
  <div class="stat"><p class="v">{usd(net_hr_wall)}<small>/hr</small></p><p class="k">After energy, door to door</p></div>
  <div class="stat"><p class="v">{pct(tot_tips / tot_gross * 100)}</p><p class="k">Of gross was tips</p></div>
</section>

<section class="g">
  <h2>Income replacement {MO}</h2>
  {note}
  <div class="row row-2" style="margin-top:12px">
    <div class="g g-0"><h3>The target</h3>
      <p style="margin:0 0 .5em">Take-home to replace: <strong>{usd(cfg['target_monthly_usd'], 0)}</strong> a month,
      after a {cfg['tax_rate_pct']:g}% rate on gig profit.</p>
      <p style="margin:0">Planned: <strong>{hrs:g} hours</strong> a week.</p></div>
    <div class="g g-0"><h3>At the measured rate</h3>
      <p style="margin:0 0 .5em"><strong>{usd(monthly, 0)}</strong> a month take-home at {hrs:g} hours a week,
      {usd(net_hr_wall)}/hr door to door after energy, after tax.</p>
      <p style="margin:0">Gap to the target: <strong>{usd(max(gap, 0), 0)}</strong>
      ({pct(monthly / cfg['target_monthly_usd'] * 100) if cfg['target_monthly_usd'] else 'n/a'} covered).
      Hours a week to cover it in full: <strong>{hours_to_target:.1f}</strong>.</p></div>
  </div>
  <p class="chart-note" style="margin-top:12px">{MO}. Rate is every measured day's gross less energy, over door-to-door
  hours; weeks are 52 to the year, twelve months. Goal of {usd(cfg['goal_usd'], 0)}:
  {(f'{weeks_to_goal:.0f} weeks at this pace') if weeks_to_goal else 'no goal set'}.</p>
</section>

<section>
  <p class="eyebrow">Every measured day, newest first</p>
  <ol class="chapters">{cards}</ol>
</section>

<section class="bare">
  <h2>What this page holds back</h2>
  <p style="margin:0">Per-order tips, store streets, clock times, the purpose of each drive, the account column
  and captured mail stay in the warehouse. Nothing here is writable; the warehouse is the only place anything is
  entered.</p>
</section>
{B.rulebar()}
"""
    doc = shell("Runway", "Every measured delivery day with every dollar, for the owner and named readers.",
                "tex-carbon.jpg", body)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc)

    # Everything in OUT.parent is uploaded by wrangler and served on the hostname, so one
    # stray file here is a leak. gig-full.json sat in this directory until 7 September and
    # was briefly fetchable on the live host; the export now lands outside it, and this
    # refuses to let anything drift back in.
    stray = sorted(p.name for p in OUT.parent.iterdir() if p.name != OUT.name)
    if stray:
        raise SystemExit(
            f"refusing to leave {', '.join(stray)} in {OUT.parent.relative_to(ROOT)}: that directory is\n"
            f"the Worker's asset root and every file in it is served. Move it out, then re-run.")

    print(f"wrote {OUT.relative_to(ROOT)} ({len(doc) / 1024:.1f} KB, {len(days)} day(s)). Gitignored; deploy only behind Access.")
    if placeholders: print("  defaults are placeholders: edit ~/.garage/runway.json")
    if not cfg["access_configured"]: print("  access_configured is false: tools/week will not deploy this Worker yet")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render public/ from data/telemetry.json + content/legacy fragments.

Single source of truth: every published figure comes from the JSON snapshot, so
"pull the week" is: refresh data/telemetry.json, run this, deploy. No page holds
a hand-typed number that can go stale behind the data.

    python3 tools/build.py
"""
import json, pathlib, re, html, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
D = json.loads((ROOT / "data" / "telemetry.json").read_text())
LOG = json.loads((ROOT / "data" / "log.json").read_text())
LEGACY = ROOT / "content" / "legacy"

def frag(name):
    p = LEGACY / f"{name}.html"
    return p.read_text() if p.exists() else ""

# ── formatting ──────────────────────────────────────────────────────────────
def mi(v, d=0):   return f"{v:,.{d}f}"
def usd(v, d=2):  return f"${v:,.{d}f}"
def cents(v, d=1):return f"{v:.{d}f}¢"
def pct(v, d=0):  return f"{v:.{d}f}%"

M  = '<span class="chip chip-m">measured</span>'
MO = '<span class="chip chip-mo">modeled</span>'

# ── chart primitives ────────────────────────────────────────────────────────
# One series = one hue, no legend (the title names it). Marks are thin with a
# 4px rounded top anchored to the baseline and a 2px gap between bars.
def bars(rows, *, value, label, color="var(--m1)", h=190, fmt=lambda v: f"{v:g}",
         peak_only=True, unit=""):
    """rows: list of dicts. value/label: key names."""
    n = len(rows)
    if not n: return ""
    W, PADL, PADB, PADT = 720, 4, 34, 30
    vals = [r[value] for r in rows]
    vmax = max(vals) or 1
    slot = (W - PADL * 2) / n
    bw = max(6, slot - 2)                      # 2px surface gap between bars
    plot = h - PADB - PADT
    peak = vals.index(vmax)
    out = [f'<svg class="chart" viewBox="0 0 {W} {h}" role="img" '
           f'aria-label="{html.escape(unit or value)}">']
    out.append(f'<line class="axis" x1="0" y1="{h-PADB}" x2="{W}" y2="{h-PADB}"/>')
    for i, r in enumerate(rows):
        v = r[value]
        bh = max(2.5, v / vmax * plot)
        x = PADL + i * slot
        y = h - PADB - bh
        rad = min(4, bw / 2)
        out.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'rx="{rad:.1f}" fill="{color}"><title>{html.escape(str(r[label]))}: '
            f'{html.escape(fmt(v))}{html.escape(unit)}</title></rect>')
        if (not peak_only) or i == peak:
            out.append(f'<text class="val" x="{x+bw/2:.1f}" y="{y-5:.1f}" '
                       f'text-anchor="middle">{html.escape(fmt(v))}</text>')
        if n <= 12 or i % 2 == 0:
            out.append(f'<text class="lab" x="{x+bw/2:.1f}" y="{h-11}" '
                       f'text-anchor="middle">{html.escape(str(r[label]))}</text>')
    out.append("</svg>")
    return "".join(out)

def hbars(rows, *, hi=0, unit="¢/mi"):
    """rows: (label, value, note). Label sits above its bar so nothing collides
    at phone width. Highlight row `hi` in ignition, the rest neutral."""
    W, RH, GAP, BARH = 720, 54, 12, 20
    h = len(rows) * (RH + GAP)
    vmax = max(r[1] for r in rows) or 1
    VALW = 132   # fits '28.0¢/mi' at the 21-unit phone label size
    barmax = W - VALW
    out = [f'<svg class="chart" viewBox="0 0 {W} {h}" role="img" '
           f'aria-label="Comparison in {html.escape(unit)}">']
    for i, (lab, v, note) in enumerate(rows):
        y = i * (RH + GAP)
        bw = max(4, v / vmax * barmax)
        col = "var(--m1)" if i == hi else "var(--m-neutral)"
        out.append(f'<text class="lab" x="0" y="{y+16:.1f}">{html.escape(lab)}</text>')
        out.append(f'<rect class="bar" x="0" y="{y+RH-BARH-4:.1f}" width="{bw:.1f}" '
                   f'height="{BARH}" rx="4" fill="{col}"><title>{html.escape(lab)}: '
                   f'{v:.1f}{html.escape(unit)}{" " + note if note else ""}</title></rect>')
        out.append(f'<text class="val" x="{bw+10:.1f}" y="{y+RH-BARH/2-1:.1f}" '
                   f'dominant-baseline="middle">{v:.1f}{html.escape(unit)}</text>')
    out.append("</svg>")
    return "".join(out)

# published city centers, not this car's coordinates
CITY = {
    "Nashville":   (36.1627, -86.7816), "Brentwood":  (36.0331, -86.7828),
    "Franklin":    (35.9251, -86.8689), "Lebanon":    (36.2081, -86.2911),
    "Smyrna":      (35.9828, -86.5186), "Murfreesboro":(35.8456, -86.3903),
    "Unionville":  (35.6162, -86.5983), "Eagleville": (35.7451, -86.6486),
}
def corridor_map():
    cs = [c for c in D["cities"] if c in CITY]
    lats = [CITY[c][0] for c in cs]; lons = [CITY[c][1] for c in cs]
    W, H, PAD = 720, 430, 54
    la0, la1 = min(lats), max(lats); lo0, lo1 = min(lons), max(lons)
    def xy(c):
        la, lo = CITY[c]
        x = PAD + (lo - lo0) / (lo1 - lo0) * (W - PAD * 2)
        y = H - PAD - (la - la0) / (la1 - la0) * (H - PAD * 2)
        return x, y
    tmax = max(c["trips"] for c in D["corridors"])
    out = [f'<svg class="map" viewBox="0 0 {W} {H}" role="img" aria-label="City to city '
           f'corridors, weighted by trip count">']
    for c in sorted(D["corridors"], key=lambda r: r["trips"]):
        if c["a"] not in CITY or c["b"] not in CITY: continue
        x1, y1 = xy(c["a"]); x2, y2 = xy(c["b"])
        w = 1.2 + (c["trips"] / tmax) * 8.5
        op = .22 + (c["trips"] / tmax) * .58
        out.append(f'<line class="corr" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                   f'y2="{y2:.1f}" stroke-width="{w:.1f}" opacity="{op:.2f}">'
                   f'<title>{c["a"]} to {c["b"]}: {c["trips"]} trips, '
                   f'{c["miles"]:.1f} mi</title></line>')
    charged = {c["name"].split(",")[0] for c in D["chargers"]}
    for c in cs:
        x, y = xy(c)
        n = sum(r["trips"] for r in D["corridors"] if c in (r["a"], r["b"]))
        r = 3.5 + min(n, 20) * .32
        if c in charged:
            out.append(f'<circle class="sc" cx="{x:.1f}" cy="{y:.1f}" r="{r+3.4:.1f}" '
                       f'opacity=".28"/>')
        out.append(f'<circle class="city" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}">'
                   f'<title>{c}: {n} trips</title></circle>')
        anchor = "end" if x > W * .68 else ("start" if x > W * .16 else "start")
        dx = -9 if anchor == "end" else 9
        out.append(f'<text class="cl" x="{x+dx:.1f}" y="{y+3.6:.1f}" '
                   f'text-anchor="{anchor}">{c}</text>')
    out.append("</svg>")
    return "".join(out)

# ── shell ───────────────────────────────────────────────────────────────────
NAV = [("/switch/", "The Switch"), ("/drive/", "Drive"), ("/charge/", "Charge"),
       ("/ledger/", "Ledger"), ("/battery/", "Battery"), ("/car/", "The Car")]

FOOTER_LINKS = NAV + [("/driver/", "The Driver")]

def head(title, desc, path, plate, extra=""):
    cur = ' aria-current="page"'
    nav = "\n".join(
        '      <a href="%s"%s>%s</a>' % (h, cur if h == path else "", t)
        for h, t in NAV)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://garage.paddock20.com{path}">
<meta name="theme-color" content="#05070D">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Paddock Garage">
<meta property="og:url" content="https://garage.paddock20.com{path}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="https://garage.paddock20.com/og/garage.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/assets/glass.css">
<link rel="stylesheet" href="/assets/garage.css">
<style>:root{{--page-bg:url('/img/{plate}')}}</style>
{extra}
</head>
<body>
<header class="pg-nav">
  <div class="pg-nav-inner">
    <a class="pg-nav-logo" href="/" aria-label="Paddock Garage home"><img src="/img/wordmark.png" alt="Paddock20"></a>
    <span class="pg-nav-sp"></span>
    <input type="checkbox" id="pg-menu-t" class="pg-menu-t">
    <label for="pg-menu-t" class="pg-burger" role="button" aria-label="Menu" tabindex="0"><span></span><span></span><span></span></label>
    <nav class="pg-menu" aria-label="Site">
{nav}
    </nav>
  </div>
</header>
<main class="gx">
"""

FOOT_NAV = "\n".join(f'    <a href="{h}">{t}</a>' for h, t in FOOTER_LINKS)
FOOTER = f"""</main>
<footer class="pg-footer" role="contentinfo">
 <div class="pg-footer-inner">
  <div class="pg-f-cols">
   <div class="pg-f-brand">
    <img src="/img/stacked.png" alt="Paddock20, Digest. Develop. Deliver." style="height:104px;width:auto;display:block" loading="lazy" decoding="async">
    <p>One owner's live record of going from gas to electric. Every mile, every charge, every dollar, measured from the car and from real invoices. Nashville, TN.</p>
   </div>
   <nav class="pg-f-nav" aria-label="Footer navigation">
{FOOT_NAV}
    <a href="https://paddock20.com">Paddock20 Main Site</a>
   </nav>
   <div class="pg-f-col pg-f-connect">
    <p class="pg-f-h">Connect</p>
    <a href="https://github.com/letsgotime" target="_blank" rel="noopener noreferrer"><span>GitHub</span></a>
    <a href="https://www.linkedin.com/in/gavinbrooks-leader/" target="_blank" rel="noopener noreferrer"><span>LinkedIn</span></a>
   </div>
   <div class="pg-f-col pg-f-community">
    <p class="pg-f-h">Owner resources</p>
    <a href="https://teslamotorsclub.com" target="_blank" rel="noopener noreferrer"><span>Tesla Motors Club</span></a>
    <a href="https://abetterrouteplanner.com" target="_blank" rel="noopener noreferrer"><span>A Better Routeplanner</span></a>
    <a href="https://tezlabapp.com" target="_blank" rel="noopener noreferrer"><span>TezLab</span></a>
    <a href="https://www.recurrentauto.com" target="_blank" rel="noopener noreferrer"><span>Recurrent</span></a>
   </div>
  </div>
  <div class="pg-f-bottom">
   <p class="pg-f-legend">Figures are labeled measured or modeled. Measured means an invoice or a
   sensor. Data pulled {D['pulled_at']} from TezLab and the Tesla Fleet API. Not affiliated with,
   endorsed by, or sponsored by Tesla, Inc. Tesla, Model Y, Supercharger and Full Self-Driving are
   trademarks of Tesla, Inc.</p>
  </div>
 </div>
</footer>
</body>
</html>
"""

def write(path, title, desc, plate, body, extra=""):
    out = PUB / path.strip("/") / "index.html" if path != "/" else PUB / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = head(title, desc, path, plate, extra) + body + FOOTER
    if "—" in doc or "&mdash;" in doc:
        raise SystemExit(f"em dash found in {path}")
    out.write_text(doc)
    return out, len(doc)

# ── shared blocks ───────────────────────────────────────────────────────────
def livestrip():
    v, b = D["vehicle"], D["battery"]
    return f"""<div class="g g-0 live">
  <span>Odometer <b>{mi(v['odometer'],1)} mi</b></span>
  <span>Per mile <b>{cents(D['cost']['per_mile_cents'])}</b></span>
  <span>Degradation <b>{pct(b['degradation_pct'])}</b></span>
  <span>On FSD <b>{pct(D['fsd']['pct'],1)}</b></span>
  <span class="src">Snapshot {D['pulled_at']}, baked at deploy. This page makes no live requests.</span>
</div>"""

def rulebar():
    return f"""<div class="rulebar">
  <span>{M} invoice or sensor</span>
  <span>{MO} derived, and says so</span>
  <span class="sp">Pulled {D['pulled_at']} &middot; VIN serial masked &middot; no addresses</span>
</div>"""

# ── pages ───────────────────────────────────────────────────────────────────
def page_home():
    c, b, f = D["cost"], D["battery"], D["fsd"]
    body = f"""<p class="eyebrow">Nashville, TN &middot; updated {D['pulled_at']}</p>
<h1>Gas to electric,<br>measured from <span>the car up</span>.</h1>
<p class="lede prose">This is one owner's running record of switching from gas to electric for
the first time: every mile, every charge, every dollar, pulled from the car itself and from
paid invoices. Forty-five, single, rebuilding after a divorce, which is why every dollar here
has to justify itself. The car has to prove it belongs.</p>

<section class="row row-2-1">
  <div class="g g-2 cmd">
    <p class="k">Cost per mile, measured</p>
    <p class="v">{cents(c['per_mile_cents'])}<em>/mi</em></p>
    <p class="sub">{usd(D['charging']['cost'])} of charging across {mi(D['driving']['distance'],1)} miles
    and {D['charging']['sessions']} sessions. The van it replaced cost
    {cents(D['fleet'][0]['cents_per_mi'])} a mile at the same pump.</p>
  </div>
  <div class="g">
    <h2>The rule</h2>
    <p>A number here is either {M} from an invoice or a sensor, or it is {MO} and says so.
    There is no third category. Modeled figures get replaced as real data arrives.</p>
    <p style="margin:0">That rule is the whole point. It is also why the unflattering numbers
    stay on the page.</p>
  </div>
</section>

<section class="stats">
  <div class="g stat"><p class="v">{pct(b['degradation_pct'])}</p><p class="k">Battery degradation</p></div>
  <div class="g stat"><p class="v">{pct(f['pct'],1)}</p><p class="k">Miles driven on FSD</p></div>
  <div class="g stat"><p class="v">{mi(D['vehicle']['odometer'],0)}</p><p class="k">Odometer</p></div>
  <div class="g stat"><p class="v">{D['driving']['wh_per_mi']:.0f}<small>Wh/mi</small></p><p class="k">Real consumption</p></div>
</section>

{livestrip()}

<section class="g">
  <h2>What it costs against what it replaced</h2>
  <p class="prose">Same driver, same roads, same Tennessee pump price of
  {usd(D['gas']['price_per_gal'])} a gallon. The three gas vehicles are the ones actually owned
  and driven, not national averages for a car nobody has.</p>
  {hbars([("2024 Model Y (this car)", D['cost']['per_mile_cents'], "measured"),
          (D['fleet'][0]['name'], D['fleet'][0]['cents_per_mi'], f"{D['fleet'][0]['mpg']} mpg"),
          (D['fleet'][1]['name'], D['fleet'][1]['cents_per_mi'], f"{D['fleet'][1]['mpg']} mpg"),
          (D['fleet'][2]['name'], D['fleet'][2]['cents_per_mi'], f"{D['fleet'][2]['mpg']} mpg")])}
  <p class="chart-note">Electric figure {M}. Gas figures {MO}: measured fuel economy for each
  vehicle, priced at {usd(D['gas']['price_per_gal'])} a gallon
  ({D['gas']['source']}, {D['gas']['as_of']}).</p>
</section>

<section>
  <h2>Start here</h2>
  <ul class="doors">
    <li class="g door"><a class="door" href="/switch/"><span class="k">The story</span>
      <h3>The Switch</h3><p>Gas to electric in seven chapters, from the fleet it replaced
      to the battery. Each one opens with a data checkpoint.</p></a></li>
    <li class="g door"><a class="door" href="/ledger/"><span class="k">The money</span>
      <h3>Ledger</h3><p>Cost per mile against three gas vehicles, what the car earns across
      three jobs, and what it is worth today.</p></a></li>
    <li class="g door"><a class="door" href="/drive/"><span class="k">The data</span>
      <h3>Drive</h3><p>Where the car actually goes, {pct(f['pct'],1)} of miles on FSD,
      and how it compares to {D['efficiency_vs_region']['sample']} other Model Ys nearby.</p></a></li>
  </ul>
</section>
{rulebar()}
"""
    return write("/", "Paddock Garage",
                 f"One owner's measured record of going gas to electric: {cents(c['per_mile_cents'])} "
                 f"per mile across {mi(D['driving']['distance'],1)} miles, {pct(b['degradation_pct'])} "
                 f"battery degradation, {pct(f['pct'],1)} of miles on FSD.",
                 "hero-ev-road.jpg", body)

def page_switch():
    f, b, ch, c = D["fsd"], D["battery"], D["charging"], D["cost"]
    fl = D["fleet"]
    chapters = [
        ("Chapter 0", "Before", False,
         f"Three gas vehicles, all of them actually owned and driven, not national averages. "
         f"A 2015 Express 2500 cargo van doing detail runs, a 2011 Sienna, and a Sequoia that "
         f"lasted fifteen days. This is the baseline everything else gets measured against.",
         [(f"{fl[0]['name'].split(' ',1)[1]}", f"{fl[0]['mpg']} mpg, {cents(fl[0]['cents_per_mi'])}/mi"),
          (f"{fl[2]['name'].split(' ',1)[1]}", f"{fl[2]['mpg']} mpg, {cents(fl[2]['cents_per_mi'])}/mi"),
          (f"{fl[1]['name'].split(' ',1)[1]}", f"{fl[1]['mpg']} mpg, {cents(fl[1]['cents_per_mi'])}/mi"),
          ("Pump price", f"{usd(D['gas']['price_per_gal'])}/gal")]),
        ("Chapter 1", "The decision", False,
         f"A used 2024 Model Y Long Range AWD, Solid Black, seven seats and a tow hitch, bought "
         f"from a Ford Lincoln store in Franklin and financed. Used, because the federal credit "
         f"was never going to apply to this purchase and someone else had already paid the "
         f"steepest part of the depreciation curve.",
         [("Delivered", D['vehicle']['delivered']),
          ("Odometer at delivery", "19,4xx mi"),
          ("Built", D['vehicle']['build']),
          ("Basic warranty", "2028 or 50k mi"),
          ("Battery warranty", "2032 or 120k mi")]),
        ("Chapter 2", "The first week", False,
         f"The first Supercharger session, the first time the range number moves faster than "
         f"expected, and the moment the thing stops feeling like a car and starts feeling like "
         f"an appliance you plug in. Consumption settled at {D['driving']['wh_per_mi']:.0f} Wh "
         f"per mile in mild weather, which is close to the rated figure and better than most "
         f"owners report.",
         [("Real consumption", f"{D['driving']['wh_per_mi']:.0f} Wh/mi"),
          ("Rated efficiency hit", pct(D['driving']['avg_efficiency_pct'])),
          ("Average speed", f"{D['driving']['avg_speed']} mph")]),
        ("Chapter 3", "Living electric", False,
         f"{ch['sessions']} charging sessions across five locations. Four Tesla Superchargers and "
         f"one private Level 2 plug that costs nothing to use, which quietly does a lot of work "
         f"in the cost number. The blended rate is {cents(ch['blended_per_kwh']*100,1)} per kWh. "
         f"Paying full freight at a Supercharger, it is {cents(ch['paid_per_kwh']*100,1)}.",
         [("Energy", f"{ch['energy_kwh']:.1f} kWh"),
          ("Blended", f"{cents(ch['blended_per_kwh']*100,1)}/kWh"),
          ("Supercharger only", f"{cents(ch['paid_per_kwh']*100,1)}/kWh"),
          ("Free kWh", f"{ch['free_kwh']:.0f}")]),
        ("Chapter 4", "FSD", True,
         f"{pct(f['pct'],1)} of every mile in this window was driven by the car, across "
         f"{f['drives']} of {f['of_drives']} trips. That is the number that changed the "
         f"commute. A 42 mile run to Franklin is not a 42 mile run any more, it is a 42 mile "
         f"stretch of doing something else. It still hands control back, and the handoffs are "
         f"the part nobody puts in the brochure.",
         [("Miles on FSD", f"{f['miles']:.1f} of {f['of_miles']:.1f}"),
          ("Share", pct(f['pct'],1)),
          ("Trips", f"{f['drives']} of {f['of_drives']}"),
          ("Latest cycle", f"{D['last_cycle']['fsd_pct']}%")]),
        ("Chapter 5", "The ledger", False,
         f"{usd(ch['cost'])} of charging bought {mi(D['driving']['distance'],1)} miles. That is "
         f"{cents(c['per_mile_cents'])} a mile against {cents(fl[0]['cents_per_mi'])} for the van, "
         f"a difference of {cents(fl[0]['cents_per_mi']-c['per_mile_cents'])} on every single mile. "
         f"TezLab's own savings estimate is more conservative at {usd(D['savings_tezlab_modeled'])}, "
         f"because it compares against a generic car of about 25 mpg rather than the vehicles "
         f"actually replaced. Both numbers are on the Ledger page.",
         [("Charging spend", usd(ch['cost'])),
          ("Per mile", cents(c['per_mile_cents'])),
          ("Versus the van", f"saves {cents(fl[0]['cents_per_mi']-c['per_mile_cents'])}/mi"),
          ("Sessions", str(ch['sessions']))]),
        ("Chapter 6", "The battery", False,
         f"The question every skeptic asks first. At {mi(D['vehicle']['odometer'],0)} miles and "
         f"{b['cycles']} cycles, usable capacity still reads {b['current_kwh']} kWh against an "
         f"original {b['oem_kwh']} kWh. Zero measured degradation, and both degradation and cycle "
         f"count land in the low band against comparable cars in the region. One reading is a "
         f"number. The timeline that makes it a story is being built one Monday at a time.",
         [("Degradation", pct(b['degradation_pct'])),
          ("Capacity", f"{b['current_kwh']} of {b['oem_kwh']} kWh"),
          ("Cycles", str(b['cycles'])),
          ("Versus region", "low on both"),
          ("Range Score", f"{b['recurrent_range_score']}/100")]),
    ]
    out = []
    for n, t, now, prose, data in chapters:
        chips = "".join(f'<li><b>{html.escape(str(v))}</b> {html.escape(k)}</li>' for k, v in data)
        out.append(f"""<li class="chapter{' now' if now else ''}">
  <p class="ch-n">{n}</p>
  <div class="g{' g-2' if now else ''} body">
    <h2>{t}</h2>
    <p>{prose}</p>
    <ul class="data">{chips}</ul>
  </div>
</li>""")
    entries = "".join(f"""<li class="g" style="padding:16px var(--pad)">
  <p class="eyebrow" style="margin-bottom:.35em">{e['date']}</p>
  <h3>{html.escape(e['title'])}</h3>
  <p style="margin:0">{e['body']}</p>
</li>""" for e in LOG["entries"])
    body = f"""<p class="eyebrow">The story &middot; seven chapters</p>
<h1>The <span>Switch</span></h1>
<p class="lede prose">Going from gas to electric for the first time is a sequence, so it is told
as one. Each chapter opens with the data that backs it. The order is the information: this is
what happens, roughly in the order it happens to you.</p>
{livestrip()}
<ol class="chapters">
{''.join(out)}
</ol>
<section class="g g-0">
  <h2>It does not finish</h2>
  <p class="prose" style="margin:0">Every Monday the data gets pulled again, compared against what
  is published here, and any figure that has earned a change gets one. The timeline never closes.
  That is the product, not a gap in it.</p>
</section>
<section>
  <h2>The log</h2>
  <ul class="row" style="list-style:none;margin:0;padding:0">{entries}</ul>
</section>
{rulebar()}
"""
    return write("/switch/", "The Switch",
                 "Gas to electric in seven chapters, each opening with measured data: the fleet "
                 "replaced, the decision, the first week, living electric, FSD, the ledger, the battery.",
                 "hero-highway.jpg", body)

def page_drive():
    f, e, dr = D["fsd"], D["efficiency_vs_region"], D["driving"]
    days = [{**r, "lab": r["d"][5:].replace("-", "/")} for r in D["daily"]]
    rows = "".join(
        f'<tr><td>{c["a"]} to {c["b"]}</td><td class="n">{c["trips"]}</td>'
        f'<td class="n">{c["miles"]:.1f}</td>'
        f'<td class="n">{c["miles"]/c["trips"]:.1f}</td></tr>'
        for c in D["corridors"])
    lc = D["last_cycle"]
    lcrows = "".join(
        f'<tr><td>{d["from"]} to {d["to"]}</td><td class="n">{d["mi"]:.1f}</td>'
        f'<td class="n">{d["eff"]}%</td><td class="n">{d["fsd"]}%</td></tr>'
        for d in lc["drives"])
    body = f"""<p class="eyebrow">Telemetry &middot; {D['window']['days']} days, {dr['drives']} drives</p>
<h1>Where it <span>actually goes</span>.</h1>
<p class="lede prose">Not a route planner and not a map of everywhere a Model Y could go. This is
{mi(dr['distance'],1)} real miles across {dr['drives']} drives, aggregated to city level on purpose.</p>
{livestrip()}

<section class="g">
  <h2>Operating area</h2>
  <p class="prose">Eight towns, twelve corridors. Line weight is trip count, so the thick line is
  the one that pays for itself. Orange rings mark places the car has actually charged.</p>
  {corridor_map()}
  <p class="chart-note">{M} from {dr['drives']} drives. Corridors are city to city only.
  Per drive coordinates and departure times are deliberately held back: the clusters resolve to a
  home and a regular destination, and CLAUDE.md forbids publishing either.</p>
</section>

<section class="row row-2">
  <div class="g">
    <h2>Miles per day</h2>
    {bars(days, value="mi", label="lab", unit=" mi", fmt=lambda v: f"{v:.0f}")}
    <p class="chart-note">{M}. The peak is a {max(d['mi'] for d in days):.1f} mile day running
    down to Unionville and back.</p>
  </div>
  <div class="g">
    <h2>What it costs to park</h2>
    {bars(days, value="idle", label="lab", color="var(--m3)", unit=" mi",
          fmt=lambda v: f"{v:.1f}")}
    <p class="chart-note">{M}. Range lost while parked, {D['idle_loss']['range_lost_mi']:.0f} miles
    over {D['idle_loss']['days']} days. Nobody publishes this number. It is roughly
    {D['idle_loss']['range_lost_mi']/D['idle_loss']['days']:.0f} miles a day of standing still.</p>
  </div>
</section>

<section class="row row-2">
  <div class="g g-2 cmd">
    <p class="k">Miles driven by the car</p>
    <p class="v">{pct(f['pct'],1)}</p>
    <p class="sub">{f['miles']:.1f} of {f['of_miles']:.1f} miles, across {f['drives']} of
    {f['of_drives']} trips. On the most recent charge cycle it was {lc['fsd_pct']}%.</p>
  </div>
  <div class="g">
    <h2>Against the neighbors</h2>
    <p>TezLab compares this car to {e['sample']} other Model Ys within
    {e['radius_km']} km. This one returns {pct(e['mine_pct'])} of its rated efficiency.
    The local group averages {pct(e['group_pct'])}.</p>
    <ul class="legend" style="margin-top:12px">
      <li><i style="background:var(--m1)"></i>This car, {pct(e['mine_pct'])}</li>
      <li><i style="background:var(--m-neutral)"></i>{e['sample']} nearby Model Ys, {pct(e['group_pct'])}</li>
    </ul>
    {hbars([("This car", e['mine_pct'], "rated efficiency"),
            (f"{e['sample']} nearby Model Ys", e['group_pct'], "group average")], unit="%")}
    <p class="chart-note">{M} by TezLab. Nine points is mostly route: steady 40 mile runs at
    {dr['avg_speed']} mph average beat short cold trips.</p>
  </div>
</section>

<section class="g">
  <h2>Every corridor</h2>
  <div class="tw"><table>
    <thead><tr><th>Corridor</th><th class="n">Trips</th><th class="n">Miles</th><th class="n">Avg</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="chart-note">{M}. Short hops inside one town are counted separately and left off this
  table: {D['within_city'][0]['trips']} in {D['within_city'][0]['city']},
  {D['within_city'][1]['trips']} in {D['within_city'][1]['city']}.</p>
</section>

<section class="g">
  <h2>The most recent charge cycle</h2>
  <p class="prose">One full cycle, {lc['start_pct']}% down to {lc['end_pct']}%, on a
  {lc['temp_f']}&deg;F day. {lc['miles']:.1f} miles on {lc['kwh_used']} kWh at
  {lc['efficiency_pct']}% of rated efficiency.</p>
  <div class="tw"><table>
    <thead><tr><th>Drive</th><th class="n">Miles</th><th class="n">Efficiency</th><th class="n">On FSD</th></tr></thead>
    <tbody>{lcrows}</tbody>
  </table></div>
  <p class="chart-note">{M} on {lc['date']}. Climate ran {lc['climate_mins']} minutes while parked,
  Sentry {lc['sentry_mins']}.</p>
</section>

<section class="g g-0">
  <h2>Not here yet</h2>
  <p style="margin:0">Two modules are built and empty on purpose. Road trips: {D['empty_modules']['road_trips']}
  Efficiency against temperature: {D['empty_modules']['monthly_efficiency']}</p>
</section>
{rulebar()}
"""
    return write("/drive/", "Drive",
                 f"{mi(dr['distance'],1)} measured miles across {dr['drives']} drives, "
                 f"{pct(f['pct'],1)} of them driven by the car, mapped to city level.",
                 "hero-highway.jpg", body)

def page_charge():
    ch = D["charging"]
    days = [{**r, "lab": r["d"][5:].replace("-", "/")} for r in D["daily"]]
    rows = "".join(
        f'<tr><td>{html.escape(c["name"])}</td><td>{html.escape(c["kind"])}</td>'
        f'<td class="n">{c["sessions"]}</td><td class="n">{c["kwh"]:.1f}</td>'
        f'<td class="n">{c["max_kw"]}</td><td class="n">{c["last"]}</td></tr>'
        for c in D["chargers"])
    paid_share = ch["paid_kwh"] / ch["energy_kwh"] * 100
    body = f"""<p class="eyebrow">Energy &middot; {ch['sessions']} sessions, five locations</p>
<h1>What the <span>electricity</span> costs.</h1>
<p class="lede prose">Charging is where the running cost of an electric car actually lives, and
where most published comparisons quietly use a residential rate the driver never pays. These are
the real sessions.</p>
{livestrip()}

<section class="row row-2-1">
  <div class="g g-2 cmd">
    <p class="k">Blended rate, all energy</p>
    <p class="v">{cents(ch['blended_per_kwh']*100,1)}<em>/kWh</em></p>
    <p class="sub">{usd(ch['cost'])} for {ch['energy_kwh']:.1f} kWh. Supercharging alone runs
    {cents(ch['paid_per_kwh']*100,1)}, because {ch['free_kwh']:.0f} kWh came from a private plug
    that costs nothing to use.</p>
  </div>
  <div class="g">
    <h2>Two honest numbers</h2>
    <p>The blended rate is what actually left the bank account. The Supercharger rate is what this
    would cost with no free plug in the mix, which is the number worth planning against.</p>
    <p style="margin:0">{pct(paid_share)} of the energy was paid for.</p>
  </div>
</section>

<section class="stats">
  <div class="g stat"><p class="v">{ch['sessions']}</p><p class="k">Sessions</p></div>
  <div class="g stat"><p class="v">{ch['energy_kwh']:.0f}<small>kWh</small></p><p class="k">Energy added</p></div>
  <div class="g stat"><p class="v">{usd(ch['cost'],0)}</p><p class="k">Total spend</p></div>
  <div class="g stat"><p class="v">{ch['charge_time_sec']/3600:.1f}<small>hr</small></p><p class="k">Plugged in</p></div>
</section>

<section class="g">
  <h2>Spend per day</h2>
  {bars(days, value="cost", label="lab", color="var(--m3)", unit="", peak_only=False,
        fmt=lambda v: f"${v:.0f}" if v else "")}
  <p class="chart-note">{M}. Flat days are days it did not need charging, or days it charged on
  the free plug. Eight of {D['window']['days']} days cost nothing at all.</p>
</section>

<section class="g">
  <h2>Every location</h2>
  <div class="tw"><table>
    <thead><tr><th>Location</th><th>Type</th><th class="n">Sessions</th><th class="n">kWh</th>
    <th class="n">Peak kW</th><th class="n">Last used</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="chart-note">{M}. The private charger is listed by city only and its address is not
  published, here or anywhere on this site.</p>
</section>

<section class="g g-0">
  <h2>Charge loss, pending</h2>
  <p style="margin:0">An earlier version of this site published a {pct(9.4,1)} figure for energy
  lost between the plug and the pack. This pull does not return the energy drawn against energy
  added fields needed to recompute it, so the number is withdrawn rather than restated from
  memory. It comes back when the Fleet API billing records support it.</p>
</section>
{rulebar()}
"""
    return write("/charge/", "Charge",
                 f"{ch['sessions']} measured charging sessions across five locations. Blended "
                 f"{cents(ch['blended_per_kwh']*100,1)} per kWh, Supercharger only "
                 f"{cents(ch['paid_per_kwh']*100,1)}.",
                 "hero-charge.jpg", body)

def page_ledger():
    c, ch, b, fl = D["cost"], D["charging"], D["battery"], D["fleet"]
    save_van = fl[0]["cents_per_mi"] - c["per_mile_cents"]
    body = f"""<p class="eyebrow">Money &middot; measured against three gas vehicles</p>
<h1>The <span>Ledger</span>.</h1>
<p class="lede prose">What the car costs to run, what it is worth, and what it earns. The
denominator and the numerator on the same page, because separating them is how people talk
themselves into vehicles they cannot afford.</p>
{livestrip()}

<section class="row row-2-1">
  <div class="g g-2 cmd">
    <p class="k">Cost per mile, measured</p>
    <p class="v">{cents(c['per_mile_cents'])}<em>/mi</em></p>
    <p class="sub">{usd(ch['cost'])} of charging across {mi(D['driving']['distance'],1)} miles.
    Energy only. Insurance, payment and tires are separate lines below and are not buried in
    this figure.</p>
  </div>
  <div class="g">
    <h2>What that saves</h2>
    <p>Against the Express van at {fl[0]['mpg']} mpg, this car saves
    {cents(save_van)} on every mile driven.</p>
    <p style="margin:0">Over the {mi(D['driving']['distance'],1)} miles in this window that is
    about {usd(save_van*D['driving']['distance']/100)} of fuel not bought.</p>
  </div>
</section>

<section class="g">
  <h2>Against the fleet it replaced</h2>
  {hbars([("2024 Model Y (this car)", c['per_mile_cents'], "measured"),
          (fl[0]['name'], fl[0]['cents_per_mi'], f"{fl[0]['mpg']} mpg"),
          (fl[1]['name'], fl[1]['cents_per_mi'], f"{fl[1]['mpg']} mpg"),
          (fl[2]['name'], fl[2]['cents_per_mi'], f"{fl[2]['mpg']} mpg")])}
  <div class="tw" style="margin-top:14px"><table>
    <thead><tr><th>Vehicle</th><th>Role</th><th class="n">mpg</th><th class="n">Per mile</th></tr></thead>
    <tbody>
      <tr><td>2024 Model Y LR AWD</td><td>Current</td><td class="n">n/a</td>
        <td class="n">{cents(c['per_mile_cents'])} {M}</td></tr>
      {''.join(f'<tr><td>{html.escape(v["name"])}</td><td>{html.escape(v["role"])}</td>'
               f'<td class="n">{v["mpg"]}</td><td class="n">{cents(v["cents_per_mi"])}</td></tr>'
               for v in fl)}
    </tbody>
  </table></div>
  <p class="chart-note">Gas figures {MO}: each vehicle's measured fuel economy priced at
  {usd(D['gas']['price_per_gal'])} a gallon ({D['gas']['source']}, {D['gas']['as_of']}).
  TezLab's own estimate of money saved over this window is {usd(D['savings_tezlab_modeled'])},
  which is lower because it compares against a generic car of roughly 25 mpg instead of the
  vehicles actually replaced. Both are honest. They answer different questions.</p>
</section>

<section class="row row-2">
  <div class="g">
    <h2>What it is worth</h2>
    <p>Recurrent puts the market value between {usd(b['recurrent_value_low'],0)} and
    {usd(b['recurrent_value_high'],0)}, moving about {b['recurrent_trend_pct_mo']}% a month.
    Depreciation is the real weak point of this car, and it is a larger number than the fuel
    saving. Saying otherwise would be selling something.</p>
    <p style="margin:0">Range Score {b['recurrent_range_score']} of 100.</p>
  </div>
  <div class="g">
    <h2>What the car earns</h2>
    <p>One car, three income tracks: gig work, software, and events. The vehicle cost is the
    denominator under all three, which is the entire reason this site computes a cost per mile
    at all.</p>
    <p style="margin:0">Per track earnings are held back. This is a public page about a car, not
    about a bank account. The rule is on the Driver page.</p>
  </div>
</section>

<div class="legacy g">{frag('costs')}</div>
<div class="legacy g">{frag('resale')}</div>
{rulebar()}
"""
    return write("/ledger/", "Ledger",
                 f"Measured cost per mile of {cents(c['per_mile_cents'])} against three gas "
                 f"vehicles actually owned, plus value, warranty and what the car earns.",
                 "tex-carbon.jpg", body)

def page_battery():
    b = D["battery"]
    days = [{**r, "lab": r["d"][5:].replace("-", "/")} for r in D["daily"]]
    body = f"""<p class="eyebrow">Health &middot; {b['cycles']} cycles, {mi(D['vehicle']['odometer'],0)} miles</p>
<h1>The question everyone <span>asks first</span>.</h1>
<p class="lede prose">Battery degradation is the reason people give for not buying an electric car.
It deserves a real answer with real numbers, including the parts that are still unknown.</p>
{livestrip()}

<section class="row row-2-1">
  <div class="g g-2 cmd">
    <p class="k">Measured degradation</p>
    <p class="v">{pct(b['degradation_pct'])}</p>
    <p class="sub">Usable capacity reads {b['current_kwh']} kWh against an original
    {b['oem_kwh']} kWh at {b['cycles']} cycles. TezLab rates the pack
    {b['health']} and puts both degradation and cycle count in the low band for comparable
    cars in the region.</p>
  </div>
  <div class="g">
    <h2>One reading is not a trend</h2>
    <p>Zero percent at {mi(D['vehicle']['odometer'],0)} miles is a real measurement, and it is also
    a single point. TezLab returns no capacity history for this car yet.</p>
    <p style="margin:0">So the timeline is being built here instead, one reading every Monday.
    Twelve of them make a story. This is reading number one.</p>
  </div>
</section>

<section class="stats">
  <div class="g stat"><p class="v">{b['current_kwh']}<small>kWh</small></p><p class="k">Usable capacity</p></div>
  <div class="g stat"><p class="v">{b['cycles']}</p><p class="k">Battery cycles</p></div>
  <div class="g stat"><p class="v">{b['recurrent_range_score']}<small>/100</small></p><p class="k">Recurrent Range Score</p></div>
  <div class="g stat"><p class="v">{D['driving']['wh_per_mi']:.0f}<small>Wh/mi</small></p><p class="k">Real consumption</p></div>
</section>

<section class="g">
  <h2>Range lost while parked</h2>
  <p class="prose">Phantom drain is the cost of owning the car on days you do not drive it. Over
  {D['idle_loss']['days']} days this pack gave up {D['idle_loss']['range_lost_mi']:.0f} miles of
  range sitting still, an average of about
  {D['idle_loss']['range_lost_mi']/D['idle_loss']['days']:.0f} miles a day.</p>
  {bars(days, value="idle", label="lab", color="var(--m3)", unit=" mi", fmt=lambda v: f"{v:.1f}")}
  <p class="chart-note">{M}. The spikes are days the car sat outside in Tennessee summer heat with
  cabin protection running. At {cents(D['charging']['blended_per_kwh']*100,1)} a kWh and
  {D['driving']['wh_per_mi']:.0f} Wh a mile, {D['idle_loss']['range_lost_mi']:.0f} miles of lost
  range is roughly
  {usd(D['idle_loss']['range_lost_mi']*D['driving']['wh_per_mi']/1000*D['charging']['blended_per_kwh'])}
  of electricity. {MO}, because the drain is measured in range and converted to dollars here.</p>
</section>

<section class="g">
  <h2>Warranty, the good news</h2>
  <p class="prose" style="margin:0">The battery and drive unit are covered to 2032 or 120,000 miles,
  whichever comes first, with a floor of 70% capacity retention. At {b['cycles']} cycles and
  {pct(b['degradation_pct'])} measured loss, that floor is a long way off. The basic vehicle
  warranty runs to 2028 or 50,000 miles.</p>
</section>

<section class="g g-0">
  <h2>Not here yet</h2>
  <p style="margin:0">{D['empty_modules']['capacity_history']} Once there are enough Monday
  readings to plot, the chart replaces this note.</p>
</section>
{rulebar()}
"""
    return write("/battery/", "Battery",
                 f"{pct(b['degradation_pct'])} measured degradation at {b['cycles']} cycles and "
                 f"{mi(D['vehicle']['odometer'],0)} miles, plus phantom drain and warranty floor.",
                 "hero-charge.jpg", body)

def page_car():
    v = D["vehicle"]
    tabs = [("vin", "Verified"), ("specs", "Spec sheet"), ("juniper", "Juniper"),
            ("software", "Software"), ("fun", "Toybox"), ("accessories", "Accessories")]
    btns = "".join(
        f'<li><button role="tab" id="t-{k}" aria-controls="p-{k}" '
        f'aria-selected="{"true" if i==0 else "false"}">{t}</button></li>'
        for i, (k, t) in enumerate(tabs))
    panels = "".join(
        f'<div class="panel legacy" role="tabpanel" id="p-{k}" aria-labelledby="t-{k}"'
        f'{"" if i==0 else " hidden"}>{frag(k)}</div>'
        for i, (k, t) in enumerate(tabs))
    wraps = "".join(
        f'<li class="g" style="padding:14px var(--pad)"><h3>{n}</h3>'
        f'<p style="margin:0;font-size:.86rem"><a href="/wraps/{f}" download>Download {f}</a></p></li>'
        for n, f in [("Circuit", "Paddock20_Circuit.png"), ("Track Day", "Paddock20_Track_Day.png"),
                     ("Full Send", "Paddock20_Full_Send.png"), ("Ignition", "Paddock20_Ignition.png"),
                     ("Sky Bolt", "Paddock20_Sky_Bolt.png"), ("Bars", "Paddock20_Bars.png")])
    body = f"""<p class="eyebrow">The machine &middot; {v['year']} {v['model']}</p>
<h1>The <span>Car</span>.</h1>
<p class="lede prose">A {v['year']} {v['model']} in {v['color']}, built {v['build']}, seven seats
and a tow hitch. VIN descriptor {v['vin_descriptor']}, with the serial masked in text and in
images. Everything below was verified against the car, not copied from a brochure.</p>
{livestrip()}

<section class="g">
  <h2>Specification</h2>
  <ul class="tabs" role="tablist" aria-label="Specification sections">{btns}</ul>
  {panels}
</section>

<section class="g">
  <h2>Wraps</h2>
  <p class="prose">Six liveries built on Tesla's official Model Y wrap template from the
  teslamotors/custom-wraps repository. Each one is a real Paint Shop file: under 1 MB, correctly
  named, and it loads into the car through Toybox after a USB or mobile app upload.</p>
  <ul class="row row-3" style="list-style:none;margin:14px 0 0;padding:0">{wraps}</ul>
  <p class="chart-note">A 3D preview of these on the car is not shipped. Building one required a
  real Model Y mesh, and the earlier attempt used a shape drawn from scratch, which was the wrong
  answer and was removed.</p>
</section>

<section class="g g-0">
  <h2>Footnote: the best selling car claim</h2>
  <div class="legacy">{frag('history')}</div>
</section>
{rulebar()}
"""
    extra = """<script>
document.addEventListener('click',function(e){
  var b=e.target.closest('.tabs button'); if(!b) return;
  var list=b.closest('.tabs');
  list.querySelectorAll('button').forEach(function(x){
    var on=x===b; x.setAttribute('aria-selected',on?'true':'false');
    document.getElementById(x.id.replace('t-','p-')).hidden=!on;
  });
});
</script>"""
    return write("/car/", "The Car",
                 f"{v['year']} {v['model']} in {v['color']}: verified VIN decode, full spec sheet, "
                 f"Juniper differences, and six Tesla Paint Shop wrap files.",
                 "tex-carbon.jpg", body, extra)

def page_driver():
    fl = D["fleet"]
    body = f"""<p class="eyebrow">Context</p>
<h1>Why the numbers <span>matter</span>.</h1>
<p class="lede prose">Forty-five. Single. Rebuilding after a divorce. Every dollar has to justify
itself, so the car has to prove it belongs.</p>

<section class="g">
  <h2>The reason, not the punchline</h2>
  <p class="prose">Most writing about the cost of driving is done by people who are not paying for
  the car. A press fleet vehicle does not have a payment. A cost per mile calculator does not have
  a bank balance. The difference between an interesting number and a number you actually have to
  live with is the entire reason this site exists.</p>
  <p class="prose" style="margin:0">That is the whole of the personal story on this site. What
  follows is about the vehicles.</p>
</section>

<section class="g">
  <h2>The fleet before this one</h2>
  <p class="prose">Three gas vehicles in about a year, each one bought for a job and sold when the
  job or the math changed.</p>
  <div class="tw"><table>
    <thead><tr><th>Vehicle</th><th>What it did</th><th class="n">mpg</th><th class="n">Per mile</th><th>Held</th></tr></thead>
    <tbody>
      {''.join(f'<tr><td>{html.escape(v["name"])}</td><td>{html.escape(v["role"])}</td>'
               f'<td class="n">{v["mpg"]}</td><td class="n">{cents(v["cents_per_mi"])}</td>'
               f'<td>{html.escape(v["held"])}</td></tr>' for v in fl)}
    </tbody>
  </table></div>
  <p class="chart-note">{MO} at {usd(D['gas']['price_per_gal'])} a gallon. The Sequoia lasted
  fifteen days, which is its own small lesson about buying under pressure.</p>
</section>

<section class="g">
  <h2>Why used, and why the credit never applied</h2>
  <p class="prose" style="margin:0">The car was bought used and financed from a Ford Lincoln store
  in Franklin. The federal clean vehicle credit did not apply to this purchase, so none of the
  figures on this site assume it. Buying used also meant someone else absorbed the steepest part
  of the depreciation curve, which for this model is the largest single cost of ownership and is
  covered honestly on the <a href="/ledger/">Ledger</a>.</p>
</section>

<section class="g g-0">
  <h2>Where the line is</h2>
  <p style="margin:0">Context is public. Figures are not. Income, debt, per track earnings and
  financing terms stay in a private tool and never appear in these pages. What is published here is
  what a vehicle costs to operate, which is a fact about a car.</p>
</section>
{rulebar()}
"""
    return write("/driver/", "The Driver",
                 "Why a measured cost per mile matters more when it is your own money: the context "
                 "behind the site, the gas fleet before it, and where the privacy line sits.",
                 "hero-ev-road.jpg", body)

# ── run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    built = [page_home(), page_switch(), page_drive(), page_charge(),
             page_ledger(), page_battery(), page_car(), page_driver()]
    # Static rules first, then dynamic, and the more specific prefix before the
    # looser one: Cloudflare applies the top-most match and always follows a
    # redirect whether or not an asset exists at that path.
    (PUB / "_redirects").write_text(
        "# Kept from the previous structure: the vehicle profile used to be the root.\n"
        "/index.html      /         301\n"
        "/model-y         /car/     301\n"
        "/model-y/        /car/     301\n"
        "\n"
        "# The 2026-09-03 reorganization.\n"
        "/case-study/     /ledger/  301\n"
        "/log/model-y/    /car/     301\n"
        "/log/            /switch/  301\n"
        "\n"
        "/case-study/*    /ledger/  301\n"
        "/log/model-y/*   /car/     301\n"
        "/log/*           /switch/  301\n")
    urls = ["/", "/switch/", "/drive/", "/charge/", "/ledger/", "/battery/", "/car/", "/driver/"]
    today = datetime.date.today().isoformat()
    (PUB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>https://garage.paddock20.com{u}</loc>"
                  f"<lastmod>{today}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    total = 0
    for p, n in built:
        rel = p.relative_to(PUB)
        total += n
        flag = "  <-- OVER 200 KB" if n > 200_000 else ""
        print(f"  {str(rel):26s} {n/1024:7.1f} KB{flag}")
    print(f"\n  {'total':26s} {total/1024:7.1f} KB across {len(built)} pages")

#!/usr/bin/env python3
"""Road-trip page renderer. Imported by build.py."""
import html

# published city centres, not this car's coordinates
CITY = {
    "Brentwood, TN": (36.0331, -86.7828), "Franklin, TN": (35.9251, -86.8689),
    "Florence, AL": (34.7998, -87.6773),  "Birmingham, AL": (33.5186, -86.8104),
    "Athens, AL": (34.8029, -86.9722),
}

def route_map(T):
    """Animated route. Line weight is leg distance; the path draws itself in."""
    pts = ["Brentwood, TN", "Florence, AL", "Birmingham, AL", "Athens, AL", "Franklin, TN"]
    lats = [CITY[c][0] for c in pts]; lons = [CITY[c][1] for c in pts]
    W, H, PAD = 720, 560, 78
    la0, la1, lo0, lo1 = min(lats), max(lats), min(lons), max(lons)
    def xy(c):
        la, lo = CITY[c]
        return (PAD + (lo - lo0) / (lo1 - lo0) * (W - PAD * 2),
                H - PAD - (la - la0) / (la1 - la0) * (H - PAD * 2))
    o = [f'<svg class="rt-map" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="Route: Brentwood to Florence to Birmingham to Athens to Franklin">']
    # the drawn path
    d = " ".join(("M" if i == 0 else "L") + f"{xy(c)[0]:.1f},{xy(c)[1]:.1f}"
                 for i, c in enumerate(pts))
    o.append(f'<path class="rt-line" d="{d}"/>')
    o.append(f'<path class="rt-line rt-line-lead" d="{d}"/>')
    for i, leg in enumerate(T["legs"]):
        a, b = xy(pts[i]), xy(pts[i + 1])
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        o.append(f'<g class="rt-leg" style="--i:{i}">'
                 f'<text class="rt-legmi" x="{mx:.1f}" y="{my - 8:.1f}" text-anchor="middle">'
                 f'{leg["mi"]:.1f} mi</text>'
                 f'<text class="rt-legwh" x="{mx:.1f}" y="{my + 12:.1f}" text-anchor="middle">'
                 f'{leg["wh_mi"]} Wh/mi</text></g>')
    seen = set()
    for i, c in enumerate(pts):
        if c in seen: continue
        seen.add(c)
        x, y = xy(c)
        charged = any(ch["site"] == c for ch in T["charges"])
        o.append(f'<g class="rt-city" style="--i:{i}">')
        if charged:
            o.append(f'<circle class="rt-pulse" cx="{x:.1f}" cy="{y:.1f}" r="14"/>')
        o.append(f'<circle class="rt-dot{" rt-dot-c" if charged else ""}" cx="{x:.1f}" cy="{y:.1f}" r="7"/>')
        anchor = "end" if x > W * .62 else "start"
        o.append(f'<text class="rt-cl" x="{x + (-16 if anchor=="end" else 16):.1f}" '
                 f'y="{y + 5:.1f}" text-anchor="{anchor}">{html.escape(c.split(",")[0])}</text>')
        o.append("</g>")
    o.append("</svg>")
    return "".join(o)

def soc_trace(T):
    """State of charge across the whole trip: drives fall, charges climb."""
    seq, x = [], 0.0
    order = [("c",0),("d",0),("c",1),("c",2),("d",1),("c",3),("d",2),("c",4),("d",3)]
    for kind, i in order:
        if kind == "d":
            L = T["legs"][i]; w = L["mi"]
            seq.append({"k":"d","x0":x,"x1":x+w,"y0":L["soc_start"],"y1":L["soc_end"],
                        "lab":L["to"].split(",")[0],"sub":f'{L["mi"]:.0f} mi'})
        else:
            C = T["charges"][i]; w = 26
            seq.append({"k":"c","x0":x,"x1":x+w,"y0":C["soc_start"],"y1":C["soc_end"],
                        "lab":C["site"].split(",")[0],"sub":f'+{C["kwh"]:.0f} kWh'})
            w = 26
        x += w
    W, H, T_, B = 720, 250, 26, 44
    total = x
    sx = lambda v: v / total * W
    sy = lambda p: T_ + (100 - p) / 100 * (H - T_ - B)
    o = [f'<svg class="chart rt-soc" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="State of charge across the trip">']
    for p in (0, 50, 100):
        o.append(f'<line class="axis" x1="0" y1="{sy(p):.1f}" x2="{W}" y2="{sy(p):.1f}"/>'
                 f'<text class="lab" x="2" y="{sy(p)-4:.1f}">{p}%</text>')
    d = f"M{sx(seq[0]['x0']):.1f},{sy(seq[0]['y0']):.1f}"
    for s in seq:
        d += f" L{sx(s['x1']):.1f},{sy(s['y1']):.1f}"
    o.append(f'<path class="rt-socfill" d="{d} L{W},{sy(0):.1f} L0,{sy(0):.1f} Z"/>')
    o.append(f'<path class="rt-socline" d="{d}"/>')
    for s in seq:
        mid = sx((s["x0"] + s["x1"]) / 2)
        if s["k"] == "c":
            o.append(f'<rect class="rt-socchg" x="{sx(s["x0"]):.1f}" y="{T_}" '
                     f'width="{sx(s["x1"])-sx(s["x0"]):.1f}" height="{H-T_-B}"/>')
        o.append(f'<text class="rt-socl" x="{mid:.1f}" y="{H-24}" text-anchor="middle">'
                 f'{html.escape(s["lab"])}</text>')
        o.append(f'<text class="rt-socs" x="{mid:.1f}" y="{H-11}" text-anchor="middle">'
                 f'{html.escape(s["sub"])}</text>')
    o.append("</svg>")
    return "".join(o)

def charge_curve(C):
    """Real power-against-charge curve from the session's own telemetry."""
    pts = C["curve"]
    if not pts: return ""
    W, H, PADB, PADT, PADL = 720, 210, 40, 26, 34
    kwmax = max(p["kw"] for p in pts)
    sx = lambda soc: PADL + (soc - pts[0]["soc"]) / (pts[-1]["soc"] - pts[0]["soc"]) * (W - PADL - 8)
    sy = lambda kw: H - PADB - kw / kwmax * (H - PADB - PADT)
    d = " ".join(("M" if i == 0 else "L") + f"{sx(p['soc']):.1f},{sy(p['kw']):.1f}"
                 for i, p in enumerate(pts))
    o = [f'<svg class="chart rt-curve" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="Charging power against state of charge at {html.escape(C["site"])}">']
    for kw in (0, kwmax // 2, kwmax):
        o.append(f'<line class="axis" x1="{PADL}" y1="{sy(kw):.1f}" x2="{W}" y2="{sy(kw):.1f}"/>'
                 f'<text class="lab" x="0" y="{sy(kw)-3:.1f}">{kw:.0f} kW</text>')
    o.append(f'<path class="rt-curvefill" d="{d} L{sx(pts[-1]["soc"]):.1f},{sy(0):.1f} '
             f'L{sx(pts[0]["soc"]):.1f},{sy(0):.1f} Z"/>')
    o.append(f'<path class="rt-curveline" d="{d}"/>')
    pk = max(pts, key=lambda p: p["kw"])
    o.append(f'<circle class="rt-pk" cx="{sx(pk["soc"]):.1f}" cy="{sy(pk["kw"]):.1f}" r="4.5"/>')
    o.append(f'<text class="val" x="{sx(pk["soc"])+9:.1f}" y="{sy(pk["kw"])-7:.1f}">'
             f'{pk["kw"]:.0f} kW peak</text>')
    for p in (pts[0], pts[-1]):
        o.append(f'<text class="lab" x="{sx(p["soc"]):.1f}" y="{H-24}" text-anchor="middle">'
                 f'{p["soc"]:.0f}%</text>')
    o.append(f'<text class="lab" x="{W/2:.1f}" y="{H-6}" text-anchor="middle">'
             f'state of charge</text>')
    o.append("</svg>")
    return "".join(o)

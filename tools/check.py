#!/usr/bin/env python3
"""Pre-deploy gate. Fails loudly rather than shipping a rule violation.

    python3 tools/check.py              gate every page under public/
    python3 tools/check.py --self-test  prove the gate fails tools/fixtures/runway-v6.html

Rules, from CLAUDE.md and the 2026-09-06 site strategy:

  FORBIDDEN      literal patterns that fail anywhere on any page: em dashes, the VIN serial,
                 the street, the private coordinates, the legal name, the former employer,
                 the retired product prefix, and the literal take-home target.

  dollar         a dollar amount fails when its sentence also carries a pay word (gross, pay,
  sentence       paid, tip, tips, earned, earnings, income, net, take-home, target, replace,
                 per hour, /hr, a shift, per delivery, per batch, per order), a platform name,
                 a store name, or the word batch, order or delivery. Percentages, durations,
                 counts and miles always pass: tip share, hours, dead miles, items.
                 "The electricity for the whole day cost $3.19" passes; every pay figure fails
                 in every unit. A sentence is a run of text between block boundaries and
                 sentence punctuation; titles, descriptions, alt text and aria labels count.
                 Store names come from the fixed list below plus whatever data/gig.json names.

  clock time     on /shift/ any clock time fails. Durations only: a start time is the departure
                 pattern CLAUDE.md forbids.

  assets         every local asset referenced must exist; no page over 200 KB; every measured
                 page carries a chip.

The fixture under tools/fixtures/ is the Runway artifact as it stood on 2026-09-06 (v6), with
the ZIP, the legal entity, store streets, the home-zone and home-charger lines and the weekly
window neutralised, because this repository is public. Everything the gate must catch is
still in it: pay in every unit, the target literal, platform and store names beside dollars.
"""
import pathlib, re, sys, json, html

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
FIXTURE = ROOT / "tools" / "fixtures" / "runway-v6.html"

# ── hard rules from CLAUDE.md: literal, anywhere, any page ──────────────────
FORBIDDEN = {
    "em dash":            r"—|&mdash;",
    "VIN serial":         r"7SAYGAEE8RF\d{6}|169869",
    "street address":     r"Alligood",
    "private coordinate": r"36\.17\d{4}|35\.9679\d*|-86\.8235|-86\.2953",
    # the operator's legal name and personal profile stay off this site. The
    # PaddockGavin brand and its domain are deliberately allowed.
    "legal name":         r"Gavin\s+Brooks|linkedin\.com/in/gavinbrooks",
    # former employer: the role ended 2026-09-04. Client is referred to only by
    # description. "DRX" was that engagement's product prefix and is retired.
    "former employer":    r"(?i)du\s?pont",
    "retired product":    r"(?i)\bdrx\b",
    # the take-home target is the owner's financial profile, not a fact about the car
    "take-home target":   r"3,422|\$3422\b",
}

# ── the dollar-sentence rule ────────────────────────────────────────────────
PAY_WORDS = ("gross", "pay", "paid", "tip", "tips", "earned", "earnings", "income", "net",
             "take-home", "target", "replace", "replacement", "per hour", "an hour", "a shift",
             "per shift", "per delivery", "per batch", "per order")
PAY = re.compile(r"(?i)\b(?:%s)\b|/\s?hr\b" % "|".join(re.escape(w) for w in PAY_WORDS))
PLATFORMS = ("Instacart", "DoorDash", "Uber Eats", "Uber", "Lyft", "Amazon Flex", "Walmart Spark",
             "Spark", "Shipt", "Grubhub", "Gopuff", "Favor", "Roadie")
PLATFORM = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(p) for p in PLATFORMS))
STORES = ["Costco", "Target", "The Fresh Market", "Fresh Market", "Kroger", "Publix", "Aldi",
          "Walmart", "Whole Foods", "Sam's Club", "Sprouts", "Trader Joe's", "CVS", "Walgreens",
          "Food Lion", "Meijer", "H-E-B", "Wegmans", "Safeway", "Albertsons", "Petco", "PetSmart",
          "Best Buy", "Staples", "Lowe's", "Home Depot", "Dollar General", "Dollar Tree", "Sephora"]
try:
    for _d in json.loads((ROOT / "data" / "gig.json").read_text()).get("days", []):
        for _b in _d.get("batches", []):
            if _b.get("store") and _b["store"] not in STORES: STORES.append(_b["store"])
except FileNotFoundError:
    pass
# store names are matched as written (Target the store, not target the word: the pay list
# already catches the lower-case word); apostrophes may arrive straight or curly
STORE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(s).replace(r"\'", "['’]") for s in STORES))
WORDS = re.compile(r"(?i)\b(?:batch|batches|order|orders|delivery|deliveries)\b")
DOLLAR = re.compile(r"\$\s?\d")

# on /shift/: 11:03, 11:03am, 11:03 PM, 7pm, 11 am
CLOCK = re.compile(r"(?i)\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?(?![\d.])|\b\d{1,2}\s?[ap]\.?m\b")

BLOCK = re.compile(r"(?is)</?(?:p|li|td|th|h[1-6]|div|section|tr|br|dt|dd|dl|figcaption|title|ul|ol|"
                   r"table|thead|tbody|nav|header|footer|main|article|aside|label|button|option|pre|"
                   r"blockquote|hr|svg|g|text|tspan|rect|line|circle|figure|form|fieldset|legend|"
                   r"details|summary|small)\b[^>]*>")
ATTR = re.compile(r'(?:content|alt|title|aria-label)="([^"]*)"')
SPLIT = re.compile(r"(?<=[.!?])\s+")

def sentences(doc):
    """Reader-visible sentences of one page: element text split at block boundaries and
    sentence punctuation, plus the title, description, alt and aria-label attributes."""
    doc = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", doc)
    attrs = ATTR.findall(doc)
    txt = BLOCK.sub("\n", doc)
    txt = re.sub(r"<[^>]+>", " ", txt)
    out = []
    for chunk in [txt] + attrs:
        for line in html.unescape(chunk).split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if line:
                out += [s.strip() for s in SPLIT.split(line) if s.strip()]
    return out

def dollar_hits(sentence):
    """Why one sentence fails the dollar rule, or [] when it passes."""
    if not DOLLAR.search(sentence): return []
    why = []
    for name, rx in (("pay word", PAY), ("platform", PLATFORM), ("store", STORE), ("word", WORDS)):
        m = rx.search(sentence)
        if m: why.append(f"{name} {m.group(0)!r}")
    return why

def attribute_values(doc):
    return re.findall(r'="([^"]*)"', re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", doc))

def gate(doc, page):
    """All failures for one document. `page` is its site path, e.g. /shift/."""
    fails = []
    for name, pat in FORBIDDEN.items():
        for m in re.finditer(pat, doc):
            fails.append((name, m.group(0)))
    for s in sentences(doc):
        why = dollar_hits(s)
        if why: fails.append(("dollar sentence", f"{s[:140]!r} ({', '.join(why)})"))
    if page.strip("/") == "shift":
        for s in sentences(doc) + attribute_values(doc):
            for m in CLOCK.finditer(s):
                fails.append(("clock time", f"{m.group(0)!r} in {s[:80]!r}"))
    return fails

def site():
    fails, warns = [], []
    pages = sorted(PUB.rglob("index.html"))
    for p in pages:
        t = p.read_text()
        page = "/" + str(p.parent.relative_to(PUB)).strip(".") + "/"
        page = page.replace("//", "/")
        for name, what in gate(t, page):
            fails.append(f"{p}: {name} -> {what}")
        # every local asset referenced must exist
        for ref in set(re.findall(r'(?:src|href)="(/[^"#?]+)"', t)):
            tgt = PUB / ref.strip("/") / "index.html" if ref.endswith("/") else PUB / ref.lstrip("/")
            if not tgt.exists():
                fails.append(f"{p}: missing asset {ref}")
        kb = p.stat().st_size / 1024
        if kb > 200:
            fails.append(f"{p}: {kb:.0f} KB over the 200 KB ceiling")
        # every figure that claims measurement should carry a chip somewhere on the page
        if p.parent.name in {"", "switch", "drive", "charge", "ledger", "battery", "car", "driver", "shift"} \
                and "chip-m" not in t and "chip-mo" not in t:
            warns.append(f"{p}: no measured/modeled chip on the page")
    print(f"checked {len(pages)} pages")
    for w in warns: print("  WARN ", w)
    for f in fails: print("  FAIL ", f)
    print(("\nFAILED: %d" % len(fails)) if fails else "\nall checks pass")
    return 1 if fails else 0

def self_test():
    """The gate must fail the Runway fixture on the dollar-sentence rule and on the target
    literal, and must pass the one dollar sentence the strategy says passes."""
    ok = True
    def expect(cond, msg):
        nonlocal ok
        print(("  ok    " if cond else "  BAD   ") + msg); ok = ok and cond
    passes = "The electricity for the whole day cost $3.19."
    expect(not dollar_hits(passes), f"passes: {passes!r}")
    for s in ("Gross pay was $85.04.", "$85.04 across three batches.", "$20.91/hr on the clock.",
              "Costco paid the most, $40.05.", "Tips were $53.59 of it.", "Instacart sent $18.22.",
              "About $5 an hour.", "$15.99 per hour door to door."):
        expect(bool(dollar_hits(s)), f"fails: {s!r} ({', '.join(dollar_hits(s))})")
    for s in ("Tips were 63% of it.", "4h04m on the clock, 5h19m door to door.", "0.4 dead miles.",
              "89 items across three batches.", "29.3 miles at 10.9 cents a mile."):
        expect(not dollar_hits(s), f"passes (no dollar): {s!r}")
    for s in ("Accepted at 11:03am.", "delivered 4:22 pm", "a 9am start"):
        expect(bool(CLOCK.search(s)), f"clock time caught: {s!r}")
    for s in ("5h19m door to door", "4h04m on the app", "17% to 80%", "82 min for 45 items"):
        expect(not CLOCK.search(s), f"duration allowed: {s!r}")
    if not FIXTURE.exists():
        expect(False, f"fixture missing: {FIXTURE}")
    else:
        fails = gate(FIXTURE.read_text(), "/shift/")
        by = {}
        for name, what in fails: by.setdefault(name, []).append(what)
        expect(len(by.get("dollar sentence", [])) >= 10,
               f"fixture fails the dollar-sentence rule: {len(by.get('dollar sentence', []))} sentences")
        for what in by.get("dollar sentence", [])[:6]: print("            " + what)
        expect(bool(by.get("take-home target")), f"fixture fails the target literal: {by.get('take-home target')}")
        expect(bool(by.get("clock time")), f"fixture would fail the clock rule on /shift/: {len(by.get('clock time', []))} hits")
        for name in ("VIN serial", "street address", "private coordinate", "legal name", "former employer"):
            expect(not by.get(name), f"fixture carries none of: {name}")
    print("\nself-test " + ("passed: the gate fails the fixture" if ok else "FAILED"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else site())

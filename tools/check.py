#!/usr/bin/env python3
"""Pre-deploy gate. Fails loudly rather than shipping a rule violation."""
import pathlib, re, sys, json

PUB = pathlib.Path("public")
fails, warns = [], []
pages = sorted(PUB.rglob("index.html"))

# hard rules from CLAUDE.md
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
}
for p in pages:
    t = p.read_text()
    for name, pat in FORBIDDEN.items():
        for m in re.finditer(pat, t):
            fails.append(f"{p}: {name} -> {m.group(0)!r}")

# every local asset referenced must exist
for p in pages:
    t = p.read_text()
    for ref in set(re.findall(r'(?:src|href)="(/[^"#?]+)"', t)):
        if ref.endswith("/"):
            tgt = PUB / ref.strip("/") / "index.html"
        else:
            tgt = PUB / ref.lstrip("/")
        if not tgt.exists():
            fails.append(f"{p}: missing asset {ref}")

# page weight ceiling
for p in pages:
    kb = p.stat().st_size / 1024
    if kb > 200:
        fails.append(f"{p}: {kb:.0f} KB over the 200 KB ceiling")

# every figure that claims measurement should carry a chip somewhere on the page
for p in pages:
    t = p.read_text()
    if p.parent.name in {"", "switch", "drive", "charge", "ledger", "battery", "car", "driver"} \
            and "chip-m" not in t and "chip-mo" not in t:
        warns.append(f"{p}: no measured/modeled chip on the page")

print(f"checked {len(pages)} pages")
for w in warns: print("  WARN ", w)
for f in fails: print("  FAIL ", f)
print(("\nFAILED: %d" % len(fails)) if fails else "\nall checks pass")
sys.exit(1 if fails else 0)

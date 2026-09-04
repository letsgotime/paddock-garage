#!/usr/bin/env python3
"""One-time: pull inline base64 images and topic blocks out of the legacy 1 MB page.

Images become real files under public/img/car/ (deduped by content hash).
Topic blocks become fragments under content/legacy/ with their <img> src rewritten.
Pixel redactions already applied to these images are preserved byte for byte.
"""
import re, base64, hashlib, json, pathlib

SRC = pathlib.Path("public/log/model-y/index.html")
IMGDIR = pathlib.Path("public/img/car")
FRAGDIR = pathlib.Path("content/legacy")
IMGDIR.mkdir(parents=True, exist_ok=True)
FRAGDIR.mkdir(parents=True, exist_ok=True)

html = SRC.read_text()

# --- 1. images -------------------------------------------------------------
seen, manifest = {}, []
def name_for(idx, ctx):
    ctx = ctx.lower()
    for key, nm in [("vin", "vin-plate"), ("nhtsa", "nhtsa-decode"), ("hw4", "screen-hw4"),
                    ("screen", "screen"), ("window", "window-sticker"), ("monroney", "window-sticker"),
                    ("charge", "charging"), ("odometer", "odometer"), ("interior", "interior"),
                    ("wheel", "wheels"), ("badge", "badge")]:
        if key in ctx:
            return nm
    return f"plate-{idx}"

def repl(m):
    kind, b64 = m.group(1), m.group(2)
    h = hashlib.sha1(b64.encode()).hexdigest()[:10]
    if h in seen:
        return seen[h]
    ext = "png" if kind == "png" else "jpg"
    start = max(0, m.start() - 400)
    ctx = re.sub(r"<[^>]+>", " ", html[start:m.start()])
    nm = name_for(len(manifest), ctx)
    fn = f"{nm}-{h[:6]}.{ext}"
    p = IMGDIR / fn
    raw = base64.b64decode(b64)
    p.write_bytes(raw)
    url = f"/img/car/{fn}"
    seen[h] = url
    manifest.append({"file": fn, "bytes": len(raw), "kind": kind})
    return url

out = re.sub(r"data:image/([a-z+]+);base64,([A-Za-z0-9+/=]+)", repl, html)

# every extracted <img> loads lazily and async-decodes
out = re.sub(r'<img (?![^>]*loading=)', '<img loading="lazy" decoding="async" ', out)

# --- 2. topic blocks -------------------------------------------------------
def extent(s, text):
    depth = 0
    for m in re.finditer(r"</?details\b", text[s:]):
        if m.group(0) == "<details":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return s + m.end() + 1
    return -1

frags = {}
for m in re.finditer(r'<details[^>]*id="([^"]+)"', out):
    tid = m.group(1)
    e = extent(m.start(), out)
    block = out[m.start():e]
    # unwrap: <details><summary><span class="chev">+</span><div class="s-head">H2 + teaser</div></summary> BODY </details>
    head = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S)
    teas = re.search(r'<p class="teaser">(.*?)</p>', block, re.S)
    body = re.split(r"</summary>", block, 1)
    body = body[1].rsplit("</details>", 1)[0] if len(body) > 1 else block
    frags[tid] = {
        "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", head.group(1))).strip() if head else tid,
        "teaser": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", teas.group(1))).strip() if teas else "",
        "body": body.strip(),
    }
    (FRAGDIR / f"{tid}.html").write_text(body.strip())

(FRAGDIR / "_index.json").write_text(json.dumps(
    {k: {"title": v["title"], "teaser": v["teaser"], "bytes": len(v["body"])} for k, v in frags.items()}, indent=2))

print(f"images: {len(manifest)} unique files, {sum(i['bytes'] for i in manifest)//1024} KB")
for i in sorted(manifest, key=lambda x: -x["bytes"]):
    print(f"   {i['file']:28s} {i['bytes']//1024:5d} KB")
print(f"\nfragments: {len(frags)}")
for k, v in frags.items():
    print(f"   {k:14s} {len(v['body'])//1024:4d} KB  {v['title'][:52]}")

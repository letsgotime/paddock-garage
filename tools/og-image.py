#!/usr/bin/env python3
"""Build the Open Graph card for garage.paddock20.com.

Follows the paddock20.com house format: a photo-real dark automotive
plate, a heavy all-caps headline with a single ignition-orange payoff
line, tapered stripe rules, a caps eyebrow, and a bottom stat line.

The background plate is pulled straight out of public/index.html, so the
card always uses the same photography as the page it represents.

    python3 tools/og-image.py public/og/garage.png
"""
import base64, io, os, re, sys
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

W, H   = 1200, 630
PLATE  = 3                       # index of the hero photo in index.html
INK        = (255, 255, 255)
IGNITION   = (244, 81, 30)
SKY        = (87, 180, 230)
INK_FAINT  = (176, 184, 196)
GROUND     = (10, 14, 26)

FD = "/System/Library/Fonts/Supplemental/"
def font(name, size):
    for c in (FD + name, "/Library/Fonts/" + name):
        try: return ImageFont.truetype(c, size)
        except OSError: pass
    return ImageFont.load_default()
black = lambda s: font("Arial Black.ttf", s)
bold  = lambda s: font("Arial Bold.ttf", s)

def tracked(d, xy, text, f, fill, track=0.0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track
    return x

def track_width(d, text, f, track=0.0):
    return sum(d.textlength(c, font=f) + track for c in text) - track

# ---------- background plate -------------------------------------------
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(here, "public", "index.html"), encoding="utf-8").read()
uris = re.findall(r"data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)", html)
src  = Image.open(io.BytesIO(base64.b64decode(uris[PLATE]))).convert("RGB")

# cover-fit, then bias the crop so the car sits right of centre
scale = max(W / src.width, H / src.height) * 1.18
big   = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
left  = 0                                    # keep the left of frame: pushes car right
top   = int((big.height - H) * 0.52)
plate = big.crop((left, top, left + W, top + H))

plate = ImageEnhance.Brightness(plate).enhance(0.52)
plate = ImageEnhance.Contrast(plate).enhance(1.06)

im = Image.new("RGB", (W, H), GROUND)
im.paste(plate, (0, 0))

# left-to-right scrim so type always clears the photo
scrim = Image.new("L", (W, 1))
for x in range(W):
    t = min(max((x - 40) / 820.0, 0.0), 1.0)
    scrim.putpixel((x, 0), int(238 * (1 - t) ** 1.35 + 26))
im = Image.composite(Image.new("RGB", (W, H), GROUND), im, scrim.resize((W, H)))

# bottom vignette to seat the stat line
vig = Image.new("L", (1, H))
for y in range(H):
    vig.putpixel((0, y), int(150 * max(0.0, (y - 430) / 200.0) ** 1.3))
im = Image.composite(Image.new("RGB", (W, H), GROUND), im, vig.resize((W, H)))

d = ImageDraw.Draw(im)
M = 74

# ---------- headline ----------------------------------------------------
HL, LEAD, y = 80, 86, 92
d.text((M, y),            "EVERY NUMBER",  font=black(HL), fill=INK)
d.text((M, y + LEAD),     "ON THIS CAR.",  font=black(HL), fill=INK)
d.text((M, y + LEAD * 2), "MEASURED.",     font=black(HL), fill=IGNITION)

# ---------- tapered stripe rules ---------------------------------------
sy = y + LEAD * 3 + 26
d.polygon([(M, sy),      (M + 432, sy),      (M + 410, sy + 15), (M, sy + 15)], fill=IGNITION)
d.polygon([(M, sy + 21), (M + 406, sy + 21), (M + 386, sy + 34), (M, sy + 34)], fill=SKY)

# ---------- eyebrow -----------------------------------------------------
tracked(d, (M, sy + 60), "2024 TESLA MODEL Y LONG RANGE AWD", bold(21), INK, 2.4)

# ---------- bottom stat line -------------------------------------------
stats = "12.0¢ PER MILE  ·  0% BATTERY DEGRADATION  ·  90.8% ON FSD"
tracked(d, (M, H - 96), stats, bold(19), INK_FAINT, 1.6)
tracked(d, (M, H - 58), "GARAGE.PADDOCK20.COM", black(19), IGNITION, 2.6)

out = sys.argv[1] if len(sys.argv) > 1 else "public/og/garage.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
im.save(out, "PNG", optimize=True)
print("wrote", out, im.size, os.path.getsize(out) // 1024, "KB")

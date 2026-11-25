#!/usr/bin/env python3
"""Turns the avatar into a colour ASCII portrait (scripts/ascii.json) for the hero.

Run it by hand when the avatar changes (needs Pillow: pip install pillow):
  python3 scripts/ascii.py [image-or-url]
Only the figure is kept: a mask built from saturation and brightness decides how
dense each glyph is, so the dark background turns into empty space and the
portrait melts into the night sky.
"""
import io
import json
import os
import sys
import urllib.request

from PIL import Image, ImageFilter, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS, LH = 6.4, 6.6  # font size / line height used by render.py
CW = FS * 0.6
ROWS = 41


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    src = sys.argv[1] if len(sys.argv) > 1 else f"https://github.com/{cfg['login']}.png?size=600"
    data = open(src, "rb").read() if os.path.exists(src) else urllib.request.urlopen(src, timeout=30).read()
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im = ImageOps.fit(im, (600, 600))
    l, t, r, b = cfg.get("portrait_crop", [0, 0, 1, 1])
    im = im.crop((int(l * 600), int(t * 600), int(r * 600), int(b * 600)))
    cols = round(ROWS * LH / CW * im.width / im.height)
    # figure mask: the red costume (by hue) plus pale skin, cleaned up
    hsv, px = im.convert("HSV").load(), im.load()
    mask = Image.new("L", im.size)
    mp = mask.load()
    for y in range(im.height):
        for x in range(im.width):
            h, s_, v = hsv[x, y]
            r, g, b = px[x, y]
            w = 0.0
            if (h < 18 or h > 238) and s_ > 90 and v > 60:
                w = min(1.0, (r - max(g, b)) / 255 * 2.6)
            if v > 110 and s_ < 150 and r > g > b and h < 30:
                w = max(w, min(1.0, (v - 100) / 120))
            mp[x, y] = int(w * 255)
    mask = mask.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(2))
    small = im.resize((cols, ROWS), Image.LANCZOS)
    msmall = mask.resize((cols, ROWS), Image.BOX)
    lum = ImageOps.autocontrast(small.convert("L"), cutoff=3)
    grid = []
    for y in range(ROWS):
        row = []
        for x in range(cols):
            m = msmall.getpixel((x, y)) / 255
            m = 0.0 if m < 0.18 else m
            L = lum.getpixel((x, y)) / 255
            w = min(1.0, m * (0.55 + 0.6 * L))
            R, G, B = small.getpixel((x, y))
            row.append([round(w, 3), round(L, 3), R, G, B])
        grid.append(row)
    with open(os.path.join(ROOT, "scripts", "ascii.json"), "w") as fh:
        json.dump({"cols": cols, "rows": ROWS, "fs": FS, "lh": LH, "grid": grid}, fh, separators=(",", ":"))
    print(f"ascii {cols}x{ROWS}")


if __name__ == "__main__":
    main()

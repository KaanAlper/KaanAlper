#!/usr/bin/env python3
"""Renders the profile README and its SVG cards from config.json + live GitHub data.

Look: calm tonal cards (Rubik), with the Hyprland cyan -> green accent, a night-sky
hero and a few monospace signature bits (name, typing line, ASCII portrait).

Usage:
  python3 scripts/render.py                 # fetch data with $GITHUB_TOKEN
  python3 scripts/render.py --data raw.json # use a saved GraphQL response
  python3 scripts/render.py --print-query   # print the GraphQL query
  PREVIEW=1 python3 scripts/render.py ...   # freeze CSS animations at their end (screenshots)
Stdlib only, so the workflow needs no installs.
"""
import argparse
import base64
import datetime as dt
import html
import json
import math
import os
import random
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "scripts")
ASSETS = os.path.join(ROOT, "assets")
W = 840
CW = 0.6  # JetBrains Mono advance width / em
NOISE = {"Inno Setup", "Batchfile", "VBScript", "Makefile", "Dockerfile", "Jupyter Notebook", "CMake", "NSIS"}

QUERY = """query($login:String!){user(login:$login){
  createdAt followers{totalCount}
  repositories(ownerAffiliations:OWNER,privacy:PUBLIC,first:100,orderBy:{field:PUSHED_AT,direction:DESC}){
    totalCount
    nodes{name description isFork stargazerCount forkCount url
      primaryLanguage{name color}
      languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}
  contributionsCollection{contributionCalendar{totalContributions
    weeks{contributionDays{contributionCount date weekday}}}}}}"""

PAL = {
    "dark": dict(
        bg="#0d1117", surface="#121925", c1="#1a2333", c2="#233046", text="#dbe3f0",
        muted="#8592ab", dim="#4f5b74", a="#33ccff", b="#00ff99", soft="#8fe3ff", softink="#00293a",
        tonal="#16384a", tonalink="#c9f1ff", warn="#ffcb6b", pink="#ff7eb6", purple="#b48cff",
        sky1="#04060c", sky2="#0b1526", moon="#e9f1ff", ink="#05070c",
    ),
    "light": dict(
        bg="#ffffff", surface="#eef4fa", c1="#e1eaf4", c2="#d3e0ee", text="#172033",
        muted="#56627a", dim="#9aa6bb", a="#0a8fd6", b="#0aa46b", soft="#0a8fd6", softink="#ffffff",
        tonal="#d3ecfa", tonalink="#063a55", warn="#b7791f", pink="#d6336c", purple="#7c4ddb",
        sky1="#d9f0ff", sky2="#f2fff9", moon="#8aa2bf", ink="#ffffff",
    ),
}

PREVIEW = "*{animation-delay:-40s!important;animation-play-state:paused!important}" if os.environ.get("PREVIEW") else ""
ICONS = json.load(open(os.path.join(HERE, "icons.json")))
FONT_DIR = os.path.join(HERE, "fonts")


def _b64(name):
    with open(os.path.join(FONT_DIR, name), "rb") as fh:
        return base64.b64encode(fh.read()).decode()


FONTS = {("KM", 400): _b64("jbm-Regular.woff"), ("KM", 700): _b64("jbm-Bold.woff"), ("KM", 800): _b64("jbm-ExtraBold.woff"),
         ("RB", 400): _b64("rubik-400.woff"), ("RB", 500): _b64("rubik-500.woff"), ("RB", 700): _b64("rubik-700.woff")}
RUBIK = {int(k): v for k, v in json.load(open(os.path.join(FONT_DIR, "rubik-metrics.json"))).items()}
MONO = 'font-family="KM,ui-monospace,SFMono-Regular,Menlo,monospace"'


# ---------------------------------------------------------------- helpers
def X(s):
    return html.escape(str(s), quote=True)


def tw(s, fs, weight=400, mono=False):
    """Text width: monospace is exact, Rubik uses its real advance widths."""
    if mono:
        return len(s) * fs * CW
    m = RUBIK[min(RUBIK, key=lambda w: abs(w - weight))]
    return sum(m.get(c, 0.55) for c in str(s)) * fs


def wrap(text, maxw, fs, maxlines, weight=400):
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if tw(nxt, fs, weight) <= maxw:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > maxlines:
        lines = lines[:maxlines]
        lines[-1] = lines[-1].rstrip(" ,.:;") + "..."
    return lines


def lum(hexc):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def readable(hexc, p, theme):
    """Brand/language colour, swapped for the text colour when it would vanish."""
    if not hexc:
        return p["muted"]
    hexc = hexc if hexc.startswith("#") else "#" + hexc
    L = lum(hexc)
    if theme == "dark" and L < 0.06:
        return p["text"]
    if theme == "light" and L > 0.7:
        return p["text"]
    return hexc


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def icon(name, x, y, size, color, theme=None, p=None, fill=True):
    """Vector icon: 'brand:<slug>' from Simple Icons, otherwise a Material Symbol."""
    if name.startswith("brand:"):
        b = ICONS["brand"][name[6:]]
        c = color or readable(b["c"], p, theme)
        return (f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" viewBox="0 0 24 24">'
                f'<path d="{b["d"]}" fill="{c}"/></svg>')
    d = ICONS["symbol"].get(name + "#fill" if fill else name) or ICONS["symbol"][name]
    return (f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" viewBox="0 -960 960 960">'
            f'<path d="{d}" fill="{color}"/></svg>')


def doc(w, h, body, p, fonts=(("RB", 400), ("RB", 700)), defs="", css="", title=""):
    faces = "".join(
        f"@font-face{{font-family:{fam};font-weight:{wt};src:url(data:font/woff;base64,{FONTS[(fam, wt)]}) format('woff')}}"
        for fam, wt in fonts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{X(title)}">
<title>{X(title)}</title>
<defs>
<linearGradient id="hl" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['a']}"/><stop offset="1" stop-color="{p['b']}"/></linearGradient>
<linearGradient id="hlh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['a']}"/><stop offset="1" stop-color="{p['b']}"/></linearGradient>
{defs}
</defs>
<style>
{faces}
text{{white-space:pre}}
text:not([font-family]){{font-family:RB,Rubik,'Google Sans',system-ui,sans-serif}}
.in{{animation:in .7s cubic-bezier(.2,.8,.2,1) both}}
@keyframes in{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.flo{{animation:flo 4.5s ease-in-out infinite}}
@keyframes flo{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-4px)}}}}
.rot{{animation:rot 24s linear infinite;transform-box:fill-box;transform-origin:center}}
@keyframes rot{{to{{transform:rotate(360deg)}}}}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
{PREVIEW}
</style>
{body}
</svg>
"""


def cookie(cx, cy, R, n=8, amp=0.07, rot=0.0):
    """Scalloped circle (Material 3 style shape): r = R(1 + amp cos(n t))."""
    pts = []
    for k in range(0, 360, 2):
        t = math.radians(k)
        r = R * (1 + amp * math.cos(n * (t + rot)))
        pts.append(f"{cx + r * math.cos(t):.1f},{cy + r * math.sin(t):.1f}")
    return "M" + " L".join(pts) + "Z"


def badge(x, y, size, name, p, theme, tint, n=8, amp=0.08, spin=False, solid=False):
    """Icon sitting on a scalloped shape."""
    c = size / 2
    shape = f'<path d="{cookie(x + c, y + c, c / (1 + amp), n, amp)}" fill="{tint}"' + ("" if solid else ' fill-opacity=".2"') + "/>"
    if spin:
        shape = f'<g class="rot">{shape}</g>'
    isz = size * 0.56
    fg = p["ink"] if solid else (None if name.startswith("brand:") else tint)
    return shape + icon(name, x + (size - isz) / 2, y + (size - isz) / 2, isz, fg, theme, p)


def shell(w, h, p, title=None, ic=None, theme=None, tint=None):
    s = [f'<rect width="{w}" height="{h}" rx="24" fill="{p["surface"]}"/>']
    if title:
        s.append(badge(24, 22, 38, ic, p, theme, tint or p["a"], spin=True)
                 + f'<text x="74" y="48" font-size="20" font-weight="700" fill="{p["text"]}">{X(title)}</text>')
    return "".join(s)


def wave(amp, period, base, width, height, phase=0.0):
    pts = []
    for x in range(0, int(width) + 1, 8):
        y = base + amp * math.sin((x / period) * 2 * math.pi + phase) + amp * 0.35 * math.sin((x / period) * 4 * math.pi + phase * 2)
        pts.append(f"{x},{y:.1f}")
    return f"M0,{height} L" + " L".join(pts) + f" L{int(width)},{height} Z"


# ---------------------------------------------------------------- data
def gql(query, variables, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-render"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)
    if j.get("errors"):
        raise SystemExit(json.dumps(j["errors"]))
    return j


def digest(raw):
    u = raw["data"]["user"]
    nodes = u["repositories"]["nodes"]
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    days = [d for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    days = [d for d in days if d["date"] <= today]
    counts = [d["contributionCount"] for d in days]
    cur, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1  # today not done yet does not break the streak
    while i >= 0 and counts[i] > 0:
        cur += 1
        i -= 1
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    langs, colors = {}, {}
    for r in nodes:
        if r["isFork"]:
            continue
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n in NOISE:
                continue
            langs[n] = langs.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    return dict(
        stars=sum(r["stargazerCount"] for r in nodes if not r["isFork"]),
        repos=u["repositories"]["totalCount"],
        followers=u["followers"]["totalCount"],
        contributions=u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        days=days,
        streak=cur,
        longest=longest,
        languages=[(n, s / total * 100, colors.get(n)) for n, s in top],
        repo={r["name"]: r for r in nodes},
        today=today,
    )


# ---------------------------------------------------------------- hero
RAMP = " .:-=+*#%@"


def _glyph(w):
    w = w ** .6 if w > 0 else 0
    return 0 if w < .12 else min(len(RAMP) - 1, 1 + int((w - .12) / .88 * (len(RAMP) - 1)))


def ascii_art(p, theme, x, y, bg):
    """The avatar as an ASCII portrait (scripts/ascii.json, made by scripts/ascii.py).

    Glyphs take the theme gradient with only a hint of the painting's colour.
    Rows fade in one by one, the feet dissolve into the waves, and a light band
    sweeps through the glyphs only (the text itself is the clip path).
    """
    A = json.load(open(os.path.join(HERE, "ascii.json")))
    fs, lh, cols = A["fs"], A["lh"], A["cols"]
    aw, ah = cols * fs * CW, A["rows"] * lh
    rows_txt, rows_clip = [], []
    for r, row in enumerate(A["grid"]):
        base = mix(p["a"], p["b"], r / max(1, A["rows"] - 1))
        spans, last, buf = [], None, ""
        for w, l, R, G, B in row:
            k = _glyph(w)
            ww = w ** .6 if w > 0 else 0
            c = mix(base, f"#{R:02x}{G:02x}{B:02x}", .2)
            if theme == "dark":
                c = mix(mix(c, "#ffffff", .3 * l), bg, .3 * (1 - ww))
            else:
                c = mix(mix(c, "#000000", .3), bg, .25 * (1 - ww))
            c = c[:2] + c[2] + c[4] + c[4] + c[6] + c[6]  # quantise so runs merge
            ch = RAMP[k]
            if ch == " ":
                c = last or c
            if c != last and buf:
                spans.append(f'<tspan fill="{last}">{X(buf)}</tspan>')
                buf = ""
            last, buf = c, buf + ch
        if buf:
            spans.append(f'<tspan fill="{last}">{X(buf)}</tspan>')
        attrs = (f'{MONO} x="{x:.1f}" y="{y + (r + 1) * lh - 1:.1f}" font-size="{fs}" font-weight="800" '
                 f'textLength="{aw:.1f}" lengthAdjust="spacingAndGlyphs"')
        rows_txt.append(f'<text class="row" style="animation-delay:{.2 + r * .035:.2f}s" {attrs}>{"".join(spans)}</text>')
        rows_clip.append(f'<text {attrs}>{X("".join(RAMP[_glyph(w)] for w, *_ in row))}</text>')
    return "".join([
        f'<linearGradient id="artFadeG" x1="0" y1="0" x2="0" y2="1"><stop offset=".82" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity=".1"/></linearGradient>',
        f'<mask id="artFade"><rect x="{x - 4}" y="{y - 4}" width="{aw + 8:.0f}" height="{ah + 8:.0f}" fill="url(#artFadeG)"/></mask>',
        f'<clipPath id="asc">{"".join(rows_clip)}</clipPath>',
        f'<g mask="url(#artFade)">{"".join(rows_txt)}',
        f'<g clip-path="url(#asc)"><rect class="scan" x="{x}" y="{y - 30}" width="{aw:.0f}" height="26" fill="url(#scanG)"/></g></g>'])


def pixel_card(cx, cy, w, h, rot, p, seed, border):
    """Back card: a tilted sticker card filled with a chunky pixel pattern in the theme colours."""
    rnd = random.Random(seed)
    cell = 14
    cells = []
    cols, rows = int(w // cell) + 1, int(h // cell) + 1
    for j in range(rows):
        for i in range(cols):
            v = rnd.random() + (j / rows) * .25
            if v > .72:
                c = p["a"] if rnd.random() < .6 else p["b"]
                op = .5 + rnd.random() * .5
                cells.append(f'<rect x="{-w / 2 + i * cell}" y="{-h / 2 + j * cell}" width="{cell}" height="{cell}" fill="{c}" opacity="{op:.2f}"/>')
    cid = f"pc{seed}"
    return (f'<g transform="translate({cx} {cy}) rotate({rot})">'
            f'<clipPath id="{cid}"><rect x="{-w / 2}" y="{-h / 2}" width="{w}" height="{h}" rx="16"/></clipPath>'
            f'<rect x="{-w / 2}" y="{-h / 2}" width="{w}" height="{h}" rx="16" fill="{p["c2"]}"/>'
            f'<g clip-path="url(#{cid})">{"".join(cells)}</g>'
            f'<rect x="{-w / 2}" y="{-h / 2}" width="{w}" height="{h}" rx="16" fill="none" stroke="{border}" stroke-width="5"/></g>')


def banner(cfg, D, p, theme):
    """Hero in the spirit of a trading-card banner: tilted sticker cards spill out of a
    striped panel, a big chunky name, and a row of little tiles hanging off the bottom."""
    H = 330
    px, py, pw, ph = 96, 22, W - 96, 250  # panel
    P = 300
    page = theme
    # the panel is bright pastel in both themes so it pops off the page; the portrait card stays dark
    p = dict(PAL["light"], sky1="#c4ecff", sky2="#c9fbe6", a="#1fb6f0", b="#00d27c", text="#0d2132",
             muted="#3a5870", c1="#ffffff", c2="#e4f3fb")
    dark = PAL["dark"]
    theme = "light"
    border = "#ffffff"
    defs = f"""<clipPath id="panel"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="18"/></clipPath>
<linearGradient id="sky" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['sky1']}"/><stop offset="1" stop-color="{p['sky2']}"/></linearGradient>
<filter id="soft" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="2.5"/></filter>
<filter id="drop" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#000" flood-opacity="{.5 if page == 'dark' else .2}"/></filter>
<linearGradient id="scanG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".7" stop-color="#fff" stop-opacity=".25"/><stop offset="1" stop-color="#fff" stop-opacity=".9"/></linearGradient>"""
    css = f"""
.st1{{animation:st 9s linear infinite}}.st2{{animation:st 13s linear infinite reverse}}.st3{{animation:st 17s linear infinite}}
@keyframes st{{to{{transform:translateX(-{P}px)}}}}
.tw{{animation:tw 3.2s ease-in-out infinite}}
@keyframes tw{{0%,100%{{opacity:.15}}50%{{opacity:1}}}}
.card{{animation:card 6s ease-in-out infinite}}
@keyframes card{{0%,100%{{transform:translateY(0) rotate(0)}}50%{{transform:translateY(-5px) rotate(.6deg)}}}}
.row{{animation:row .5s ease-out both}}
@keyframes row{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
.scan{{animation:scan 6s cubic-bezier(.5,0,.5,1) 2s infinite}}
@keyframes scan{{from{{transform:translateY(0)}}to{{transform:translateY(320px)}}}}
.pop{{animation:pop .55s cubic-bezier(.3,1.6,.5,1) both;transform-box:fill-box;transform-origin:center}}
@keyframes pop{{from{{transform:scale(0) rotate(-20deg)}}to{{transform:none}}}}
.hop{{animation:hop 3s ease-in-out infinite}}
@keyframes hop{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-5px)}}}}
"""
    s = []
    # panel: sky + bold diagonal stripes with wavy edges, sliding
    s.append(f'<g clip-path="url(#panel)"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="url(#sky)"/>')
    rnd = random.Random(7)
    for _ in range(0):
        s.append(f'<circle class="tw" cx="{rnd.uniform(px, W):.0f}" cy="{rnd.uniform(py, py + ph):.0f}" r="{rnd.uniform(.5, 1.4):.2f}" fill="{p["moon"]}" style="animation-delay:-{rnd.uniform(0, 3):.2f}s"/>')
    span = 1400 + P
    s.append(f'<g transform="rotate(-28 470 150)" filter="url(#soft)">'
             f'<g class="st1"><path d="{wave(10, P, 40, span, 120)}" transform="translate(-300 0)" fill="{p["a"]}" opacity=".55"/></g>'
             f'<g class="st2"><path d="{wave(9, P, 120, span, 170, 1.7)}" transform="translate(-300 0)" fill="#ffffff" opacity=".75"/></g>'
             f'<g class="st3"><path d="{wave(12, P, 170, span, 260, .8)}" transform="translate(-300 0)" fill="{p["b"]}" opacity=".45"/></g>'
             f'<g class="st2"><path d="{wave(10, P, 260, span, 330, 2.4)}" transform="translate(-300 0)" fill="{p["a"]}" opacity=".35"/></g></g>')
    s.append("</g>")
    # stacked sticker cards spilling out of the panel's left edge
    s.append(f'<g filter="url(#drop)">')
    s.append(f'<g class="card" style="animation-delay:-2s">{pixel_card(112, 168, 150, 214, -14, p, 3, border)}</g>')
    s.append(f'<g class="card" style="animation-delay:-4s">{pixel_card(150, 160, 150, 214, -7, p, 5, border)}</g>')
    # front card with the ASCII portrait
    A = json.load(open(os.path.join(HERE, "ascii.json")))
    aw, ah = A["cols"] * A["fs"] * CW, A["rows"] * A["lh"]
    cw_, ch_ = 168, 236
    sc = min((cw_ - 24) / aw, (ch_ - 26) / ah)
    s.append(f'<g class="card"><g transform="translate(222 170) rotate(5)">'
             f'<rect x="{-cw_ / 2}" y="{-ch_ / 2}" width="{cw_}" height="{ch_}" rx="16" fill="{dark["sky2"]}"/>'
             f'<g transform="translate({-aw * sc / 2:.1f} {-ah * sc / 2 + 4:.1f}) scale({sc:.3f})">{ascii_art(dark, "dark", 0, 0, dark["sky2"])}</g>'
             f'<rect x="{-cw_ / 2}" y="{-ch_ / 2}" width="{cw_}" height="{ch_}" rx="16" fill="none" stroke="{border}" stroke-width="5"/>'
             f'<text {MONO} x="{cw_ / 2 - 6}" y="{-ch_ / 2 - 9}" font-size="13" font-weight="700" fill="{p["text"]}" text-anchor="end">@{X(cfg["login"])}</text>'
             f'</g></g></g>')
    # big chunky name with an offset shadow
    x0 = 330
    name = X(cfg["name"])
    s.append(f'<g class="in" style="animation-delay:.15s">'
             f'<text {MONO} x="{x0 + 4}" y="{py + 92}" font-size="72" font-weight="800" fill="{p["a"]}" opacity=".55" letter-spacing="-2">{name}</text>'
             f'<text {MONO} x="{x0}" y="{py + 88}" font-size="72" font-weight="800" fill="{p["text"]}" letter-spacing="-2">{name}</text></g>')
    s.append(f'<g class="in" style="animation-delay:.3s"><text {MONO} x="{x0 + 2}" y="{py + 124}" font-size="19" font-weight="700" fill="{p["text"]}">{X(cfg["headline"])}</text>'
             f'<text {MONO} x="{x0 + 2}" y="{py + 148}" font-size="14" fill="{p["muted"]}">{X(cfg["subline"])}</text></g>')
    s.append(f'<g class="in" style="animation-delay:.45s"><text {MONO} x="{x0 + 2}" y="{py + 192}" font-size="20" font-weight="800" fill="{p["text"]}">Daily drivers</text></g>')
    # tiles hanging off the bottom edge of the panel
    for i, slug in enumerate(cfg["drivers"]):
        tx, ty, ts = x0 + 2 + i * 62, py + 206, 54
        s.append(f'<g class="pop" style="animation-delay:{.6 + i * .08:.2f}s"><g class="hop" style="animation-delay:-{i * .4:.1f}s">'
                 f'<rect x="{tx}" y="{ty}" width="{ts}" height="{ts}" rx="12" fill="{p["c1"]}" stroke="{border}" stroke-width="3.5" filter="url(#drop)"/>'
                 + icon("brand:" + slug, tx + 14, ty + 14, 26, None, theme, p)
                 + f'<title>{X(ICONS["brand"][slug]["t"])}</title></g></g>')
    return doc(W, H, "".join(s), p, (("KM", 400), ("KM", 700), ("KM", 800)), defs, css,
               f"{cfg['name']}: {cfg['headline']}. {cfg['subline']}")


def greet(cfg, p, theme):
    """Big centred typing line under the hero."""
    H, fs = 76, 32
    lines = cfg["greetings"]
    s, ids = [], [f"g{i}" for i in range(len(lines))]
    for i, line in enumerate(lines):
        width = tw(line, fs, mono=True)
        x = (W - width) / 2
        type_t, hold, erase = len(line) * 0.07, 2.6, 0.6
        dur = type_t + hold + erase
        k1, k2 = type_t / dur, (type_t + hold) / dur
        begin = f"0s;{ids[-1]}.end" if i == 0 else f"{ids[i - 1]}.end"
        s.append(f'<clipPath id="gc{i}"><rect x="{x - 2:.1f}" y="0" width="0" height="{H}">'
                 f'<animate id="{ids[i]}" attributeName="width" begin="{begin}" dur="{dur:.2f}s" values="0;{width + 4:.1f};{width + 4:.1f};0" keyTimes="0;{k1:.3f};{k2:.3f};1"/>'
                 f'</rect></clipPath>')
        s.append(f'<g clip-path="url(#gc{i})"><text {MONO} x="{x:.1f}" y="48" font-size="{fs}" font-weight="700" fill="{p["text"]}">{X(line)}</text></g>')
        s.append(f'<rect x="{x:.1f}" y="22" width="4" height="34" rx="2" fill="{p["b"]}" opacity="0">'
                 f'<set attributeName="opacity" to="1" begin="{ids[i]}.begin" end="{ids[i]}.end"/>'
                 f'<animate attributeName="x" begin="{ids[i]}.begin" dur="{dur:.2f}s" values="{x:.1f};{x + width + 6:.1f};{x + width + 6:.1f};{x:.1f}" keyTimes="0;{k1:.3f};{k2:.3f};1"/></rect>')
    return doc(W, H, "".join(s), p, (("KM", 700),), title=" / ".join(lines))


# ---------------------------------------------------------------- cards
def about(cfg, D, p, theme):
    items = cfg["about"]
    rows = math.ceil(len(items) / 2)
    H = 82 + rows * 56 + 14
    cw = (W - 48 - 10) / 2
    tints = [p["a"], p["b"], p["purple"], p["pink"]]
    s = [shell(W, H, p, "About me", "favorite", theme, p["pink"])]
    for i, it in enumerate(items):
        x = 24 + (i % 2) * (cw + 10)
        y = 82 + (i // 2) * 56
        s.append(f'<g class="in" style="animation-delay:{.08 * i:.2f}s">'
                 f'<rect x="{x:.0f}" y="{y}" width="{cw:.0f}" height="46" rx="16" fill="{p["c1"]}"/>'
                 + badge(x + 10, y + 7, 32, it["icon"], p, theme, tints[i % 4], n=6, amp=.1)
                 + f'<text x="{x + 54:.0f}" y="{y + 28.5}" font-size="15" font-weight="500" fill="{p["text"]}">{X(it["label"])}</text></g>')
    return doc(W, H, "".join(s), p, (("RB", 500), ("RB", 700)), title="About me: " + ", ".join(i["label"] for i in items))


def stack(cfg, D, p, theme):
    groups = cfg["stack"]
    H = 82 + len(groups) * 68 + 6
    s = [shell(W, H, p, "Tech stack", "code", theme, p["a"])]
    y, k = 86, 0
    for g in groups:
        s.append(f'<text x="26" y="{y}" font-size="11.5" font-weight="700" fill="{p["muted"]}" letter-spacing="1.5">{X(g["title"].upper())}</text>')
        x = 24
        for slug, label in g["items"]:
            iw = 14 + 18 + 9 + tw(label, 14, 500) + 16
            s.append(f'<g class="in" style="animation-delay:{k * .04:.2f}s"><g class="flo" style="animation-delay:-{k * .45:.2f}s">'
                     f'<rect x="{x:.0f}" y="{y + 11}" width="{iw:.0f}" height="38" rx="14" fill="{p["c1"]}"/>'
                     + icon("brand:" + slug, x + 14, y + 21, 18, None, theme, p)
                     + f'<text x="{x + 41:.0f}" y="{y + 35}" font-size="14" font-weight="500" fill="{p["text"]}">{X(label)}</text></g></g>')
            x += iw + 8
            k += 1
        y += 68
    title = "; ".join(g["title"] + ": " + ", ".join(l for _, l in g["items"]) for g in groups)
    return doc(W, H, "".join(s), p, (("RB", 500), ("RB", 700)), title="Tech stack: " + title)


def card(item, D, p, theme, i):
    w, H = 410, 186
    r = D["repo"][item["repo"]]
    name = item.get("title") or r["name"]
    lang = item.get("lang") or (r["primaryLanguage"] or {}).get("name")
    tints = [p["a"], p["b"], p["purple"], p["pink"]]
    s = [shell(w, H, p)]
    s.append(badge(22, 20, 48, item["icon"], p, theme, tints[i % 4], n=9, amp=.07, spin=True))
    s.append(f'<circle cx="{w - 38}" cy="40" r="17" fill="{p["c1"]}"/>' + icon("arrow_outward", w - 47, 31, 18, p["muted"]))
    s.append(f'<text x="24" y="100" font-size="19" font-weight="700" fill="{p["text"]}">{X(name)}</text>')
    for li, ln in enumerate(wrap(item["text"], w - 48, 13.5, 2)):
        s.append(f'<text x="24" y="{124 + li * 19}" font-size="13.5" fill="{p["muted"]}">{X(ln)}</text>')
    y = H - 30
    if lang:
        lw = tw(lang, 12, 500) + 22
        s.append(f'<rect x="24" y="{y - 5}" width="{lw:.0f}" height="24" rx="9" fill="{p["c1"]}"/>'
                 f'<text x="35" y="{y + 11.5}" font-size="12" font-weight="500" fill="{p["text"]}">{X(lang)}</text>')
    st = str(r["stargazerCount"])
    s.append(f'<text x="{w - 24}" y="{y + 12}" font-size="14" font-weight="700" fill="{p["text"]}" text-anchor="end">{st}</text>')
    s.append(icon("star", w - 24 - tw(st, 14, 700) - 21, y - 2, 17, p["warn"]))
    return doc(w, H, f'<g class="in" style="animation-delay:{i * .1:.1f}s">{"".join(s)}</g>', p, (("RB", 400), ("RB", 500), ("RB", 700)),
               title=f"{name}: {item['text']}")


def activity(cfg, D, p, theme):
    H = 326
    s = [shell(W, H, p, "GitHub activity", "monitoring", theme, p["a"])]
    stats = [("star", D["stars"], "Stars earned", p["warn"]),
             ("commit", D["contributions"], "Contributions this year", p["a"]),
             ("book_2", D["repos"], "Public repos", p["b"]),
             ("group", D["followers"], "Followers", p["purple"])]
    tw_, th_ = 196, 78
    for i, (ic, val, label, c) in enumerate(stats):
        x = 24 + (i % 2) * (tw_ + 10)
        y = 78 + (i // 2) * (th_ + 10)
        s.append(f'<g class="in" style="animation-delay:{i * .08:.2f}s">'
                 f'<rect x="{x}" y="{y}" width="{tw_}" height="{th_}" rx="18" fill="{p["c1"]}"/>'
                 + badge(x + 12, y + 10, 34, ic, p, theme, c, n=8, amp=.09)
                 + f'<text x="{x + 54}" y="{y + 36}" font-size="26" font-weight="700" fill="{p["text"]}">{X(val)}</text>'
                 f'<text x="{x + 14}" y="{y + 64}" font-size="12.5" fill="{p["muted"]}">{X(label)}</text></g>')
    # last three calendar weeks, future days dashed
    cx0 = 24 + 2 * tw_ + 10 + 22
    byd = {d["date"]: d for d in D["days"]}
    end = dt.date.fromisoformat(D["today"])
    start = end - dt.timedelta(days=(end.weekday() + 1) % 7 + 14)
    slots = [byd.get((start + dt.timedelta(days=k)).isoformat()) if start + dt.timedelta(days=k) <= end else None for k in range(21)]
    s.append(f'<text x="{cx0}" y="88" font-size="13" font-weight="500" fill="{p["text"]}">Last 21 days</text>')
    cell, gap, hh = 46, 6, 40
    for wd, ch in enumerate("SMTWTFS"):
        s.append(f'<text x="{cx0 + wd * (cell + gap) + cell / 2}" y="110" font-size="11.5" font-weight="500" fill="{p["dim"]}" text-anchor="middle">{ch}</text>')
    mx = max([d["contributionCount"] for d in slots if d] + [1])
    for k, d in enumerate(slots):
        x = cx0 + (k % 7) * (cell + gap)
        y = 120 + (k // 7) * (hh + gap)
        if d is None:
            s.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{hh}" rx="13" fill="none" stroke="{p["c2"]}" stroke-dasharray="4 4"/>')
            continue
        c = d["contributionCount"]
        lv = 0 if c == 0 else min(4, 1 + int(math.sqrt(c / mx) * 3.999))
        fill = p["c2"] if lv == 0 else mix(p["c2"], p["a"] if lv < 4 else p["b"], .3 + lv * .17)
        ring = f' stroke="{p["b"]}" stroke-width="2"' if d["date"] == D["today"] else ""
        fg = p["ink"] if lv >= 3 else p["text"]
        s.append(f'<g class="in" style="animation-delay:{.2 + k * .03:.2f}s"><rect x="{x}" y="{y}" width="{cell}" height="{hh}" rx="13" fill="{fill}"{ring}/>'
                 f'<text x="{x + cell / 2}" y="{y + hh / 2 + 5:.0f}" font-size="13" font-weight="500" fill="{fg}" text-anchor="middle">{int(d["date"][8:])}</text></g>')
    # languages: rounded pills with little gaps, growing in
    langs = D["languages"][:6]
    tot = sum(v for _, v, _ in langs) or 1
    by, bw = 276, W - 48
    s.append(f'<text x="24" y="{by - 12}" font-size="13" font-weight="500" fill="{p["text"]}">Languages across my repositories</text>')
    s.append(f'<clipPath id="lb"><rect x="24" y="{by}" width="0" height="10">'
             f'<animate attributeName="width" begin=".3s" dur="1.4s" from="0" to="{bw}" fill="freeze" calcMode="spline" keySplines=".2 .8 .2 1" keyTimes="0;1"/></rect></clipPath>')
    x, seg, g = 24, [], 4
    usable = bw - g * (len(langs) - 1)
    for name, v, c in langs:
        sw = max(8, v / tot * usable)
        seg.append(f'<rect x="{x:.1f}" y="{by}" width="{sw:.1f}" height="10" rx="5" fill="{readable(c, p, theme)}"/>')
        x += sw + g
    s.append(f'<g clip-path="url(#lb)">{"".join(seg)}</g>')
    x = 24
    for i, (name, v, c) in enumerate(langs):
        lab = f"{name} {v / tot * 100:.0f}%"
        s.append(f'<g class="in" style="animation-delay:{.7 + i * .07:.2f}s"><circle cx="{x + 4}" cy="{by + 27}" r="4" fill="{readable(c, p, theme)}"/>'
                 f'<text x="{x + 13}" y="{by + 31.5}" font-size="12.5" fill="{p["muted"]}">{X(lab)}</text></g>')
        x += tw(lab, 12.5) + 26
    return doc(W, H, "".join(s), p, (("RB", 400), ("RB", 500), ("RB", 700)),
               title="GitHub activity: " + ", ".join(f"{l}: {v}" for _, v, l, _ in stats))


def streak(cfg, D, p, theme):
    H = 176
    css = """.fire{animation:fire 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:50% 90%}
@keyframes fire{0%,100%{transform:scale(1)}50%{transform:scale(1.07,1.13)}}"""
    s = [shell(W, H, p, "Streak", "local_fire_department", theme, p["pink"])]
    hw = (W - 48 - 10) / 2
    for i, (val, label, ic, hot) in enumerate([(D["streak"], "Current streak", "local_fire_department", True),
                                                (D["longest"], "Longest this year", "trophy", False)]):
        x = 24 + i * (hw + 10)
        fill = p["soft"] if hot else p["c1"]
        fg, sub = (p["softink"], p["softink"]) if hot else (p["text"], p["muted"])
        s.append(f'<g class="in" style="animation-delay:{i * .1:.1f}s"><rect x="{x:.0f}" y="78" width="{hw:.0f}" height="76" rx="20" fill="{fill}"/>')
        b = badge(x + 16, 92, 48, ic, p, theme, p["softink"] if hot else p["warn"], n=12, amp=.08, spin=True)
        s.append(f'<g class="fire">{b}</g>' if hot else b)
        s.append(f'<text x="{x + 78:.0f}" y="121" font-size="30" font-weight="700" fill="{fg}">{val}'
                 f'<tspan font-size="14" font-weight="500" fill="{sub}"> days</tspan></text>'
                 f'<text x="{x + 78:.0f}" y="140" font-size="12.5" fill="{sub}" opacity=".85">{label}</text></g>')
    return doc(W, H, "".join(s), p, (("RB", 400), ("RB", 500), ("RB", 700)), css=css,
               title=f"Current streak {D['streak']} days, longest {D['longest']} days")


def dock(cfg, D, p, theme):
    H, sz, gap = 100, 30, 22
    items = cfg["dock"]
    dw = len(items) * sz + (len(items) - 1) * gap + 52
    dx = (W - dw) / 2
    css = """.bob{animation:bob 2.8s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}"""
    s = [f'<rect x="{dx:.0f}" y="22" width="{dw:.0f}" height="58" rx="22" fill="{p["surface"]}"/>']
    for i, slug in enumerate(items):
        x = dx + 26 + i * (sz + gap)
        s.append(f'<g class="bob" style="animation-delay:{i * .16:.2f}s"><title>{X(ICONS["brand"][slug]["t"])}</title>'
                 + icon("brand:" + slug, x, 36, sz, None, theme, p) + "</g>")
    return doc(W, H, "".join(s), p, fonts=(), css=css, title="Toolbox: " + ", ".join(ICONS["brand"][x]["t"] for x in items))


def contact_title(cfg, p, theme):
    H = 70
    s = [badge(2, 8, 50, "mail", p, theme, p["b"], spin=True),
         f'<text x="64" y="38" font-size="20" font-weight="700" fill="{p["text"]}">Contact</text>',
         f'<text x="64" y="58" font-size="13" fill="{p["muted"]}">{X(cfg.get("contact_note", ""))}</text>']
    return doc(W, H, "".join(s), p, (("RB", 400), ("RB", 700)), title="Contact")


def contact(c, p, theme, i, wide=False):
    w, H = (W if wide else 410), 76
    slug = c["icon"]
    tint = readable("#" + ICONS["brand"][slug]["c"], p, theme) if slug in ICONS["brand"] else p["a"]
    s = [f'<rect width="{w}" height="{H}" rx="22" fill="{p["surface"]}"/>',
         badge(16, 14, 48, "brand:" + slug, p, theme, tint, n=9, amp=.07),
         f'<text x="78" y="34" font-size="16" font-weight="700" fill="{p["text"]}">{X(c["label"])}</text>',
         f'<text x="78" y="55" font-size="13" fill="{p["muted"]}">{X(c["handle"])}</text>',
         f'<circle cx="{w - 36}" cy="38" r="17" fill="{p["c1"]}"/>' + icon("arrow_outward", w - 45, 29, 18, p["muted"])]
    return doc(w, H, f'<g class="in" style="animation-delay:{i * .07:.2f}s">{"".join(s)}</g>', p, (("RB", 400), ("RB", 700)),
               title=f'{c["label"]}: {c["handle"]}')


def button(label, icn, p, theme, primary):
    H = 48
    w = 22 + 20 + 10 + tw(label, 15, 500) + 26
    bg, fg = (p["soft"], p["softink"]) if primary else (p["tonal"], p["tonalink"])
    s = [f'<rect width="{w:.0f}" height="{H}" rx="24" fill="{bg}"/>',
         icon(icn, 22, 14, 20, fg),
         f'<text x="52" y="29.5" font-size="15" font-weight="500" fill="{fg}">{X(label)}</text>']
    return doc(int(w), H, "".join(s), p, (("RB", 500),), title=label)


# ---------------------------------------------------------------- readme
def pic(name, alt, width="100%"):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" width="{width}" alt="{X(alt)}"></picture>')


def link(url, inner):
    return f'<a href="{X(url)}">{inner}</a>'


def build(cfg, D):
    out, readme = {}, []
    P = lambda *a: readme.append("".join(a))

    def put(name, fn):
        for theme in ("dark", "light"):
            out[f"{name}-{theme}.svg"] = fn(PAL[theme], theme)

    put("hero", lambda p, t: banner(cfg, D, p, t))
    put("greet", lambda p, t: greet(cfg, p, t))
    put("about", lambda p, t: about(cfg, D, p, t))
    put("stack", lambda p, t: stack(cfg, D, p, t))
    put("activity", lambda p, t: activity(cfg, D, p, t))
    put("streak", lambda p, t: streak(cfg, D, p, t))
    put("dock", lambda p, t: dock(cfg, D, p, t))
    put("contact", lambda p, t: contact_title(cfg, p, t))

    P('<div align="center">\n\n')
    P(pic("hero", f"{cfg['name']}: {cfg['headline']}"), "\n")
    P(pic("greet", " / ".join(cfg["greetings"])), "\n\n")
    P(pic("about", "About me"), "\n\n")
    P(pic("stack", "Tech stack"), "\n\n")
    cards = []
    for i, it in enumerate(it for it in cfg["projects"] if it["repo"] in D["repo"]):
        key = "project-" + it["repo"].lower()
        put(key, lambda p, t, it=it, i=i: card(it, D, p, t, i))
        cards.append(link(D["repo"][it["repo"]]["url"], pic(key, it.get("title") or it["repo"], "49%")))
    for i in range(0, len(cards), 2):
        P("&nbsp;".join(cards[i:i + 2]), "\n\n")
    P(pic("activity", "GitHub activity"), "\n\n")
    P(pic("streak", "Streak"), "\n\n")
    raw = f"https://raw.githubusercontent.com/{cfg['login']}/{cfg['login']}/output"
    P(f'<picture><source media="(prefers-color-scheme: dark)" srcset="{raw}/snake-dark.svg">'
      f'<img src="{raw}/snake-light.svg" width="100%" alt="A snake eating the contribution graph"></picture>\n\n')
    P(pic("dock", "Toolbox"), "\n\n")
    P(pic("contact", "Contact"), "\n\n")
    contacts = cfg["contacts"]
    pills = []
    for i, c in enumerate(contacts):
        key = f"contact-{c['icon']}"
        wide = c.get("wide", False)
        put(key, lambda p, t, c=c, i=i, wide=wide: contact(c, p, t, i, wide))
        pills.append((wide, link(c["url"], pic(key, f'{c["label"]}: {c["handle"]}', "100%" if wide else "49%"))))
    row = []
    for wide, html_ in pills:
        if wide:
            if row:
                P("&nbsp;".join(row), "\n\n")
                row = []
            P(html_, "\n\n")
            continue
        row.append(html_)
        if len(row) == 2:
            P("&nbsp;".join(row), "\n\n")
            row = []
    if row:
        P("&nbsp;".join(row), "\n\n")
    btns = []
    for i, b in enumerate(cfg["buttons"]):
        put(f"button-{i}", lambda p, t, b=b, i=i: button(b["label"], b["icon"], p, t, i == 0))
        btns.append(link(b["url"], pic(f"button-{i}", b["label"], "auto")))
    P("<br>\n\n", "&nbsp;&nbsp;".join(btns), "\n\n")
    P("</div>\n")
    return out, "".join(readme)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="saved GraphQL response (JSON)")
    ap.add_argument("--print-query", action="store_true")
    args = ap.parse_args()
    if args.print_query:
        print(QUERY)
        return
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    if args.data:
        raw = json.load(open(args.data, encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        raw = gql(QUERY, {"login": cfg["login"]}, token)
    D = digest(raw)
    files, readme = build(cfg, D)
    os.makedirs(ASSETS, exist_ok=True)
    for old in os.listdir(ASSETS):
        if old.endswith(".svg") and old not in files:
            os.remove(os.path.join(ASSETS, old))
    for name, body in files.items():
        with open(os.path.join(ASSETS, name), "w", encoding="utf-8") as fh:
            fh.write(body)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)
    print(f"wrote {len(files)} svgs + README.md")


if __name__ == "__main__":
    main()

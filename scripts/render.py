#!/usr/bin/env python3
"""Renders the profile README and its SVG cards from config.json + live GitHub data.

Theme: a Hyprland session. Every card is a window with the default Hyprland
cyan -> green border, every section opens with a terminal prompt.

Usage:
  python3 scripts/render.py                 # fetch data with $GITHUB_TOKEN
  python3 scripts/render.py --data raw.json # use a saved GraphQL response
  python3 scripts/render.py --print-query   # print the GraphQL query
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
        bg="#0a0d14", surface="#121925", surface2="#1a2333", c1="#1a2333", c2="#233046", border="#243045", text="#dbe3f0",
        muted="#7c89a3", dim="#4a5670", a="#33ccff", b="#00ff99", warn="#ffcb6b", pink="#ff7eb6",
        purple="#b48cff", sky1="#04060c", sky2="#0b1526", moon="#e9f1ff", ink="#05070c",
        graph=["#151b27", "#0b4a5e", "#0d7f9e", "#1fb4d9", "#5ff5c3"],
    ),
    "light": dict(
        bg="#f3f6fa", surface="#eef4fa", surface2="#e1eaf4", c1="#e1eaf4", c2="#d3e0ee", border="#d3dbe7", text="#172033",
        muted="#56627a", dim="#9aa6bb", a="#0a8fd6", b="#0aa46b", warn="#b7791f", pink="#d6336c",
        purple="#7c4ddb", sky1="#d9f0ff", sky2="#f2fff9", moon="#8aa2bf", ink="#ffffff",
        graph=["#e6edf5", "#bfe6f7", "#74c9ee", "#239fdc", "#0aa46b"],
    ),
}

PREVIEW = "*{animation-delay:-40s!important;animation-play-state:paused!important}" if os.environ.get("PREVIEW") else ""
ICONS = json.load(open(os.path.join(HERE, "icons.json")))
FONTS = {}
for _w, _f in ((400, "Regular"), (700, "Bold"), (800, "ExtraBold")):
    with open(os.path.join(HERE, "fonts", f"jbm-{_f}.woff"), "rb") as fh:
        FONTS[_w] = base64.b64encode(fh.read()).decode()


# ---------------------------------------------------------------- helpers
def X(s):
    return html.escape(str(s), quote=True)


def tw(s, fs):
    return len(s) * fs * CW


def wrap(text, maxch, maxlines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if len(nxt) <= maxch:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > maxlines:
        lines = lines[:maxlines]
        lines[-1] = lines[-1][: maxch - 3].rstrip(" ,.:;") + "..."
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


def doc(w, h, body, p, weights=(400, 700), defs="", css="", title=""):
    faces = "".join(
        f"@font-face{{font-family:KM;font-weight:{wt};src:url(data:font/woff;base64,{FONTS[wt]}) format('woff')}}"
        for wt in weights)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{X(title)}">
<title>{X(title)}</title>
<defs>
<linearGradient id="hl" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['a']}"/><stop offset="1" stop-color="{p['b']}"/></linearGradient>
<linearGradient id="hlh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['a']}"/><stop offset="1" stop-color="{p['b']}"/></linearGradient>
{defs}
</defs>
<style>
{faces}
text{{font-family:KM,'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre}}
.in{{animation:in .7s cubic-bezier(.2,.8,.2,1) both}}
@keyframes in{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.fade{{animation:fade .6s ease-out both}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
.blink{{animation:bl 1.1s steps(1) infinite}}
@keyframes bl{{50%{{opacity:0}}}}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
{PREVIEW}
</style>
{body}
</svg>
"""


def frame(w, h, p, left, right="", left_icon="terminal"):
    """A Hyprland window: rounded, gradient border, slim title row."""
    s = [f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="{p["surface"]}" stroke="url(#hl)" stroke-width="2"/>',
         icon(left_icon, 16, 13, 15, p["a"]),
         f'<text x="38" y="25" font-size="12.5" fill="{p["muted"]}">{X(left)}</text>']
    if right:
        s.append(f'<text x="{w - 18}" y="25" font-size="12.5" fill="{p["dim"]}" text-anchor="end">{X(right)}</text>')
    s.append(f'<line x1="14" y1="37.5" x2="{w - 14}" y2="37.5" stroke="{p["border"]}"/>')
    return "".join(s)


def box(x, y, w, h, title, p):
    tl = tw(title, 12.5) + 14
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{p["border"]}" stroke-width="1.2"/>'
            f'<rect x="{x + 12}" y="{y - 8}" width="{tl}" height="16" fill="{p["surface"]}"/>'
            f'<text x="{x + 19}" y="{y + 4.5}" font-size="12.5" font-weight="700" fill="{p["a"]}">{X(title)}</text>')


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
    # streaks
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
        since=u["createdAt"][:4],
        contributions=u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        days=days,
        streak=cur,
        longest=longest,
        languages=[(n, s / total * 100, colors.get(n)) for n, s in top],
        repo={r["name"]: r for r in nodes},
        today=today,
    )


def fetch_avatar(login):
    try:
        with urllib.request.urlopen(f"https://github.com/{login}.png?size=300", timeout=30) as r:
            mime = r.headers.get("content-type", "image/png").split(";")[0]
            return f"data:{mime};base64,{base64.b64encode(r.read()).decode()}"
    except Exception:
        return None



# ---------------------------------------------------------------- cards
# Calm layout: tonal surfaces, no borders, soft scalloped shapes, slow motion.
SOFT = """.flo{animation:flo 4.5s ease-in-out infinite}
@keyframes flo{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
.rot{animation:rot 24s linear infinite;transform-box:fill-box;transform-origin:center}
@keyframes rot{to{transform:rotate(360deg)}}"""


def wave(amp, period, base, width, height, phase=0.0):
    pts = []
    for x in range(0, int(width) + 1, 8):
        y = base + amp * math.sin((x / period) * 2 * math.pi + phase) + amp * 0.35 * math.sin((x / period) * 4 * math.pi + phase * 2)
        pts.append(f"{x},{y:.1f}")
    return f"M0,{height} L" + " L".join(pts) + f" L{int(width)},{height} Z"


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
    isz = size * 0.48
    fg = p["ink"] if solid else (None if name.startswith("brand:") else tint)
    return shape + icon(name, x + (size - isz) / 2, y + (size - isz) / 2, isz, fg, theme, p)


def shell(w, h, p, title=None, ic=None, theme=None, tint=None):
    s = [f'<rect width="{w}" height="{h}" rx="24" fill="{p["surface"]}"/>']
    if title:
        s.append(badge(24, 22, 38, ic, p, theme, tint or p["a"], spin=True)
                 + f'<text x="74" y="47" font-size="19" font-weight="800" fill="{p["text"]}">{X(title)}</text>')
    return "".join(s)


def ascii_art(p, theme, x, y):
    """fastfetch-style ASCII logo (scripts/art.txt) painted into the sky.

    Lines fade in one by one, the bottom dissolves into the waves, and a light
    band sweeps through the glyphs only (the text itself is the clip path).
    """
    lines = open(os.path.join(HERE, "art.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
    fs, lh = 10.5, 12
    cols = max(len(l) for l in lines)
    aw, ah = cols * fs * CW, len(lines) * lh
    tw_, th_ = 250, 250
    ox, oy = x + (tw_ - aw) / 2, y + (th_ - ah) / 2
    rows = [f'<text x="{ox:.1f}" y="{oy + (i + 1) * lh - 2:.1f}" font-size="{fs}" font-weight="700">{X(l)}</text>'
            for i, l in enumerate(lines)]
    out = [f'<linearGradient id="artG" gradientUnits="userSpaceOnUse" x1="0" y1="{oy}" x2="0" y2="{oy + ah}">'
           f'<stop offset="0" stop-color="{p["a"]}"/><stop offset="1" stop-color="{p["b"]}"/></linearGradient>',
           f'<linearGradient id="artFadeG" x1="0" y1="0" x2="0" y2="1"><stop offset=".55" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
           f'<mask id="artFade"><rect x="{x}" y="{oy}" width="{tw_}" height="{ah + 4:.0f}" fill="url(#artFadeG)"/></mask>',
           f'<clipPath id="asc">{"".join(rows)}</clipPath>',
           f'<radialGradient id="artGlow"><stop offset="0" stop-color="{p["a"]}" stop-opacity=".18"/><stop offset="1" stop-color="{p["a"]}" stop-opacity="0"/></radialGradient>',
           f'<ellipse cx="{ox + aw / 2:.0f}" cy="{oy + ah * .55:.0f}" rx="{aw * .75:.0f}" ry="{ah * .6:.0f}" fill="url(#artGlow)"/>',
           f'<g mask="url(#artFade)" opacity="{.85 if theme == "dark" else .9}">']
    for i, r in enumerate(rows):
        out.append(r.replace("<text ", f'<text class="row" style="animation-delay:{.2 + i * .06:.2f}s" fill="url(#artG)" ', 1))
    out.append(f'<g clip-path="url(#asc)"><rect class="scan" x="{x}" y="{y - 30}" width="{tw_}" height="26" fill="url(#scanG)"/></g></g>')
    return "".join(out)


def banner(cfg, D, p, theme, avatar):
    H = 270
    rnd = random.Random(1923)
    P = 280  # wave period: the tile scrolls by exactly one period, so the loop is seamless
    defs = f"""<clipPath id="bc"><rect width="{W}" height="{H}" rx="24"/></clipPath>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p['sky1']}"/><stop offset="1" stop-color="{p['sky2']}"/></linearGradient>
<radialGradient id="glow"><stop offset="0" stop-color="{p['a']}" stop-opacity=".35"/><stop offset="1" stop-color="{p['a']}" stop-opacity="0"/></radialGradient>
<mask id="cres"><rect width="{W}" height="{H}" fill="#fff"/><circle cx="{W - 70 + 9}" cy="{58 - 6}" r="19" fill="#000"/></mask>
<linearGradient id="scanG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p['a']}" stop-opacity="0"/><stop offset=".7" stop-color="#ffffff" stop-opacity=".25"/><stop offset="1" stop-color="#ffffff" stop-opacity=".9"/></linearGradient>"""
    css = SOFT + f"""
.tw{{animation:tw 3.2s ease-in-out infinite}}
@keyframes tw{{0%,100%{{opacity:.15}}50%{{opacity:1}}}}
.w1{{animation:wv 18s linear infinite}}.w2{{animation:wv 27s linear infinite}}.w3{{animation:wv 39s linear infinite reverse}}
@keyframes wv{{to{{transform:translateX(-{P}px)}}}}
.slow{{animation:rot 40s linear infinite;transform-box:fill-box;transform-origin:center}}
.back{{animation:rot 60s linear infinite reverse;transform-box:fill-box;transform-origin:center}}
.row{{animation:row .5s ease-out both}}
@keyframes row{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
.scan{{animation:scan 6s cubic-bezier(.5,0,.5,1) 2s infinite}}
@keyframes scan{{from{{transform:translateY(0)}}to{{transform:translateY(300px)}}}}
"""
    s = [f'<g clip-path="url(#bc)"><rect width="{W}" height="{H}" fill="url(#sky)"/>']
    for _ in range(46 if theme == "dark" else 24):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, 160), rnd.uniform(0.5, 1.5)
        col = p["moon"] if theme == "dark" else p["a"]
        s.append(f'<circle class="tw" cx="{x:.0f}" cy="{y:.0f}" r="{r:.2f}" fill="{col}" style="animation-delay:-{rnd.uniform(0, 3.2):.2f}s"/>')
    # soft shapes drifting in the corner
    s.append(f'<g class="flo" style="animation-duration:7s"><path class="slow" d="{cookie(W - 40, H + 6, 92, 12, 0.09)}" fill="{p["a"]}" opacity=".16"/></g>')
    s.append(f'<g class="flo" style="animation-duration:9s;animation-delay:-3s"><path class="back" d="{cookie(W - 168, H - 6, 46, 6, 0.14)}" fill="{p["b"]}" opacity=".18"/></g>')
    s.append(f'<circle cx="{W - 70}" cy="58" r="60" fill="url(#glow)"/>')
    s.append(f'<circle cx="{W - 70}" cy="58" r="19" fill="{p["moon"]}" mask="url(#cres)"/>')
    span = W + P
    s.append(ascii_art(p, theme, 18, 10))  # behind the waves, so it sinks into them
    s.append(f'<g class="w3" opacity=".10"><path d="{wave(12, P, 214, span, H, 1.3)}" fill="url(#hlh)"/></g>')
    s.append(f'<g class="w2" opacity=".16"><path d="{wave(9, P, 232, span, H, 0.4)}" fill="url(#hlh)"/></g>')
    s.append(f'<g class="w1" opacity=".24"><path d="{wave(7, P, 248, span, H, 2.2)}" fill="url(#hlh)"/></g>')
    s.append("</g>")
    # name + rotating line
    x0 = 290
    s.append(f'<g class="in" style="animation-delay:.1s"><text x="{x0}" y="86" font-size="18" fill="{p["muted"]}">{X(cfg["greeting"])}</text></g>')
    s.append(f'<g class="in" style="animation-delay:.25s"><text x="{x0 - 3}" y="146" font-size="58" font-weight="800" fill="url(#hlh)" letter-spacing="-1">{X(cfg["name"])}</text></g>')
    lines, fs, ty = cfg["roles"], 16, 182
    ids = [f"r{i}" for i in range(len(lines))]
    for i, line in enumerate(lines):
        width = tw(line, fs)
        type_t, hold, erase = len(line) * 0.055, 3.0, 0.5
        dur = type_t + hold + erase
        k1, k2 = type_t / dur, (type_t + hold) / dur
        begin = f"1s;{ids[-1]}.end" if i == 0 else f"{ids[i - 1]}.end"
        s.append(f'<clipPath id="rc{i}"><rect x="{x0 - 2}" y="{ty - 20}" width="0" height="30">'
                 f'<animate id="{ids[i]}" attributeName="width" begin="{begin}" dur="{dur:.2f}s" values="0;{width + 4:.1f};{width + 4:.1f};0" keyTimes="0;{k1:.3f};{k2:.3f};1"/>'
                 f'</rect></clipPath>')
        s.append(f'<g clip-path="url(#rc{i})"><text x="{x0}" y="{ty}" font-size="{fs}" fill="{p["text"]}">{X(line)}</text></g>')
        s.append(f'<rect x="{x0}" y="{ty - 15}" width="2.5" height="20" rx="1.2" fill="{p["b"]}" opacity="0">'
                 f'<set attributeName="opacity" to="1" begin="{ids[i]}.begin" end="{ids[i]}.end"/>'
                 f'<animate attributeName="x" begin="{ids[i]}.begin" dur="{dur:.2f}s" values="{x0};{x0 + width + 4:.1f};{x0 + width + 4:.1f};{x0}" keyTimes="0;{k1:.3f};{k2:.3f};1"/></rect>')
    cx = x0
    for i, c in enumerate(cfg["chips"]):
        cw = 12 + 16 + 8 + tw(c["label"], 12.5) + 14
        s.append(f'<g class="in" style="animation-delay:{.5 + i * .08:.2f}s">'
                 f'<rect x="{cx}" y="204" width="{cw:.0f}" height="30" rx="10" fill="{p["c1"]}" fill-opacity=".9"/>'
                 + icon(c["icon"], cx + 12, 211, 16, p["a"] if not c["icon"].startswith("brand:") else None, theme, p)
                 + f'<text x="{cx + 36}" y="223.5" font-size="12.5" fill="{p["text"]}">{X(c["label"])}</text></g>')
        cx += cw + 8
    return doc(W, H, "".join(s), p, (400, 700, 800), defs, css, f"{cfg['name']}: " + " / ".join(lines))


def about(cfg, D, p, theme):
    items = cfg["about"]
    rows = math.ceil(len(items) / 2)
    H = 80 + rows * 52 + 14
    cw = (W - 48 - 10) / 2
    tints = [p["a"], p["b"], p["purple"], p["pink"]]
    s = [shell(W, H, p, "about me", "favorite", theme, p["pink"])]
    for i, it in enumerate(items):
        x = 24 + (i % 2) * (cw + 10)
        y = 80 + (i // 2) * 52
        s.append(f'<g class="in" style="animation-delay:{.08 * i:.2f}s">'
                 f'<rect x="{x:.0f}" y="{y}" width="{cw:.0f}" height="42" rx="14" fill="{p["c1"]}"/>'
                 + badge(x + 9, y + 6, 30, it["icon"], p, theme, tints[i % 4], n=6, amp=.1)
                 + f'<text x="{x + 50:.0f}" y="{y + 26}" font-size="13.5" fill="{p["text"]}">{X(it["label"])}</text></g>')
    return doc(W, H, "".join(s), p, (400, 700, 800), css=SOFT, title="About me: " + ", ".join(i["label"] for i in items))


def stack(cfg, D, p, theme):
    groups = cfg["stack"]
    H = 80 + len(groups) * 64 + 6
    s = [shell(W, H, p, "tech stack", "code", theme, p["a"])]
    y, k = 84, 0
    for g in groups:
        s.append(f'<text x="26" y="{y}" font-size="11" font-weight="700" fill="{p["muted"]}" letter-spacing="2">{X(g["title"].upper())}</text>')
        x = 24
        for slug, label in g["items"]:
            iw = 12 + 16 + 9 + tw(label, 13) + 14
            s.append(f'<g class="in" style="animation-delay:{k * .04:.2f}s"><g class="flo" style="animation-delay:-{k * .45:.2f}s">'
                     f'<rect x="{x:.0f}" y="{y + 10}" width="{iw:.0f}" height="34" rx="12" fill="{p["c1"]}"/>'
                     + icon("brand:" + slug, x + 12, y + 19, 16, None, theme, p)
                     + f'<text x="{x + 37:.0f}" y="{y + 31.5}" font-size="13" fill="{p["text"]}">{X(label)}</text></g></g>')
            x += iw + 8
            k += 1
        y += 64
    title = "; ".join(g["title"] + ": " + ", ".join(l for _, l in g["items"]) for g in groups)
    return doc(W, H, "".join(s), p, (400, 700, 800), css=SOFT, title="Tech stack: " + title)


def card(item, D, p, theme, i):
    w, H = 410, 182
    r = D["repo"][item["repo"]]
    name = item.get("title") or r["name"]
    lang = item.get("lang") or (r["primaryLanguage"] or {}).get("name")
    tints = [p["a"], p["b"], p["purple"], p["pink"]]
    s = [shell(w, H, p)]
    s.append(badge(22, 20, 46, item["icon"], p, theme, tints[i % 4], n=9, amp=.07, spin=True))
    s.append(f'<circle cx="{w - 38}" cy="38" r="16" fill="{p["c1"]}"/>' + icon("arrow_outward", w - 47, 29, 18, p["muted"]))
    s.append(f'<text x="24" y="98" font-size="17" font-weight="800" fill="{p["text"]}">{X(name)}</text>')
    for li, ln in enumerate(wrap(item["text"], int((w - 48) / (12.5 * CW)), 2)):
        s.append(f'<text x="24" y="{121 + li * 18}" font-size="12.5" fill="{p["muted"]}">{X(ln)}</text>')
    y = H - 30
    if lang:
        lw = tw(lang, 11.5) + 20
        s.append(f'<rect x="24" y="{y - 4}" width="{lw:.0f}" height="22" rx="8" fill="{p["c1"]}"/>'
                 f'<text x="34" y="{y + 11}" font-size="11.5" fill="{p["text"]}">{X(lang)}</text>')
    st = str(r["stargazerCount"])
    s.append(f'<text x="{w - 24}" y="{y + 11}" font-size="13" font-weight="700" fill="{p["text"]}" text-anchor="end">{st}</text>')
    s.append(icon("star", w - 24 - tw(st, 13) - 20, y - 2, 16, p["warn"]))
    return doc(w, H, f'<g class="in" style="animation-delay:{i * .1:.1f}s">{"".join(s)}</g>', p, (400, 700, 800), css=SOFT,
               title=f"{name}: {item['text']}")


def activity(cfg, D, p, theme):
    H = 322
    s = [shell(W, H, p, "github activity", "monitoring", theme, p["a"])]
    stats = [("star", D["stars"], "stars earned", p["warn"]),
             ("commit", D["contributions"], "contributions this year", p["a"]),
             ("book_2", D["repos"], "public repos", p["b"]),
             ("group", D["followers"], "followers", p["purple"])]
    tw_, th_ = 196, 76
    for i, (ic, val, label, c) in enumerate(stats):
        x = 24 + (i % 2) * (tw_ + 10)
        y = 76 + (i // 2) * (th_ + 10)
        s.append(f'<g class="in" style="animation-delay:{i * .08:.2f}s">'
                 f'<rect x="{x}" y="{y}" width="{tw_}" height="{th_}" rx="16" fill="{p["c1"]}"/>'
                 + badge(x + 12, y + 10, 32, ic, p, theme, c, n=8, amp=.09)
                 + f'<text x="{x + 52}" y="{y + 34}" font-size="22" font-weight="800" fill="{p["text"]}">{X(val)}</text>'
                 f'<text x="{x + 14}" y="{y + 62}" font-size="11.5" fill="{p["muted"]}">{X(label)}</text></g>')
    # last three calendar weeks, future days dashed
    cx0 = 24 + 2 * tw_ + 10 + 22
    byd = {d["date"]: d for d in D["days"]}
    end = dt.date.fromisoformat(D["today"])
    start = end - dt.timedelta(days=(end.weekday() + 1) % 7 + 14)  # Sunday, two weeks back
    slots = []
    for k in range(21):
        day = start + dt.timedelta(days=k)
        slots.append(byd.get(day.isoformat()) if day <= end else None)
    s.append(f'<text x="{cx0}" y="86" font-size="12" font-weight="700" fill="{p["text"]}">last 21 days</text>')
    cell, gap, hh = 46, 6, 40
    for wd, ch in enumerate("SMTWTFS"):
        s.append(f'<text x="{cx0 + wd * (cell + gap) + cell / 2}" y="108" font-size="11" fill="{p["dim"]}" text-anchor="middle">{ch}</text>')
    mx = max([d["contributionCount"] for d in slots if d] + [1])
    for k, d in enumerate(slots):
        x = cx0 + (k % 7) * (cell + gap)
        y = 118 + (k // 7) * (hh + gap)
        if d is None:
            s.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{hh}" rx="12" fill="none" stroke="{p["c2"]}" stroke-dasharray="4 4"/>')
            continue
        c = d["contributionCount"]
        lv = 0 if c == 0 else min(4, 1 + int(math.sqrt(c / mx) * 3.999))
        fill = p["c2"] if lv == 0 else mix(p["c2"], p["a"] if lv < 4 else p["b"], .3 + lv * .17)
        today = d["date"] == D["today"]
        ring = f' stroke="{p["b"]}" stroke-width="2"' if today else ""
        fg = p["ink"] if lv >= 3 else p["text"]
        s.append(f'<g class="in" style="animation-delay:{.2 + k * .03:.2f}s"><rect x="{x}" y="{y}" width="{cell}" height="{hh}" rx="12" fill="{fill}"{ring}/>'
                 f'<text x="{x + cell / 2}" y="{y + hh / 2 + 4.5:.0f}" font-size="12.5" fill="{fg}" text-anchor="middle">{int(d["date"][8:])}</text></g>')
    # languages: rounded pills with little gaps, growing in
    langs = D["languages"][:6]
    tot = sum(v for _, v, _ in langs) or 1
    by, bw = 270, W - 48
    s.append(f'<text x="24" y="{by - 12}" font-size="12" font-weight="700" fill="{p["text"]}">languages across my repositories</text>')
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
        s.append(f'<g class="in" style="animation-delay:{.7 + i * .07:.2f}s"><circle cx="{x + 4}" cy="{by + 26}" r="4" fill="{readable(c, p, theme)}"/>'
                 f'<text x="{x + 13}" y="{by + 30}" font-size="11.5" fill="{p["muted"]}">{X(lab)}</text></g>')
        x += tw(lab, 11.5) + 30
    return doc(W, H, "".join(s), p, (400, 700, 800), css=SOFT,
               title="GitHub activity: " + ", ".join(f"{l}: {v}" for _, v, l, _ in stats))


def streak(cfg, D, p, theme):
    H = 172
    css = SOFT + """
.fire{animation:fire 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:50% 90%}
@keyframes fire{0%,100%{transform:scale(1)}50%{transform:scale(1.07,1.13)}}"""
    s = [shell(W, H, p, "streak", "local_fire_department", theme, p["pink"])]
    hw = (W - 48 - 10) / 2
    for i, (val, label, ic, hot) in enumerate([(D["streak"], "current streak", "local_fire_department", True),
                                                (D["longest"], "longest this year", "trophy", False)]):
        x = 24 + i * (hw + 10)
        fill = "url(#hl)" if hot else p["c1"]
        fg, sub = (p["ink"], p["ink"]) if hot else (p["text"], p["muted"])
        s.append(f'<g class="in" style="animation-delay:{i * .1:.1f}s"><rect x="{x:.0f}" y="76" width="{hw:.0f}" height="74" rx="18" fill="{fill}"/>')
        b = badge(x + 16, 89, 48, ic, p, theme, p["ink"] if hot else p["warn"], n=12, amp=.08, spin=True)
        s.append(f'<g class="fire">{b}</g>' if hot else b)
        s.append(f'<text x="{x + 78:.0f}" y="117" font-size="28" font-weight="800" fill="{fg}">{val}'
                 f'<tspan font-size="13" font-weight="700" fill="{sub}"> days</tspan></text>'
                 f'<text x="{x + 78:.0f}" y="136" font-size="12" fill="{sub}" opacity=".85">{label}</text></g>')
    return doc(W, H, "".join(s), p, (400, 700, 800), css=css,
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
    return doc(W, H, "".join(s), p, weights=(), css=css, title="Toolbox: " + ", ".join(ICONS["brand"][x]["t"] for x in items))


def button(label, icn, p, theme, filled):
    H = 42
    w = 18 + 18 + 10 + tw(label, 13.5) + 20
    bg = "url(#hlh)" if filled else p["surface"]
    fg = p["ink"] if filled else p["text"]
    s = [f'<rect width="{w:.0f}" height="{H}" rx="21" fill="{bg}"/>',
         icon(icn, 18, 12, 18, fg if filled else p["a"]),
         f'<text x="46" y="26" font-size="13.5" font-weight="700" fill="{fg}">{X(label)}</text>']
    return doc(int(w), H, "".join(s), p, title=label)


def social(slug, p, theme):
    S = 42
    s = [f'<rect width="{S}" height="{S}" rx="21" fill="{p["surface"]}"/>', icon("brand:" + slug, 12, 12, 18, None, theme, p)]
    return doc(S, S, "".join(s), p, weights=(), title=ICONS["brand"][slug]["t"])


# ---------------------------------------------------------------- readme
def pic(name, alt, width="100%"):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" width="{width}" alt="{X(alt)}"></picture>')


def link(url, inner):
    return f'<a href="{X(url)}">{inner}</a>'


def build(cfg, D, avatar):
    out, readme = {}, []
    P = lambda *a: readme.append("".join(a))

    def put(name, fn):
        for theme in ("dark", "light"):
            out[f"{name}-{theme}.svg"] = fn(PAL[theme], theme)

    put("hero", lambda p, t: banner(cfg, D, p, t, avatar))
    put("about", lambda p, t: about(cfg, D, p, t))
    put("stack", lambda p, t: stack(cfg, D, p, t))
    put("activity", lambda p, t: activity(cfg, D, p, t))
    put("streak", lambda p, t: streak(cfg, D, p, t))
    put("dock", lambda p, t: dock(cfg, D, p, t))

    P('<div align="center">\n\n')
    P(pic("hero", f"{cfg['name']}: " + " / ".join(cfg["roles"])), "\n\n")
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
    row = []
    for i, b in enumerate(cfg["buttons"]):
        put(f"button-{i}", lambda p, t, b=b, i=i: button(b["label"], b["icon"], p, t, i == 0))
        row.append(link(b["url"], pic(f"button-{i}", b["label"], "auto")))
    for so in cfg["socials"]:
        put(f"social-{so['icon']}", lambda p, t, so=so: social(so["icon"], p, t))
        row.append(link(so["url"], pic(f"social-{so['icon']}", so["icon"], "auto")))
    P("&nbsp;".join(row), "\n\n")
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
    files, readme = build(cfg, D, None)
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

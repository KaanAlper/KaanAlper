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
        bg="#0a0d14", surface="#0f131c", surface2="#161c28", border="#243045", text="#dbe3f0",
        muted="#7c89a3", dim="#4a5670", a="#33ccff", b="#00ff99", warn="#ffcb6b", pink="#ff7eb6",
        purple="#b48cff", sky1="#04060c", sky2="#0b1526", moon="#e9f1ff", ink="#05070c",
        graph=["#151b27", "#0b4a5e", "#0d7f9e", "#1fb4d9", "#5ff5c3"],
    ),
    "light": dict(
        bg="#f3f6fa", surface="#ffffff", surface2="#eef3f9", border="#d3dbe7", text="#172033",
        muted="#56627a", dim="#9aa6bb", a="#0a8fd6", b="#0aa46b", warn="#b7791f", pink="#d6336c",
        purple="#7c4ddb", sky1="#d9f0ff", sky2="#f2fff9", moon="#8aa2bf", ink="#ffffff",
        graph=["#e6edf5", "#bfe6f7", "#74c9ee", "#239fdc", "#0aa46b"],
    ),
}

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
def wave(amp, period, base, width, height, phase=0.0, line=False):
    pts = []
    for x in range(0, int(width) + 1, 8):
        y = base + amp * math.sin((x / period) * 2 * math.pi + phase) + amp * 0.35 * math.sin((x / period) * 4 * math.pi + phase * 2)
        pts.append(f"{x},{y:.1f}")
    if line:
        return "M" + " L".join(pts)
    return f"M0,{height} L" + " L".join(pts) + f" L{int(width)},{height} Z"


def banner(cfg, D, p, theme, avatar):
    H = 300
    rnd = random.Random(1923)
    P = 280  # wave period: the tile scrolls by exactly one period, so the loop is seamless
    defs = f"""<clipPath id="bc"><rect width="{W}" height="{H}" rx="18"/></clipPath>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p['sky1']}"/><stop offset="1" stop-color="{p['sky2']}"/></linearGradient>
<radialGradient id="glow"><stop offset="0" stop-color="{p['a']}" stop-opacity=".35"/><stop offset="1" stop-color="{p['a']}" stop-opacity="0"/></radialGradient>
<mask id="cres"><rect width="{W}" height="{H}" fill="#fff"/><circle cx="{W - 66 + 9}" cy="{56 - 6}" r="19" fill="#000"/></mask>
<clipPath id="av"><rect x="-70" y="-92" width="140" height="140" rx="12"/></clipPath>"""
    css = f"""
.tw{{animation:tw 3.2s ease-in-out infinite}}
@keyframes tw{{0%,100%{{opacity:.15}}50%{{opacity:1}}}}
.w1{{animation:wv 18s linear infinite}}.w2{{animation:wv 27s linear infinite}}.w3{{animation:wv 39s linear infinite reverse}}
@keyframes wv{{to{{transform:translateX(-{P}px)}}}}
.fl{{animation:fl 6s ease-in-out infinite}}
@keyframes fl{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-6px)}}}}
"""
    s = [f'<g clip-path="url(#bc)"><rect width="{W}" height="{H}" fill="url(#sky)"/>']
    # stars
    for _ in range(56 if theme == "dark" else 30):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, 190), rnd.uniform(0.5, 1.5)
        col = p["moon"] if theme == "dark" else p["a"]
        s.append(f'<circle class="tw" cx="{x:.0f}" cy="{y:.0f}" r="{r:.2f}" fill="{col}" style="animation-delay:-{rnd.uniform(0, 3.2):.2f}s"/>')
    # moon: the wolf's moon, a nod to the Asena projects
    s.append(f'<circle cx="{W - 66}" cy="56" r="60" fill="url(#glow)"/>')
    s.append(f'<circle cx="{W - 66}" cy="56" r="19" fill="{p["moon"]}" mask="url(#cres)"/>')
    # aurora waves
    span = W + P
    s.append(f'<g class="w3" opacity=".16"><path d="{wave(14, P, 214, span, H, 1.3)}" fill="url(#hlh)"/></g>')
    s.append(f'<g class="w2" opacity=".24"><path d="{wave(11, P, 236, span, H, 0.4)}" fill="url(#hlh)"/></g>')
    s.append(f'<g class="w1" opacity=".38"><path d="{wave(8, P, 258, span, H, 2.2)}" fill="url(#hlh)"/></g>')
    s.append(f'<g class="w1"><path d="{wave(8, P, 258, span, H, 2.2, line=True)}" fill="none" stroke="url(#hlh)" stroke-width="1.5" opacity=".8"/></g>')
    s.append("</g>")
    s.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="{p["border"]}"/>')
    # stacked window cards with the avatar
    s.append(f'<g transform="translate(142 150) rotate(-9)"><rect x="-78" y="-100" width="156" height="200" rx="14" fill="{p["surface2"]}" stroke="{p["border"]}" stroke-width="1.5"/>'
             + "".join(f'<rect x="-60" y="{-78 + i * 16}" width="{rnd.choice([60, 84, 100, 116])}" height="6" rx="3" fill="{p["border"]}"/>' for i in range(9))
             + "</g>")
    s.append(f'<g transform="translate(150 150) rotate(4)"><g class="fl">'
             f'<rect x="-84" y="-106" width="168" height="212" rx="14" fill="{p["surface"]}" stroke="url(#hl)" stroke-width="2.5"/>')
    if avatar:
        s.append(f'<image href="{avatar}" x="-70" y="-92" width="140" height="140" clip-path="url(#av)" preserveAspectRatio="xMidYMid slice"/>')
    else:
        s.append(f'<rect x="-70" y="-92" width="140" height="140" rx="12" fill="url(#hl)"/>')
    s.append(f'<text x="0" y="72" font-size="14" font-weight="700" fill="{p["text"]}" text-anchor="middle">@{X(cfg["login"])}</text>'
             f'<circle cx="-30" cy="89" r="3.5" fill="{p["b"]}"/>'
             f'<text x="-21" y="93" font-size="11.5" fill="{p["muted"]}">online</text>'
             f'</g></g>')
    # text block
    x0 = 304
    s.append(f'<g class="in" style="animation-delay:.1s"><text x="{x0}" y="88" font-size="19" fill="{p["muted"]}"><tspan fill="{p["a"]}" font-weight="700">&#x276F; </tspan>{X(cfg["greeting"])}</text></g>')
    s.append(f'<g class="in" style="animation-delay:.25s"><text x="{x0 - 3}" y="152" font-size="62" font-weight="800" fill="url(#hlh)" letter-spacing="-1">{X(cfg["name"])}</text></g>')
    for i, line in enumerate(cfg["tagline"]):
        s.append(f'<g class="in" style="animation-delay:{.4 + i * .1:.2f}s"><text x="{x0}" y="{190 + i * 23}" font-size="15.5" fill="{p["text"]}">{X(line)}</text></g>')
    cx = x0
    for i, c in enumerate(cfg["chips"]):
        cw = 12 + 16 + 8 + tw(c["label"], 12.5) + 14
        s.append(f'<g class="in" style="animation-delay:{.65 + i * .08:.2f}s">'
                 f'<rect x="{cx}" y="240" width="{cw:.0f}" height="30" rx="15" fill="{p["surface"]}" fill-opacity=".82" stroke="{p["border"]}"/>'
                 + icon(c["icon"], cx + 12, 247, 16, p["a"] if not c["icon"].startswith("brand:") else None, theme, p)
                 + f'<text x="{cx + 36}" y="259.5" font-size="12.5" fill="{p["text"]}">{X(c["label"])}</text></g>')
        cx += cw + 8
    return doc(W, H, "".join(s), p, (400, 700, 800), defs, css, f"{cfg['name']} - {' '.join(cfg['tagline'])}")


def typing(cfg, D, p, theme):
    H, fs = 58, 21
    lines = cfg["typing"]
    s, ids = [], [f"t{i}" for i in range(len(lines))]
    for i, line in enumerate(lines):
        full = "❯ " + line
        width = tw(full, fs)
        x = (W - width) / 2
        type_t, hold, erase = len(full) * 0.065, 2.6, 0.55
        dur = type_t + hold + erase
        k1, k2 = type_t / dur, (type_t + hold) / dur
        begin = f"0s;{ids[-1]}.end" if i == 0 else f"{ids[i - 1]}.end"
        s.append(f'<clipPath id="c{i}"><rect x="{x - 2:.1f}" y="0" width="0" height="{H}">'
                 f'<animate id="{ids[i]}" attributeName="width" begin="{begin}" dur="{dur:.2f}s" values="0;{width + 4:.1f};{width + 4:.1f};0" keyTimes="0;{k1:.3f};{k2:.3f};1"/>'
                 f'</rect></clipPath>')
        s.append(f'<g clip-path="url(#c{i})"><text x="{x:.1f}" y="37" font-size="{fs}" font-weight="700" fill="{p["text"]}">'
                 f'<tspan fill="{p["a"]}">❯</tspan> {X(line)}</text></g>')
        s.append(f'<rect x="{x:.1f}" y="18" width="11" height="25" rx="2" fill="{p["b"]}" opacity="0">'
                 f'<set attributeName="opacity" to="1" begin="{ids[i]}.begin" end="{ids[i]}.end"/>'
                 f'<animate attributeName="x" begin="{ids[i]}.begin" dur="{dur:.2f}s" values="{x:.1f};{x + width + 3:.1f};{x + width + 3:.1f};{x:.1f}" keyTimes="0;{k1:.3f};{k2:.3f};1"/></rect>')
    return doc(W, H, "".join(s), p, (700,), title=" / ".join(lines))


def prompt(cmd, p, theme, path="~/github"):
    H = 44
    s = []
    u = "kaan@arch"
    w1 = 12 + 15 + 7 + tw(u, 13) + 12
    s.append(f'<rect x="0" y="8" width="{w1:.0f}" height="28" rx="8" fill="url(#hlh)"/>'
             + icon("brand:archlinux", 11, 14.5, 15, p["ink"])
             + f'<text x="34" y="27" font-size="13" font-weight="700" fill="{p["ink"]}">{u}</text>')
    x = w1 + 6
    w2 = tw(path, 13) + 24
    s.append(f'<rect x="{x:.0f}" y="8" width="{w2:.0f}" height="28" rx="8" fill="{p["surface2"]}" stroke="{p["border"]}"/>'
             f'<text x="{x + 12:.0f}" y="27" font-size="13" fill="{p["muted"]}">{X(path)}</text>')
    x += w2 + 12
    s.append(f'<text x="{x:.0f}" y="27.5" font-size="15" font-weight="700" fill="{p["b"]}">❯</text>')
    x += 18
    cw = tw(cmd, 14)
    dur = max(0.6, len(cmd) * 0.045)
    s.append(f'<clipPath id="cc"><rect x="{x - 1:.0f}" y="0" width="0" height="{H}">'
             f'<animate attributeName="width" begin=".35s" dur="{dur:.2f}s" from="0" to="{cw + 3:.0f}" fill="freeze"/></rect></clipPath>')
    s.append(f'<g clip-path="url(#cc)"><text x="{x:.0f}" y="27.5" font-size="14" fill="{p["text"]}">{X(cmd)}</text></g>')
    s.append(f'<rect class="blink" x="{x:.0f}" y="13" width="9" height="19" rx="1.5" fill="{p["a"]}">'
             f'<animate attributeName="x" begin=".35s" dur="{dur:.2f}s" from="{x:.0f}" to="{x + cw + 3:.0f}" fill="freeze"/></rect>')
    return doc(W, H, "".join(s), p, (400, 700), title=f"{u} {path} > {cmd}")


def fetch(cfg, D, p, theme):
    f = cfg["fetch"]
    rows = [(k, v.format(**D)) for k, v in f["rows"]]
    y0, lh = 74, 22
    H = y0 + (len(rows) + 2) * lh + 44
    s = [frame(W, H, p, "fastfetch", "kitty")]
    # distro logo, fastfetch style
    s.append(f'<g class="fade">{icon("brand:hyprland", 50, (H - 170) / 2 + 14, 160, "url(#hl)")}</g>')
    kx, vx = 262, 262 + 10 * 8.4
    s.append(f'<text x="{kx}" y="{y0}" font-size="15" font-weight="700"><tspan fill="{p["a"]}">{X(f["user"])}</tspan>'
             f'<tspan fill="{p["text"]}">@</tspan><tspan fill="{p["b"]}">{X(f["host"])}</tspan></text>')
    s.append(f'<text x="{kx}" y="{y0 + lh}" font-size="14" fill="{p["dim"]}">{"-" * (len(f["user"]) + len(f["host"]) + 1)}</text>')
    for i, (k, v) in enumerate(rows):
        y = y0 + (i + 2) * lh
        s.append(f'<g class="in" style="animation-delay:{.05 * i:.2f}s"><text x="{kx}" y="{y}" font-size="14" font-weight="700" fill="{p["a"]}">{X(k)}</text>'
                 f'<text x="{vx:.0f}" y="{y}" font-size="14" fill="{p["text"]}">{X(v)}</text></g>')
    yb = y0 + (len(rows) + 2) * lh - 8
    for i, c in enumerate([p["dim"], p["pink"], p["b"], p["warn"], p["a"], p["purple"], p["graph"][3], p["text"]]):
        s.append(f'<rect x="{kx + i * 30}" y="{yb}" width="26" height="16" rx="3" fill="{c}"/>')
    return doc(W, H, "".join(s), p, title="fastfetch: " + "; ".join(f"{k}: {v}" for k, v in rows))


def chip(label, icn, p, theme, button=False):
    H = 34
    w = 14 + 18 + 9 + tw(label, 13) + (30 if button else 16)
    s = [f'<rect x="1" y="1" width="{w - 2:.0f}" height="{H - 2}" rx="{(H - 2) / 2}" fill="{p["surface"]}" '
         + (f'stroke="url(#hlh)" stroke-width="1.6"/>' if button else f'stroke="{p["border"]}"/>')]
    s.append(icon(icn if not button else icn, 14, 8, 18, p["a"] if button else None, theme, p))
    s.append(f'<text x="41" y="21.5" font-size="13" font-weight="{700 if button else 400}" fill="{p["text"]}">{X(label)}</text>')
    if button:
        s.append(icon("arrow_outward", w - 28, 9, 16, p["b"]))
    return doc(int(w), H, "".join(s), p, title=label)


def stack(cfg, D, p, theme):
    pad, rowh = 20, 44
    rows = []  # (title, [(x, item)])
    for g in cfg["stack"]:
        lw = tw(g["title"], 13) + 26
        x, line, out = pad + lw + 10, [], []
        for slug, label in g["items"]:
            iw = 10 + 16 + 8 + tw(label, 12.5) + 12
            if x + iw > W - pad and line:
                out.append(line)
                line, x = [], pad + lw + 10
            line.append((x, slug, label, iw))
            x += iw + 8
        out.append(line)
        rows.append((g["title"], lw, out))
    n = sum(len(o) for _, _, o in rows)
    H = 52 + n * rowh + 8
    s = [frame(W, H, p, "waybar", "~/.config/waybar/config.jsonc", "deployed_code")]
    y = 52
    k = 0
    for title, lw, out in rows:
        s.append(f'<rect x="{pad}" y="{y}" width="{lw:.0f}" height="30" rx="8" fill="url(#hlh)"/>'
                 f'<text x="{pad + lw / 2:.0f}" y="{y + 19.5}" font-size="13" font-weight="700" fill="{p["ink"]}" text-anchor="middle">{X(title)}</text>')
        for line in out:
            for x, slug, label, iw in line:
                s.append(f'<g class="in" style="animation-delay:{k * .035:.2f}s">'
                         f'<rect x="{x:.0f}" y="{y}" width="{iw:.0f}" height="30" rx="8" fill="{p["surface2"]}" stroke="{p["border"]}"/>'
                         + icon("brand:" + slug, x + 10, y + 7, 16, None, theme, p)
                         + f'<text x="{x + 34:.0f}" y="{y + 19.5}" font-size="12.5" fill="{p["text"]}">{X(label)}</text></g>')
                k += 1
            y += rowh
    title = "; ".join(f"{t}: " + ", ".join(l for _, _, l, _ in sum(o, [])) for t, _, o in rows)
    return doc(W, H, "".join(s), p, title=title)


def card(item, D, p, theme, featured):
    w, H = 410, 164
    r = D["repo"][item["repo"]]
    name = item.get("title") or r["name"]
    text = item.get("text") or r["description"] or "No description yet."
    lang = item.get("lang") or (r["primaryLanguage"] or {}).get("name")
    lcol = item.get("lang_color") or (r["primaryLanguage"] or {}).get("color")
    s = [frame(w, H, p, "~/" + name, "", "folder_open")]
    # stars / forks on the title row
    x = w - 18
    for ic, val in (("call_split", r["forkCount"]), ("star", r["stargazerCount"])):
        if ic == "call_split" and not val:
            continue
        t = str(val)
        s.append(f'<text x="{x}" y="25" font-size="12.5" fill="{p["muted"]}" text-anchor="end">{t}</text>')
        x -= tw(t, 12.5) + 18
        s.append(icon(ic, x, 13, 15, p["warn"] if ic == "star" else p["muted"]))
        x -= 10
    lines = wrap(text, int((w - 40) / (13.5 * CW)), 3)
    for i, ln in enumerate(lines):
        s.append(f'<text x="20" y="{64 + i * 21}" font-size="13.5" fill="{p["text"]}">{X(ln)}</text>')
    y = H - 20
    x = 20
    if lang:
        s.append(f'<circle cx="{x + 5}" cy="{y - 4.5}" r="5" fill="{readable(lcol, p, theme)}"/>'
                 f'<text x="{x + 16}" y="{y}" font-size="12" fill="{p["muted"]}">{X(lang)}</text>')
        x += 16 + tw(lang, 12) + 16
    for t in item.get("tags", []):
        s.append(f'<text x="{x:.0f}" y="{y}" font-size="12" fill="{p["a"]}">#{X(t)}</text>')
        x += tw("#" + t, 12) + 12
    return doc(w, H, f'<g class="in">{"".join(s)}</g>', p, title=f"{name}: {text}")


def ws_header(idx, total, wsp, count, p, theme):
    H = 46
    s = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="12" fill="{p["surface"]}" stroke="{p["border"]}"/>']
    x = 12
    for i in range(1, total + 1):
        on = i == idx
        s.append(f'<rect x="{x}" y="9" width="28" height="28" rx="8" fill="{"url(#hlh)" if on else p["surface2"]}"'
                 f'{"" if on else " stroke=" + chr(34) + p["border"] + chr(34)}/>'
                 f'<text x="{x + 14}" y="27.5" font-size="13" font-weight="700" fill="{p["ink"] if on else p["dim"]}" text-anchor="middle">{i}</text>')
        x += 34
    x += 10
    s.append(icon(wsp["icon"], x, 13, 20, p["a"]))
    s.append(f'<text x="{x + 30}" y="28.5" font-size="15" font-weight="700" fill="{p["text"]}">workspace {idx}'
             f'<tspan fill="{p["dim"]}"> / </tspan><tspan fill="{p["b"]}">{X(wsp["name"])}</tspan></text>')
    s.append(f'<text x="{W - 18}" y="28" font-size="12.5" fill="{p["muted"]}" text-anchor="end">{count} windows</text>')
    return doc(W, H, "".join(s), p, title=f"workspace {idx}: {wsp['name']}")


def stats(cfg, D, p, theme):
    langs = D["languages"]
    by = 262
    H = by + 34 + len(langs) * 26 + 12
    s = [frame(W, H, p, "btop", "github.com/" + cfg["login"], "memory")]
    # numbers
    s.append(box(20, 56, 300, 190, "stats", p))
    rows = [("star", "stars earned", D["stars"], p["warn"]),
            ("commit", "contributions, 1y", D["contributions"], p["a"]),
            ("local_fire_department", "current streak", f'{D["streak"]} d', p["pink"]),
            ("trophy", "longest streak", f'{D["longest"]} d', p["warn"]),
            ("book_2", "public repos", D["repos"], p["b"]),
            ("group", "followers", D["followers"], p["purple"])]
    for i, (ic, label, val, col) in enumerate(rows):
        y = 84 + i * 27
        s.append(f'<g class="in" style="animation-delay:{i * .06:.2f}s">' + icon(ic, 36, y - 13, 17, col)
                 + f'<text x="62" y="{y}" font-size="13" fill="{p["muted"]}">{X(label)}</text>'
                 f'<text x="304" y="{y}" font-size="14" font-weight="700" fill="{p["text"]}" text-anchor="end">{X(val)}</text></g>')
    # contribution grid
    gx, gw = 336, 484
    cols = int((gw - 32) / 16)
    days = D["days"]
    # align to weeks: pad the front so the last column ends today
    weeks, wk = [], [None] * 7
    for d in days:
        wk[d["weekday"]] = d
        if d["weekday"] == 6:
            weeks.append(wk)
            wk = [None] * 7
    if any(wk):
        weeks.append(wk)
    weeks = weeks[-cols:]
    shown = [d for w_ in weeks for d in w_ if d]
    mx = max([d["contributionCount"] for d in shown] + [1])
    s.append(box(gx, 56, gw, 190, f"contributions, {len(weeks)} weeks", p))

    def lvl(c):
        if c == 0:
            return 0
        return min(4, 1 + int(math.sqrt(c / mx) * 3.999))
    ox = gx + (gw - len(weeks) * 16 + 3) / 2
    for ci, w_ in enumerate(weeks):
        for ri, d in enumerate(w_):
            if not d:
                continue
            ring = f' stroke="{p["b"]}" stroke-width="1.5"' if d["date"] == D["today"] else ""
            s.append(f'<rect class="fade" style="animation-delay:{ci * .025:.3f}s" x="{ox + ci * 16:.1f}" y="{82 + ri * 16}" width="13" height="13" rx="3" fill="{p["graph"][lvl(d["contributionCount"])]}"{ring}/>')
    tot = sum(d["contributionCount"] for d in shown)
    s.append(f'<text x="{gx + 16}" y="{226}" font-size="12" fill="{p["muted"]}">{tot} contributions</text>')
    lx = gx + gw - 16 - 5 * 14 - tw("less", 11) - tw("more", 11) - 12
    s.append(f'<text x="{lx:.0f}" y="226" font-size="11" fill="{p["dim"]}">less</text>')
    for i in range(5):
        s.append(f'<rect x="{lx + tw("less", 11) + 6 + i * 14:.0f}" y="216" width="11" height="11" rx="2.5" fill="{p["graph"][i]}"/>')
    s.append(f'<text x="{gx + gw - 16}" y="226" font-size="11" fill="{p["dim"]}" text-anchor="end">more</text>')
    # language meters, btop style
    s.append(box(20, by, 800, H - by - 18, "languages, public repos", p))
    seg, gap, nseg = 11, 3, 38
    mx_share = max([v for _, v, _ in langs] + [1])
    for i, (name, share, col) in enumerate(langs):
        y = by + 32 + i * 26
        s.append(f'<circle cx="41" cy="{y - 4.5}" r="5" fill="{readable(col, p, theme)}"/>'
                 f'<text x="54" y="{y}" font-size="13" fill="{p["text"]}">{X(name[:16])}</text>')
        filled = max(1, round(share / mx_share * nseg))
        for j in range(nseg):
            on = j < filled
            c = mix(p["a"], p["b"], j / (nseg - 1)) if on else p["surface2"]
            s.append(f'<rect class="fade" style="animation-delay:{(j * .02 + i * .05) if on else 0:.2f}s" x="{196 + j * (seg + gap)}" y="{y - 12}" width="{seg}" height="14" rx="2" fill="{c}"/>')
        s.append(f'<text x="804" y="{y}" font-size="13" font-weight="700" fill="{p["muted"]}" text-anchor="end">{share:.1f}%</text>')
    return doc(W, H, "".join(s), p, title="GitHub stats: " + ", ".join(f"{l}: {v}" for _, l, v, _ in rows))


def dock(cfg, D, p, theme):
    H, sz, gap = 140, 34, 18
    items = cfg["dock"]
    dw = len(items) * sz + (len(items) - 1) * gap + 48
    dx = (W - dw) / 2
    css = """.bob{animation:bob 2.8s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}"""
    s = [f'<text x="{W / 2}" y="22" font-size="11" letter-spacing="4" fill="{p["muted"]}" text-anchor="middle">~/.TOOLBOX</text>',
         f'<line x1="40" y1="18" x2="{W / 2 - 70}" y2="18" stroke="{p["border"]}"/><line x1="{W / 2 + 70}" y1="18" x2="{W - 40}" y2="18" stroke="{p["border"]}"/>',
         f'<rect x="{dx:.0f}" y="54" width="{dw:.0f}" height="62" rx="18" fill="{p["surface"]}" stroke="url(#hlh)" stroke-width="1.6"/>']
    for i, slug in enumerate(items):
        x = dx + 24 + i * (sz + gap)
        s.append(f'<g class="bob" style="animation-delay:{i * .16:.2f}s"><title>{X(ICONS["brand"][slug]["t"])}</title>'
                 + icon("brand:" + slug, x, 66, sz, None, theme, p) + "</g>")
        s.append(f'<circle cx="{x + sz / 2:.1f}" cy="109" r="2" fill="{p["a"]}" opacity=".7"/>')
    return doc(W, H, "".join(s), p, css=css, title="Toolbox: " + ", ".join(ICONS["brand"][x]["t"] for x in items))


def statusline(cfg, D, p, theme):
    H = 30
    s = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="8" fill="{p["surface"]}" stroke="{p["border"]}"/>']
    s.append(f'<rect x="1" y="1" width="86" height="{H - 2}" rx="8" fill="url(#hlh)"/>'
             f'<text x="44" y="19.5" font-size="12" font-weight="700" fill="{p["ink"]}" text-anchor="middle">NORMAL</text>')
    s.append(icon("brand:github", 100, 8, 14, p["muted"]))
    s.append(f'<text x="122" y="19.5" font-size="12" fill="{p["text"]}">{X(cfg["login"])}/{X(cfg["login"])}'
             f'<tspan fill="{p["dim"]}">  /  </tspan>README.md<tspan fill="{p["b"]}">  [+]</tspan></text>')
    right = f"rendered {D['today']}   utf-8   unix   100%   ln 1"
    s.append(f'<text x="{W - 14}" y="19.5" font-size="12" fill="{p["muted"]}" text-anchor="end">{right}</text>')
    return doc(W, H, "".join(s), p, title=f"rendered {D['today']}")


# ---------------------------------------------------------------- readme
def pic(name, alt, width="100%"):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" width="{width}" alt="{X(alt)}"></picture>')


def link(url, inner):
    return f'<a href="{X(url)}">{inner}</a>'


def build(cfg, D, avatar):
    out = {}
    readme = []
    P = lambda *a: readme.append("".join(a))

    def put(name, fn, *args):
        for theme in ("dark", "light"):
            out[f"{name}-{theme}.svg"] = fn(*args, PAL[theme], theme)

    put("banner", lambda p, t: banner(cfg, D, p, t, avatar))
    put("typing", lambda p, t: typing(cfg, D, p, t))
    P('<div align="center">\n')
    P(pic("banner", f"{cfg['name']}: {' '.join(cfg['tagline'])}"), "\n")
    P(pic("typing", " / ".join(cfg["typing"])), "\n")
    # socials + buttons
    row = []
    for i, so in enumerate(cfg["socials"]):
        put(f"social-{i}", lambda p, t, so=so: chip(so["label"], "brand:" + so["icon"], p, t))
        row.append(link(so["url"], pic(f"social-{i}", so["label"], "auto")))
    P("\n", "&nbsp;".join(row), "\n")
    row = []
    for i, b in enumerate(cfg["buttons"]):
        put(f"button-{i}", lambda p, t, b=b: chip(b["label"], b["icon"], p, t, button=True))
        row.append(link(b["url"], pic(f"button-{i}", b["label"], "auto")))
    P("\n", "&nbsp;".join(row), "\n")

    def section(key, cmd):
        put(f"prompt-{key}", lambda p, t: prompt(cmd, p, t))
        P("\n<br>\n\n", pic(f"prompt-{key}", f"> {cmd}"), "\n")

    section("about", "fastfetch")
    put("fetch", lambda p, t: fetch(cfg, D, p, t))
    P(pic("fetch", "fastfetch"), "\n")

    section("stack", "waybar --modules langs,ui,sys")
    put("stack", lambda p, t: stack(cfg, D, p, t))
    P(pic("stack", "Tech stack"), "\n")

    section("featured", "ls ~/projects --featured")
    cards = []
    for it in cfg["featured"]:
        if it["repo"] not in D["repo"]:
            continue
        key = "f-" + it["repo"].lower()
        put(key, lambda p, t, it=it: card(it, D, p, t, True))
        cards.append(link(D["repo"][it["repo"]]["url"], pic(key, it.get("title") or it["repo"], "49%")))
    for i in range(0, len(cards), 2):
        P("\n", "&nbsp;".join(cards[i:i + 2]), "\n")

    section("ws", "hyprctl workspaces")
    wss = cfg["workspaces"]
    for wi, ws in enumerate(wss, 1):
        items = [it for it in ws["repos"] if it["repo"] in D["repo"]]
        put(f"ws-{wi}", lambda p, t, wi=wi, ws=ws, n=len(items): ws_header(wi, len(wss), ws, n, p, t))
        P("\n", pic(f"ws-{wi}", f"workspace {wi}: {ws['name']}"), "\n")
        cards = []
        for it in items:
            key = "c-" + it["repo"].lower()
            put(key, lambda p, t, it=it: card(it, D, p, t, False))
            cards.append(link(D["repo"][it["repo"]]["url"], pic(key, it.get("title") or it["repo"], "49%")))
        for i in range(0, len(cards), 2):
            P("\n", "&nbsp;".join(cards[i:i + 2]), "\n")

    section("stats", "btop --github")
    put("stats", lambda p, t: stats(cfg, D, p, t))
    P(pic("stats", "GitHub stats"), "\n")

    section("snake", "./snake --eat contributions")
    raw = f"https://raw.githubusercontent.com/{cfg['login']}/{cfg['login']}/output"
    P(f'<picture><source media="(prefers-color-scheme: dark)" srcset="{raw}/snake-dark.svg">'
      f'<img src="{raw}/snake-light.svg" width="100%" alt="A snake eating the contribution graph"></picture>\n')

    put("dock", lambda p, t: dock(cfg, D, p, t))
    P("\n<br>\n\n", pic("dock", "Toolbox"), "\n")
    put("statusline", lambda p, t: statusline(cfg, D, p, t))
    P("\n", pic("statusline", ""), "\n")
    P("\n<sub>Rendered by <a href=\"scripts/render.py\">scripts/render.py</a> from "
      "<a href=\"config.json\">config.json</a>, refreshed daily by GitHub Actions.</sub>\n")
    P("\n</div>\n")
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
    files, readme = build(cfg, D, fetch_avatar(cfg["login"]))
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

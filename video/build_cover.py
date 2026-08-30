"""Build docs/cover.png — the lablab submission hero (1920x1080).

A cinematic metaphor scene in the style of the strongest competitor covers, but drawn
from the project's own story: the public graveyard of rejected ideas — six tombstones
engraved with the real killed strategies and the numbers that killed them — and one
glowing monolith left standing, etched with the four surviving rules. Pure SVG/CSS,
rendered by headless Edge.

    python video/build_cover.py
"""
import os
import random
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

random.seed(7)

# ---- sky ---------------------------------------------------------------------------------
stars = []
for _ in range(110):
    x, y = random.uniform(0, 1920), random.uniform(0, 560)
    r = random.uniform(0.7, 1.7)
    o = random.uniform(0.15, 0.75)
    stars.append(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='{r:.1f}' fill='#cfe1ff' opacity='{o:.2f}'/>")
for _ in range(6):  # a few brighter ones
    x, y = random.uniform(0, 1920), random.uniform(0, 480)
    stars.append(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='2.3' fill='#e8f1ff' opacity='.9' filter='url(#soft)'/>")
STARS = "".join(stars)

BIRDS = ("<path d='M 250 175 q 9 -8 18 0 q 9 -8 18 0' stroke='#39465c' stroke-width='2.4' "
         "fill='none' opacity='.6'/>"
         "<path d='M 320 130 q 7 -6 14 0 q 7 -6 14 0' stroke='#39465c' stroke-width='2' "
         "fill='none' opacity='.45'/>")

# ---- tombstones --------------------------------------------------------------------------
def stone(x, ybase, s, rot, name1, name2, sub, crack=False):
    w, h = 92, 148
    rim = (f"<path d='M {w},-6 L {w},{-h+58} Q {w},{-h} {w-58},{-h} L 8,{-h}' fill='none' "
           f"stroke='url(#rim)' stroke-width='3' opacity='.85'/>")
    crk = ("<path d='M -46,-128 L -60,-98 L -48,-94 L -66,-52' stroke='#060a12' "
           "stroke-width='2.6' fill='none' opacity='.8'/>" if crack else "")
    label = ""
    if name1:
        y2 = f"<text x='0' y='{-h*0.47:.0f}' text-anchor='middle' font-size='15.5' font-weight='700' letter-spacing='1.5' fill='#5d6d88'>{name2}</text>" if name2 else ""
        yy = -h * 0.60 if name2 else -h * 0.53
        label = (
            f"<text x='0' y='{-h*0.78:.0f}' text-anchor='middle' font-size='17' fill='#4a5871'>\u2020</text>"
            f"<text x='0' y='{yy:.0f}' text-anchor='middle' font-size='15.5' font-weight='700' letter-spacing='1.5' fill='#5d6d88'>{name1}</text>"
            f"{y2}"
            f"<text x='0' y='{-h*0.26:.0f}' text-anchor='middle' font-size='11' fill='#42506a'>{sub}</text>")
    return f"""
  <g transform='translate({x},{ybase}) scale({s}) rotate({rot})'>
    <path d='M {-w},0 L {-w},{-h+58} Q {-w},{-h} {-w+58},{-h} L {w-58},{-h} Q {w},{-h} {w},{-h+58} L {w},0 Z'
          fill='url(#stone)'/>
    {rim}{crk}
    <rect x='{-w-14}' y='-8' width='{2*(w+14)}' height='16' rx='4' fill='#0a101c'/>
    {label}
    <path d='M {-w-30},2 q 8,-16 14,0 M {w+12},2 q 8,-18 15,0' stroke='#0d1420' stroke-width='3' fill='none'/>
  </g>"""

GRAVES = "".join([
    # far silhouettes (unnamed)
    stone(330, 742, 0.42, -4, "", "", ""),
    stone(760, 736, 0.38, 3, "", "", ""),
    stone(1000, 744, 0.34, -6, "", "", ""),
    stone(1130, 738, 0.30, 4, "", "", ""),
    stone(1585, 738, 0.40, -2, "", "", ""),
    stone(1760, 748, 0.46, 5, "", "", ""),
    # mid row
    stone(415, 852, 0.78, -5, "ELLIOTT", "WAVES", "surrogates reproduce it"),
    stone(880, 842, 0.72, 3, "FIBONACCI", "LEVELS", "rank 4\u201314 of 28 bands"),
    stone(1205, 858, 0.76, -2, "MACRO", "OVERLAYS \u00d75", "4 of 5 fail out-of-sample", crack=True),
    # near row
    stone(235, 1006, 1.12, -3, "INTRADAY", "REVERSION", "it was bid-ask bounce"),
    stone(680, 1022, 1.05, 4, "LEVERAGED-ETF", "SHORT", "drift swamps the decay"),
    stone(1105, 1030, 1.10, -6, "OPTIONS", "DESIGN v1", "our own \u00b7 negative expectancy", crack=True),
])

# ---- monolith ----------------------------------------------------------------------------
ETCH = "".join(
    f"<text x='1352' y='{y}' text-anchor='middle' font-size='9.5' letter-spacing='1.1' "
    f"font-weight='600' fill='#bcd8ff' opacity='.95'>{t}</text>"
    for y, t in ((470, "OVERNIGHT CORE"), (498, "TREND GATE"),
                 (526, "CREDIT CANARY"), (554, "CAPITULATION")))

MONOLITH = f"""
  <polygon points='1252,168 1452,168 1470,700 1234,700' fill='url(#beam)' filter='url(#blur18)'/>
  <ellipse cx='1352' cy='700' rx='215' ry='26' fill='#3b82f6' opacity='.42' filter='url(#blur24)'/>
  <g filter='url(#mglow)'>
    <polygon points='1310,256 1394,256 1406,700 1298,700' fill='url(#mono)'/>
    <polygon points='1394,256 1406,700 1399,700 1388,256' fill='#7db4fb' opacity='.85'/>
    <polygon points='1310,256 1298,700 1303,700 1315,256' fill='#060b14' opacity='.9'/>
    <rect x='1327' y='300' width='50' height='2' fill='#8fc0ff' opacity='.7'/>
    <rect x='1327' y='310' width='34' height='2' fill='#8fc0ff' opacity='.45'/>
    <line x1='1322' y1='430' x2='1382' y2='430' stroke='#3f5f92' stroke-width='1'/>
    <line x1='1322' y1='572' x2='1382' y2='572' stroke='#3f5f92' stroke-width='1'/>
  </g>
  <circle cx='1352' cy='250' r='4.2' fill='#eaf3ff' filter='url(#soft)'/>
  {ETCH}
  <rect x='1302' y='700' width='100' height='300' fill='url(#refl)' opacity='.16' filter='url(#blur18)'/>"""

# ---- fog bands ---------------------------------------------------------------------------
def fog(cx, cy, rx, ry, o):
    return (f"<ellipse cx='{cx}' cy='{cy}' rx='{rx}' ry='{ry}' fill='#a8c4e8' "
            f"opacity='{o}' filter='url(#blur24)'/>")

FOG1 = fog(500, 762, 620, 34, .10) + fog(1500, 752, 520, 30, .09)
FOG2 = fog(900, 886, 760, 40, .11) + fog(180, 900, 380, 34, .10)
FOG3 = fog(600, 1058, 820, 48, .13) + fog(1500, 1072, 640, 44, .12)

SVG = f"""
<svg width='1920' height='1080' viewBox='0 0 1920 1080' xmlns='http://www.w3.org/2000/svg'
     font-family='Segoe UI,system-ui,sans-serif'>
  <defs>
    <linearGradient id='sky' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#04060c'/>
      <stop offset='.55' stop-color='#081120'/>
      <stop offset='.86' stop-color='#0f2138'/>
      <stop offset='1' stop-color='#132a46'/>
    </linearGradient>
    <linearGradient id='ground' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#0b1322'/>
      <stop offset='1' stop-color='#04060b'/>
    </linearGradient>
    <linearGradient id='stone' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#0b1220'/>
      <stop offset='.62' stop-color='#131e33'/>
      <stop offset='1' stop-color='#1c2c49'/>
    </linearGradient>
    <linearGradient id='rim' x1='0' y1='1' x2='0' y2='0'>
      <stop offset='0' stop-color='#2c3e5c'/>
      <stop offset='1' stop-color='#6f9fd8'/>
    </linearGradient>
    <linearGradient id='mono' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#0a1424'/>
      <stop offset='.55' stop-color='#152a44'/>
      <stop offset='1' stop-color='#24487c'/>
    </linearGradient>
    <linearGradient id='beam' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#3b82f6' stop-opacity='0'/>
      <stop offset='.75' stop-color='#3b82f6' stop-opacity='.20'/>
      <stop offset='1' stop-color='#60a5fa' stop-opacity='.34'/>
    </linearGradient>
    <linearGradient id='refl' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#60a5fa'/>
      <stop offset='1' stop-color='#60a5fa' stop-opacity='0'/>
    </linearGradient>
    <radialGradient id='dawn' cx='.5' cy='.5' r='.5'>
      <stop offset='0' stop-color='#2a5f9e' stop-opacity='.55'/>
      <stop offset='1' stop-color='#2a5f9e' stop-opacity='0'/>
    </radialGradient>
    <radialGradient id='vig' cx='.5' cy='.44' r='.75'>
      <stop offset='.55' stop-color='#000' stop-opacity='0'/>
      <stop offset='1' stop-color='#000' stop-opacity='.55'/>
    </radialGradient>
    <filter id='soft' x='-80%' y='-80%' width='260%' height='260%'>
      <feGaussianBlur stdDeviation='2.2'/></filter>
    <filter id='blur18' x='-40%' y='-40%' width='180%' height='180%'>
      <feGaussianBlur stdDeviation='18'/></filter>
    <filter id='blur24' x='-60%' y='-60%' width='220%' height='220%'>
      <feGaussianBlur stdDeviation='24'/></filter>
    <filter id='mglow' x='-60%' y='-30%' width='220%' height='160%'>
      <feDropShadow dx='0' dy='0' stdDeviation='14' flood-color='#3b82f6' flood-opacity='.55'/>
    </filter>
    <filter id='grain'>
      <feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>
      <feColorMatrix type='matrix' values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .045 0'/>
    </filter>
  </defs>

  <rect width='1920' height='1080' fill='url(#sky)'/>
  {STARS}{BIRDS}
  <ellipse cx='1352' cy='700' rx='860' ry='300' fill='url(#dawn)'/>
  <rect y='700' width='1920' height='380' fill='url(#ground)'/>
  <path d='M 0,742 Q 330,706 760,734 T 1920,722 L 1920,1080 L 0,1080 Z' fill='#081020' opacity='.9'/>
  <path d='M 0,880 Q 480,836 1040,872 T 1920,860 L 1920,1080 L 0,1080 Z' fill='#060c17' opacity='.95'/>
  {FOG1}
  {MONOLITH}
  {GRAVES}
  {FOG2}{FOG3}
  <rect width='1920' height='1080' fill='url(#vig)'/>
  <rect width='1920' height='1080' filter='url(#grain)' opacity='.5'/>
</svg>"""

HTML = f"""<!doctype html><html><head><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;height:1080px;background:#04060c;overflow:hidden;position:relative;
font-family:'Segoe UI',system-ui,sans-serif;color:#e5e7eb}}
svg{{position:absolute;inset:0}}
.type{{position:absolute;left:72px;top:78px;z-index:2;max-width:840px}}
.wordmark{{font-size:118px;font-weight:800;letter-spacing:-2px;line-height:1;
text-shadow:0 14px 60px rgba(0,0,0,.75)}}
.wordmark .acc{{color:#60a5fa;text-shadow:0 0 44px rgba(96,165,250,.5)}}
.headline{{font-size:40px;font-weight:700;line-height:1.22;margin-top:18px;max-width:720px;
text-shadow:0 6px 30px rgba(0,0,0,.8)}}
.headline .bad{{color:#f87171;text-shadow:0 0 26px rgba(248,113,113,.55)}}
.chips{{margin-top:22px;font-size:14.5px;letter-spacing:2.5px;font-weight:600;
color:#7aa7e0;text-transform:uppercase;text-shadow:0 2px 14px rgba(0,0,0,.8)}}
.chips span{{margin:0 7px;color:#31435f}}
.caption{{position:absolute;left:72px;bottom:44px;z-index:2;font-size:14px;
letter-spacing:2.5px;text-transform:uppercase;color:#5d7295;
text-shadow:0 2px 12px rgba(0,0,0,.8)}}
.caption b{{color:#9fc6ff;font-weight:600}}
</style></head><body>
{SVG}
<div class='type'>
  <div class='wordmark'>Edge<span class='acc'>Stack</span></div>
  <div class='headline'>Every rule survived an attempt to <span class='bad'>kill&nbsp;it</span>.</div>
  <div class='chips'>Alpaca MCP Server v2 <span>\u25cf</span> Paper only <span>\u25cf</span>
    33 years of evidence <span>\u25cf</span> 3 engines agree</div>
</div>
<div class='caption'>The public graveyard of rejected ideas \u2014 <b>one stack left standing</b>
&nbsp;\u00b7&nbsp; github.com/jpennin5/edgestack</div>
</body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "cover_hero.html")
open(path_html, "w", encoding="utf-8").write(HTML)
cover = os.path.join(ROOT, "docs", "cover.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1920,1080", f"--screenshot={cover}",
                "file:///" + path_html.replace("\\", "/")], capture_output=True, timeout=120)
print("cover:", cover, f"{os.path.getsize(cover)/1024:.0f} KB")

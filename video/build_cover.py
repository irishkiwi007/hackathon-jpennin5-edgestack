"""Build docs/cover.png — the lablab submission hero (1920x1080).

"Evidence is the doorway to opportunity": chaotic, unsettling market noise at the
edges of the frame; a monumental doorway built from four nested gate-frames (the
agent's real gates - trend, credit, volume, calm) cutting through the chaos; and
through the opening, a warm promised-land valley. Pure SVG/CSS, rendered by
headless Edge.

    python video/build_cover.py
"""
import math
import os
import random
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

random.seed(11)

# ---- chaos: jittery price-path scribbles + drifting shards, masked to the edges ----------
scribbles = []
for _ in range(96):
    edge = random.choice(["l", "r", "t", "b"])
    if edge == "l":
        x, y = random.uniform(-40, 420), random.uniform(0, 1080)
    elif edge == "r":
        x, y = random.uniform(1500, 1960), random.uniform(0, 1080)
    elif edge == "t":
        x, y = random.uniform(0, 1920), random.uniform(-40, 300)
    else:
        x, y = random.uniform(0, 1920), random.uniform(820, 1120)
    pts = [f"{x:.0f},{y:.0f}"]
    for _ in range(random.randint(22, 44)):
        x += random.uniform(6, 26)
        y += random.uniform(-26, 26) * (3.2 if random.random() < 0.08 else 1)
        pts.append(f"{x:.0f},{y:.0f}")
    col = random.choice(["#7a2e4a", "#8f2f3f", "#40518a", "#5b3a72", "#3a4a74", "#6d2237"])
    o = random.uniform(0.18, 0.50)
    wdt = random.uniform(1.2, 3.2)
    scribbles.append(f"<polyline points='{' '.join(pts)}' fill='none' stroke='{col}' "
                     f"stroke-width='{wdt:.1f}' opacity='{o:.2f}'/>")
shards = []
for _ in range(26):
    edge = random.choice(["l", "r", "t", "b"])
    if edge == "l":
        x, y = random.uniform(0, 360), random.uniform(0, 1080)
    elif edge == "r":
        x, y = random.uniform(1560, 1920), random.uniform(0, 1080)
    elif edge == "t":
        x, y = random.uniform(0, 1920), random.uniform(0, 260)
    else:
        x, y = random.uniform(0, 1920), random.uniform(860, 1080)
    s = random.uniform(6, 22)
    rot = random.uniform(0, 360)
    col = random.choice(["#5f2a3d", "#31405f", "#3f2b52"])
    shards.append(f"<rect x='{x:.0f}' y='{y:.0f}' width='{s:.0f}' height='{s*0.55:.0f}' "
                  f"transform='rotate({rot:.0f} {x:.0f} {y:.0f})' fill='{col}' "
                  f"opacity='{random.uniform(.12,.30):.2f}'/>")
bolts = []
for bx, by, ang in ((150, 90, 40), (1770, 130, 140), (110, 940, -35),
                    (1800, 900, 215), (620, 60, 75), (1350, 1030, 250)):
    a = math.radians(ang)
    pts, x, y = [f"{bx},{by}"], bx, by
    for _ in range(7):
        x += math.cos(a) * random.uniform(28, 64) + random.uniform(-22, 22)
        y += math.sin(a) * random.uniform(28, 64) + random.uniform(-22, 22)
        pts.append(f"{x:.0f},{y:.0f}")
    col = random.choice(["#d14b66", "#8f9ae8", "#c46a8a"])
    bolts.append(f"<polyline points='{' '.join(pts)}' fill='none' stroke='{col}' "
                 f"stroke-width='2' opacity='{random.uniform(.28,.44):.2f}'/>")
CHAOS_LINES = "".join(scribbles) + "".join(shards) + "".join(bolts)

STORM = "".join(
    f"<ellipse cx='{cx}' cy='{cy}' rx='{rx}' ry='{ry}' fill='{col}' opacity='{o}' filter='url(#storm)'/>"
    for cx, cy, rx, ry, col, o in (
        (140, 120, 420, 260, "#1a1030", .85), (1790, 150, 430, 280, "#241031", .8),
        (90, 950, 430, 300, "#2a1026", .85), (1830, 960, 460, 300, "#161a38", .8),
        (960, -60, 700, 200, "#141026", .8), (500, 1120, 560, 220, "#20102a", .75),
        (1450, 1120, 560, 220, "#170f2b", .75), (60, 540, 340, 320, "#2b1024", .7),
        (1870, 540, 350, 330, "#131636", .7)))

# ---- the doorway: four nested gate-frames, cold blue outside -> warm gold inside ---------
FRAMES = [  # x-inset from 640/1280, top y, edge color, engraving
    (0,   170, "#4f7fc9", "TREND GATE"),
    (54,  212, "#5f93d8", "CREDIT CANARY"),
    (108, 254, "#8fae9d", "VOLUME CEILING"),
    (162, 296, "#d8b26a", "CALM REGIME"),
]
OPEN_X0, OPEN_X1 = 640 + 216, 1280 - 216          # 856 .. 1064
OPEN_TOP, BASE = 338, 838

def arch(x0, x1, ytop, ybase):
    r = (x1 - x0) / 2
    ry = r * 0.72
    return (f"M {x0},{ybase} L {x0},{ytop + r:.0f} "
            f"A {r:.0f},{ry:.0f} 0 0 1 {x1},{ytop + r:.0f} L {x1},{ybase} Z")

frame_svg = []
for i, (inset, ytop, edge, name) in enumerate(FRAMES):
    x0, x1 = 640 + inset, 1280 - inset
    yb = BASE
    frame_svg.append(f"<path d='{arch(x0, x1, ytop, yb)}' fill='url(#jamb{i})' "
                     f"stroke='{edge}' stroke-width='2.6'/>")
    frame_svg.append(f"<path d='{arch(x0 + 8, x1 - 8, ytop + 8, yb)}' fill='none' "
                     f"stroke='#05080f' stroke-width='1.6' opacity='.85'/>")
    frame_svg.append(f"<text x='{x0 + 27}' y='{yb - 26}' font-size='11.5' letter-spacing='2.2' "
                     f"font-weight='600' fill='{edge}' opacity='.9' "
                     f"transform='rotate(-90 {x0 + 27} {yb - 26})'>{name}</text>")
FRAME_SVG = "".join(frame_svg)

# ---- paradise through the opening --------------------------------------------------------
PARADISE = f"""
  <g clip-path='url(#doorclip)'>
    <rect x='{OPEN_X0}' y='{OPEN_TOP}' width='{OPEN_X1-OPEN_X0}' height='{BASE-OPEN_TOP}' fill='url(#psky)'/>
    <circle cx='960' cy='646' r='46' fill='#fff3d6'/>
    <circle cx='960' cy='646' r='46' fill='#ffe9b8' filter='url(#blur18)'/>
    <ellipse cx='960' cy='648' rx='150' ry='90' fill='#ffd98f' opacity='.5' filter='url(#blur24)'/>
    <path d='M {OPEN_X0},700 Q 905,668 950,692 T {OPEN_X1},684 L {OPEN_X1},{BASE} L {OPEN_X0},{BASE} Z' fill='#7fae7a'/>
    <path d='M {OPEN_X0},738 Q 920,706 1000,730 T {OPEN_X1},722 L {OPEN_X1},{BASE} L {OPEN_X0},{BASE} Z' fill='#5d9161'/>
    <path d='M {OPEN_X0},788 Q 930,760 1010,782 T {OPEN_X1},774 L {OPEN_X1},{BASE} L {OPEN_X0},{BASE} Z' fill='#41724c'/>
    <path d='M 946,{BASE} Q 950,780 968,742 Q 978,716 964,690' stroke='#ffe9b0' stroke-width='7'
          fill='none' opacity='.85' stroke-linecap='round'/>
    <path d='M 946,{BASE} Q 950,780 968,742 Q 978,716 964,690' stroke='#fff7dd' stroke-width='2.4'
          fill='none' stroke-linecap='round'/>
    <g fill='#2c4d38'>
      <ellipse cx='884' cy='742' rx='15' ry='20'/><rect x='881.5' y='752' width='5' height='16'/>
      <ellipse cx='1042' cy='772' rx='18' ry='24'/><rect x='1039' y='784' width='6' height='18'/>
    </g>
    <path d='M 900 420 q 7 -6 14 0 q 7 -6 14 0' stroke='#a8834d' stroke-width='2' fill='none' opacity='.7'/>
    <path d='M 990 452 q 6 -5 12 0 q 6 -5 12 0' stroke='#a8834d' stroke-width='1.7' fill='none' opacity='.6'/>
    <circle cx='902' cy='560' r='1.8' fill='#fff' opacity='.8'/>
    <circle cx='1020' cy='520' r='1.5' fill='#fff' opacity='.7'/>
    <circle cx='944' cy='486' r='1.3' fill='#fff' opacity='.6'/>
  </g>"""

# ---- light spilling out of the doorway ---------------------------------------------------
SPILL = f"""
  <ellipse cx='960' cy='640' rx='500' ry='420' fill='url(#gold)' opacity='.42' filter='url(#blur24)'/>
  <polygon points='918,{BASE} 700,1080 1220,1080 1002,{BASE}' fill='url(#pathlight)'/>
  <polygon points='930,{BASE} 830,1080 1090,1080 990,{BASE}' fill='url(#pathcore)'/>
  <ellipse cx='960' cy='{BASE}' rx='250' ry='22' fill='#ffd98f' opacity='.5' filter='url(#blur18)'/>"""

SVG = f"""
<svg width='1920' height='1080' viewBox='0 0 1920 1080' xmlns='http://www.w3.org/2000/svg'
     font-family='Segoe UI,system-ui,sans-serif'>
  <defs>
    <linearGradient id='sky' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#07060f'/>
      <stop offset='.6' stop-color='#0b0d1d'/>
      <stop offset='1' stop-color='#0a0913'/>
    </linearGradient>
    <linearGradient id='floor' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#0d0f1e'/>
      <stop offset='1' stop-color='#050409'/>
    </linearGradient>
    <linearGradient id='jamb0' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#0b1322'/><stop offset='1' stop-color='#182c4d'/>
    </linearGradient>
    <linearGradient id='jamb1' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#0d1728'/><stop offset='1' stop-color='#1e3a5e'/>
    </linearGradient>
    <linearGradient id='jamb2' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#12202c'/><stop offset='1' stop-color='#3d5b52'/>
    </linearGradient>
    <linearGradient id='jamb3' x1='0' y1='0' x2='1' y2='0'>
      <stop offset='0' stop-color='#231d12'/><stop offset='1' stop-color='#6e5526'/>
    </linearGradient>
    <linearGradient id='psky' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#8ec8e8'/>
      <stop offset='.42' stop-color='#ffe1a6'/>
      <stop offset='.62' stop-color='#ffcf82'/>
      <stop offset='1' stop-color='#f2b968'/>
    </linearGradient>
    <radialGradient id='gold' cx='.5' cy='.5' r='.5'>
      <stop offset='0' stop-color='#ffd98f' stop-opacity='.9'/>
      <stop offset='1' stop-color='#ffd98f' stop-opacity='0'/>
    </radialGradient>
    <linearGradient id='pathlight' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#ffd98f' stop-opacity='.34'/>
      <stop offset='1' stop-color='#ffd98f' stop-opacity='0'/>
    </linearGradient>
    <linearGradient id='pathcore' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#ffe9b8' stop-opacity='.5'/>
      <stop offset='1' stop-color='#ffe9b8' stop-opacity='.02'/>
    </linearGradient>
    <radialGradient id='vig' cx='.5' cy='.5' r='.72'>
      <stop offset='.5' stop-color='#000' stop-opacity='0'/>
      <stop offset='1' stop-color='#000' stop-opacity='.62'/>
    </radialGradient>
    <radialGradient id='edgeonly' cx='.5' cy='.52' r='.62'>
      <stop offset='.32' stop-color='#000'/>
      <stop offset='.60' stop-color='#999'/>
      <stop offset='1' stop-color='#fff'/>
    </radialGradient>
    <clipPath id='doorclip'>
      <path d='{arch(OPEN_X0, OPEN_X1, OPEN_TOP, BASE)}'/>
    </clipPath>
    <mask id='edges'>
      <rect width='1920' height='1080' fill='url(#edgeonly)'/>
    </mask>
    <filter id='storm' x='-60%' y='-60%' width='220%' height='220%'>
      <feTurbulence type='fractalNoise' baseFrequency='0.012 0.02' numOctaves='3' seed='4' result='t'/>
      <feGaussianBlur in='SourceGraphic' stdDeviation='28' result='b'/>
      <feDisplacementMap in='b' in2='t' scale='120'/>
    </filter>
    <filter id='blur18' x='-40%' y='-40%' width='180%' height='180%'>
      <feGaussianBlur stdDeviation='18'/></filter>
    <filter id='blur24' x='-60%' y='-60%' width='220%' height='220%'>
      <feGaussianBlur stdDeviation='24'/></filter>
    <filter id='grain'>
      <feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>
      <feColorMatrix type='matrix' values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .04 0'/>
    </filter>
  </defs>

  <rect width='1920' height='1080' fill='url(#sky)'/>
  <rect y='{BASE}' width='1920' height='{1080-BASE}' fill='url(#floor)'/>
  {STORM}
  <g mask='url(#edges)'>{CHAOS_LINES}</g>
  {SPILL}
  {FRAME_SVG}
  {PARADISE}
  <rect width='1920' height='1080' fill='url(#vig)'/>
  <rect width='1920' height='1080' filter='url(#grain)' opacity='.55'/>
</svg>"""

HTML = f"""<!doctype html><html><head><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;height:1080px;background:#07060f;overflow:hidden;position:relative;
font-family:'Segoe UI',system-ui,sans-serif;color:#e5e7eb}}
svg{{position:absolute;inset:0}}
.type{{position:absolute;left:72px;top:84px;z-index:2;max-width:660px}}
.wordmark{{font-size:112px;font-weight:800;letter-spacing:-2px;line-height:1;
text-shadow:0 14px 60px rgba(0,0,0,.85)}}
.wordmark .acc{{color:#60a5fa;text-shadow:0 0 44px rgba(96,165,250,.5)}}
.headline{{font-size:42px;font-weight:700;line-height:1.24;margin-top:20px;max-width:600px;
text-shadow:0 6px 30px rgba(0,0,0,.9)}}
.headline .ev{{color:#8ab8f2}}
.headline .op{{color:#ffca6b;text-shadow:0 0 30px rgba(255,202,107,.55)}}
.chips{{margin-top:24px;font-size:13.5px;letter-spacing:2px;font-weight:600;white-space:nowrap;
color:#7d95bd;text-transform:uppercase;text-shadow:0 2px 14px rgba(0,0,0,.9)}}
.chips span{{margin:0 7px;color:#323d55}}
.caption{{position:absolute;left:72px;bottom:44px;z-index:2;font-size:14px;
letter-spacing:2.5px;text-transform:uppercase;color:#5d7295;
text-shadow:0 2px 12px rgba(0,0,0,.9)}}
.caption b{{color:#ffca6b;font-weight:600}}
</style></head><body>
{SVG}
<div class='type'>
  <div class='wordmark'>Edge<span class='acc'>Stack</span></div>
  <div class='headline'><span class='ev'>Evidence</span> is the doorway to
    <span class='op'>opportunity</span>.</div>
  <div class='chips'>Alpaca MCP Server v2 <span>\u25cf</span> Paper only <span>\u25cf</span>
    33 years of evidence <span>\u25cf</span> 3 engines agree</div>
</div>
<div class='caption'>Four gates between the noise and the order \u2014 <b>the agent opens them
only on proof</b> &nbsp;\u00b7&nbsp; github.com/jpennin5/edgestack</div>
</body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "cover_hero.html")
open(path_html, "w", encoding="utf-8").write(HTML)
cover = os.path.join(ROOT, "docs", "cover.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1920,1080", f"--screenshot={cover}",
                "file:///" + path_html.replace("\\", "/")], capture_output=True, timeout=120)
print("cover:", cover, f"{os.path.getsize(cover)/1024:.0f} KB")

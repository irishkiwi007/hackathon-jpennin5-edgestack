"""Build docs/cover.png — the lablab submission hero (1920x1080).

"Evidence is the doorway to opportunity", cinematic pass: storm-wrapped chaos at the
edges, a monumental four-gate portal with real tunnel depth (door-light raking across
the receding rings), a glossy reflecting floor, volumetric light with drifting motes,
a lush atmospheric valley through the opening, and a lone figure at the threshold for
scale. Pure SVG/CSS, rendered by headless Edge.

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

CX, BASE = 960, 840
INSETS = [0, 62, 124, 186, 248]          # frame boundaries; last = opening
TOPS = [160, 206, 252, 298, 344]
X0S = [600 + i for i in INSETS]
X1S = [1320 - i for i in INSETS]
GATE_NAMES = ["TREND GATE", "CREDIT CANARY", "VOLUME CEILING", "CALM REGIME"]
GATE_INK = ["#7d9cc9", "#96abb9", "#c0ab74", "#ecc27e"]

def arch(x0, x1, ytop, ybase, rev=False):
    r = (x1 - x0) / 2
    ry = r * 0.72
    if not rev:
        return (f"M {x0},{ybase} L {x0},{ytop + r:.0f} "
                f"A {r:.0f},{ry:.0f} 0 0 1 {x1},{ytop + r:.0f} L {x1},{ybase} Z")
    return (f"M {x1},{ybase} L {x1},{ytop + r:.0f} "
            f"A {r:.0f},{ry:.0f} 0 0 0 {x0},{ytop + r:.0f} L {x0},{ybase} Z")

# ---- chaos: price-path scribbles, shards, glowing bolts (edge-masked) --------------------
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
    scribbles.append(f"<polyline points='{' '.join(pts)}' fill='none' stroke='{col}' "
                     f"stroke-width='{random.uniform(1.2,3.2):.1f}' "
                     f"opacity='{random.uniform(.18,.50):.2f}'/>")
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
    shards.append(f"<rect x='{x:.0f}' y='{y:.0f}' width='{s:.0f}' height='{s*0.55:.0f}' "
                  f"transform='rotate({random.uniform(0,360):.0f} {x:.0f} {y:.0f})' "
                  f"fill='{random.choice(['#5f2a3d', '#31405f', '#3f2b52'])}' "
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
    p = " ".join(pts)
    bolts.append(f"<polyline points='{p}' fill='none' stroke='{col}' stroke-width='9' "
                 f"opacity='.16' filter='url(#blur6)'/>"
                 f"<polyline points='{p}' fill='none' stroke='{col}' stroke-width='2' "
                 f"opacity='{random.uniform(.30,.46):.2f}'/>")
CHAOS_LINES = "".join(scribbles) + "".join(shards) + "".join(bolts)

STORM = "".join(
    f"<ellipse cx='{cx}' cy='{cy}' rx='{rx}' ry='{ry}' fill='{col}' opacity='{o}' filter='url(#storm)'/>"
    for cx, cy, rx, ry, col, o in (
        (140, 120, 420, 260, "#1a1030", .85), (1790, 150, 430, 280, "#241031", .8),
        (90, 950, 430, 300, "#2a1026", .85), (1830, 960, 460, 300, "#161a38", .8),
        (960, -60, 700, 200, "#141026", .8), (500, 1120, 560, 220, "#20102a", .75),
        (1450, 1120, 560, 220, "#170f2b", .75), (60, 540, 340, 320, "#2b1024", .7),
        (1870, 540, 350, 330, "#131636", .7)))

# storm crescents hugging the portal so the chaos wraps it
HUG = (f"<path d='M 540,{BASE} A 420,340 0 0 1 1380,{BASE}' fill='none' stroke='#12081f' "
       f"stroke-width='74' opacity='.55' filter='url(#blur24)'/>"
       f"<path d='M 500,{BASE} A 460,380 0 0 1 1420,{BASE}' fill='none' stroke='#240f22' "
       f"stroke-width='60' opacity='.45' filter='url(#blur24)'/>")

# ---- the portal: rings lit by the door light ---------------------------------------------
rings = []
for i in range(4):
    ring = (f"<path d='{arch(X0S[i], X1S[i], TOPS[i], BASE)} "
            f"{arch(X0S[i+1], X1S[i+1], TOPS[i+1], BASE, rev=True)}' "
            f"fill-rule='evenodd' fill='url(#tunnel)'/>")
    rim_in = (f"<path d='{arch(X0S[i+1], X1S[i+1], TOPS[i+1], BASE)}' fill='none' "
              f"stroke='#f0c987' stroke-width='{2.4 - i*0.3:.1f}' opacity='{.85 - i*.12:.2f}'/>")
    label = (f"<text x='{X0S[i] + 32}' y='{BASE - 26}' font-size='11.5' letter-spacing='2.2' "
             f"font-weight='600' fill='{GATE_INK[i]}' opacity='.92' "
             f"transform='rotate(-90 {X0S[i] + 32} {BASE - 26})'>{GATE_NAMES[i]}</text>")
    rings.append(ring + rim_in + label)
FRAME_SVG = ("".join(rings)
             + f"<path d='{arch(X0S[0], X1S[0], TOPS[0], BASE)}' fill='none' "
               f"stroke='#5f93d8' stroke-width='2.6' opacity='.9'/>")

# stone texture over the rings
TEXTURE = (f"<g clip-path='url(#ringclip)'><rect x='560' y='120' width='800' height='760' "
           f"filter='url(#stone)' opacity='.10'/></g>")

# ---- paradise through the opening --------------------------------------------------------
OX0, OX1, OTOP = X0S[4], X1S[4], TOPS[4]
PARADISE = f"""
  <g clip-path='url(#doorclip)'>
    <rect x='{OX0}' y='{OTOP}' width='{OX1-OX0}' height='{BASE-OTOP}' fill='url(#psky)'/>
    <ellipse cx='960' cy='450' rx='120' ry='26' fill='#ffffff' opacity='.20' filter='url(#blur18)'/>
    <ellipse cx='905' cy='500' rx='90' ry='18' fill='#ffe9c8' opacity='.25' filter='url(#blur18)'/>
    <circle cx='960' cy='640' r='120' fill='#ffe9b8' opacity='.55' filter='url(#blur24)'/>
    <circle cx='960' cy='640' r='44' fill='#fff6de'/>
    <circle cx='960' cy='640' r='58' fill='#ffedc2' opacity='.8' filter='url(#blur6)'/>
    <ellipse cx='960' cy='642' rx='108' ry='3.5' fill='#fff7dd' opacity='.6' filter='url(#blur6)'/>
    <path d='M {OX0},690 Q 910,664 950,680 T {OX1},672 L {OX1},700 L {OX0},700 Z' fill='#cfe0b4' opacity='.9'/>
    <path d='M {OX0},696 Q 905,668 950,690 T {OX1},682 L {OX1},{BASE} L {OX0},{BASE} Z' fill='#a3c48d'/>
    <path d='M {OX0},734 Q 920,704 1000,728 T {OX1},720 L {OX1},{BASE} L {OX0},{BASE} Z' fill='#6fa06f'/>
    <path d='M {OX0},786 Q 930,758 1010,780 T {OX1},772 L {OX1},{BASE} L {OX0},{BASE} Z' fill='#487a52'/>
    <path d='M 946,{BASE} Q 950,782 968,744 Q 978,718 964,692' stroke='#ffe9b0' stroke-width='8'
          fill='none' opacity='.9' stroke-linecap='round'/>
    <path d='M 946,{BASE} Q 950,782 968,744 Q 978,718 964,692' stroke='#fff9e6' stroke-width='2.6'
          fill='none' stroke-linecap='round'/>
    <g fill='#2c4d38'>
      <ellipse cx='886' cy='744' rx='14' ry='19'/><rect x='883.5' y='754' width='5' height='15'/>
      <ellipse cx='1040' cy='774' rx='17' ry='23'/><rect x='1037' y='786' width='6' height='17'/>
    </g>
    <path d='M 906 424 q 7 -6 14 0 q 7 -6 14 0' stroke='#a8834d' stroke-width='2' fill='none' opacity='.7'/>
    <path d='M 992 452 q 6 -5 12 0 q 6 -5 12 0' stroke='#a8834d' stroke-width='1.7' fill='none' opacity='.6'/>
  </g>"""

# ---- volumetric light, motes, threshold --------------------------------------------------
motes = []
for _ in range(30):
    mx = random.uniform(850, 1070) + random.uniform(-40, 40)
    my = random.uniform(420, 1020)
    r = random.uniform(1.0, 2.8)
    blur = " filter='url(#blur6)'" if random.random() < 0.35 else ""
    motes.append(f"<circle cx='{mx:.0f}' cy='{my:.0f}' r='{r:.1f}' fill='#ffe9b8' "
                 f"opacity='{random.uniform(.25,.75):.2f}'{blur}/>")
MOTES = "".join(motes)

SPILL = f"""
  <ellipse cx='960' cy='620' rx='520' ry='430' fill='url(#gold)' opacity='.45' filter='url(#blur24)'/>
  <ellipse cx='960' cy='600' rx='170' ry='280' fill='#ffe9b8' opacity='.22' filter='url(#blur24)'/>
  <polygon points='912,{BASE} 620,1080 1300,1080 1008,{BASE}' fill='url(#pathlight)' filter='url(#blur6)'/>
  <polygon points='928,{BASE} 810,1080 1110,1080 992,{BASE}' fill='url(#pathcore)'/>
  <ellipse cx='960' cy='{BASE}' rx='260' ry='24' fill='#ffd98f' opacity='.55' filter='url(#blur18)'/>"""

# ---- the figure at the threshold ---------------------------------------------------------
FIGURE = f"""
  <ellipse cx='960' cy='806' rx='30' ry='52' fill='#ffdf9e' opacity='.4' filter='url(#blur18)'/>
  <polygon points='948,{BASE+6} 972,{BASE+6} 1006,1080 918,1080' fill='#04050a' opacity='.30' filter='url(#blur6)'/>
  <g fill='#0a0d15'>
    <circle cx='960' cy='764' r='7.5'/>
    <path d='M 951,773 Q 947,780 948,796 L 950,816 L 947,{BASE+4} L 955,{BASE+4} L 957,818
             L 963,818 L 965,{BASE+4} L 973,{BASE+4} L 970,816 L 972,796 Q 973,780 969,773 Z'/>
  </g>
  <path d='M 953,774 Q 950,780 950,794' stroke='#ffd98f' stroke-width='1.6' fill='none' opacity='.8'/>
  <path d='M 967,774 Q 970,780 970,794' stroke='#ffd98f' stroke-width='1.6' fill='none' opacity='.8'/>
  <ellipse cx='960' cy='{BASE+5}' rx='26' ry='5' fill='#050608' opacity='.6' filter='url(#blur6)'/>"""

# ---- floor reflection of the portal ------------------------------------------------------
REFLECT = f"""
  <g transform='translate(0,{2*BASE}) scale(1,-1)' mask='url(#reflmask)' opacity='.30'
     filter='url(#blur6)'>
    {FRAME_SVG}{PARADISE}
  </g>"""

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
      <stop offset='0' stop-color='#10121f'/>
      <stop offset='1' stop-color='#040308'/>
    </linearGradient>
    <radialGradient id='tunnel' cx='960' cy='650' r='500' gradientUnits='userSpaceOnUse'>
      <stop offset='0' stop-color='#f7d896'/>
      <stop offset='.28' stop-color='#d8ae66'/>
      <stop offset='.46' stop-color='#8a7a52'/>
      <stop offset='.64' stop-color='#41506e'/>
      <stop offset='.84' stop-color='#1c2846'/>
      <stop offset='1' stop-color='#101a30'/>
    </radialGradient>
    <linearGradient id='psky' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#7fc4e8'/>
      <stop offset='.38' stop-color='#ffe3ae'/>
      <stop offset='.60' stop-color='#ffd188'/>
      <stop offset='1' stop-color='#f2b968'/>
    </linearGradient>
    <radialGradient id='gold' cx='.5' cy='.5' r='.5'>
      <stop offset='0' stop-color='#ffd98f' stop-opacity='.9'/>
      <stop offset='1' stop-color='#ffd98f' stop-opacity='0'/>
    </radialGradient>
    <linearGradient id='pathlight' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#ffd98f' stop-opacity='.36'/>
      <stop offset='1' stop-color='#ffd98f' stop-opacity='0'/>
    </linearGradient>
    <linearGradient id='pathcore' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#ffe9b8' stop-opacity='.55'/>
      <stop offset='1' stop-color='#ffe9b8' stop-opacity='.03'/>
    </linearGradient>
    <radialGradient id='vig' cx='.5' cy='.5' r='.72'>
      <stop offset='.48' stop-color='#000' stop-opacity='0'/>
      <stop offset='1' stop-color='#000' stop-opacity='.66'/>
    </radialGradient>
    <radialGradient id='edgeonly' cx='.5' cy='.52' r='.62'>
      <stop offset='.32' stop-color='#000'/>
      <stop offset='.60' stop-color='#999'/>
      <stop offset='1' stop-color='#fff'/>
    </radialGradient>
    <linearGradient id='reflfade' x1='0' y1='{BASE}' x2='0' y2='1010'
                    gradientUnits='userSpaceOnUse'>
      <stop offset='0' stop-color='#fff'/>
      <stop offset='1' stop-color='#000'/>
    </linearGradient>
    <mask id='reflmask'>
      <rect x='0' y='{BASE}' width='1920' height='{1080-BASE}' fill='url(#reflfade)'/>
    </mask>
    <clipPath id='doorclip'><path d='{arch(OX0, OX1, OTOP, BASE)}'/></clipPath>
    <clipPath id='ringclip'><path d='{arch(X0S[0], X1S[0], TOPS[0], BASE)}'/></clipPath>
    <mask id='edges'><rect width='1920' height='1080' fill='url(#edgeonly)'/></mask>
    <filter id='storm' x='-60%' y='-60%' width='220%' height='220%'>
      <feTurbulence type='fractalNoise' baseFrequency='0.012 0.02' numOctaves='4' seed='4' result='t'/>
      <feGaussianBlur in='SourceGraphic' stdDeviation='28' result='b'/>
      <feDisplacementMap in='b' in2='t' scale='140'/>
    </filter>
    <filter id='stone' x='-20%' y='-20%' width='140%' height='140%'>
      <feTurbulence type='fractalNoise' baseFrequency='0.06 0.09' numOctaves='3' seed='9'/>
      <feColorMatrix type='matrix' values='0 0 0 0 .85  0 0 0 0 .78  0 0 0 0 .62  0 0 0 .5 0'/>
      <feComposite operator='in' in2='SourceGraphic'/>
    </filter>
    <filter id='blur6' x='-60%' y='-60%' width='220%' height='220%'>
      <feGaussianBlur stdDeviation='6'/></filter>
    <filter id='blur18' x='-40%' y='-40%' width='180%' height='180%'>
      <feGaussianBlur stdDeviation='18'/></filter>
    <filter id='blur24' x='-60%' y='-60%' width='220%' height='220%'>
      <feGaussianBlur stdDeviation='24'/></filter>
    <filter id='grain'>
      <feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>
      <feColorMatrix type='matrix' values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .045 0'/>
    </filter>
  </defs>

  <rect width='1920' height='1080' fill='url(#sky)'/>
  <rect y='{BASE}' width='1920' height='{1080-BASE}' fill='url(#floor)'/>
  {STORM}
  <g mask='url(#edges)'>{CHAOS_LINES}</g>
  {HUG}
  {REFLECT}
  {SPILL}
  {FRAME_SVG}
  {TEXTURE}
  {PARADISE}
  {MOTES}
  {FIGURE}
  <rect width='1920' height='1080' fill='#1a2b4a' opacity='.10'/>
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

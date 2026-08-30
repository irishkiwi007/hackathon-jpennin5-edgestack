"""Build docs/cover.png — the lablab submission hero graphic (1920x1080).

Advertising-hero layout, but every number on it is real: the drawdown chart is the
research record (video/raw/cover_curves.json, regenerated from scripts/equity_wide.py),
and the journal card quotes the live decision journal verbatim. Series colors validated
with the dataviz palette checker (#3b82f6 / #d97706 on #121826, all checks pass).

    python video/build_cover.py
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

D = json.load(open(os.path.join(HERE, "raw", "cover_curves.json")))
PTS, META = D["points"], D["meta"]

# ---- chart geometry ---------------------------------------------------------------------
W, H = 1010, 880                  # svg viewport
PL, PR, PT, PB = 10, 148, 14, 34  # padding: right side reserved for axis labels
X0, X1 = PTS[0][0], PTS[-1][0]
Y0, Y1 = 0.0, -60.0

def sx(year):
    return PL + (year - X0) / (X1 - X0) * (W - PL - PR)

def sy(dd):
    return PT + (dd - Y0) / (Y1 - Y0) * (H - PT - PB)

def path(col, close=False):
    p = " ".join(f"L{sx(r[0]):.1f},{sy(r[col]):.1f}" for r in PTS)
    p = "M" + p[1:]
    if close:
        p += f" L{sx(X1):.1f},{sy(0):.1f} L{sx(X0):.1f},{sy(0):.1f} Z"
    return p

BLUE, AMBER = "#3b82f6", "#d97706"
grid_rows = "".join(
    f"<line x1='{PL}' y1='{sy(v):.1f}' x2='{W-PR}' y2='{sy(v):.1f}' stroke='#1f2937' "
    f"stroke-width='1'/><text x='{W-PR+10}' y='{sy(v)+5:.1f}' fill='#8b98a9' "
    f"font-size='15'>{v:.0f}%</text>" for v in (0, -20, -40, -60))
grid_cols = "".join(
    f"<text x='{sx(y):.1f}' y='{H-8}' fill='#8b98a9' font-size='15' "
    f"text-anchor='{'start' if y == 1994 else 'middle'}'>{y}</text>"
    for y in (1994, 2002, 2010, 2018, 2026))

tb = min(PTS, key=lambda r: r[2])   # buy&hold trough row
ts = min(PTS, key=lambda r: r[1])   # stack trough row
gfc_x, gfc_y = sx(tb[0]), sy(tb[2])
cov_x, cov_y = sx(ts[0]), sy(ts[1])

SVG = f"""
<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' font-family='Segoe UI,system-ui,sans-serif'>
  <defs>
    <linearGradient id='af' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='{AMBER}' stop-opacity='.04'/>
      <stop offset='.45' stop-color='{AMBER}' stop-opacity='.30'/>
      <stop offset='1' stop-color='#92400e' stop-opacity='.60'/>
    </linearGradient>
    <linearGradient id='bf' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='{BLUE}' stop-opacity='.06'/>
      <stop offset='1' stop-color='{BLUE}' stop-opacity='.44'/>
    </linearGradient>
    <filter id='ga' x='-30%' y='-30%' width='160%' height='160%'>
      <feDropShadow dx='0' dy='0' stdDeviation='8' flood-color='{AMBER}' flood-opacity='.50'/>
    </filter>
    <filter id='gb' x='-30%' y='-30%' width='160%' height='160%'>
      <feDropShadow dx='0' dy='0' stdDeviation='8' flood-color='{BLUE}' flood-opacity='.60'/>
    </filter>
  </defs>
  {grid_rows}{grid_cols}
  <path d='{path(2, close=True)}' fill='url(#af)'/>
  <path d='{path(1, close=True)}' fill='url(#bf)'/>
  <path d='{path(2)}' fill='none' stroke='{AMBER}' stroke-width='4' stroke-linejoin='round' filter='url(#ga)'/>
  <path d='{path(1)}' fill='none' stroke='{BLUE}' stroke-width='4.5' stroke-linejoin='round' filter='url(#gb)'/>
  <line x1='{PL}' y1='{sy(0):.1f}' x2='{W-PR}' y2='{sy(0):.1f}' stroke='#e5e7eb' stroke-width='1.5' opacity='.8'/>

  <circle cx='{gfc_x:.1f}' cy='{gfc_y:.1f}' r='7' fill='{AMBER}' stroke='#121826' stroke-width='2'/>
  <text x='{gfc_x+16:.1f}' y='{gfc_y+2:.1f}' fill='#e5e7eb' font-size='19' font-weight='700'>buy &amp; hold {META['dd_bh']:.0f}%</text>
  <text x='{gfc_x+16:.1f}' y='{gfc_y+24:.1f}' fill='#8b98a9' font-size='14'>2008\u201309 \u00b7 EdgeStack \u22127% through the same crash</text>

  <circle cx='{cov_x:.1f}' cy='{cov_y:.1f}' r='7' fill='{BLUE}' stroke='#121826' stroke-width='2'/>
  <text x='{cov_x+16:.1f}' y='{cov_y-16:.1f}' fill='#e5e7eb' font-size='19' font-weight='700'>EdgeStack {META['dd_stack']:.0f}% worst-ever</text>
  <text x='{cov_x+16:.1f}' y='{cov_y+6:.1f}' fill='#8b98a9' font-size='14'>covid 2020 \u00b7 buy &amp; hold hit \u221234%</text>
</svg>"""

HTML = f"""<!doctype html><html><head><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;height:1080px;background:#080c13;color:#e5e7eb;overflow:hidden;
font:16px/1.5 'Segoe UI',system-ui,sans-serif;position:relative}}
body::before{{content:'';position:absolute;inset:0;
background:radial-gradient(1100px 780px at 72% 26%,rgba(59,130,246,.22),transparent 62%),
radial-gradient(900px 640px at 28% 106%,rgba(217,119,6,.10),transparent 60%),
radial-gradient(760px 560px at 10% 6%,rgba(248,113,113,.08),transparent 60%),
radial-gradient(1700px 1250px at 50% 46%,transparent 52%,rgba(0,0,0,.58) 100%)}}
body::after{{content:'';position:absolute;inset:0;
background:linear-gradient(#ffffff08 1px,transparent 1px),
linear-gradient(90deg,#ffffff08 1px,transparent 1px);background-size:64px 64px;
mask-image:radial-gradient(1200px 900px at 60% 40%,#000,transparent 85%)}}
.wrap{{position:absolute;inset:0;padding:56px 64px;display:flex;gap:48px;z-index:1}}
.left{{width:760px;display:flex;flex-direction:column;flex-shrink:0}}
.chips{{display:flex;gap:10px;margin-bottom:40px}}
.chip{{border:1px solid #1f2937;background:#121826;border-radius:99px;padding:7px 18px;
font-size:14px;color:#8b98a9}}
.kicker{{color:#8b98a9;letter-spacing:4px;font-size:16px;text-transform:uppercase;
margin-bottom:10px}}
.wordmark{{font-size:150px;font-weight:800;line-height:1.0;letter-spacing:-3px;
text-shadow:0 12px 60px rgba(0,0,0,.6)}}
.wordmark .acc{{color:#60a5fa;text-shadow:0 0 46px rgba(96,165,250,.45)}}
.headline{{font-size:54px;font-weight:700;line-height:1.16;margin-top:16px}}
.headline .bad{{color:#f87171;text-shadow:0 0 30px rgba(248,113,113,.5)}}
.sub{{font-size:23px;color:#8b98a9;line-height:1.5;margin-top:18px;max-width:700px}}
.pills{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:44px;max-width:700px}}
.pill{{background:#121826;border:1px solid #1f2937;border-radius:14px;padding:14px 18px}}
.pill .n{{font-size:31px;font-weight:700}}
.pill .l{{font-size:12px;color:#8b98a9;text-transform:uppercase;letter-spacing:1px;margin-top:2px}}
.foot{{color:#8b98a9;font-size:14px;border-top:1px solid #1f2937;padding-top:14px;
display:flex;justify-content:space-between;max-width:700px;margin-top:auto}}
.right{{flex:1;position:relative}}
.chart{{position:absolute;inset:0;background:#121826;
border:1px solid #1f2937;border-radius:20px;padding:22px 26px 14px;
box-shadow:0 30px 80px rgba(0,0,0,.5)}}
.chead{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}}
.ctitle{{font-size:19px;font-weight:700;letter-spacing:2px;text-transform:uppercase}}
.csub{{font-size:13px;color:#8b98a9;margin-top:3px}}
.legend{{display:flex;gap:18px;font-size:14px;color:#e5e7eb}}
.sw{{display:inline-block;width:13px;height:13px;border-radius:3px;margin-right:7px;
vertical-align:-1px}}
.journal{{width:640px;margin-top:36px;background:#0d1420;
border:1px solid #1f2937;border-left:4px solid #f87171;border-radius:14px;
padding:16px 20px;font-family:Consolas,monospace;font-size:15.5px;line-height:1.55;
box-shadow:0 24px 60px rgba(0,0,0,.55),0 0 46px rgba(248,113,113,.10)}}
.journal .jh{{display:flex;justify-content:space-between;align-items:center;
margin-bottom:8px;font-family:'Segoe UI',system-ui,sans-serif}}
.journal .jt{{color:#8b98a9;font-size:13px;letter-spacing:1px;text-transform:uppercase}}
.refused{{background:rgba(248,113,113,.14);color:#f87171;border:1px solid #f87171;
border-radius:99px;padding:3px 14px;font-size:13px;font-weight:700;letter-spacing:1px}}
.journal .dim{{color:#8b98a9}} .journal .r{{color:#f87171}} .journal .g{{color:#34d399}}
</style></head><body>
<div class='wrap'>
  <div class='left'>
    <div class='chips'><span class='chip'>PAPER ONLY</span>
      <span class='chip'>Alpaca MCP Server v2</span>
      <span class='chip'>lablab.ai \u00d7 Alpaca 2026</span></div>
    <div class='kicker'>Evidence-gated autonomous trading</div>
    <div class='wordmark'>Edge<span class='acc'>Stack</span></div>
    <div class='headline'>Every rule survived an attempt to <span class='bad'>kill it</span>.</div>
    <div class='sub'>33 years of data, three backtest engines forced to agree, and a public
      graveyard of rejected ideas \u2014 behind an agent that explains every trade and every
      refusal.</div>
    <div class='pills'>
      <div class='pill'><div class='n'>0.85 <span style='color:#8b98a9;font-size:19px'>vs 0.32</span></div>
        <div class='l'>Sharpe \u00b7 stack vs buy &amp; hold</div></div>
      <div class='pill'><div class='n'>\u221227% <span style='color:#8b98a9;font-size:19px'>vs \u221255%</span></div>
        <div class='l'>Max drawdown, 33 years</div></div>
      <div class='pill'><div class='n'>136 <span style='color:#8b98a9;font-size:19px'>events \u00b7 t = 4.3</span></div>
        <div class='l'>Capitulation edge, surrogate-tested</div></div>
      <div class='pill'><div class='n'>3 <span style='color:#8b98a9;font-size:19px'>engines agree</span></div>
        <div class='l'>incl. independent QuantConnect replay</div></div>
    </div>
    <div class='journal'>
      <div class='jh'><span class='jt'>decision journal \u00b7 2026-08-30</span>
        <span class='refused'>REFUSED</span></div>
      <div><span class='dim'>signal:</span> none \u2014 closest XLI stretch \u22120.86 <span class='dim'>(needs &lt; \u22122.5)</span></div>
      <div><span class='dim'>core gate:</span> <span class='r'>HELD OUT</span> \u2014 credit deteriorating</div>
      <div class='dim'>&nbsp;&nbsp;HYG 79.74 &lt; 100d SMA 79.85</div>
      <div class='dim' style='margin-top:8px;font-size:13.5px'>every trade \u2014 and every refusal \u2014 journaled in public</div>
    </div>
    <div class='foot'><span>github.com/jpennin5/edgestack</span>
      <span>jpennin5.github.io/edgestack</span><span>paper PA3ZCDDOPR2N</span></div>
  </div>
  <div class='right'>
    <div class='chart'>
      <div class='chead'>
        <div><div class='ctitle'>The losses it refused to take</div>
          <div class='csub'>drawdown from peak \u00b7 SPY record 1994\u20132026 \u00b7 research engine, costs included. Every pixel is real — no renders.</div></div>
        <div class='legend'><span><span class='sw' style='background:{BLUE}'></span>EdgeStack</span>
          <span><span class='sw' style='background:{AMBER}'></span>SPY buy &amp; hold</span></div>
      </div>
      {SVG}
    </div>
  </div>
</div>
</body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "cover_hero.html")
open(path_html, "w", encoding="utf-8").write(HTML)
cover = os.path.join(ROOT, "docs", "cover.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1920,1080", f"--screenshot={cover}",
                "file:///" + path_html.replace("\\", "/")], capture_output=True, timeout=120)
print("cover:", cover, f"{os.path.getsize(cover)/1024:.0f} KB")

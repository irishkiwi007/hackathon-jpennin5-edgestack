"""Build docs/cover.png — the lablab submission hero (1920x1080).

Composites the EdgeStack typography over the user-supplied AI artwork
(video/raw/cover_art.png: storm of market fears around an AI-faced gate opening
onto a golden valley, lone figure at the threshold, baked-in caption "evidence
opens the door to opportunity"). The overlay adds the wordmark, the proof chips,
and the repo links; the artwork's own caption serves as the slogan. Bottom-right
and top-right corners stay quiet for lablab's Play button and avatar overlays.

    python video/build_cover.py
"""
import base64
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

art = os.path.join(HERE, "raw", "cover_art.png")
b64 = base64.b64encode(open(art, "rb").read()).decode()

HTML = f"""<!doctype html><html><head><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;height:1080px;overflow:hidden;position:relative;background:#05060c;
font-family:'Segoe UI',system-ui,sans-serif;color:#e5e7eb}}
img.bg{{position:absolute;inset:0;width:1920px;height:1080px;object-fit:cover}}
.scrim{{position:absolute;inset:0;
background:linear-gradient(115deg,rgba(2,4,10,.66) 0%,rgba(2,4,10,.38) 22%,transparent 44%)}}
.type{{position:absolute;left:64px;top:64px;z-index:2}}
.wordmark{{font-size:104px;font-weight:800;letter-spacing:-2px;line-height:1;
text-shadow:0 4px 14px rgba(0,0,0,.95),0 14px 60px rgba(0,0,0,.9)}}
.wordmark .acc{{color:#7ab3f7;text-shadow:0 4px 14px rgba(0,0,0,.95),
0 0 44px rgba(96,165,250,.55)}}
.chips{{margin-top:18px;font-size:14px;letter-spacing:2.2px;font-weight:600;
white-space:nowrap;color:#c8d6ee;text-transform:uppercase;
text-shadow:0 2px 8px rgba(0,0,0,.95),0 0 22px rgba(0,0,0,.8)}}
.chips span{{margin:0 8px;color:#6b7ea3}}
.links{{position:absolute;left:64px;bottom:40px;z-index:2;font-size:14.5px;
letter-spacing:1.8px;text-transform:uppercase;color:#b8c6de;font-weight:600;
text-shadow:0 2px 8px rgba(0,0,0,.95),0 0 20px rgba(0,0,0,.85)}}
.links .dot{{margin:0 8px;color:#6b7ea3}}
.gate{{position:absolute;z-index:2;text-transform:uppercase}}
.gate .nm{{font-size:15px;font-weight:700;letter-spacing:3px;color:#ffd98f;
text-shadow:0 2px 6px rgba(0,0,0,.95),0 0 18px rgba(255,200,120,.55)}}
.gate .ds{{font-size:11.5px;letter-spacing:1.6px;color:#cfdaec;margin-top:3px;
text-shadow:0 2px 6px rgba(0,0,0,.95)}}
.gate.l{{text-align:right}}
.gate .tick{{position:absolute;top:9px;width:30px;height:2px;
background:linear-gradient(90deg,rgba(255,217,143,0),#ffd98f);
box-shadow:0 0 10px rgba(255,200,120,.7)}}
.gate.l .tick{{right:-42px}}
.gate.r .tick{{left:-42px;transform:scaleX(-1)}}
.gate .tick::after{{content:'';position:absolute;right:-3px;top:-2.5px;width:7px;height:7px;
border-radius:50%;background:#ffd98f;box-shadow:0 0 12px rgba(255,210,130,.9)}}
</style></head><body>
<img class='bg' src='data:image/png;base64,{b64}'/>
<div class='scrim'></div>
<div class='type'>
  <div class='wordmark'>Edge<span class='acc'>Stack</span></div>
  <div class='chips'>Alpaca MCP Server v2 <span>\u25cf</span> Paper only <span>\u25cf</span>
    33 years of evidence <span>\u25cf</span> 3 engines agree</div>
</div>
<div class='gate l' style='right:1332px;top:492px'>
  <div class='nm'>Trend Gate</div><div class='ds'>12-month trend must be up</div>
  <div class='tick'></div></div>
<div class='gate l' style='right:1332px;top:614px'>
  <div class='nm'>Credit Canary</div><div class='ds'>HYG above its 100-day average</div>
  <div class='tick'></div></div>
<div class='gate r' style='left:1338px;top:452px'>
  <div class='nm'>Volume Ceiling</div><div class='ds'>panic volume, not real news</div>
  <div class='tick'></div></div>
<div class='gate r' style='left:1338px;top:580px'>
  <div class='nm'>Calm Regime</div><div class='ds'>bond volatility at ease</div>
  <div class='tick'></div></div>
<div class='links'>github.com/jpennin5/edgestack</div>
</body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "cover_hero.html")
open(path_html, "w", encoding="utf-8").write(HTML)
cover = os.path.join(ROOT, "docs", "cover.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1920,1080", f"--screenshot={cover}",
                "file:///" + path_html.replace("\\", "/")], capture_output=True, timeout=120)
print("cover:", cover, f"{os.path.getsize(cover)/1024:.0f} KB")

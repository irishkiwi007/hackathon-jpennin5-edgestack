"""Build docs/day3_retire.png — the Day 3 LinkedIn attachment (1200x1200).

The live-rule retirement, shown the way a developer audience reads it: the
statistic that failed, the one-line change, the two safety properties, the
real gate refusal string, and the test count. Every string here is copied
from the running code (agent/signal_engine.py, agent/risk_gates.py) and from
`python agent/test_risk_gates.py` — nothing is mocked up.

    python video/build_day3_card.py
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

HTML = """<html><head><meta charset='utf-8'><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1200px;height:1200px;overflow:hidden;background:#05060c;
font-family:'Segoe UI',system-ui,sans-serif;color:#e5e7eb;
background-image:radial-gradient(900px 620px at 80% -10%,rgba(122,179,247,.15),transparent 62%),
radial-gradient(700px 500px at 0% 105%,rgba(255,217,143,.08),transparent 60%)}
.wrap{padding:54px 58px}
.top{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1px solid #1b2436;padding-bottom:18px}
.mark{font-size:38px;font-weight:800;letter-spacing:-1px}
.mark .acc{color:#7ab3f7}
.tag{font-size:12.5px;letter-spacing:3px;font-weight:700;color:#6b7ea3;text-transform:uppercase}
h1{margin-top:26px;font-size:56px;font-weight:800;letter-spacing:-1.6px;line-height:1.05}
h1 .k{color:#ffd98f}
.sub{margin-top:14px;font-size:19px;color:#aebdd6;max-width:1020px;line-height:1.5}
.stat{margin-top:30px;display:flex;gap:14px}
.box{flex:1;border:1px solid #1b2436;border-radius:12px;padding:15px 18px;
background:rgba(255,255,255,.022)}
.box .lb{font-size:11px;letter-spacing:2.4px;color:#6b7ea3;text-transform:uppercase}
.box .vl{margin-top:7px;font-size:30px;font-weight:800;font-family:'Consolas',monospace}
.was{color:#ff9d9d}.now{color:#8ee6b0}
.box .nt{margin-top:5px;font-size:12.5px;color:#8ea3c4}
.code{margin-top:26px;border:1px solid #1b2436;border-radius:12px;overflow:hidden;
font-family:'Consolas','Courier New',monospace;font-size:16.5px}
.code .hd{background:#0d1420;padding:9px 16px;color:#7d8fae;font-size:12.5px;
letter-spacing:1.4px;border-bottom:1px solid #1b2436}
.code .bd{padding:14px 16px;line-height:1.7;background:rgba(255,255,255,.015)}
.del{color:#ff9d9d}.add{color:#8ee6b0}.dim{color:#6b7ea3}
.props{margin-top:26px;display:flex;gap:14px}
.p{flex:1;border-left:3px solid #7ab3f7;padding:4px 0 4px 16px}
.p .t{font-size:16.5px;font-weight:700;color:#7ab3f7}
.p .d{margin-top:6px;font-size:14.5px;color:#aebdd6;line-height:1.5}
.jr{margin-top:26px;border-left:3px solid #ffd98f;padding:10px 0 10px 18px;
background:linear-gradient(90deg,rgba(255,217,143,.07),transparent 72%)}
.jr .lb{font-size:11px;letter-spacing:2.4px;color:#ffd98f;text-transform:uppercase}
.jr .q{margin-top:8px;font-family:'Consolas',monospace;font-size:16px;color:#e5e7eb}
.tests{margin-top:24px;font-family:'Consolas',monospace;font-size:17px;color:#8ee6b0}
.tests span{color:#6b7ea3}
.kept{margin-top:26px;border:1px solid #1b2436;border-radius:12px;padding:15px 20px;
background:rgba(255,255,255,.022);font-size:15.5px;color:#aebdd6;line-height:1.55}
.kept b{color:#8ee6b0}
.punch{margin-top:28px;font-size:31px;font-weight:800;letter-spacing:-.6px;line-height:1.25}
.punch .g{color:#8ea3c4;font-weight:600;display:block;font-size:17px;margin-top:9px;
letter-spacing:0}
.foot{position:absolute;left:58px;right:58px;bottom:44px;border-top:1px solid #1b2436;
padding-top:18px;display:flex;justify-content:space-between;align-items:center}
.slog{font-size:16.5px;color:#ffd98f;font-weight:600}
.repo{font-size:12.5px;letter-spacing:1.6px;color:#7d8fae;font-weight:600;text-transform:uppercase}
</style></head><body><div class='wrap'>

<div class='top'>
  <div class='mark'>Edge<span class='acc'>Stack</span></div>
  <div class='tag'>Live rule retirement &nbsp;·&nbsp; 2026-09-01</div>
</div>

<h1>I deleted my own <span class='k'>edge</span>.</h1>
<div class='sub'>The MEDIUM tier (capitulation on &ge;2.5&times; volume) shipped with a
t-statistic that assumed independent events. Its 27 signal days cluster in 2015,
2018 and 2020 — and some "events" are one panic hitting several ETFs at once.</div>

<div class='stat'>
  <div class='box'><div class='lb'>t, per event</div>
    <div class='vl was'>3.96</div><div class='nt'>as shipped — looks decisive</div></div>
  <div class='box'><div class='lb'>t, clustered by signal day</div>
    <div class='vl now'>~1.0</div><div class='nt'>block bootstrap agrees — noise</div></div>
  <div class='box'><div class='lb'>cost of removing it</div>
    <div class='vl now'>0.00</div><div class='nt'>leave-one-out, both windows</div></div>
</div>

<div class='code'>
  <div class='hd'>agent/signal_engine.py &nbsp;— &nbsp;TIER_TABLES</div>
  <div class='bd'>
<span class='del'>- ("MEDIUM", 2.5, inf, 0.60, 0.672, 1.578, 3.50, True)</span><br>
<span class='add'>+ ("MEDIUM", 2.5, inf, 0.60, 0.672, 1.578, 3.50, False)</span><br>
<span class='dim'>&nbsp;&nbsp;# numbers stay: the journal shows what we believed, and what killed it</span>
  </div>
</div>

<div class='props'>
  <div class='p'><div class='t'>It can only refuse</div>
    <div class='d'>The flag cannot open a position or resize one. Worst case is
    a trade that doesn't happen.</div></div>
  <div class='p'><div class='t'>Open positions still exit</div>
    <div class='d'>Exit proposals rebuild from the journal defaulting to
    tradeable — retire forward, never retroactively.</div></div>
</div>

<div class='jr'>
  <div class='lb'>What the public journal now records</div>
  <div class='q'>tier MEDIUM retired by clustered-t audit (t~1.0 once the panic
  days are clustered, not 3.5); refused</div>
</div>

<div class='tests'>$ python agent/test_risk_gates.py<br>
&nbsp;&nbsp;24 checks, 0 failed &nbsp;<span>— 2 written today, pinning the refusal</span></div>

<div class='kept'>What deliberately did <b>not</b> change: the FULL tier (1.8–2.5&times;) survived the
same audit and still trades. One cell was retired, not the strategy — and the equity
sleeve already filtered on the same flag, so a single line retired it from both books.</div>

<div class='punch'>Deleting your own edge is not a setback.
<span class='g'>It's the job — and it happened on a running system, mid-competition,
without touching an open position.</span></div>

<div class='foot'>
  <div class='slog'>Evidence opens the door to opportunity.</div>
  <div class='repo'>github.com/jpennin5/edgestack</div>
</div>
</div></body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "day3_retire.html")
open(path_html, "w", encoding="utf-8").write(HTML)
out = os.path.join(ROOT, "docs", "day3_retire.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1200,1200", f"--screenshot={out}",
                "file:///" + path_html.replace("\\", "/")],
               capture_output=True, timeout=120)
print("card:", out, f"{os.path.getsize(out)/1024:.0f} KB")

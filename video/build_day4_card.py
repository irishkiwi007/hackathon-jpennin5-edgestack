"""Build docs/day4_stress.png — the Day 4 LinkedIn attachment (1200x1200).

The deploy pipeline used as a stress test on the running competition system:
the drills, the market-hours promotion, the two failures no drill covered, and
the hardening that shipped through the same pipeline. Every string is taken
from the deployer log (edgestack-deploy/build.log), the scheduler log and the
commits of 2026-09-02 — nothing is mocked up.

    python video/build_day4_card.py
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
radial-gradient(700px 500px at 0% 105%,rgba(255,157,157,.07),transparent 60%)}
.wrap{padding:54px 58px}
.top{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1px solid #1b2436;padding-bottom:18px}
.mark{font-size:38px;font-weight:800;letter-spacing:-1px}.mark .acc{color:#7ab3f7}
.tag{font-size:12.5px;letter-spacing:3px;font-weight:700;color:#6b7ea3;text-transform:uppercase}
h1{margin-top:26px;font-size:52px;font-weight:800;letter-spacing:-1.5px;line-height:1.06}
h1 .k{color:#ffd98f}
.sub{margin-top:14px;font-size:18.5px;color:#aebdd6;max-width:1040px;line-height:1.5}
.flow{margin-top:24px;font-family:'Consolas',monospace;font-size:15.5px;color:#8ea3c4;
border:1px solid #1b2436;border-radius:12px;padding:12px 16px;background:rgba(255,255,255,.018)}
.flow b{color:#7ab3f7;font-weight:600}
.cols{margin-top:22px;display:flex;gap:14px}
.c{flex:1;border:1px solid #1b2436;border-radius:12px;padding:14px 16px;background:rgba(255,255,255,.022)}
.c .lb{font-size:11px;letter-spacing:2.4px;text-transform:uppercase;font-weight:700}
.drill .lb{color:#8ee6b0}.broke .lb{color:#ff9d9d}.hard .lb{color:#ffd98f}
.c ul{margin-top:9px;list-style:none}
.c li{font-size:14px;color:#c9d3e4;line-height:1.42;padding:5px 0 5px 14px;position:relative;
border-top:1px solid #131a28}
.c li:first-child{border-top:0}
.c li:before{content:'';position:absolute;left:0;top:13px;width:6px;height:6px;border-radius:50%}
.drill li:before{background:#8ee6b0}.broke li:before{background:#ff9d9d}.hard li:before{background:#ffd98f}
.c li code{font-family:'Consolas',monospace;font-size:13px;color:#e5e7eb}
.stat{margin-top:20px;display:flex;gap:14px}
.box{flex:1;border:1px solid #1b2436;border-radius:12px;padding:12px 16px;background:rgba(255,255,255,.022)}
.box .lb{font-size:11px;letter-spacing:2.4px;color:#6b7ea3;text-transform:uppercase}
.box .vl{margin-top:6px;font-size:28px;font-weight:800;font-family:'Consolas',monospace;color:#8ee6b0}
.box .vl.r{color:#ff9d9d}
.box .nt{margin-top:4px;font-size:12.5px;color:#8ea3c4}
.punch{margin-top:22px;font-size:27px;font-weight:800;letter-spacing:-.5px;line-height:1.25}
.punch .g{color:#8ea3c4;font-weight:600;display:block;font-size:16px;margin-top:8px;letter-spacing:0}
.foot{position:absolute;left:58px;right:58px;bottom:44px;border-top:1px solid #1b2436;
padding-top:18px;display:flex;justify-content:space-between;align-items:center}
.slog{font-size:16.5px;color:#ffd98f;font-weight:600}
.repo{font-size:12.5px;letter-spacing:1.6px;color:#7d8fae;font-weight:600;text-transform:uppercase}
</style></head><body><div class='wrap'>

<div class='top'>
  <div class='mark'>Edge<span class='acc'>Stack</span></div>
  <div class='tag'>Live cutover as a stress test &nbsp;·&nbsp; 2026-09-02</div>
</div>

<h1>I put the live agent behind a promotion pipeline, <span class='k'>then let it break.</span></h1>
<div class='sub'>Work lands on <code>master</code> in a private forge. <code>git push forge master:live</code>
promotes. A poller validates the new checkout before anything running is touched, swaps it in,
health-checks it, rolls back if it doesn't come up. GitHub is a mirror. Deploys hold through both
trading windows.</div>

<div class='flow'><b>promote</b> &rarr; validate (compile + wiring) &rarr; hold if a pass could be trading &rarr;
swap junction &rarr; health gate (scheduler + dashboard) &rarr; <b>OK</b> &nbsp;|&nbsp; else <b>rollback</b> to previous SHA</div>

<div class='cols'>
  <div class='c drill'><div class='lb'>Drills, on real code</div><ul>
    <li>Unparseable promotion: refused before the stack even stopped</li>
    <li>Compiles-but-crashes promotion: swapped, failed health, <b>rolled back in 8 s</b></li>
    <li>Found 4 bugs in the deployer: <code>Git</code> shadowing git.exe, stdout in exit codes,
        a backspace literal in a path, a lock held forever</li>
  </ul></div>
  <div class='c broke'><div class='lb'>What no drill covered</div><ul>
    <li>MCP server died at the cutover: <code>uvx</code> re-resolved <code>fastmcp 4.0.1</code>;
        agent fell back to REST, only signal a red card</li>
    <li>15:45 entry pass: transient TLS chain error, <b>no retry</b> &mdash; no entry decision today</li>
    <li>Journal auto-commit failing silently from the detached checkout</li>
  </ul></div>
  <div class='c hard'><div class='lb'>Hardened by 16:45 ET</div><ul>
    <li><code>fastmcp==3.4.7</code> pinned; card probes the server live</li>
    <li>Entry pass retries twice while still ahead of the 15:50 MOC cutoff</li>
    <li>REST client falls back to certifi's bundle on chain-verify failure</li>
    <li>Journal commits push through the forge (mirror &rarr; GitHub)</li>
  </ul></div>
</div>

<div class='stat'>
  <div class='box'><div class='lb'>promotions today</div><div class='vl'>3</div>
    <div class='nt'>one with the market open, two after the close</div></div>
  <div class='box'><div class='lb'>swap time</div><div class='vl'>~12 s</div>
    <div class='nt'>validate &rarr; swap &rarr; health OK</div></div>
  <div class='box'><div class='lb'>drill rollback</div><div class='vl'>8 s</div>
    <div class='nt'>automatic, previous SHA kept</div></div>
  <div class='box'><div class='lb'>capital while it broke</div><div class='vl r'>parked</div>
    <div class='nt'>$70k in SGOV at 3.90%, from the day before</div></div>
</div>

<div class='punch'>Every fix was a promotion with a rollback behind it.
<span class='g'>Not an edit on a live box. The failures the pipeline didn't prevent are the ones worth writing down.</span></div>

<div class='foot'>
  <div class='slog'>Evidence opens the door to opportunity.</div>
  <div class='repo'>github.com/jpennin5/edgestack</div>
</div>
</div></body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "day4_stress.html")
open(path_html, "w", encoding="utf-8").write(HTML)
out = os.path.join(ROOT, "docs", "day4_stress.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1200,1200", f"--screenshot={out}",
                "file:///" + path_html.replace("\\", "/")],
               capture_output=True, timeout=120)
print("card:", out, f"{os.path.getsize(out)/1024:.0f} KB")

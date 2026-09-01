"""Build docs/day1_journal.png — the Day 2 LinkedIn attachment (1200x1200).

Renders the REAL first-live-session journal entry (2026-08-31) as a branded
card: the equity gate that closed, the canary that closed it, and the
capitulation misses that never came near firing. Every number here is copied
from journal/decisions.jsonl and journal/scheduler.log — nothing is invented.

    python video/build_day1_card.py
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# --- real closest-miss rows from the 15:45 ET entry pass --------------------
MISSES = [
    ("XLI", "-1.29", "0.95x"),
    ("IWM", "-0.95", "1.00x"),
    ("XLV", "-0.83", "0.66x"),
    ("XLB", "-0.73", "0.91x"),
    ("XLU", "-0.65", "1.37x"),
]
rows = "".join(
    f"<tr><td class='sym'>{s}</td><td class='num'>{st}</td>"
    f"<td class='num'>{v}</td><td class='no'>no fire</td></tr>"
    for s, st, v in MISSES)

HTML = f"""<html><head><meta charset='utf-8'><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1200px;height:1200px;overflow:hidden;background:#05060c;
font-family:'Segoe UI',system-ui,sans-serif;color:#e5e7eb;
background-image:radial-gradient(900px 620px at 78% -8%,rgba(122,179,247,.16),transparent 62%),
radial-gradient(760px 520px at 6% 104%,rgba(255,217,143,.09),transparent 60%)}}
.wrap{{padding:54px 58px}}
.top{{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1px solid #1b2436;padding-bottom:18px}}
.mark{{font-size:40px;font-weight:800;letter-spacing:-1px}}
.mark .acc{{color:#7ab3f7}}
.tag{{font-size:13px;letter-spacing:3px;font-weight:700;color:#6b7ea3;
text-transform:uppercase}}
.sess{{margin-top:20px;font-size:13.5px;letter-spacing:2.6px;font-weight:600;
color:#8ea3c4;text-transform:uppercase}}
.verdict{{margin-top:16px;font-size:74px;font-weight:800;letter-spacing:-2px;
color:#ffd98f;line-height:1}}
.sub{{margin-top:12px;font-size:20px;color:#c8d6ee;font-weight:500}}
.sub b{{color:#e5e7eb}}
.sec{{margin-top:34px;font-size:12.5px;letter-spacing:3px;font-weight:700;
color:#6b7ea3;text-transform:uppercase}}
.gate{{margin-top:14px;border:1px solid #1b2436;border-radius:12px;
padding:16px 20px;background:rgba(255,255,255,.022);display:flex;
align-items:center;gap:18px}}
.gate + .gate{{margin-top:10px}}
.pill{{font-size:12px;font-weight:800;letter-spacing:1.6px;padding:6px 12px;
border-radius:999px;white-space:nowrap}}
.open{{color:#8ee6b0;background:rgba(110,231,168,.11);border:1px solid rgba(110,231,168,.35)}}
.shut{{color:#ffd98f;background:rgba(255,217,143,.11);border:1px solid rgba(255,217,143,.42)}}
.gname{{font-size:19px;font-weight:700;width:210px}}
.gdet{{font-size:17px;color:#aebdd6;font-family:'Consolas',monospace}}
table{{margin-top:12px;width:100%;border-collapse:collapse;
font-family:'Consolas','Courier New',monospace;font-size:17px}}
th{{text-align:left;font-size:11.5px;letter-spacing:2px;color:#6b7ea3;
font-weight:700;padding:0 0 9px;text-transform:uppercase;
font-family:'Segoe UI',sans-serif}}
td{{padding:9px 0;border-top:1px solid #141c2b;color:#c8d6ee}}
.sym{{color:#e5e7eb;font-weight:700;width:120px}}
.num{{width:170px}}
.no{{color:#6b7ea3}}
.rule{{margin-top:10px;font-size:15px;color:#8ea3c4;font-style:italic}}
.foot{{position:absolute;left:58px;right:58px;bottom:46px;
border-top:1px solid #1b2436;padding-top:20px;display:flex;
justify-content:space-between;align-items:center}}
.slog{{font-size:17px;color:#ffd98f;font-weight:600;letter-spacing:.2px}}
.repo{{font-size:13px;letter-spacing:1.6px;color:#7d8fae;font-weight:600;
text-transform:uppercase}}
.meta{{margin-top:16px;font-size:15px;color:#8ea3c4;font-family:'Consolas',monospace;
line-height:1.75}}
.meta b{{color:#aebdd6;font-weight:400}}
.note{{margin-top:30px;border-left:3px solid #ffd98f;padding:4px 0 4px 22px;
background:linear-gradient(90deg,rgba(255,217,143,.07),transparent 70%)}}
.nlab{{font-size:11.5px;letter-spacing:3px;font-weight:700;color:#ffd98f;
text-transform:uppercase}}
.ntxt{{margin-top:9px;font-size:19px;line-height:1.5;color:#cfdaec;max-width:1010px}}
.ntxt b{{color:#fff}}
</style></head><body><div class='wrap'>

<div class='top'>
  <div class='mark'>Edge<span class='acc'>Stack</span></div>
  <div class='tag'>Live Decision Journal</div>
</div>

<div class='sess'>Session 2026-08-31 &nbsp;·&nbsp; first live market day
&nbsp;·&nbsp; exit pass 09:31 ET &nbsp;·&nbsp; entry pass 15:45 ET</div>

<div class='verdict'>STOOD DOWN</div>
<div class='sub'>1 decision &nbsp;·&nbsp; <b>0 trades</b> &nbsp;·&nbsp;
equity <b>$100,000</b> unchanged &nbsp;·&nbsp; 0 open positions</div>

<div class='sec'>Equity gate — CLOSED</div>
<div class='gate'>
  <div class='pill open'>OPEN</div>
  <div class='gname'>12-month trend</div>
  <div class='gdet'>SPY trend UP &nbsp;+18.6%</div>
</div>
<div class='gate'>
  <div class='pill shut'>BLOCKED</div>
  <div class='gname'>Credit canary</div>
  <div class='gdet'>HYG 79.78 &nbsp;vs&nbsp; 100-day 79.85 &nbsp;→&nbsp; -0.09%</div>
</div>

<div class='sec'>Capitulation sleeve — no signal fired</div>
<table>
  <tr><th>symbol</th><th>stretch</th><th>volume</th><th>outcome</th></tr>
  {rows}
</table>
<div class='rule'>trigger requires stretch &lt; -2.50 AND volume &ge; 1.40x
— nothing came within a point of it</div>

<div class='meta'>
<b>regime:</b> TLT 21d sd 0.540 vs 90d mean 0.761 (ratio 0.71) → CALM<br>
<b>broker:</b> Alpaca MCP Server v2 — connected, account read via MCP<br>
<b>universe:</b> 16 symbols with usable history · options level 3
</div>

<div class='note'>
  <div class='nlab'>Why the veto stands</div>
  <div class='ntxt'>Seven cents of credit spread kept the agent flat. Deleting that
  canary costs <b>0.08–0.25 Sortino</b> across two disjoint validation windows — so it
  keeps its veto on quiet Mondays too. <b>A rule you overrule isn't a rule.</b></div>
</div>

<div class='foot'>
  <div class='slog'>Evidence opens the door to opportunity.</div>
  <div class='repo'>github.com/jpennin5/edgestack</div>
</div>
</div></body></html>"""

os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
path_html = os.path.join(HERE, "cards", "day1_journal.html")
open(path_html, "w", encoding="utf-8").write(HTML)
out = os.path.join(ROOT, "docs", "day1_journal.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1200,1200", f"--screenshot={out}",
                "file:///" + path_html.replace("\\", "/")],
               capture_output=True, timeout=120)
print("card:", out, f"{os.path.getsize(out)/1024:.0f} KB")

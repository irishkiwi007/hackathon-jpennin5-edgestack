"""Build docs/slides.pdf (10 slides, 16:9) + docs/cover.png (1920x1080 lablab cover).

Same pipeline as the video: HTML rendered by Edge headless, so the deck, the dashboard and
the video share one visual language. Charts are pure CSS (print-safe). Rebuild:
    python video/build_slides.py
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DASH = "file:///" + os.path.join(HERE, "raw", "dash.png").replace("\\", "/")

CSS = """
*{box-sizing:border-box;margin:0}
:root{--bg:#0b0f14;--card:#121826;--line:#1f2937;--txt:#e5e7eb;--dim:#8b98a9;
--green:#34d399;--red:#f87171;--amber:#fbbf24;--acc:#60a5fa}
@page{size:13.333in 7.5in;margin:0}
html,body{background:var(--bg);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.slide{width:13.333in;height:7.5in;page-break-after:always;position:relative;
background:var(--bg);color:var(--txt);font:15px/1.5 'Segoe UI',system-ui,sans-serif;
padding:.75in .9in;display:flex;flex-direction:column;overflow:hidden}
.chips{position:absolute;top:.55in;right:.9in;display:flex;gap:10px}
.chip{border:1px solid var(--line);background:var(--card);border-radius:99px;
padding:6px 16px;font-size:13px;color:var(--dim)}
.kicker{color:var(--amber);letter-spacing:3px;font-size:15px;text-transform:uppercase;
margin-bottom:14px}
h1{font-size:64px;line-height:1.08;font-weight:700}
h1 .acc{color:var(--acc)} .ok{color:var(--green)} .bad{color:var(--red)}
.sub{font-size:21px;color:var(--dim);max-width:10.4in;margin-top:20px;line-height:1.55}
.cards{display:flex;gap:16px;margin-top:auto}
.card{flex:1;background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:18px 20px}
.card .n{font-size:34px;font-weight:700}.card .l{font-size:13px;color:var(--dim);
margin-top:2px;text-transform:uppercase;letter-spacing:1px}
table{width:100%;border-collapse:collapse;font-size:17px;margin-top:22px}
td,th{padding:11px 14px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:1px}
li{font-size:20px;margin:13px 0 13px 24px;color:#cbd5e1;max-width:10.6in}
li b{color:var(--txt)}
.footer{position:absolute;bottom:.45in;left:.9in;right:.9in;color:var(--dim);
font-size:12px;border-top:1px solid var(--line);padding-top:10px;display:flex;
justify-content:space-between}
.mono{font-family:Consolas,monospace}
.bars{display:flex;align-items:flex-end;gap:34px;height:3.1in;margin-top:30px}
.bar{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;
height:100%}
.bar .col{width:1.15in;border-radius:8px 8px 0 0}
.bar .v{font-size:22px;font-weight:700;margin-bottom:8px}
.bar .l{font-size:14px;color:var(--dim);margin-top:10px;text-align:center;max-width:1.5in}
.two{display:flex;gap:.5in;margin-top:6px}.two>div{flex:1}
h2{font-size:40px;line-height:1.15;margin-top:6px}
.shot{margin-top:24px;border:1px solid var(--line);border-radius:14px;overflow:hidden;
box-shadow:0 20px 60px rgba(0,0,0,.5)}
.shot img{width:100%;display:block}
"""


def bar(pct, color, val, label):
    return (f"<div class='bar'><div class='v'>{val}</div>"
            f"<div class='col' style='height:{pct}%;background:{color}'></div>"
            f"<div class='l'>{label}</div></div>")


FOOT = ("<div class='footer'><span>EdgeStack &middot; lablab.ai &times; Alpaca AI Trading "
        "Agents Hackathon 2026</span><span>github.com/jpennin5/edgestack &middot; paper "
        "<span class='mono'>PA3ZCDDOPR2N</span></span></div>")

CHIPS = ("<div class='chips'><span class='chip'>PAPER ONLY</span>"
         "<span class='chip'>Alpaca MCP Server v2</span>"
         "<span class='chip'>Alpaca AI Trading Agents 2026</span></div>")

SLIDES = []

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div style='margin-top:.9in'>
<div class='kicker'>Evidence-gated autonomous trading</div>
<h1>Edge<span class='acc'>Stack</span></h1>
<h1 style='font-size:46px;margin-top:14px'>Every rule survived an attempt
to <span class='bad'>kill it</span>.</h1>
<p class='sub'>An agent whose strategy was built backward: months spent trying to
disprove candidate edges — and it only trades what survived.</p></div>
<div class='cards'>
<div class='card'><div class='n'>33 <span style='font-size:20px'>years</span></div>
<div class='l'>of validation data</div></div>
<div class='card'><div class='n'>3</div><div class='l'>backtest engines forced to agree</div></div>
<div class='card'><div class='n'>110</div><div class='l'>research scripts, all public</div></div>
<div class='card'><div class='n'>1</div><div class='l'>graveyard of rejected ideas</div></div>
</div>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>The problem</div>
<h2>LLM trading agents lose money <span class='bad'>confidently</span> —<br>
their rules come from vibes.</h2>
<p class='sub'>Ask a model for a strategy and it gives you one: plausible, articulate,
untested. The field's fix is to wrap the model in deterministic guardrails — and this event
is full of excellent guardrails. But guardrails only decide <i>whether a proposal is
allowed</i>. Nobody asks the harder question:</p>
<h2 style='margin-top:34px'>What evidence does a trading rule need<br>
<span class='acc'>before it deserves to exist?</span></h2>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>What we killed first</div>
<h2>The graveyard is the point.</h2>
<ul style='margin-top:20px'>
<li><b>Elliott waves</b> — shuffled-return surrogates reproduce the "patterns" (corr −0.525 vs −0.526)</li>
<li><b>Fibonacci retracements</b> — 38.2/50/61.8 rank 4th–14th of 28 arbitrary bands</li>
<li><b>Intraday mean reversion</b> — the "edge" was bid-ask bounce (trade AC −0.43, midquote +0.07)</li>
<li><b>Leveraged-ETF decay shorting</b> — the drag is real (t=−5.4) and drift swamps it 10:1</li>
<li><b>Five macro overlays</b> — four contradicted out-of-sample, including one we had already explained</li>
<li><b>Our own first options design</b> — negative expectancy from quoting the worst fill.
<span class='ok'>Found, measured, fixed.</span></li>
</ul>
<p class='sub' style='margin-top:auto'>Every rejection is documented with the number that
killed it. The negative results are load-bearing: they are why the survivors can be trusted.</p>
{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>What survived</div>
<h2>Three components. Every number is a measurement.</h2>
<table>
<tr><th>component</th><th>rule</th><th>evidence</th></tr>
<tr><td><b>Overnight core</b></td><td>Long SPY close→open only, gated by 12-month trend
AND the credit canary</td><td>Sharpe <b class='ok'>0.89</b> overnight vs
<b class='bad'>0.05</b> intraday · 8/9 eras since 1993</td></tr>
<tr><td><b>Capitulation sleeve</b></td><td>Buy 5σ panics on heavy-but-not-extreme volume
(1.4–2.5×), 7 ETFs, 3-session hold</td><td><b class='ok'>+1.42%/event</b> · 67.6% win ·
t=4.27 · 136 events / 33y · surrogate-tested</td></tr>
<tr><td><b>Options component</b></td><td>Defined-risk bull put spreads behind 14
deterministic gates</td><td>direction validated in the underlying; sized as a satellite —
we measured why (spreads eat retail edge)</td></tr>
</table>
{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>The core edge, drawn to scale</div>
<h2>The index earns its return while the market is closed.</h2>
<div class='two'>
<div><div class='bars'>
{bar(89, 'var(--green)', '0.89', 'SPY overnight only (close→open)')}
{bar(5, 'var(--red)', '0.05', 'SPY intraday (open→close)')}
{bar(47, 'var(--dim)', '0.47', 'buy & hold')}
</div><p class='sub' style='font-size:15px;margin-top:14px'>Sharpe ratio, 1993–2026.
corr(overnight, intraday) = 0.004 — dropping the intraday half is risk reduction,
not relabeling.</p></div>
<div><div class='bars'>
{bar(60, 'var(--acc)', '+1.55%', 'capitulation bounce, calm bond regime')}
{bar(3, 'var(--dim)', '+0.07%', 'same signal, stressed bonds')}
</div><p class='sub' style='font-size:15px;margin-top:14px'>t(diff)=6.58, out-of-sample,
n=4,359. The same boundary appears in the volume ceiling and the credit canary:
<b>markets revert emotional moves and honor informational ones.</b></p></div>
</div>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>The discipline</div>
<h2>Every parameter tuning <span class='bad'>failed validation</span>.<br>
The untuned rules won — and that is the point.</h2>
<table style='font-size:16px'>
<tr><th>config</th><th>train Sharpe (2008–17)</th><th>validation Sharpe (2018–26)</th><th>validation DD</th></tr>
<tr><td>always-on core (no gates)</td><td>0.51 · DD −50.7%</td><td>—</td><td>—</td></tr>
<tr><td><b>research defaults</b></td><td>0.80</td><td><b>0.65</b></td><td>21.2%</td></tr>
<tr><td>"improved" (tuned on train)</td><td><b class='ok'>0.89</b></td><td><b class='bad'>0.44</b></td><td>28.1%</td></tr>
<tr><td><b>+ credit canary</b> (from the trader's own older strategy — adopted only after
passing BOTH windows)</td><td><b class='ok'>0.98</b></td><td><b class='ok'>1.02</b></td>
<td><b class='ok'>11.8%</b></td></tr>
</table>
<p class='sub' style='margin-top:auto'>A rule change counts only if it survives a disjoint
window. One did. Full protocol: ENGINE-TRIAL.md.</p>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>The machine</div>
<h2>Signals are arithmetic. Gates are pure functions.<br>The LLM narrates — it never
sizes, prices, or authorizes.</h2>
<ul style='margin-top:22px'>
<li><b>Production engine reproduces the 33-year research record to 3 decimals</b> —
research and live code cannot drift apart silently (test_signal_engine.py)</li>
<li><b>14 deterministic risk gates</b>, 22-case suite where the <i>right</i> gate must
object — a gate that never fires is not a control</li>
<li><b>Alpaca MCP Server v2 integration is real</b>: account reads and order submission
route through MCP (streamable-http), REST fallback logged per call</li>
<li><b>Append-only decision journal</b> — every session recorded, including refusals,
with the evidence for each</li>
<li><b>Self-hosted, unattended</b>: ensure-running supervisors, logon persistence,
public live dashboard</li>
</ul>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>Live right now</div>
<div class='shot' style='margin-top:8px'><img src='{DASH}'></div>
<p class='sub' style='margin-top:16px'>The equity gate is <b class='amber'>CLOSED</b>:
trend is up, but credit slipped below its 100-day average — risk is being repriced on
information, so the agent refuses. <b>Refusal is a decision with evidence attached.</b></p>
{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div class='kicker'>Honest limits</div>
<h2>What we will not pretend.</h2>
<ul style='margin-top:24px'>
<li>The equity edges are <b>risk-adjusted</b> edges. A 5-session P&amp;L window is mostly
noise, for every entrant — we say so out loud.</li>
<li>Signals are rare by design. The gates refuse most sessions. <b>Flat is a
position.</b></li>
<li>Option-level expectancy could not be established from free historical data (no quote
history exists on this tier) — so the options book is a satellite, priced from live quotes
only, and the write-up explains exactly why.</li>
</ul>
<p class='sub' style='margin-top:auto'>An entry that hides its limits is asking judges to
find them. We measured ours first.</p>{FOOT}</div>""")

SLIDES.append(f"""<div class='slide'>{CHIPS}
<div style='margin-top:1.2in'>
<h1 style='font-size:44px'>Rules that <span class='acc'>earned their existence</span>.<br>
An engine that <span class='acc'>provably implements them</span>.<br>
An agent that <span class='acc'>explains every refusal</span>.</h1>
<p class='sub' style='margin-top:30px'>github.com/jpennin5/edgestack &middot; live
dashboard (URL in repo) &middot; Alpaca paper <span class='mono'>PA3ZCDDOPR2N</span>
&middot; demo video: docs/demo.mp4</p></div>
<h1 style='margin-top:auto'>Edge<span class='acc'>Stack</span></h1>{FOOT}</div>""")

html = ("<!doctype html><html><head><meta charset='utf-8'><style>" + CSS
        + "</style></head><body>" + "\n".join(SLIDES) + "</body></html>")
path = os.path.join(HERE, "cards", "slides.html")
open(path, "w", encoding="utf-8").write(html)
uri = "file:///" + path.replace("\\", "/")

pdf = os.path.join(ROOT, "docs", "slides.pdf")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", uri], capture_output=True, timeout=180)
print("PDF:", pdf, f"{os.path.getsize(pdf)/1024:.0f} KB")

# cover image for the lablab form = slide 1 rendered at 1920x1080
cover_html = ("<!doctype html><html><head><meta charset='utf-8'><style>" + CSS
              + ".slide{width:1920px;height:1080px;padding:80px 96px}@page{size:auto}"
              + "</style></head><body>" + SLIDES[0] + "</body></html>")
cpath = os.path.join(HERE, "cards", "cover.html")
open(cpath, "w", encoding="utf-8").write(cover_html)
cover = os.path.join(ROOT, "docs", "cover.png")
subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1920,1080", f"--screenshot={cover}",
                "file:///" + cpath.replace("\\", "/")], capture_output=True, timeout=120)
print("cover:", cover, f"{os.path.getsize(cover)/1024:.0f} KB")

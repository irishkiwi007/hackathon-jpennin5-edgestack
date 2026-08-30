"""Build the demo video end-to-end: HTML cards -> Edge screenshots -> SAPI narration ->
ffmpeg assembly. Output: docs/demo.mp4 (1080p).

Every frame is rendered by Edge from HTML so the whole video shares the dashboard's visual
language. Narration is Windows SAPI (synthetic; the trader can re-record over the same cut).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FF = os.path.join(ROOT, "host", "bin", "ffmpeg.exe")
FP = os.path.join(ROOT, "host", "bin", "ffprobe.exe")
RAW, CARDS, WAV, SEG = (os.path.join(HERE, d) for d in ("raw", "cards", "wav", "seg"))
for d in (CARDS, WAV, SEG):
    os.makedirs(d, exist_ok=True)

BASE_CSS = """
*{box-sizing:border-box;margin:0}
body{width:1920px;height:1080px;background:#0b0f14;color:#e5e7eb;overflow:hidden;
font:15px/1.55 'Segoe UI',system-ui,sans-serif;display:flex;flex-direction:column;
justify-content:center;padding:120px}
h1{font-size:88px;letter-spacing:.5px}h1 b{color:#60a5fa}
h2{font-size:44px;line-height:1.3;font-weight:600;max-width:1500px}
p{font-size:30px;color:#8b98a9;max-width:1480px;margin-top:26px;line-height:1.5}
.acc{color:#60a5fa}.ok{color:#34d399}.bad{color:#f87171}.amber{color:#fbbf24}
.tag{font-size:26px;color:#8b98a9;letter-spacing:2px;text-transform:uppercase;
margin-bottom:22px}
ul{margin-top:30px}li{font-size:30px;color:#cbd5e1;margin:16px 0 16px 26px;max-width:1480px}
li b{color:#e5e7eb}
.frame{position:absolute;inset:0;overflow:hidden;background:#0b0f14}
.frame img{position:absolute}
.cap{position:absolute;left:0;right:0;bottom:0;background:rgba(11,15,20,.92);
border-top:1px solid #1f2937;padding:26px 60px;font-size:28px;color:#cbd5e1}
.cap b{color:#60a5fa}
mono,.mono{font-family:Consolas,monospace}
"""


def card(name, body, extra_css=""):
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}"
            f"{extra_css}</style></head><body>{body}</body></html>")
    path = os.path.join(CARDS, name + ".html")
    open(path, "w", encoding="utf-8").write(html)
    png = os.path.join(CARDS, name + ".png")
    subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--window-size=1920,1080", f"--screenshot={png}",
                    "file:///" + path.replace("\\", "/")],
                   capture_output=True, timeout=120)
    return png


def shot_card(name, img, scale, left, top, caption):
    """Full-bleed screenshot at a chosen zoom/offset with a caption bar."""
    img_uri = "file:///" + os.path.join(RAW, img).replace("\\", "/")
    body = (f"<div class='frame'><img src='{img_uri}' "
            f"style='width:1920px;transform:scale({scale});transform-origin:0 0;"
            f"left:{left}px;top:{top}px'>"
            f"<div class='cap'>{caption}</div></div>")
    return card(name, body)


# ---------------------------------------------------------------- segment spec
SEGMENTS = [
    ("s01", card("s01", """
<div class='tag'>lablab.ai &times; Alpaca &middot; AI Trading Agents Hackathon</div>
<h1>Edge<b>Stack</b></h1>
<p style='font-size:40px;color:#e5e7eb;margin-top:34px'>Every rule in this agent survived
an attempt to kill it.</p>
<p>33 years of data &middot; three backtest engines &middot; one graveyard &middot;
live on Alpaca paper &middot; account <span class='mono'>PA3ZCDDOPR2N</span></p>"""),
     "EdgeStack. An autonomous trading agent built for the Alpaca A I Trading Agents "
     "Hackathon, with one organizing idea: every rule had to survive an attempt to kill it."),

    ("s02", card("s02", """
<div class='tag'>The problem</div>
<h2>LLM trading agents lose money <span class='bad'>confidently</span> —
their rules come from vibes.</h2>
<p>Ask a model for a trading strategy and it will give you one. Plausible. Articulate.
Untested.</p>
<p style='color:#e5e7eb'>The question nobody makes the agent answer:<br>
<span class='acc' style='font-size:36px'>What evidence does a trading rule need before it
deserves to exist?</span></p>"""),
     "Ask a language model for a trading strategy, and it will give you one. Confident. "
     "Plausible. Untested. L L M agents lose money confidently, because their rules come "
     "from vibes. EdgeStack asks the question nobody makes the agent answer: what evidence "
     "does a trading rule need, before it deserves to exist?"),

    ("s03", shot_card("s03", "dash.png", 1.0, 0, 0,
                      "<b>Live dashboard</b> — generated from the same files the agent itself writes"),
     "This is the agent. Live, on Alpaca paper trading, on a real account that judges can "
     "pull. Every order routes through Alpaca's M C P server, and the journal logs which "
     "path served every call. The page you are looking at is generated from the same files "
     "the agent itself writes."),

    ("s04", shot_card("s04", "dash.png", 2.0, -700, 130,
                      "<b>The equity gate is closed</b> — credit is deteriorating, so the agent refuses"),
     "Right now, the equity gate is closed. The twelve month trend is up. But high yield "
     "credit has slipped below its hundred day average. Deteriorating credit means risk is "
     "being repriced on information — and this agent only trades emotional moves, never "
     "informational ones. So it refuses. Refusal is a decision, with evidence attached."),

    ("s05", shot_card("s05", "dash.png", 1.9, -580, -1050,
                      "<b>The decision journal</b> — every session recorded, including the boring ones"),
     "Every session is journaled — including the boring ones. No trade. Gates held. An "
     "agent that can explain why it did nothing, is the point."),

    ("s06", shot_card("s06", "repo.png", 1.0, 0, 0,
                      "<b>github.com/jpennin5/edgestack</b> — 110 research scripts, every finding documented"),
     "The rules come from a research program. A hundred and ten scripts. Thirty three "
     "years of data. And three independent backtest engines that had to agree — my own "
     "engine, QuantConnect, and the research harness."),

    ("s07", card("s07", """
<div class='tag'>What survived</div>
<ul>
<li><b>SPY overnight-only core</b> — Sharpe <span class='ok'>0.89</span> overnight vs
<span class='bad'>0.05</span> intraday &middot; positive in 8 of 9 eras since 1993</li>
<li><b>Capitulation sleeve</b> — buys 5-day panics on heavy-but-not-extreme volume &middot;
<span class='ok'>+1.42%/event</span>, 67.6% win, t = 4.27 &middot; 136 events / 33 years</li>
<li><b>Credit canary</b> — HYG under its 100-day average closes the core &middot;
validated on two disjoint windows: 0.80&rarr;<span class='ok'>0.98</span> and
0.65&rarr;<span class='ok'>1.02</span> Sharpe</li>
<li><b>Options component</b> — defined-risk put spreads behind
<span class='acc'>14 deterministic gates</span></li>
</ul>"""),
     "What survived is small. S P Y, held overnight only — Sharpe zero point eight nine, "
     "against zero point zero five for the intraday session. A capitulation basket that "
     "buys five sigma panics on heavy, but not extreme, volume — one point four two "
     "percent per event, at a t statistic of four point three, across thirty three years. "
     "And a credit canary that closes the core when high yield credit deteriorates."),

    ("s08", shot_card("s08", "trial.png", 1.15, -80, -700,
                      "<b>Out-of-sample discipline</b> — every parameter tuning FAILED validation; the untuned rules won"),
     "And the discipline. Parameters were tuned on a training window, then validated on a "
     "disjoint one. Every tuning failed validation. The untuned rules won. That failure is "
     "exactly why the defaults can be trusted. One borrowed rule — a credit canary mined "
     "from my own older strategies — passed both windows, and was adopted."),

    ("s09", card("s09", """
<div class='tag'>The graveyard is the point</div>
<ul>
<li><b>Elliott waves</b> — surrogate data reproduces the "patterns"</li>
<li><b>Fibonacci levels</b> — rank 4th–14th out of 28 arbitrary bands</li>
<li><b>Five macro overlays</b> — four contradicted out-of-sample</li>
<li><b>Intraday mean reversion</b> — it was bid-ask bounce all along</li>
<li><b>Our own first options design</b> — negative expectancy.
<span class='ok'>Found, measured, fixed.</span></li>
</ul>"""),
     "The graveyard is the point. Elliott waves — surrogate data reproduces the patterns. "
     "Fibonacci levels — they rank no better than arbitrary bands. Five macro overlays — "
     "four contradicted out of sample. And our own first options design — negative "
     "expectancy. Found, measured, fixed."),

    ("s10", card("s10", """
<h2 style='font-size:52px'>Rules that <span class='acc'>earned their existence</span>.<br>
An engine that <span class='acc'>provably implements them</span>.<br>
An agent that <span class='acc'>explains every refusal</span>.</h2>
<p style='margin-top:44px'>github.com/jpennin5/edgestack &middot; Alpaca paper
<span class='mono'>PA3ZCDDOPR2N</span> &middot; built on Alpaca's MCP Server v2</p>
<h1 style='font-size:64px;margin-top:40px'>Edge<b>Stack</b></h1>"""),
     "The P and L window is five sessions, and these edges are risk adjusted. I won't "
     "pretend otherwise. What EdgeStack demonstrates is the discipline that survives any "
     "market. Rules that earned their existence. An engine that provably implements them. "
     "And an agent that explains every trade — and every refusal. EdgeStack."),
]

# ---------------------------------------------------------------- narration
PS = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Zira Desktop')
$s.Rate = -1
$s.SetOutputToWaveFile('{wav}')
$s.Speak('{text}')
$s.Dispose()
"""
for name, png, text in SEGMENTS:
    wav = os.path.join(WAV, name + ".wav")
    script = PS.format(wav=wav, text=text.replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-Command", script],
                   capture_output=True, timeout=180)
    if not os.path.exists(wav):
        print("TTS FAILED for", name)
        sys.exit(1)
print("narration synthesized")

# ---------------------------------------------------------------- assembly
def dur(path):
    out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


concat = []
for name, png, _text in SEGMENTS:
    d = dur(os.path.join(WAV, name + ".wav")) + 0.9
    seg = os.path.join(SEG, name + ".mp4")
    subprocess.run([FF, "-y", "-loop", "1", "-i", png,
                    "-i", os.path.join(WAV, name + ".wav"),
                    "-t", f"{d:.2f}",
                    "-vf", f"fade=t=in:st=0:d=0.35,fade=t=out:st={d - 0.4:.2f}:d=0.4,"
                           "scale=1920:1080,format=yuv420p",
                    "-af", "apad",
                    "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", seg],
                   capture_output=True, timeout=600)
    concat.append(f"file '{seg}'")
    print(f"segment {name}: {d:.1f}s")

lst = os.path.join(SEG, "list.txt")
open(lst, "w").write("\n".join(concat))
out = os.path.join(ROOT, "docs", "demo.mp4")
subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", out], capture_output=True, timeout=300)
print("OUTPUT:", out, f"{os.path.getsize(out) / 1e6:.1f} MB, {dur(out):.0f}s")

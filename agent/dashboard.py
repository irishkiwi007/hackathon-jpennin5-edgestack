"""EdgeStack live dashboard — the submission's "live application URL".

Stdlib-only HTTP server (port 8787). Serves a status page built from the same artifacts the
agent itself writes (decision journal, state files) plus a cached live account read routed
through the Alpaca MCP server. Nothing here can trade; it is a read-only window.

    python agent/dashboard.py            # http://127.0.0.1:8787
"""
from __future__ import annotations

import datetime
import html
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.join(HERE, "..")
JOURNAL = os.path.join(ROOT, "journal")
PORT = int(os.environ.get("EDGESTACK_DASH_PORT", "8787"))

_cache: dict = {"t": 0.0, "data": None}
_lock = threading.Lock()


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _read_jsonl(path, last_n=14):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out[-last_n:]


def collect() -> dict:
    """Everything the page needs. Account read is cached for 120s."""
    with _lock:
        now = time.time()
        if _cache["data"] and now - _cache["t"] < 120:
            return _cache["data"]

        acct, routes = {}, []
        try:
            from broker import Alpaca, load_env
            load_env(os.path.join(ROOT, ".env"))
            api = Alpaca()
            acct = api.account()
            routes = list(api.route_log)
        except Exception as exc:                       # noqa: BLE001
            routes = [f"account read failed: {exc}"]

        recs = _read_jsonl(os.path.join(JOURNAL, "decisions.jsonl"))
        latest = recs[-1] if recs else {}
        sched_alive = False
        try:
            mt = os.path.getmtime(os.path.join(JOURNAL, "scheduler.log"))
            sched_alive = (now - mt) < 26 * 3600
        except OSError:
            pass

        data = {
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"),
            "account": {
                "number": acct.get("account_number", "?"),
                "equity": float(acct.get("equity", 0) or 0),
                "options_bp": float(acct.get("options_buying_power", 0) or 0),
                "status": acct.get("status", "?"),
            },
            "broker_routes": routes[-6:],
            "scheduler_alive": sched_alive,
            "equity_state": _read_json(os.path.join(JOURNAL, "equity_state.json"),
                                       {"core": None, "sleeve": []}),
            "option_trades": _read_json(os.path.join(JOURNAL, "open_trades.json"), []),
            "journal": recs,
            "latest": {
                "session": latest.get("session_date", "-"),
                "regime": (latest.get("account") or {}).get("regime", "-"),
                "gate": (latest.get("account") or {}).get("equity_gate", "-"),
                "signals": len(latest.get("signals_fired") or []),
            },
        }
        _cache.update(t=now, data=data)
        return data


# ------------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0b0f14;--card:#121826;--line:#1f2937;--txt:#e5e7eb;--dim:#8b98a9;
--green:#34d399;--red:#f87171;--amber:#fbbf24;--acc:#60a5fa}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:15px/1.55 'Segoe UI',system-ui,sans-serif;
padding:28px;max-width:1080px;margin:0 auto}
h1{font-size:26px;letter-spacing:.3px} h1 span{color:var(--acc)}
.tag{color:var(--dim);margin:4px 0 22px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.k{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.8px}
.v{font-size:22px;font-weight:600;margin-top:4px}
.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}
.sec{margin-top:26px}.sec h2{font-size:15px;color:var(--dim);text-transform:uppercase;
letter-spacing:1px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px;text-transform:uppercase}
.mono{font-family:Consolas,monospace;font-size:13px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;
border:1px solid var(--line);margin:2px 4px 2px 0;color:var(--dim)}
.evidence{display:flex;flex-wrap:wrap;gap:8px}
footer{margin-top:34px;color:var(--dim);font-size:13px;border-top:1px solid var(--line);
padding-top:14px}
"""


def esc(x) -> str:
    return html.escape(str(x))


def render(d: dict) -> str:
    a = d["account"]
    eq = a["equity"]
    pnl = eq - 100_000.0
    pnl_cls = "ok" if pnl >= 0 else "bad"
    gate = d["latest"]["gate"]
    gate_open = "DETERIORATING" not in str(gate) and "DOWN" not in str(gate) \
        and gate not in ("-", None)
    core = d["equity_state"].get("core")
    sleeve = d["equity_state"].get("sleeve") or []
    opts = d["option_trades"] or []
    alive_cls, alive_txt = (("ok", "LIVE") if d["scheduler_alive"]
                            else ("warn", "IDLE"))
    mcp_ok = any("via MCP" in r or "mcp: connected" in r for r in d["broker_routes"])

    rows = ""
    for r in reversed(d["journal"]):
        acts = r.get("actions_taken") or []
        sigs = r.get("signals_fired") or []
        what = "; ".join(f"{x.get('action')}: {str(x.get('detail'))[:70]}"
                         for x in acts[:3]) or "no trade — gates held"
        rows += (f"<tr><td class=mono>{esc(r.get('session_date'))}</td>"
                 f"<td>{len(sigs)}</td><td>{esc(what)}</td></tr>")

    pos_rows = ""
    if core:
        pos_rows += (f"<tr><td>SPY</td><td>overnight core</td>"
                     f"<td class=mono>x{esc(core.get('qty'))}</td>"
                     f"<td class=mono>{esc(core.get('entry_date'))}</td></tr>")
    for p in sleeve:
        pos_rows += (f"<tr><td>{esc(p.get('symbol'))}</td><td>capitulation sleeve</td>"
                     f"<td class=mono>x{esc(p.get('qty'))}</td>"
                     f"<td class=mono>{esc(p.get('entry_date'))}</td></tr>")
    for p in opts:
        pos_rows += (f"<tr><td>{esc(p.get('symbol'))}</td><td>bull put spread "
                     f"{esc(p.get('short_strike'))}/{esc(p.get('long_strike'))}</td>"
                     f"<td class=mono>x{esc(p.get('contracts'))}</td>"
                     f"<td class=mono>{esc(p.get('entry_date'))}</td></tr>")
    if not pos_rows:
        pos_rows = "<tr><td colspan=4 style='color:var(--dim)'>flat — waiting for signals that clear the gates</td></tr>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="90"><title>EdgeStack</title>
<style>{CSS}</style></head><body>
<h1>Edge<span>Stack</span> <span style="font-size:13px" class="{alive_cls}">&#9679; {alive_txt}</span></h1>
<p class="tag">Evidence opens the door to opportunity &middot; 33 years of evidence, three
backtest engines, one graveyard &middot; Alpaca paper account <span class="mono">{esc(a['number'])}</span></p>

<div class="grid">
<div class="card"><div class="k">Equity</div><div class="v">${eq:,.0f}</div>
<div class="{pnl_cls}">{pnl:+,.0f} vs $100k start</div></div>
<div class="card"><div class="k">Equity gate</div>
<div class="v {'ok' if gate_open else 'warn'}">{'OPEN' if gate_open else 'CLOSED'}</div>
<div style="font-size:12px;color:var(--dim)">{esc(gate)}</div></div>
<div class="card"><div class="k">Macro regime</div>
<div style="font-size:13px;margin-top:6px">{esc(d['latest']['regime'])}</div></div>
<div class="card"><div class="k">Alpaca MCP server</div>
<div class="v {'ok' if mcp_ok else 'bad'}">{'ROUTING' if mcp_ok else 'FALLBACK'}</div>
<div style="font-size:12px;color:var(--dim)">orders + account via MCP, REST fallback</div></div>
</div>

<div class="sec"><h2>Open positions</h2>
<table><tr><th>symbol</th><th>component</th><th>size</th><th>entered</th></tr>{pos_rows}</table></div>

<div class="sec"><h2>Strategy — every number is a measurement</h2>
<div class="evidence">
<span class="pill">SPY overnight core &middot; Sharpe 0.89 vs 0.05 intraday &middot; 8/9 eras</span>
<span class="pill">gate: 12-month trend AND credit canary (HYG &gt; SMA100) &middot; validated on
disjoint windows 0.80&rarr;0.98 / 0.65&rarr;1.02</span>
<span class="pill">capitulation sleeve &middot; +1.42%/event &middot; 67.6% win &middot; t=4.27 &middot; 33y</span>
<span class="pill">volume ceiling 2.5x — above it "real news arrived", edge dies</span>
<span class="pill">options: defined-risk put spreads behind 14 deterministic gates</span>
</div></div>

<div class="sec"><h2>Decision journal (latest sessions)</h2>
<table><tr><th>session</th><th>signals</th><th>what happened &amp; why</th></tr>{rows}</table></div>

<footer>Generated {esc(d['generated'])} &middot; auto-refresh 90s &middot;
routes: {esc('; '.join(d['broker_routes'][-2:]))} &middot;
no-trade sessions are the gates working — the journal records every refusal with its reason.
</footer></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):                                  # noqa: N802
        try:
            if self.path.startswith("/api"):
                body = json.dumps(collect(), indent=1).encode()
                ctype = "application/json"
            else:
                body = render(collect()).encode()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:                       # noqa: BLE001
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def do_HEAD(self):                                 # noqa: N802 — probes use HEAD
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def log_message(self, fmt, *args):                 # quiet
        pass


if __name__ == "__main__":
    print(f"EdgeStack dashboard on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

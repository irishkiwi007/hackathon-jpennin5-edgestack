"""Backtests — run the borrowed TrustyRustyEngine runner on any strategy in engine/strategies.

The runner (engine/run_backtest.py) and the strategy contract (engine/bridge/) are copied
verbatim from the TrustyRustyEngine container (see engine/BORROWED.md); the lab's candidate
strategies and the CSV history they reference ride along. This module is the thin layer the
dashboard's Backtest tab talks to:

    strategies()           every strategy file with its kind, params and adoption dossiers
    run(name, options)     start a backtest in a thread; returns the result id
    results() / get(id)    the stored results (journal/backtests/<id>.json)

Results keep the metrics, the params actually used, both equity curves (downsampled), and
the fill count. Nothing here touches the broker.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
ENGINE = os.path.join(ROOT, "engine")
# A PRIVATE instance (the operator's own server) points these at the engine's
# real tree - every strategy, private ones included - instead of the
# allowlisted copy this public repo carries (2026-09-02).
STRATS = os.environ.get("EDGESTACK_STRATEGIES") or os.path.join(ENGINE, "strategies")
DATA = os.environ.get("EDGESTACK_DATA") or os.path.join(ENGINE, "data")
RUNNER = os.path.join(ENGINE, "run_backtest.py")
INSPECTOR = os.path.join(ENGINE, "inspect_strategy.py")
OUT = os.path.join(ROOT, "journal", "backtests")
LAB_REPORTS = os.environ.get("EDGESTACK_LAB_REPORTS",
                             r"C:\Users\Lenovo\edgestack-deploy\lab-journal\reports")
MAX_POINTS = 600

_inspect_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


# ----------------------------------------------------------------------------- strategies
def strategy_path(name: str) -> str:
    """Only plain file names inside engine/strategies are addressable."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.py", name) or ".." in name:
        raise ValueError(f"bad strategy name: {name!r}")
    p = os.path.join(STRATS, name)
    if not os.path.isfile(p):
        raise FileNotFoundError(name)
    return p


def kind_of(name: str) -> str:
    stem = name[:-3]
    if stem.startswith("bench_"):
        return "benchmark"
    if re.search(r"_c\d+", stem):
        return "candidate"
    if stem.endswith("_manual"):
        return "manual"
    return "baseline"


def _dossiers() -> dict[str, list[str]]:
    """strategy file -> adoption dossiers that reference it (from the lab journal mirror)."""
    out: dict[str, list[str]] = {}
    try:
        names = sorted(os.listdir(LAB_REPORTS))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".md"):
            continue
        try:
            with open(os.path.join(LAB_REPORTS, n), encoding="utf-8", errors="replace") as fh:
                head = fh.read(4000)
        except OSError:
            continue
        m = re.search(r"\*\*strategy\*\*: `([^`]+)`", head)
        if m:
            out.setdefault(m.group(1), []).append(n[:-3])
    return out


def inspect(name: str) -> dict:
    """name/symbols/lookback/params via the engine's own inspector (cached by mtime)."""
    p = strategy_path(name)
    mt = os.path.getmtime(p)
    hit = _inspect_cache.get(name)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        r = subprocess.run([sys.executable, INSPECTOR, p], capture_output=True, text=True,
                           timeout=60, cwd=ENGINE)
        info = json.loads(r.stdout or "{}")
    except Exception as exc:                               # noqa: BLE001
        info = {"error": str(exc)[:300]}
    _inspect_cache[name] = (mt, info)
    return info


def strategies() -> list[dict]:
    doss = _dossiers()
    rows = []
    for n in sorted(os.listdir(STRATS)):
        if not n.endswith(".py") or n.startswith("_"):
            continue
        info = inspect(n)
        rows.append({"name": n, "kind": kind_of(n), "strategy": info.get("name"),
                     "symbols": info.get("symbols") or [], "lookback": info.get("lookback"),
                     "params": info.get("params") or {}, "error": info.get("error"),
                     "dossiers": doss.get(n, [])})
    return rows


def data_status() -> dict:
    """Which symbols have history and how far it reaches."""
    out = {}
    try:
        for n in sorted(os.listdir(DATA)):
            if not n.endswith(".csv"):
                continue
            p = os.path.join(DATA, n)
            try:
                with open(p, "rb") as fh:
                    fh.seek(0, 2)
                    size = fh.tell()
                    fh.seek(max(0, size - 200))
                    tail = fh.read().decode(errors="replace").strip().splitlines()
                last = tail[-1].split(",")[0] if tail else "?"
            except OSError:
                last = "?"
            out[n[:-4]] = last
    except OSError:
        pass
    return out


# ----------------------------------------------------------------------------- results
def _downsample(curve: list[dict], n: int = MAX_POINTS) -> list[dict]:
    if len(curve) <= n:
        return curve
    step = len(curve) / n
    picked = [curve[int(i * step)] for i in range(n)]
    if picked[-1] is not curve[-1]:
        picked.append(curve[-1])
    return picked


def _index_path() -> str:
    return os.path.join(OUT, "index.json")


def _load_index() -> list[dict]:
    try:
        with open(_index_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_index(rows: list[dict]) -> None:
    os.makedirs(OUT, exist_ok=True)
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows[-500:], fh)
    os.replace(tmp, _index_path())


def _upsert(row: dict) -> None:
    with _lock:
        rows = [r for r in _load_index() if r.get("id") != row["id"]]
        rows.append(row)
        _save_index(rows)


def results() -> list[dict]:
    return sorted(_load_index(), key=lambda r: r.get("created", ""), reverse=True)


def round_trips(fills: list[dict]) -> list[dict]:
    """Pair buys and sells per symbol, FIFO, into round trips - what the
    strategy actually did. A partial exit closes part of the oldest lot; a
    position still held at the end is listed as open. P&L nets both
    commissions. Newest first."""
    from collections import defaultdict
    lots: dict[str, list] = defaultdict(list)          # symbol -> [entry lots]
    trips: list[dict] = []
    for f in fills or []:
        sym, side = f.get("symbol"), f.get("side")
        qty, px = float(f.get("qty") or 0), float(f.get("price") or 0)
        comm, rule = float(f.get("commission") or 0), str(f.get("rule") or "")
        if qty <= 0 or px <= 0:
            continue
        if side == "buy":
            lots[sym].append({"date": f.get("date"), "px": px, "qty": qty, "comm": comm, "rule": rule})
            continue
        remaining = qty
        while remaining > 1e-9 and lots[sym]:
            lot = lots[sym][0]
            m = min(remaining, lot["qty"])
            share_in = lot["comm"] * (m / lot["qty"]) if lot["qty"] else 0.0
            share_out = comm * (m / qty)
            pnl = m * (px - lot["px"]) - share_in - share_out
            trips.append({"symbol": sym, "qty": round(m, 3), "entry_date": lot["date"],
                          "entry_px": round(lot["px"], 4), "entry_rule": lot["rule"],
                          "exit_date": f.get("date"), "exit_px": round(px, 4), "exit_rule": rule,
                          "pnl_usd": round(pnl, 2),
                          "pnl_pct": round(pnl / (m * lot["px"]) * 100, 3) if lot["px"] else None,
                          "open": False})
            remaining -= m
            lot["qty"] -= m
            lot["comm"] -= share_in
            if lot["qty"] <= 1e-9:
                lots[sym].pop(0)
    for sym, ls in lots.items():
        for lot in ls:
            trips.append({"symbol": sym, "qty": round(lot["qty"], 3), "entry_date": lot["date"],
                          "entry_px": round(lot["px"], 4), "entry_rule": lot["rule"],
                          "exit_date": None, "exit_px": None, "exit_rule": None,
                          "pnl_usd": None, "pnl_pct": None, "open": True})
    trips.sort(key=lambda t: (t["entry_date"] or "", t["exit_date"] or "9999"), reverse=True)
    for i, t in enumerate(trips):
        t["n"] = len(trips) - i
    return trips


def _runner_metrics(curve: list[dict], capital: float) -> dict:
    """The engine runner's own metric function, applied to any equity curve — so
    SPY buy-and-hold is scored by exactly the code that scores the strategy."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_bt_runner_", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                      # type: ignore[union-attr]
        return mod._compute_metrics(curve, [], float(capital)) or {}
    except Exception:                                      # noqa: BLE001
        return {}


def versus_spy(metrics: dict, bench: dict, curve: list[dict], bcurve: list[dict]) -> dict:
    """Apples to apples: the same capital, the same window, in SPY instead."""
    def d(k):
        a, b = metrics.get(k), bench.get(k)
        return round(a - b, 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
    return {"final_equity": (curve[-1]["equity"] if curve else None),
            "final_spy": (bcurve[-1]["equity"] if bcurve else None),
            "d_total_return": d("total_return"), "d_cagr": d("cagr"),
            "d_max_drawdown": d("max_drawdown"), "d_sharpe": d("sharpe_ratio")}


def get(bt_id: str) -> dict | None:
    if not re.fullmatch(r"[a-f0-9]{12}", bt_id or ""):
        return None
    try:
        with open(os.path.join(OUT, f"{bt_id}.json"), encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    if rec.get("status") == "done" and "benchmark_metrics" not in rec:
        # older result: score the stored (downsampled) SPY curve on the spot
        cap = float((rec.get("options") or {}).get("initial_capital") or 100_000.0)
        rec["benchmark_metrics"] = _runner_metrics(rec.get("benchmark_curve") or [], cap)
        rec["benchmark_metrics"]["approximate"] = True
        rec["vs_spy"] = versus_spy(rec.get("metrics") or {}, rec["benchmark_metrics"],
                                   rec.get("equity_curve") or [], rec.get("benchmark_curve") or [])
    return rec


def delete(bt_id: str) -> bool:
    """Remove a stored result and its index row. A run still in flight keeps
    its index row until it finishes writing; deleting it then is fine too."""
    if not re.fullmatch(r"[a-f0-9]{12}", bt_id or ""):
        raise ValueError("bad backtest id")
    with _lock:
        rows = _load_index()
        keep = [r for r in rows if r.get("id") != bt_id]
        found = len(keep) != len(rows)
        _save_index(keep)
    try:
        os.remove(os.path.join(OUT, f"{bt_id}.json"))
        found = True
    except OSError:
        pass
    return found


def run_sync(name: str, options: dict) -> dict:
    """Run the engine runner as a subprocess (exactly how the Rust API server calls it)."""
    p = strategy_path(name)
    opts = {}
    for k in ("start_date", "end_date"):
        v = str(options.get(k) or "").strip()
        if v:
            datetime.date.fromisoformat(v)             # validates
            opts[k] = v
    opts["initial_capital"] = float(options.get("initial_capital") or 100_000.0)
    opts["slippage_bps"] = int(options.get("slippage_bps", 5))
    opts["commission_bps"] = int(options.get("commission_bps", 5))
    over = options.get("param_overrides") or {}
    if isinstance(over, dict):
        opts["param_overrides"] = {str(k)[:60]: v for k, v in over.items()
                                   if isinstance(v, (int, float, str)) and str(k)}
    t0 = time.time()
    r = subprocess.run([sys.executable, RUNNER, p, DATA, json.dumps(opts)],
                       capture_output=True, text=True, timeout=900, cwd=ENGINE)
    try:
        res = json.loads(r.stdout or "{}")
    except ValueError:
        res = {"error": f"runner produced no JSON (rc={r.returncode}): {r.stderr[-400:]}"}
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["options"] = opts
    return res


def run(name: str, options: dict, who: str = "operator") -> str:
    """Start a backtest; the result file appears when it finishes."""
    strategy_path(name)
    bt_id = uuid.uuid4().hex[:12]
    created = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    row = {"id": bt_id, "strategy": name, "kind": kind_of(name), "created": created,
           "status": "running", "by": who, "options": options}
    _upsert(row)

    def work():
        try:
            res = run_sync(name, options)
        except Exception as exc:                           # noqa: BLE001
            res = {"error": str(exc)[:500]}
        bench = _runner_metrics(res.get("benchmark_curve") or [],
                                float((res.get("options") or {}).get("initial_capital") or 100_000.0))
        rec = {"id": bt_id, "strategy": name, "kind": kind_of(name), "created": created,
               "by": who, "options": res.get("options", options),
               "status": "error" if res.get("error") else "done",
               "error": res.get("error"), "metrics": res.get("metrics") or {},
               "benchmark_metrics": bench,
               "vs_spy": versus_spy(res.get("metrics") or {}, bench, res.get("equity_curve") or [],
                                    res.get("benchmark_curve") or []),
               "params": res.get("params") or {}, "elapsed_s": res.get("elapsed_s"),
               "fills": len(res.get("fills") or []),
               "trades": round_trips(res.get("fills") or []),
               "equity_curve": _downsample(res.get("equity_curve") or []),
               "benchmark_curve": _downsample(res.get("benchmark_curve") or []),
               "final_weights": res.get("final_weights") or {},
               "universe": res.get("universe") or []}
        os.makedirs(OUT, exist_ok=True)
        tmp = os.path.join(OUT, f"{bt_id}.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        os.replace(tmp, os.path.join(OUT, f"{bt_id}.json"))
        summary = {k: rec[k] for k in ("id", "strategy", "kind", "created", "by", "status",
                                       "error", "metrics", "params", "elapsed_s", "fills",
                                       "options", "benchmark_metrics", "vs_spy")}
        _upsert(summary)

    threading.Thread(target=work, name=f"bt-{bt_id}", daemon=True).start()
    return bt_id


if __name__ == "__main__":                                   # python agent/backtests.py <file>
    if len(sys.argv) > 1:
        out = run_sync(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
        print(json.dumps({k: out.get(k) for k in ("metrics", "params", "error", "elapsed_s",
                                                   "final_weights", "last_bar_date")}, indent=1))
    else:
        for s in strategies():
            print(f"{s['kind']:10} {s['name']:40} {len(s['params'])} params  "
                  f"dossiers={s['dossiers']}")

"""Rule-improvement sweep for edgestack, driven through TrustyRustyEngine's own runner.

Overfit guard: parameters are explored on a TRAIN window and the finalists re-run on a
disjoint VALIDATION window. A rule change only counts as an improvement if it survives
validation.

  TRAIN      2007-01..2017-12  (warmup eats ~1y -> effective ~2008-04..2017-12, incl. GFC)
  VALIDATE   2017-01..2026-04  (warmup eats 2017 -> effective 2018-01..2026-04)

Engine defaults kept: 5bps slippage + 5bps commission per side (their realism, not ours).

Specific prediction under test: with the engine's T+1-open fills, vol_floor=1.8 should beat
1.4 (delay study: the 1.4-1.8x tier inverts on next-open entry). If the sweep disagrees,
that is reportable either way.
"""
import io
import json
import math
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python_strategies"))
from run_backtest import run_backtest  # noqa: E402  (the engine's own tool)

STRAT = str(ROOT / "python_strategies" / "strategies" / "edgestack.py")
DATA = str(ROOT / "data" / "historical")

TRAIN = {"start_date": "2007-01-01", "end_date": "2017-12-31"}
VALID = {"start_date": "2017-01-01", "end_date": "2026-04-30"}


def run(window, overrides):
    opts = dict(window)
    opts["initial_capital"] = 100000.0
    opts["param_overrides"] = overrides
    t0 = time.time()
    res = run_backtest(STRAT, DATA, opts)
    if res.get("error"):
        return {"error": res["error"][:200], "secs": time.time() - t0}
    m = res["metrics"]
    # annualised vol from the equity curve (metrics do not include it)
    eq = [e["equity"] for e in res["equity_curve"]]
    rets = [(eq[i] - eq[i - 1]) / eq[i - 1] for i in range(1, len(eq)) if eq[i - 1] > 0]
    n = len(rets)
    mu = sum(rets) / n
    vol = math.sqrt(sum((r - mu) ** 2 for r in rets) / (n - 1)) * math.sqrt(252)
    return {"cagr": m["cagr"], "sharpe": m["sharpe_ratio"], "dd": m["max_drawdown"],
            "vol": vol, "trades": m["total_trades"], "win": m["win_rate"],
            "secs": round(time.time() - t0, 1)}


def show(tag, r):
    if "error" in r:
        print(f"  {tag:<44} ERROR {r['error']}")
        return
    print(f"  {tag:<44} CAGR {100*r['cagr']:>6.2f}%  vol {100*r['vol']:>5.2f}%  "
          f"Sharpe {r['sharpe']:>5.2f}  DD {100*r['dd']:>5.1f}%  "
          f"trades {r['trades']:>4}  ({r['secs']}s)")


RUNS = []


def do(tag, window, overrides):
    r = run(window, overrides)
    show(tag, r)
    RUNS.append((tag, overrides, r))
    return r


print("=" * 100)
print("PHASE 1 — BASELINES, TRAIN window")
print("=" * 100)
do("B0 SPY-ish buy&hold (core always, no sleeve)", TRAIN,
   {"core_mode": 2, "core_weight": 0.98, "sleeve_weight": 0.0})
do("B1 trend core only", TRAIN,
   {"core_mode": 1, "core_weight": 0.98, "sleeve_weight": 0.0})
do("B2 sleeve only", TRAIN,
   {"core_mode": 0, "sleeve_weight": 0.5, "max_total_sleeve": 1.0})
do("B3 default combo (core .7 / sleeve .3)", TRAIN, {})

print()
print("=" * 100)
print("PHASE 2 — ONE-AXIS-AT-A-TIME from the default, TRAIN window")
print("=" * 100)
print("-- the vol_floor prediction (engine fills at next open -> 1.8 should beat 1.4):")
do("vol_floor 1.4", TRAIN, {"vol_floor": 1.4})
do("vol_floor 1.8 (default)", TRAIN, {})
print("-- stretch trigger:")
do("stretch -2.0", TRAIN, {"stretch_trigger": -2.0})
do("stretch -3.0", TRAIN, {"stretch_trigger": -3.0})
print("-- hold:")
do("hold 2", TRAIN, {"hold_sessions": 2})
do("hold 5", TRAIN, {"hold_sessions": 5})
print("-- sleeve size:")
do("sleeve .2/.4", TRAIN, {"sleeve_weight": 0.2, "max_total_sleeve": 0.4})
do("sleeve .5/1.0", TRAIN, {"sleeve_weight": 0.5, "max_total_sleeve": 1.0})
print("-- core:")
do("core_weight .5", TRAIN, {"core_weight": 0.5})
do("core_weight .98", TRAIN, {"core_weight": 0.98})
do("core always-on (mode 2)", TRAIN, {"core_mode": 2})
print("-- calm-bond gate on sleeve:")
do("calm filter ON", TRAIN, {"use_calm_filter": 1})

json.dump([(t, o, r) for t, o, r in RUNS], open("C:/tmp/sweep_train.json", "w"), indent=1)
print()
print("train results saved; run phase 3 after inspecting")

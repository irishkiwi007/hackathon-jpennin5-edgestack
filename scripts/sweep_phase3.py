import io, json, math, sys, time
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "python_strategies"))
from run_backtest import run_backtest
STRAT = str(ROOT / "python_strategies" / "strategies" / "edgestack.py")
DATA = str(ROOT / "data" / "historical")
TRAIN = {"start_date": "2007-01-01", "end_date": "2017-12-31"}
VALID = {"start_date": "2017-01-01", "end_date": "2026-04-30"}

def run(window, overrides):
    opts = dict(window); opts["initial_capital"] = 100000.0; opts["param_overrides"] = overrides
    res = run_backtest(STRAT, DATA, opts)
    if res.get("error"): return {"error": res["error"][:200]}
    m = res["metrics"]
    eq = [e["equity"] for e in res["equity_curve"]]
    rets = [(eq[i]-eq[i-1])/eq[i-1] for i in range(1,len(eq)) if eq[i-1] > 0]
    mu = sum(rets)/len(rets)
    vol = math.sqrt(sum((r-mu)**2 for r in rets)/(len(rets)-1))*math.sqrt(252)
    return {"cagr": m["cagr"], "sharpe": m["sharpe_ratio"], "dd": m["max_drawdown"], "vol": vol}

def show(tag, r):
    if "error" in r: print(f"  {tag:<40} ERROR {r['error']}"); return
    print(f"  {tag:<40} CAGR {100*r['cagr']:>6.2f}%  vol {100*r['vol']:>5.2f}%  "
          f"Sharpe {r['sharpe']:>5.2f}  DD {100*r['dd']:>5.1f}%")

CONFIGS = {
  "B1 trend core only": {"core_mode":1,"core_weight":0.98,"sleeve_weight":0.0},
  "B3 default": {},
  "C1 str-2.0 slv.5": {"stretch_trigger":-2.0,"sleeve_weight":0.5,"max_total_sleeve":1.0},
  "C2 C1 + hold5": {"stretch_trigger":-2.0,"sleeve_weight":0.5,"max_total_sleeve":1.0,"hold_sessions":5},
  "C3 C1 + core.98": {"stretch_trigger":-2.0,"sleeve_weight":0.5,"max_total_sleeve":1.0,"core_weight":0.98},
  "C4 C1 + calm": {"stretch_trigger":-2.0,"sleeve_weight":0.5,"max_total_sleeve":1.0,"use_calm_filter":1},
  "C1 with vol_floor 1.4": {"stretch_trigger":-2.0,"sleeve_weight":0.5,"max_total_sleeve":1.0,"vol_floor":1.4},
}
print("="*100); print("PHASE 3 — COMBINED CONFIGS, TRAIN (2008-2017 effective)"); print("="*100)
for tag,ov in CONFIGS.items(): show(tag, run(TRAIN, ov))
print(); print("="*100); print("VALIDATION (2018-2026 effective) — the only table that counts"); print("="*100)
for tag,ov in CONFIGS.items(): show(tag, run(VALID, ov))

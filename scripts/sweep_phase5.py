import io, math, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "python_strategies"))
from run_backtest import run_backtest
STRAT = str(ROOT/"python_strategies"/"strategies"/"edgestack.py"); DATA = str(ROOT/"data"/"historical")
WINDOWS = (("TRAIN", {"start_date":"2007-01-01","end_date":"2017-12-31"}),
           ("VALID", {"start_date":"2017-01-01","end_date":"2026-04-30"}),
           ("FULL ", {"start_date":"2007-01-01","end_date":"2026-04-30"}))
def run(w, ov):
    o = dict(w); o["initial_capital"]=100000.0; o["param_overrides"]=ov
    r = run_backtest(STRAT, DATA, o)
    if r.get("error"): return None
    m=r["metrics"]; eq=[e["equity"] for e in r["equity_curve"]]
    rt=[(eq[i]-eq[i-1])/eq[i-1] for i in range(1,len(eq)) if eq[i-1]>0]
    mu=sum(rt)/len(rt); vol=math.sqrt(sum((x-mu)**2 for x in rt)/(len(rt)-1))*math.sqrt(252)
    return m["cagr"], vol, m["sharpe_ratio"], m["max_drawdown"]
CONFIGS = [
  ("B3 baseline",            {}),
  ("G1 credit canary",       {"gate_mode":1}),
  ("G1 + trailing stop",     {"gate_mode":1,"use_trailing_stop":1}),
  ("G1 + calm sleeve",       {"gate_mode":1,"use_calm_filter":1}),
  ("G1 + TS + calm",         {"gate_mode":1,"use_trailing_stop":1,"use_calm_filter":1}),
]
for wname, w in WINDOWS:
    print("="*96); print(wname); print("="*96)
    for tag, ov in CONFIGS:
        r = run(w, ov)
        if r is None: print(f"  {tag:<26} ERROR"); continue
        c,v,s,d = r
        print(f"  {tag:<26} CAGR {100*c:6.2f}%  vol {100*v:5.2f}%  Sharpe {s:5.2f}  DD {100*d:5.1f}%")
    print()

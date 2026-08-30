import io, math, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "python_strategies"))
from run_backtest import run_backtest
STRAT = str(ROOT/"python_strategies"/"strategies"/"edgestack.py"); DATA = str(ROOT/"data"/"historical")
TRAIN = {"start_date":"2007-01-01","end_date":"2017-12-31"}
VALID = {"start_date":"2017-01-01","end_date":"2026-04-30"}
def run(w, ov):
    o = dict(w); o["initial_capital"]=100000.0; o["param_overrides"]=ov
    r = run_backtest(STRAT, DATA, o)
    if r.get("error"): return None
    m=r["metrics"]; eq=[e["equity"] for e in r["equity_curve"]]
    rt=[(eq[i]-eq[i-1])/eq[i-1] for i in range(1,len(eq)) if eq[i-1]>0]
    mu=sum(rt)/len(rt); vol=math.sqrt(sum((x-mu)**2 for x in rt)/(len(rt)-1))*math.sqrt(252)
    return m["cagr"], vol, m["sharpe_ratio"], m["max_drawdown"]
CONFIGS = [
  ("B3 regression (v1 defaults)", {}),
  ("R1 riskoff -> defensives",    {"riskoff_mode":1}),
  ("R2 riskoff -> def+gold",      {"riskoff_mode":2}),
  ("G1 gate: +credit canary",     {"gate_mode":1}),
  ("G2 gate: +FDN canary",        {"gate_mode":2}),
  ("G3 gate: +divergence",        {"gate_mode":3}),
  ("G4 gate: all canaries",       {"gate_mode":4}),
  ("G6 gate: trend&risk_on",      {"gate_mode":6}),
  ("W5 weekly gate cadence",      {"gate_cadence":5}),
  ("TS trailing stop 15%",        {"use_trailing_stop":1}),
  ("SN sniper entries union",     {"sniper_mode":1}),
]
res = {}
for wname, w in (("TRAIN", TRAIN), ("VALID", VALID)):
    print("="*98); print(f"{wname}  (baseline to beat: B3 = 0.80 train / 0.65 valid, DD 15.0/21.2)"); print("="*98)
    for tag, ov in CONFIGS:
        r = run(w, ov)
        if r is None: print(f"  {tag:<34} ERROR"); continue
        c,v,s,d = r; res[(wname,tag)] = r
        print(f"  {tag:<34} CAGR {100*c:6.2f}%  vol {100*v:5.2f}%  Sharpe {s:5.2f}  DD {100*d:5.1f}%")
    print()

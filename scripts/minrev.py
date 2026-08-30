import json,os,subprocess,sys,io,datetime,math
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
A=r'C:\Users\Lenovo\go\bin\alpaca.exe'; env=dict(os.environ)
def run(a):
    r=subprocess.run([A]+a+['--quiet'],capture_output=True,text=True,env=env)
    if r.returncode!=0: return None
    try: return json.loads(r.stdout)
    except Exception: return None
# 1-min SIP bars over ~3 months
out,tok=[],None
while True:
    a=['data','bars','--symbol','SPY','--timeframe','1Min','--feed','sip',
       '--start','2026-06-01T13:30:00Z','--end','2026-08-28T20:00:00Z','--limit','10000']
    if tok: a+=['--page-token',tok]
    d=run(a)
    if not d: break
    out+=d.get('bars') or []
    tok=d.get('next_page_token')
    if not tok: break
print(f'1-min bars: {len(out)}  {out[0]["t"][:10]} -> {out[-1]["t"][:10]}')
# group by session, regular hours only
from collections import defaultdict
sess=defaultdict(list)
for b in out:
    t=datetime.datetime.fromisoformat(b['t'].replace('Z','+00:00'))
    if 13*60+30 <= t.hour*60+t.minute < 20*60:
        sess[b['t'][:10]].append((t,b['c'],b['vw']))
print(f'sessions: {len(sess)}')
rng=np.random.default_rng(3)
def ac1(x):
    r=np.diff(np.log(x)); r=r[np.isfinite(r)]
    if len(r)<30 or r.std()==0: return None
    r=r-r.mean()
    return float((r[:-1]*r[1:]).sum()/(r*r).sum())
print('\nWITHIN-SESSION lag-1 autocorrelation of 1-min returns (close vs VWAP)')
print(f'{"agg":>6} {"n sessions":>11} {"close AC1":>11} {"vwap AC1":>10} {"surrogate 95% band":>26}')
for agg in (1,2,5,10,15,30):
    cs,vs=[],[]
    sur=[]
    for day,rows_ in sess.items():
        if len(rows_)<60: continue
        c=np.array([x[1] for x in rows_]); v=np.array([x[2] for x in rows_])
        ca=np.array([c[i] for i in range(0,len(c),agg)])
        va=np.array([v[i] for i in range(0,len(v),agg)])
        a1=ac1(ca); a2=ac1(va)
        if a1 is not None: cs.append(a1)
        if a2 is not None: vs.append(a2)
        r=np.diff(np.log(ca))
        if len(r)>30:
            sh=rng.permutation(r)
            p=np.exp(np.concatenate([[0],np.cumsum(sh)]))
            s=ac1(p)
            if s is not None: sur.append(s)
    if not cs: continue
    lo,hi=np.percentile(sur,[2.5,97.5]) if len(sur)>20 else (float('nan'),float('nan'))
    n=len(cs)
    se=np.std(cs)/math.sqrt(n)
    print(f'{agg:>5}m {n:>11} {np.mean(cs):>+11.4f} {np.mean(vs):>+10.4f}   [{lo:+.4f}, {hi:+.4f}]  (se {se:.4f})')
print("""
CLOSE prices are last-TRADE prints -> exposed to bid-ask bounce.
VWAP is volume-weighted over the minute -> averages across bid and ask, much less bounce.
If close shows far more reversion than vwap, the difference is microstructure, not signal.""")

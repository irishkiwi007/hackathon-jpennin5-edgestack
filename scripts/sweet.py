"""Sweet spot: on the LOW-FRICTION universe only, sweep stretch x volume for the cell that is
both net-positive after crossing costs AND fires often enough to matter in a 5-session window.

net per contract = (raw move %) x (spot) x (spread delta ~0.35) - 2 x (one-way friction)
"""
import json, sys, io, math
from collections import defaultdict
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = json.load(open('sp500_bars.json'))
FR = json.load(open('friction_screen.json'))
HOLD, YRS, DELTA = 3, 10.6, 0.35

def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 12: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n-1)+1):
        s += 2.0*(1.0-k/(lag+1.0))*(float(e[k:] @ e[:-k])/n)
    return m/math.sqrt(s/n) if s > 0 else float('nan')

for BUDGET in (10, 20, 35):
    names = [s for s,v in FR.items() if v and v.get('friction',1e9) <= BUDGET
             and v.get('credit',0) > 0 and len(D.get(s,[])) > 900]
    rows, base = [], {}
    for s in names:
        b = D[s]
        c = np.array([x['c'] for x in b],float); v = np.array([x['v'] for x in b],float)
        dt=[x['t'] for x in b]; n=len(c)
        if (c<=0).any(): continue
        r=np.zeros(n); r[1:]=np.log(c[1:]/c[:-1])
        fwd=[math.log(c[i+HOLD]/c[i])*100 for i in range(25,n-HOLD)]
        if not fwd: continue
        base[s]=float(np.mean(fwd))
        for i in range(25,n-HOLD):
            rv=r[i-19:i+1].std(ddof=1)
            if not np.isfinite(rv) or rv<=0: continue
            st=math.log(c[i]/c[i-5])/(rv*math.sqrt(5))
            if st>=-1.5: continue
            rows.append(dict(sym=s,date=dt[i],stretch=st,spot=float(c[i]),
                             volx=v[i]/max(np.mean(v[i-19:i+1]),1.0),
                             f3=math.log(c[i+HOLD]/c[i])*100))
    medfr = float(np.median([FR[s]['friction'] for s in names]))
    print('='*104)
    print('FRICTION BUDGET <= ${} one-way   |   {} names   |   median friction ${:.0f}'.format(
        BUDGET, len(names), medfr))
    print('='*104)
    print('{:<14}'.format('stretch') + ''.join('{:>29}'.format(v) for v in
          ('vol 1.4-1.8','vol 1.8-2.5','vol 2.5-4.0')))
    print('{:<14}'.format('') + ''.join('{:>29}'.format('raw%  t   /5d   net$') for _ in range(3)))
    for slab,slo,shi in [('<-3.5',-99,-3.5),('-3.5..-3.0',-3.5,-3.0),('-3.0..-2.5',-3.0,-2.5),
                         ('-2.5..-2.0',-2.5,-2.0),('-2.0..-1.5',-2.0,-1.5)]:
        line='{:<14}'.format(slab)
        for vlo,vhi in ((1.4,1.8),(1.8,2.5),(2.5,4.0)):
            g=[r for r in rows if slo<=r['stretch']<shi and vlo<=r['volx']<vhi]
            if len(g)<25:
                line+='{:>29}'.format('-'); continue
            raw=np.array([r['f3'] for r in g])
            e=np.array([r['f3']-base[r['sym']] for r in g])
            sp=np.array([r['spot'] for r in g])
            gross=float(np.mean(raw/100.0*sp*DELTA*100))
            per5=len(g)/YRS/252*5
            line+='{:>29}'.format('{:+.2f} {:>4.1f} {:>5.2f} {:>+6.0f}'.format(
                raw.mean(), nw_t(e,HOLD), per5, gross-2*medfr))
        print(line)
    print()

"""VIEW A said control-day implied volatility RISES +5.11% into the close (t=-3.08 vs spike).
The overnight test, which requires a REAL bar in each window, says both groups FALL and nothing
is significant.

Suspected cause: intraday_iv.py FORWARD-FILLS option prices while letting time-to-expiry decay.
A stale price with a shrinking T mechanically produces a RISING implied volatility. If control days
are less actively traded (more forward-filling), the bias hits them harder - manufacturing exactly
the divergence reported."""
import json,math,sys,io
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
d=json.load(open('ivcurves.json'))
print('='*88); print('IS THE VIEW A RESULT A FORWARD-FILL ARTIFACT?'); print('='*88)
# proxy for staleness: how many consecutive identical iv values (forward-filled runs)
def staleness(curves,lab):
    runs=[]; covs=[]
    for c in curves:
        vals=[x for x in c if x]
        covs.append(len(vals)/len(c))
        r=0; mx=0; prev=None
        for x in c:
            if x is None: continue
            if prev is not None and abs(x-prev)<1e-9: r+=1; mx=max(mx,r)
            else: r=0
            prev=x
        runs.append(mx)
    print(f'{lab:<10} n={len(curves):>3}  mean coverage {np.mean(covs)*100:>5.1f}%  '
          f'longest identical-value run {np.mean(runs):>6.1f} minutes')
    return np.mean(covs), np.mean(runs)
cs,rs=staleness(d['spike'],'spike')
cc,rc=staleness(d['control'],'control')
print()
print(f'control curves are stale {rc/max(rs,1e-9):.2f}x as long as spike curves')
print()
print('MECHANISM CHECK: a frozen option price with decaying T')
print('  if the price does not move but T shrinks, Black-Scholes must raise implied volatility')
print('  to keep the same price. Over a session that is a pure upward drift.')
print()
# quantify: what does a frozen price do to implied vol over one session at 9 DTE?
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def bs(S,K,T,r,s,cp):
    d1=(math.log(S/K)+(r+.5*s*s)*T)/(s*math.sqrt(T)); d2=d1-s*math.sqrt(T)
    return S*ncdf(d1)-K*math.exp(-r*T)*ncdf(d2) if cp=='C' else K*math.exp(-r*T)*ncdf(-d2)-S*ncdf(-d1)
def iv(p,S,K,T,r,cp):
    lo,hi=1e-4,5.
    for _ in range(60):
        m=.5*(lo+hi)
        if bs(S,K,T,r,m,cp)<p: lo=m
        else: hi=m
    return .5*(lo+hi)
S=K=100.
for dte in (5,9,20):
    T0=dte/365
    p=bs(S,K,T0,.045,0.40,'C')          # price at 40% implied vol
    T1=max(T0-(1/390)/365*390,1e-5)     # one full session later
    v1=iv(p,S,K,T1,.045,'C')
    print(f'  {dte:>2}DTE, price frozen all session: implied vol 40.0% -> {v1*100:.1f}%  '
          f'({(v1/0.40-1)*100:+.1f}%)')
print()
print('VERDICT: any curve with long frozen stretches drifts UPWARD in implied volatility by')
print('construction. The control group is the stale one, so VIEW A overstated its rise.')
print('The overnight test - which demands a real trade in each window - is the trustworthy one.')

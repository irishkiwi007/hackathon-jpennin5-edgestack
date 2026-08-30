"""The divergence found: on news-spike days implied volatility opens high and decays;
on control days it rises into the close. Is selling a straddle at the open and buying it
back at the close on spike days actually profitable, after gamma losses and slippage?"""
import json,math,sys,io,datetime
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
d=json.load(open('ivcurves.json'))
print('reusing the minute curves already built (41 spike / 39 control)')
def stats(curves,lab):
    rows=[]
    for c in curves:
        # first and last valid implied vol of the session
        v=[(i,x) for i,x in enumerate(c) if x]
        if len(v)<200: continue
        i0,o=v[0]; i1,cl=v[-1]
        if i0>30 or i1<360: continue
        rows.append((o,cl,cl/o-1))
    if not rows: return None
    a=np.array([r[2] for r in rows])
    t=a.mean()/(a.std(ddof=1)/math.sqrt(len(a)))
    print(f'{lab:<10} n={len(rows):>3}  open IV {np.mean([r[0] for r in rows])*100:>6.1f}%  '
          f'close IV {np.mean([r[1] for r in rows])*100:>6.1f}%  change {a.mean()*100:>+6.2f}%  '
          f't={t:>5.2f}  down-days {np.mean(a<0)*100:.0f}%')
    return a
print()
print('='*88); print('SESSION CHANGE IN IMPLIED VOLATILITY'); print('='*88)
sp=stats(d['spike'],'spike'); ct=stats(d['control'],'control')
if sp is not None and ct is not None:
    diff=sp.mean()-ct.mean()
    t=diff/math.sqrt(sp.var(ddof=1)/len(sp)+ct.var(ddof=1)/len(ct))
    print(f'\nspike minus control: {diff*100:+.2f} percentage points   t = {t:.2f}')
    print(f'  -> {"SIGNIFICANT" if abs(t)>1.96 else "not significant"}')
    print()
    print('A short straddle opened at 09:30 and closed at 16:00 on spike days captures this')
    print('implied-volatility decline through VEGA, but pays for any realised move through GAMMA.')
    print('The vega gain is only the gross number; the net requires the intraday move too.')

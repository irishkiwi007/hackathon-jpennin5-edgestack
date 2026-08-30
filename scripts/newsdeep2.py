import json,math,sys,io
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
LOOK=20
cache=json.load(open('newscache.json'))
ROWS=[]
for s,D in cache.items():
    bars=D['bars']; cnt=D['cnt']
    dts=[b['t'] for b in bars]; px=np.array([b['c'] for b in bars])
    counts=np.array([cnt.get(d,0) for d in dts],dtype=float); n=len(px)
    for i in range(LOOK+6,n-21):
        w=counts[i-LOOK:i]; mu,sd=w.mean(),w.std(ddof=1)
        if sd<0.5 or mu<0.5: continue
        ret=np.diff(np.log(px[i-20:i+1])); rv=ret.std(ddof=1)*math.sqrt(252)
        if rv<=0: continue
        r=dict(sym=s,date=dts[i],nz=(counts[i]-mu)/sd,rv=rv,past5=math.log(px[i]/px[i-5]))
        for h in (1,3,5):
            if i+h<n:
                r[f'f{h}']=math.log(px[i+h]/px[i]); r[f'a{h}']=abs(r[f'f{h}'])
                r[f'n{h}']=abs(r[f'f{h}'])/(rv/math.sqrt(252)*math.sqrt(h))
        ROWS.append(r)
print(f'observations {len(ROWS)}')

print('\n'+'='*100)
print('A. PER-SYMBOL: does a coverage spike raise the VOL-NORMALISED move? (nz>=1.0)')
print('='*100)
print(f'{"sym":>7} {"n spike":>8} {"n rest":>8} {"spike norm":>11} {"rest norm":>10} {"ratio":>7} {"t":>7}')
bysym=defaultdict(list)
for r in ROWS: bysym[r['sym']].append(r)
pos=0; tot=0
for s,rs in sorted(bysym.items()):
    sp=np.array([r['n1'] for r in rs if r['nz']>=1.0 and 'n1' in r])
    rest=np.array([r['n1'] for r in rs if r['nz']<1.0 and 'n1' in r])
    if len(sp)<40: print(f'{s:>7} {len(sp):>8}  (thin)'); continue
    diff=sp.mean()-rest.mean()
    t=diff/math.sqrt(sp.var(ddof=1)/len(sp)+rest.var(ddof=1)/len(rest))
    tot+=1; pos+= 1 if diff>0 else 0
    print(f'{s:>7} {len(sp):>8} {len(rest):>8} {sp.mean():>11.3f} {rest.mean():>10.3f} {sp.mean()/rest.mean():>7.3f} {t:>7.2f}')
print(f'\npositive in {pos} of {tot} symbols  <-- the sign-consistency test')

print('\n'+'='*100)
print('B. PER-SYMBOL: DIRECTIONAL continuation score (nz>=1.0, f3)')
print('='*100)
print(f'{"sym":>7} {"n":>6} {"cont score":>12} {"up t":>7} {"dn t":>7}')
signs=[]
for s,rs in sorted(bysym.items()):
    g=[r for r in rs if r['nz']>=1.0 and 'f3' in r]
    if len(g)<40: print(f'{s:>7} {len(g):>6}  (thin)'); continue
    base=np.mean([r['f3'] for r in g])
    up=[r['f3'] for r in g if r['past5']>0]; dn=[r['f3'] for r in g if r['past5']<=0]
    if len(up)<15 or len(dn)<15: print(f'{s:>7} {len(g):>6}  (thin split)'); continue
    up,dn=np.array(up),np.array(dn)
    ue=up.mean()-base; de=dn.mean()-base
    ut=ue/(up.std(ddof=1)/math.sqrt(len(up))); dt=de/(dn.std(ddof=1)/math.sqrt(len(dn)))
    signs.append(ue-de)
    print(f'{s:>7} {len(g):>6} {(ue-de)*100:>+12.3f} {ut:>7.2f} {dt:>7.2f}')
if signs: print(f'\ncontinuation (positive) in {sum(1 for x in signs if x>0)} of {len(signs)} symbols')

print('\n'+'='*100)
print('C. INDEPENDENCE CHECK — how correlated are these 8 names? (pooling inflates t)')
print('='*100)
dates=sorted(set(r['date'] for r in ROWS))
M={}
for s,rs in bysym.items():
    d={r['date']:r.get('f1') for r in rs if 'f1' in r}
    M[s]=np.array([d.get(dt,np.nan) for dt in dates])
syms=sorted(M)
cs=[]
for i in range(len(syms)):
    for j in range(i+1,len(syms)):
        a,b=M[syms[i]],M[syms[j]]
        m=~(np.isnan(a)|np.isnan(b))
        if m.sum()>100: cs.append(np.corrcoef(a[m],b[m])[0,1])
print(f'mean pairwise daily-return correlation across the 8 names: {np.mean(cs):.3f}')
neff=len(syms)/(1+(len(syms)-1)*np.mean(cs))
print(f'effective independent names ~ {neff:.2f} of {len(syms)}')
print(f'=> pooled t-stats are inflated by roughly sqrt({len(syms)}/{neff:.2f}) = {math.sqrt(len(syms)/neff):.2f}x')

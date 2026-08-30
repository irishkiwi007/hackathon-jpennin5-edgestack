"""Does the implied-volatility decline on news-spike days survive gamma?

Short the ATM straddle at 09:30, cover at 16:00, using ACTUAL option minute prices. That captures
vega, gamma and theta together - no modelling. Spike days vs control days.

NOTE: a naked short straddle is not Alpaca-legal. This measures whether the effect is economically
real; if it is, the defined-risk version (iron butterfly) is the next step."""
import os
import json,math,sys,io,datetime,urllib.request,time,random
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
random.seed(6)
def q(u,t=3):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=50))
        except Exception: time.sleep(1)
    return None
cache=json.load(open('newscache.json'))
SYMS=['NVDA','TSLA','AMD','AAPL','AMZN','META','MSFT','SPY']
EV=[]
for s in SYMS:
    if s not in cache: continue
    D=cache[s]; dts=[b['t'] for b in D['bars']]; px=np.array([b['c'] for b in D['bars']])
    c=np.array([D['cnt'].get(d,0) for d in dts],float)
    for i in range(26,len(dts)-8):
        if dts[i]<'2025-06-01': continue
        w=c[i-20:i]; mu,sd=w.mean(),w.std(ddof=1)
        if sd<0.5 or mu<0.5: continue
        z=(c[i]-mu)/sd
        j=None
        for k in range(i+3,min(i+12,len(dts))):
            if datetime.date.fromisoformat(dts[k]).weekday()==4: j=k;break
        if j: EV.append(dict(sym=s,day=dts[i],nz=z,spot=float(px[i-1]),exp=datetime.date.fromisoformat(dts[j])))
sp=sorted([e for e in EV if e['nz']>=2.0],key=lambda e:-e['nz'])[:80]
ct=[e for e in EV if abs(e['nz'])<0.5]; random.shuffle(ct); ct=ct[:80]
print(f'spike {len(sp)}, control {len(ct)}')
SLIP=0.03
def occ(sym,exp,cp,k): return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'
def run(e):
    sm=q(f'https://data.alpaca.markets/v2/stocks/{e["sym"]}/bars?timeframe=1Min&feed=sip&start={e["day"]}T13:30:00Z&end={e["day"]}T20:05:00Z&limit=10000&adjustment=all')
    if not sm or not sm.get('bars'): return None
    sb={b['t'][11:16]:b['c'] for b in sm['bars']}
    o=sb.get('13:30')
    if not o: return None
    ks=set()
    for inc in (1.,2.5,5.):
        b=round(o/inc)*inc
        for k in (-1,0,1): ks.add(round(b+k*inc,2))
    ks=sorted(ks)
    om=defaultdict(dict); syms=[occ(e['sym'],e['exp'],cp,k) for k in ks for cp in ('C','P')]
    for z in range(0,len(syms),20):
        d=q('https://data.alpaca.markets/v1beta1/options/bars?symbols='+','.join(syms[z:z+20])+f'&timeframe=1Min&start={e["day"]}T13:30:00Z&end={e["day"]}T20:05:00Z&limit=10000')
        if d and d.get('bars'):
            for sy,rows in d['bars'].items():
                for r in rows: om[sy][r['t'][11:16]]=r['c']
    bk,bn=None,0
    for k in ks:
        n=min(len(om.get(occ(e['sym'],e['exp'],'C',k),{})),len(om.get(occ(e['sym'],e['exp'],'P',k),{})))
        if n>bn: bk,bn=k,n
    if bk is None or bn<60: return None
    C=om[occ(e['sym'],e['exp'],'C',bk)]; P=om[occ(e['sym'],e['exp'],'P',bk)]
    def px_at(D,rng):
        for hm in rng: 
            if hm in D: return D[hm]
        return None
    om_=[f'13:{m:02d}' for m in range(30,45)]
    cm_=[f'19:{m:02d}' for m in range(59,44,-1)]
    c0,p0=px_at(C,om_),px_at(P,om_)
    c1,p1=px_at(C,cm_),px_at(P,cm_)
    if None in (c0,p0,c1,p1): return None
    open_str=c0+p0; close_str=c1+p1
    # short at open (receive bid-ish), cover at close (pay ask-ish)
    pnl=(open_str-2*SLIP)-(close_str+2*SLIP)
    return dict(pnl=pnl*100, open=open_str, close=close_str,
                move=abs(sb.get('19:59',sb.get(max(sb)))-o)/o*100)
res={'spike':[],'control':[]}
for lab,evs in (('spike',sp),('control',ct)):
    for i,e in enumerate(evs):
        r=run(e)
        if r: res[lab].append(r)
        if (i+1)%25==0: print(f'  {lab} {i+1}/{len(evs)} usable {len(res[lab])}')
print()
print('='*92); print('SHORT ATM STRADDLE 09:30 -> 16:00, actual option prices'); print('='*92)
print(f'{"group":<10} {"n":>4} {"open $":>9} {"close $":>9} {"mean P&L":>10} {"t":>7} {"win%":>7} {"worst":>9} {"|move|%":>9}')
out={}
for lab in ('spike','control'):
    g=res[lab]
    if len(g)<15: print(f'{lab:<10} {len(g):>4}  (thin)'); continue
    v=np.array([x['pnl'] for x in g])
    t=v.mean()/(v.std(ddof=1)/math.sqrt(len(v)))
    out[lab]=v
    print(f'{lab:<10} {len(g):>4} {np.mean([x["open"] for x in g]):>9.2f} {np.mean([x["close"] for x in g]):>9.2f} '
          f'{v.mean():>10.1f} {t:>7.2f} {(v>0).mean()*100:>6.1f}% {v.min():>9.0f} {np.mean([x["move"] for x in g]):>8.2f}%')
if 'spike' in out and 'control' in out:
    a,b=out['spike'],out['control']
    d=a.mean()-b.mean(); t=d/math.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
    print(f'\nspike minus control: {d:+.1f} per straddle   t = {t:.2f}')
    print(f'  -> {"SIGNIFICANT" if abs(t)>1.96 else "not significant"}')

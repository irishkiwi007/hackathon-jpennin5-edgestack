"""Alpaca-legal version: intraday IRON BUTTERFLY on news-spike days.
Short ATM straddle + long wings, opened 09:30, closed 16:00, actual option prices.
Adds per-symbol and per-period breakdowns."""
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
sp=sorted([e for e in EV if e['nz']>=2.0],key=lambda e:-e['nz'])[:90]
print(f'spike events: {len(sp)}')
SLIP=0.03
def occ(sym,exp,cp,k): return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'
def run(e):
    sm=q(f'https://data.alpaca.markets/v2/stocks/{e["sym"]}/bars?timeframe=1Min&feed=sip&start={e["day"]}T13:30:00Z&end={e["day"]}T20:05:00Z&limit=10000&adjustment=all')
    if not sm or not sm.get('bars'): return None
    sb={b['t'][11:16]:b['c'] for b in sm['bars']}
    o=sb.get('13:30')
    if not o: return None
    body=set(); wings=set()
    for inc in (1.,2.5,5.):
        b=round(o/inc)*inc
        for k in (-1,0,1): body.add(round(b+k*inc,2))
        for wp in (0.04,0.06,0.09):
            for sg in (1,-1):
                v=round(round(o*(1+sg*wp)/inc)*inc,2)
                if v>0: wings.add(v)
    allk=sorted(body|wings)
    om=defaultdict(dict); syms=[occ(e['sym'],e['exp'],cp,k) for k in allk for cp in ('C','P')]
    for z in range(0,len(syms),20):
        d=q('https://data.alpaca.markets/v1beta1/options/bars?symbols='+','.join(syms[z:z+20])+f'&timeframe=1Min&start={e["day"]}T13:30:00Z&end={e["day"]}T20:05:00Z&limit=10000')
        if d and d.get('bars'):
            for sy,rows in d['bars'].items():
                for r in rows: om[sy][r['t'][11:16]]=r['c']
    def px_at(sym_,rng):
        D=om.get(sym_,{})
        for hm in rng:
            if hm in D: return D[hm]
        return None
    OM=[f'13:{m:02d}' for m in range(30,46)]; CM=[f'19:{m:02d}' for m in range(59,43,-1)]
    bk,bn=None,0
    for k in sorted(body):
        n=min(len(om.get(occ(e['sym'],e['exp'],'C',k),{})),len(om.get(occ(e['sym'],e['exp'],'P',k),{})))
        if n>bn: bk,bn=k,n
    if bk is None or bn<60: return None
    out={}
    for wp in (0.04,0.06,0.09):
        cu=min([k for k in wings if k>bk*1.01], key=lambda k:abs(k-bk*(1+wp)), default=None)
        pd_=min([k for k in wings if k<bk*0.99], key=lambda k:abs(k-bk*(1-wp)), default=None)
        if cu is None or pd_ is None: continue
        legs=[(occ(e['sym'],e['exp'],'C',bk),-1),(occ(e['sym'],e['exp'],'P',bk),-1),
              (occ(e['sym'],e['exp'],'C',cu),1),(occ(e['sym'],e['exp'],'P',pd_),1)]
        p0=[px_at(sy,OM) for sy,_ in legs]; p1=[px_at(sy,CM) for sy,_ in legs]
        if any(x is None or x<=0 for x in p0+p1): continue
        credit0=sum(-w*p for (sy,w),p in zip(legs,p0))-4*SLIP
        credit1=sum(-w*p for (sy,w),p in zip(legs,p1))+4*SLIP
        out[wp]=(credit0-credit1)*100
    return out if out else None
res=defaultdict(list); meta=[]
for i,e in enumerate(sp):
    r=run(e)
    if r:
        for wp,v in r.items(): res[wp].append(v)
        meta.append((e['sym'],e['day'],r))
    if (i+1)%25==0: print(f'  {i+1}/{len(sp)} usable {len(meta)}')
print()
print('='*90); print('INTRADAY IRON BUTTERFLY on news-spike days (09:30 -> 16:00, Alpaca-legal)'); print('='*90)
print(f'{"wing":<10} {"n":>5} {"total $":>10} {"mean $":>9} {"t":>7} {"win%":>7} {"worst":>9}')
for wp in (0.04,0.06,0.09):
    v=np.array(res[wp])
    if len(v)<20: continue
    t=v.mean()/(v.std(ddof=1)/math.sqrt(len(v)))
    print(f'{wp*100:>8.0f}% {len(v):>5} {v.sum():>10.0f} {v.mean():>9.1f} {t:>7.2f} {(v>0).mean()*100:>6.1f}% {v.min():>9.0f}')
best=0.06
print(f'\nPER-SYMBOL (wing {best*100:.0f}%)')
print(f'{"sym":>7} {"n":>4} {"mean $":>9} {"t":>7}')
bs=defaultdict(list)
for sym,day,r in meta:
    if best in r: bs[sym].append(r[best])
pos=tot=0
for s2,v in sorted(bs.items()):
    v=np.array(v)
    if len(v)<6: continue
    t=v.mean()/(v.std(ddof=1)/math.sqrt(len(v))) if len(v)>2 else float('nan')
    tot+=1; pos+= 1 if v.mean()>0 else 0
    print(f'{s2:>7} {len(v):>4} {v.mean():>9.1f} {t:>7.2f}')
print(f'\nprofitable in {pos} of {tot} symbols')
print(f'\nBY PERIOD (wing {best*100:.0f}%)')
by=defaultdict(list)
for sym,day,r in meta:
    if best in r: by[day[:4]+'-H'+('1' if int(day[5:7])<=6 else '2')].append(r[best])
for k in sorted(by):
    v=np.array(by[k])
    if len(v)<6: continue
    t=v.mean()/(v.std(ddof=1)/math.sqrt(len(v)))
    print(f'  {k}  n={len(v):>3}  mean {v.mean():>8.1f}  t={t:>5.2f}')

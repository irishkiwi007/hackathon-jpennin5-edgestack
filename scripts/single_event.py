"""One clean example, minute by minute — the mechanism made visible."""
import os
import json,math,sys,io,datetime,urllib.request,time
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
def q(u,t=4):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=60))
        except Exception: time.sleep(1)
    return None
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def bs(S,K,T,r,s,cp):
    if s<=0 or T<=0: return max(0.0,(S-K) if cp=='C' else (K-S))
    d1=(math.log(S/K)+(r+.5*s*s)*T)/(s*math.sqrt(T)); d2=d1-s*math.sqrt(T)
    return S*ncdf(d1)-K*math.exp(-r*T)*ncdf(d2) if cp=='C' else K*math.exp(-r*T)*ncdf(-d2)-S*ncdf(-d1)
def iv(p,S,K,T,r,cp):
    intr=max(0.0,(S-K*math.exp(-r*T)) if cp=='C' else (K*math.exp(-r*T)-S))
    if p<=intr+1e-6 or T<=0: return None
    lo,hi=1e-4,5.0
    if bs(S,K,T,r,hi,cp)<p: return None
    for _ in range(60):
        m=.5*(lo+hi)
        if bs(S,K,T,r,m,cp)<p: lo=m
        else: hi=m
    return .5*(lo+hi)
cache=json.load(open('newscache.json'))
# biggest news-volume spike day in 2026 for a liquid name
best=None
for sym in ('NVDA','TSLA','AMD','AAPL'):
    D=cache[sym]; dts=[b['t'] for b in D['bars']]
    c=np.array([D['cnt'].get(d,0) for d in dts],float); px=np.array([b['c'] for b in D['bars']])
    for i in range(26,len(dts)-8):
        if dts[i]<'2026-04-01': continue
        w=c[i-20:i]; mu,sd=w.mean(),w.std(ddof=1)
        if sd<0.5: continue
        z=(c[i]-mu)/sd
        if best is None or z>best[0]: best=(z,sym,dts[i],float(px[i]),int(c[i]),float(mu))
z,sym,day,spot,narts,mu=best
print(f'BIGGEST 2026 NEWS-VOLUME SPIKE: {sym} on {day}')
print(f'  {narts} articles vs {mu:.1f}/day baseline  ->  news_z = {z:.1f}')
print(f'  spot at close {spot:.2f}')
dts=[b['t'] for b in cache[sym]['bars']]; i=dts.index(day)
j=None
for k in range(i+3,min(i+12,len(dts))):
    if datetime.date.fromisoformat(dts[k]).weekday()==4: j=k;break
exp=datetime.date.fromisoformat(dts[j]); T0=(exp-datetime.date.fromisoformat(day)).days/365
print(f'  using expiry {exp} ({(exp-datetime.date.fromisoformat(day)).days}d)')
sm=q(f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&feed=sip&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000&adjustment=all')
spot_by={b['t'][11:16]:b['c'] for b in (sm or {}).get('bars',[])}
o=spot_by.get('13:30',spot)
ks=set()
for inc in (1.,2.5,5.):
    b=round(o/inc)*inc
    for k in (-1,0,1): ks.add(round(b+k*inc,2))
def occ(cp,k): return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'
om=defaultdict(dict); syms=[occ(cp,k) for k in sorted(ks) for cp in ('C','P')]
for zz in range(0,len(syms),20):
    d=q('https://data.alpaca.markets/v1beta1/options/bars?symbols='+','.join(syms[zz:zz+20])+f'&timeframe=1Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000')
    if d and d.get('bars'):
        for sy,rows in d['bars'].items():
            for r in rows: om[sy][r['t'][11:16]]=r['c']
bk,bn=None,0
for k in sorted(ks):
    n=min(len(om.get(occ('C',k),{})),len(om.get(occ('P',k),{})))
    if n>bn: bk,bn=k,n
print(f'  strike {bk} with {bn} minute bars on both legs')
arts=q(f'https://data.alpaca.markets/v1beta1/news?symbols={sym}&start={day}T13:00:00Z&end={day}T20:30:00Z&limit=50')
at=sorted(a['created_at'][11:16] for a in (arts or {}).get('news',[]))
print(f'  {len(at)} articles during the window; first {at[0] if at else "-"}, last {at[-1] if at else "-"}')
print()
print(f'{"ET":>7} {"spot":>9} {"impl vol":>9} {"vs 09:30":>9} {"articles this minute":>21}')
acount=defaultdict(int)
for t in at: acount[t]+=1
lS=lC=lP=None; base=None; rows=[]
t0=datetime.datetime(2000,1,1,13,30)
for m in range(391):
    hm=(t0+datetime.timedelta(minutes=m)).strftime('%H:%M')
    lS=spot_by.get(hm,lS); lC=om[occ('C',bk)].get(hm,lC); lP=om[occ('P',bk)].get(hm,lP)
    if lS is None or lC is None or lP is None: continue
    T=max(T0-(m/390)/365,1e-4)
    a=iv(lC,lS,bk,T,.045,'C'); b=iv(lP,lS,bk,T,.045,'P')
    vs=[x for x in (a,b) if x and .03<x<4]
    if not vs: continue
    v=sum(vs)/len(vs)
    if base is None: base=v
    rows.append((hm,lS,v,v/base,acount.get(hm,0)))
for hm,S,v,r,ac in rows[::10]:
    et=(datetime.datetime.strptime(hm,'%H:%M')-datetime.timedelta(hours=4)).strftime('%H:%M')
    mark='  <== '+('#'*min(ac,8)) if ac else ''
    print(f'{et:>7} {S:>9.2f} {v*100:>8.1f}% {r:>9.3f}{mark}')
if rows:
    vs=[r[2] for r in rows]
    print(f'\n  implied volatility range across the session: {min(vs)*100:.1f}% -> {max(vs)*100:.1f}%')
    print(f'  open {rows[0][2]*100:.1f}%   close {rows[-1][2]*100:.1f}%   change {(rows[-1][2]/rows[0][2]-1)*100:+.1f}%')
    big=sorted(((rows[k][2]/rows[k-1][2]-1,rows[k][0]) for k in range(1,len(rows))),reverse=True)[:5]
    print('  largest single-minute jumps:')
    for ch,hm in big:
        et=(datetime.datetime.strptime(hm,'%H:%M')-datetime.timedelta(hours=4)).strftime('%H:%M')
        print(f'    {et} {ch*100:+.1f}%   articles that minute: {acount.get(hm,0)}')

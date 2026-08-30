"""Does AMD's pattern repeat? Top news-volume spikes, one summary line each."""
import os
import json,math,sys,io,datetime,urllib.request,time
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
def q(u,t=3):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=50))
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
    for _ in range(50):
        m=.5*(lo+hi)
        if bs(S,K,T,r,m,cp)<p: lo=m
        else: hi=m
    return .5*(lo+hi)
cache=json.load(open('newscache.json'))
EV=[]
for sym in ('NVDA','TSLA','AMD','AAPL','AMZN','META','MSFT'):
    if sym not in cache: continue
    D=cache[sym]; dts=[b['t'] for b in D['bars']]; px=np.array([b['c'] for b in D['bars']])
    c=np.array([D['cnt'].get(d,0) for d in dts],float)
    for i in range(26,len(dts)-8):
        if dts[i]<'2025-09-01': continue
        w=c[i-20:i]; mu,sd=w.mean(),w.std(ddof=1)
        if sd<0.5 or mu<0.5: continue
        z=(c[i]-mu)/sd
        j=None
        for k in range(i+3,min(i+12,len(dts))):
            if datetime.date.fromisoformat(dts[k]).weekday()==4: j=k;break
        if j: EV.append((z,sym,dts[i],float(px[i]),datetime.date.fromisoformat(dts[j]),int(c[i])))
EV.sort(reverse=True)
print(f'{"sym":>6} {"date":>12} {"news_z":>7} {"arts":>5} {"1st art ET":>11} {"IV open":>9} {"IV close":>9} {"intraday":>9} {"peak ET":>8}')
done=0
for z,sym,day,spot,exp,narts in EV[:40]:
    if done>=12: break
    sm=q(f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&feed=sip&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000&adjustment=all')
    if not sm or not sm.get('bars'): continue
    spot_by={b['t'][11:16]:b['c'] for b in sm['bars']}
    o=spot_by.get('13:30',spot)
    ks=set()
    for inc in (1.,2.5,5.):
        b=round(o/inc)*inc
        for k in (-1,0,1): ks.add(round(b+k*inc,2))
    ks=sorted(ks)
    def occ(cp,k): return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'
    om=defaultdict(dict); syms=[occ(cp,k) for k in ks for cp in ('C','P')]
    for zz in range(0,len(syms),20):
        d=q('https://data.alpaca.markets/v1beta1/options/bars?symbols='+','.join(syms[zz:zz+20])+f'&timeframe=1Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000')
        if d and d.get('bars'):
            for sy,rows in d['bars'].items():
                for r in rows: om[sy][r['t'][11:16]]=r['c']
    bk,bn=None,0
    for k in ks:
        n=min(len(om.get(occ('C',k),{})),len(om.get(occ('P',k),{})))
        if n>bn: bk,bn=k,n
    if bk is None or bn<50: continue
    T0=(exp-datetime.date.fromisoformat(day)).days/365
    arts=q(f'https://data.alpaca.markets/v1beta1/news?symbols={sym}&start={day}T08:00:00Z&end={day}T20:30:00Z&limit=50')
    at=sorted(a['created_at'][11:16] for a in (arts or {}).get('news',[]))
    first=at[0] if at else None
    firstET=(datetime.datetime.strptime(first,'%H:%M')-datetime.timedelta(hours=4)).strftime('%H:%M') if first else '-'
    lS=lC=lP=None; series=[]
    t0=datetime.datetime(2000,1,1,13,30)
    for m in range(391):
        hm=(t0+datetime.timedelta(minutes=m)).strftime('%H:%M')
        lS=spot_by.get(hm,lS); lC=om[occ('C',bk)].get(hm,lC); lP=om[occ('P',bk)].get(hm,lP)
        if None in (lS,lC,lP): continue
        T=max(T0-(m/390)/365,1e-4)
        a=iv(lC,lS,bk,T,.045,'C'); b2=iv(lP,lS,bk,T,.045,'P')
        vs=[x for x in (a,b2) if x and .03<x<4]
        if vs: series.append((hm,sum(vs)/len(vs)))
    if len(series)<80: continue
    ivo,ivc=series[0][1],series[-1][1]
    pk=max(series,key=lambda x:x[1])
    pkET=(datetime.datetime.strptime(pk[0],'%H:%M')-datetime.timedelta(hours=4)).strftime('%H:%M')
    print(f'{sym:>6} {day:>12} {z:>7.1f} {narts:>5} {firstET:>11} {ivo*100:>8.1f}% {ivc*100:>8.1f}% {(ivc/ivo-1)*100:>+8.1f}% {pkET:>8}')
    done+=1

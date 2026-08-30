"""Where does the expansion actually happen? Test the OVERNIGHT window explicitly:
implied volatility at the prior session's close vs the spike session's open."""
import os
import json,math,sys,io,datetime,urllib.request,time,random
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
random.seed(4)
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
SYMS=['NVDA','TSLA','AMD','AAPL','AMZN','META','MSFT']
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
        if j is None: continue
        EV.append(dict(sym=s,i=i,prev=dts[i-1],day=dts[i],nz=z,spot=float(px[i-1]),
                       exp=datetime.date.fromisoformat(dts[j])))
sp=sorted([e for e in EV if e['nz']>=2.0],key=lambda e:-e['nz'])[:70]
ct=[e for e in EV if abs(e['nz'])<0.5]; random.shuffle(ct); ct=ct[:70]
print(f'spike {len(sp)}, control {len(ct)}')
def occ(sym,exp,cp,k): return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'
def ivs_for(e):
    ks=set()
    for inc in (1.,2.5,5.):
        b=round(e['spot']/inc)*inc
        for k in (-1,0,1): ks.add(round(b+k*inc,2))
    ks=sorted(ks)
    syms=[occ(e['sym'],e['exp'],cp,k) for k in ks for cp in ('C','P')]
    om=defaultdict(dict)
    for z in range(0,len(syms),20):
        d=q('https://data.alpaca.markets/v1beta1/options/bars?symbols='+','.join(syms[z:z+20])+
            f'&timeframe=1Min&start={e["prev"]}T19:00:00Z&end={e["day"]}T20:05:00Z&limit=10000')
        if d and d.get('bars'):
            for sy,rows in d['bars'].items():
                for r in rows: om[sy][r['t'][:16]]=r['c']
    sm={}
    for dd in (e['prev'],e['day']):
        d=q(f'https://data.alpaca.markets/v2/stocks/{e["sym"]}/bars?timeframe=1Min&feed=sip&start={dd}T13:30:00Z&end={dd}T20:05:00Z&limit=10000&adjustment=all')
        for b in (d or {}).get('bars',[]): sm[b['t'][:16]]=b['c']
    bk,bn=None,0
    for k in ks:
        n=min(len(om.get(occ(e['sym'],e['exp'],'C',k),{})),len(om.get(occ(e['sym'],e['exp'],'P',k),{})))
        if n>bn: bk,bn=k,n
    if bk is None or bn<30: return None
    def at(pref,rng):
        for hm in rng:
            key=pref+'T'+hm
            S=sm.get(key); c=om[occ(e['sym'],e['exp'],'C',bk)].get(key); p=om[occ(e['sym'],e['exp'],'P',bk)].get(key)
            if S and c and p:
                T=max((e['exp']-datetime.date.fromisoformat(pref)).days/365,1e-4)
                a=iv(c,S,bk,T,.045,'C'); b2=iv(p,S,bk,T,.045,'P')
                vs=[x for x in (a,b2) if x and .03<x<4]
                if vs: return sum(vs)/len(vs)
        return None
    close_prev=at(e['prev'],[f'19:{m:02d}' for m in range(59,40,-1)])
    open_day =at(e['day'], [f'13:{m:02d}' for m in range(30,50)])
    close_day=at(e['day'], [f'19:{m:02d}' for m in range(59,40,-1)])
    if not (close_prev and open_day and close_day): return None
    return close_prev,open_day,close_day
def run(evs,lab):
    out=[]
    for i,e in enumerate(evs):
        r=ivs_for(e)
        if r: out.append(r)
        if (i+1)%20==0: print(f'  {lab} {i+1}/{len(evs)} usable {len(out)}')
    return out
SP=run(sp,'spike'); CT=run(ct,'control')
print(f'\nusable: spike {len(SP)}, control {len(CT)}')
print()
print('='*92)
print('WHERE DOES IMPLIED VOLATILITY ACTUALLY EXPAND?')
print('='*92)
print(f'{"group":<10} {"n":>5} {"prev close":>11} {"open":>9} {"OVERNIGHT":>11} {"close":>9} {"INTRADAY":>10}')
for lab,G in (('spike',SP),('control',CT)):
    if len(G)<15: continue
    a=np.array([x[0] for x in G]); b=np.array([x[1] for x in G]); c=np.array([x[2] for x in G])
    on=(b/a-1)*100; idy=(c/b-1)*100
    print(f'{lab:<10} {len(G):>5} {a.mean()*100:>10.1f}% {b.mean()*100:>8.1f}% {on.mean():>+10.2f}% {c.mean()*100:>8.1f}% {idy.mean():>+9.2f}%')
if len(SP)>15 and len(CT)>15:
    ons=np.array([(x[1]/x[0]-1) for x in SP]); onc=np.array([(x[1]/x[0]-1) for x in CT])
    ids=np.array([(x[2]/x[1]-1) for x in SP]); idc=np.array([(x[2]/x[1]-1) for x in CT])
    for lab,a,b in (('OVERNIGHT',ons,onc),('INTRADAY',ids,idc)):
        d=a.mean()-b.mean(); t=d/math.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
        print(f'\n{lab}: spike {a.mean()*100:+.2f}% vs control {b.mean()*100:+.2f}%  diff {d*100:+.2f}pp  t={t:.2f}')

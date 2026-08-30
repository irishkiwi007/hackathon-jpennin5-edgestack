"""Measure the live volatility SKEW on SPY/QQQ.

An iron condor sells both a put spread and a call spread. Pricing both sides off the same ATM
implied volatility would overstate the call credit badly, because equity index options carry a
persistent skew: OTM puts trade richer than OTM calls. Measuring it rather than assuming it.
"""
import os
import json,sys,io,math,time,datetime,urllib.request
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
PAPER='https://paper-api.alpaca.markets'; DATA='https://data.alpaca.markets'; RATE=0.045
def q(u,t=2):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=45))
        except Exception: time.sleep(0.4)
    return None
def ncdf(x): return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
def bsp(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T)); return K*math.exp(-r*T)*ncdf(-(d1-s*math.sqrt(T)))-S*ncdf(-d1)
def bsc(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,S-K)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T)); return S*ncdf(d1)-K*math.exp(-r*T)*ncdf(d1-s*math.sqrt(T))
def ivof(p,S,K,T,r,cp):
    f=bsp if cp=='P' else bsc
    intr=max(0.0,(K*math.exp(-r*T)-S) if cp=='P' else (S-K*math.exp(-r*T)))
    if p<=intr+1e-6: return None
    lo,hi=1e-4,4.0
    if f(S,K,T,r,hi)<p: return None
    for _ in range(70):
        m=0.5*(lo+hi)
        if f(S,K,T,r,m)<p: lo=m
        else: hi=m
    return 0.5*(lo+hi)
today=datetime.date.today()
lo=(today+datetime.timedelta(days=8)).isoformat(); hi=(today+datetime.timedelta(days=18)).isoformat()
OUT={}
for sym in ('SPY','QQQ','IWM'):
    d=q(DATA+'/v2/stocks/bars/latest?symbols='+sym+'&feed=iex')
    S=float((d or {}).get('bars',{}).get(sym,{}).get('c',0))
    if not S: continue
    rec={}
    for cp,typ in (('P','put'),('C','call')):
        c=q('%s/v2/options/contracts?underlying_symbols=%s&expiration_date_gte=%s&expiration_date_lte=%s&type=%s&limit=500&status=active'%(PAPER,sym,lo,hi,typ))
        cand=[x for x in ((c or {}).get('option_contracts') or []) if x.get('tradable') and 0.90*S<=float(x['strike_price'])<=1.10*S]
        if not cand: continue
        exps=sorted({x['expiration_date'] for x in cand}); cand=[x for x in cand if x['expiration_date']==exps[0]]
        occ=[x['symbol'] for x in cand]; snaps={}
        for i in range(0,len(occ),100):
            sd=q(DATA+'/v1beta1/options/snapshots?symbols='+','.join(occ[i:i+100]))
            for k,v in (sd or {}).get('snapshots',{}).items():
                qt=v.get('latestQuote') or {}
                b_,a_=float(qt.get('bp',0) or 0),float(qt.get('ap',0) or 0)
                if b_>0 and a_>=b_: snaps[k]=(0.5*(b_+a_),0.5*(a_-b_))
        T=(datetime.date.fromisoformat(exps[0])-today).days/365.0
        for x in cand:
            if x['symbol'] not in snaps: continue
            K=float(x['strike_price']); mid,half=snaps[x['symbol']]
            iv=ivof(mid,S,K,T,RATE,cp)
            if iv and 0.02<iv<3: rec[(cp,round(K/S-1,4))]=(iv,half*100,K)
    OUT[sym]=(S,rec)
print('SKEW — implied volatility by moneyness (live, 8-18 DTE)')
print('='*96)
BANDS=[(-0.06,'6% OTM put'),(-0.04,'4% OTM put'),(-0.02,'2% OTM put'),(0.0,'ATM'),
       (0.02,'2% OTM call'),(0.04,'4% OTM call'),(0.06,'6% OTM call')]
print('%-7s %9s'%('sym','spot')+''.join('%14s'%b[1] for b in BANDS))
skews={}
for sym,(S,rec) in OUT.items():
    line='%-7s %9.2f'%(sym,S); row={}
    for off,lab in BANDS:
        cp='P' if off<=0 else 'C'
        best=None
        for (c2,o2),(iv,half,K) in rec.items():
            if c2!=cp: continue
            if best is None or abs(o2-off)<abs(best[0]-off): best=(o2,iv,half)
        if best and abs(best[0]-off)<0.012:
            row[off]=best[1]; line+='%13.3f '%best[1]
        else: line+='%14s'%'-'
    print(line); skews[sym]=row
print()
atmv=[r.get(0.0) for r in skews.values() if r.get(0.0)]
p4=[r.get(-0.04) for r in skews.values() if r.get(-0.04)]
c4=[r.get(0.04) for r in skews.values() if r.get(0.04)]
if atmv and p4 and c4:
    a,p,c=np.mean(atmv),np.mean(p4),np.mean(c4)
    print('  mean ATM IV        %.3f'%a)
    print('  mean 4%% OTM put    %.3f   ratio to ATM %.3f'%(p,p/a))
    print('  mean 4%% OTM call   %.3f   ratio to ATM %.3f'%(c,c/a))
    print()
    print('  put/call skew at 4%% OTM: %.3f  (puts are %.0f%% richer)'%(p/c,100*(p/c-1)))
    print()
    print('  For an iron condor this means the PUT side carries most of the credit.')
    print('  Modelling both sides at ATM IV would overstate the call credit by ~%.0f%%.'%(100*(a/c-1)))
print()
print('  one-way crossing cost per leg ($/contract):')
for sym,(S,rec) in OUT.items():
    hs=[v[1] for v in rec.values()]
    if hs: print('    %-5s median %.0f   (4-leg condor round trip = %.0f)'%(sym,np.median(hs),8*np.median(hs)))

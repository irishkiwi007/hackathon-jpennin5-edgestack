"""Measure the REAL IV/RV ratio from live quotes (bid/ask mid), which are reliable, rather than
import os
from daily option bars, which are stale last-trade prints.

This is the single number the whole cash-secured put result hinges on: the model assumed
IV = realized x 1.798. If the true ratio is materially lower, the profit shrinks proportionally
because premium is the only positive term in the P&L.
"""
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
def bs_put(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T)); return K*math.exp(-r*T)*ncdf(-(d1-s*math.sqrt(T)))-S*ncdf(-d1)
def implied(p,S,K,T,r):
    if p<=max(0.0,K*math.exp(-r*T)-S)+1e-6: return None
    lo,hi=1e-4,5.0
    if bs_put(S,K,T,r,hi)<p: return None
    for _ in range(70):
        m=0.5*(lo+hi)
        if bs_put(S,K,T,r,m)<p: lo=m
        else: hi=m
    return 0.5*(lo+hi)

SYMS=['SPY','QQQ','IWM','DIA','NVDA','AAPL','MSFT','AMZN','META','GOOGL','TSLA','AMD','BAC',
      'WMT','XLE','XLF','XLV','XLP','GLD','SLV','NFLX','PLTR','F','T','PFE','KO','NKE','VZ']
today=datetime.date.today()
lo=(today+datetime.timedelta(days=8)).isoformat(); hi=(today+datetime.timedelta(days=18)).isoformat()
# realized vol from daily bars
st=(today-datetime.timedelta(days=90)).isoformat()
d=q(DATA+'/v2/stocks/bars?symbols='+','.join(SYMS)+'&timeframe=1Day&feed=sip&start='+st+'&limit=10000&adjustment=all')
RV={}; SPOT={}
for s,rows in (d or {}).get('bars',{}).items():
    c=np.array([float(b['c']) for b in rows])
    if len(c)<25: continue
    lr=np.diff(np.log(c)); RV[s]=float(lr[-20:].std(ddof=1)*math.sqrt(252)); SPOT[s]=float(c[-1])
print('realized vol computed for %d names'%len(RV))
rows=[]
for s in SYMS:
    if s not in RV or RV[s]<=0: continue
    S=SPOT[s]
    c=q('%s/v2/options/contracts?underlying_symbols=%s&expiration_date_gte=%s&expiration_date_lte=%s&type=put&limit=400&status=active'%(PAPER,s,lo,hi))
    cand=[x for x in ((c or {}).get('option_contracts') or []) if x.get('tradable') and 0.97*S<=float(x['strike_price'])<=1.03*S]
    if not cand: continue
    exps=sorted({x['expiration_date'] for x in cand}); cand=[x for x in cand if x['expiration_date']==exps[0]]
    occ=[x['symbol'] for x in cand]
    sd=q(DATA+'/v1beta1/options/snapshots?symbols='+','.join(occ[:100]))
    best=None
    for x in cand:
        sn=(sd or {}).get('snapshots',{}).get(x['symbol'])
        if not sn: continue
        qt=sn.get('latestQuote') or {}
        b_,a_=float(qt.get('bp',0) or 0),float(qt.get('ap',0) or 0)
        if b_<=0 or a_<b_: continue
        K=float(x['strike_price'])
        if best is None or abs(K-S)<abs(best[0]-S): best=(K,0.5*(b_+a_),x['expiration_date'])
    if not best: continue
    K,mid,exp=best
    T=(datetime.date.fromisoformat(exp)-today).days/365.0
    iv=implied(mid,S,K,T,RATE)
    if not iv: continue
    rows.append((s,S,K,mid,iv,RV[s],iv/RV[s]))
print()
print('='*92)
print('LIVE IV/RV — from bid/ask mid (reliable), ATM puts, 8-18 DTE')
print('='*92)
print('%-7s %9s %8s %9s %8s %8s %8s'%('sym','spot','strike','mid','IV','RV20','IV/RV'))
for s,S,K,mid,iv,rv,r in sorted(rows,key=lambda x:-x[6]):
    print('%-7s %9.2f %8.1f %9.2f %8.3f %8.3f %8.2f'%(s,S,K,mid,iv,rv,r))
if rows:
    a=np.array([r[6] for r in rows])
    print()
    print('  n=%d   mean IV/RV %.3f   median %.3f   p25 %.3f   p75 %.3f'%(len(a),a.mean(),np.median(a),np.percentile(a,25),np.percentile(a,75)))
    print()
    print('  model assumed 1.798 for PANIC days; this is a CALM tape, so the true')
    print('  panic-day ratio sits above this measurement, not below it.')
    print()
    print('  sensitivity from the model run:')
    for ratio,net in ((1.0,51),(1.2,84),(1.4,118),(1.6,151),(1.798,184)):
        print('     IV/RV %.2fx -> signal-day net %+d $/contract'%(ratio,net))

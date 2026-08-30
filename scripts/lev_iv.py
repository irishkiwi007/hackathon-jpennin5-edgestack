"""Do leveraged-ETF options price at ~L x the underlying index implied volatility?

For SPY/QQQ the measured IV was VIX/VXN. Leveraged ETFs have no such index, so the historical
test needs a proxy. Theory says a 3x ETF's instantaneous volatility is 3x the underlying's, so
IV(TQQQ) ~ 3 x IV(QQQ). That has to be VERIFIED against live chains before it can carry a
backtest - if leveraged options are systematically richer or cheaper than 3x, that IS the edge
(or the trap).

Also measures the friction and the spot/friction ratio, which decided everything so far.
"""
import os
import json,sys,io,math,time,datetime,urllib.request,urllib.parse,http.cookiejar
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
def bsput(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T))
    return K*math.exp(-r*T)*ncdf(-(d1-s*math.sqrt(T)))-S*ncdf(-d1)
def iv_of(p,S,K,T,r):
    if p<=max(0.0,K*math.exp(-r*T)-S)+1e-6: return None
    lo,hi=1e-4,6.0
    if bsput(S,K,T,r,hi)<p: return None
    for _ in range(70):
        m=0.5*(lo+hi)
        if bsput(S,K,T,r,m)<p: lo=m
        else: hi=m
    return 0.5*(lo+hi)

PAIRS=[('TQQQ','QQQ',3),('SQQQ','QQQ',3),('SPXL','SPY',3),('SPXU','SPY',3),
       ('UPRO','SPY',3),('SSO','SPY',2),('QLD','QQQ',2),('SOXL','SOXX',3),
       ('TNA','IWM',3),('FAS','XLF',3)]
SYMS=sorted({s for p in PAIRS for s in p[:2]})
today=datetime.date.today()
lo=(today+datetime.timedelta(days=8)).isoformat(); hi=(today+datetime.timedelta(days=18)).isoformat()
st=(today-datetime.timedelta(days=90)).isoformat()
d=q(DATA+'/v2/stocks/bars?symbols='+','.join(SYMS)+'&timeframe=1Day&feed=sip&start='+st+'&limit=10000&adjustment=all')
RV={};SPOT={}
for s,rows in (d or {}).get('bars',{}).items():
    c=np.array([float(b['c']) for b in rows])
    if len(c)<25: continue
    lr=np.diff(np.log(c)); RV[s]=float(lr[-20:].std(ddof=1)*math.sqrt(252)); SPOT[s]=float(c[-1])

def atm_put(sym):
    if sym not in SPOT: return None
    S=SPOT[sym]
    c=q('%s/v2/options/contracts?underlying_symbols=%s&expiration_date_gte=%s&expiration_date_lte=%s&type=put&limit=400&status=active'%(PAPER,sym,lo,hi))
    cand=[x for x in ((c or {}).get('option_contracts') or []) if x.get('tradable') and 0.95*S<=float(x['strike_price'])<=1.05*S]
    if not cand: return None
    exps=sorted({x['expiration_date'] for x in cand}); cand=[x for x in cand if x['expiration_date']==exps[0]]
    sd=q(DATA+'/v1beta1/options/snapshots?symbols='+','.join([x['symbol'] for x in cand][:100]))
    best=None
    for x in cand:
        sn=(sd or {}).get('snapshots',{}).get(x['symbol'])
        if not sn: continue
        qt=sn.get('latestQuote') or {}
        b_,a_=float(qt.get('bp',0) or 0),float(qt.get('ap',0) or 0)
        if b_<=0 or a_<b_: continue
        K=float(x['strike_price'])
        if best is None or abs(K-S)<abs(best[0]-S): best=(K,0.5*(b_+a_),0.5*(a_-b_),x['expiration_date'])
    if not best: return None
    K,mid,half,exp=best
    T=(datetime.date.fromisoformat(exp)-today).days/365.0
    iv=iv_of(mid,S,K,T,RATE)
    return dict(sym=sym,S=S,K=K,mid=mid,half=half*100,iv=iv,rv=RV.get(sym))

CACHE={}
for s in SYMS:
    CACHE[s]=atm_put(s)
print('LEVERAGED ETF OPTION ECONOMICS (ATM puts, 8-18 DTE, live quotes)')
print('='*108)
print('%-6s %-6s %3s %9s %8s %8s %8s %9s %10s %10s'%('lev','base','L','spot','IV lev','IV base','IV/L·base','RV lev','fric $/ct','spot/fric'))
rows=[]
for lev,base,L in PAIRS:
    a,b=CACHE.get(lev),CACHE.get(base)
    if not a or not b or not a.get('iv') or not b.get('iv'): 
        print('%-6s %-6s %3d  (no quote)'%(lev,base,L)); continue
    ratio=a['iv']/(L*b['iv'])
    rows.append((lev,base,L,ratio,a))
    print('%-6s %-6s %3d %9.2f %8.3f %8.3f %9.3f %9.3f %10.0f %10.0f'%(
        lev,base,L,a['S'],a['iv'],b['iv'],ratio,a['rv'] or 0,a['half'],a['S']*100/max(a['half'],0.01)))
if rows:
    r=np.array([x[3] for x in rows])
    print()
    print('  IV(leveraged) / (L x IV(base)):  mean %.3f   median %.3f'%(r.mean(),np.median(r)))
    print()
    if r.mean()<0.92:
        print('  >>> Leveraged options are priced BELOW L x base IV by %.0f%%.'%(100*(1-r.mean())))
        print('      They are relatively CHEAP -> favours BUYING them, penalises selling.')
    elif r.mean()>1.08:
        print('  >>> Leveraged options are priced ABOVE L x base IV by %.0f%%.'%(100*(r.mean()-1)))
        print('      They are relatively RICH -> favours SELLING them. This would be the edge.')
    else:
        print('  >>> Priced at approximately L x base IV. The 3x proxy is valid for backtesting,')
        print('      but there is no free mispricing in the leverage itself.')
    print()
    print('  Compare spot/friction: SPY 19,234 · QQQ 4,478 (the only two that cleared before)')

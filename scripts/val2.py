"""Stronger validation of the earnings-date locator.

The first check recovered 7/13 news-confirmed dates (54%), below the 60% bar - but 13 dates is
far too small to conclude anything. This pulls much deeper news history for more names, and adds
an independent check that does not depend on news coverage at all:

  Days were selected by VOLUME. If they are real earnings days, the MOVE on them should be far
  larger than on ordinary days AND larger than on random high-volume days. Since the move was
  never used to select them, that is genuine evidence rather than circularity.
"""
import os
import json,sys,io,math,time,datetime,urllib.request
from collections import defaultdict
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HDR={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_SECRET_KEY']}
DATA='https://data.alpaca.markets'
def aget(u,t=3):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=60))
        except Exception: time.sleep(0.5)
    return None
_src=open('earn_final.py',encoding='utf-8').read().split("print()\nprint('=' * 100)\nprint('VALIDATION")[0]
_src="\n".join(l for l in _src.splitlines() if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

KEY=('q1 earnings','q2 earnings','q3 earnings','q4 earnings','quarterly results','earnings results',
     'reports q','fiscal q','earnings call','tops estimates','beats','misses','eps of',
     'reports fourth-quarter','reports third-quarter','reports second-quarter','reports first-quarter',
     'q1 eps','q2 eps','q3 eps','q4 eps','earnings preview','earnings snapshot')
def news_dates(sym,pages=120):
    hits,tok=defaultdict(int),None
    for _ in range(pages):
        u=(DATA+'/v1beta1/news?symbols='+sym+'&start=2022-06-01T00:00:00Z&end=2026-08-28T23:59:00Z&limit=50')
        if tok: u+='&page_token='+tok
        d=aget(u)
        if not d: break
        for a in d.get('news',[]):
            h=(a.get('headline') or '').lower()
            if any(k in h for k in KEY): hits[a['created_at'][:10]]+=1
        tok=d.get('next_page_token')
        if not tok: break
    return sorted([d for d,c in hits.items() if c>=2])

print()
print('='*96)
print('A. NEWS CROSS-CHECK, deeper history')
print('='*96)
TEST=['AAPL','MSFT','NVDA','JPM','BAC','META','TSLA','WMT','DIS','NFLX']
hit=miss=0
print('%-7s %12s %14s %10s'%('sym','news dates','located <=2d','pct'))
for s in TEST:
    if s not in BARS: continue
    nd=news_dates(s); loc=[d for _,d,_ in locate(s)]
    if not nd: print('%-7s %12s'%(s,'none')); continue
    m=0
    for d in nd:
        dd=datetime.date.fromisoformat(d)
        if any(abs((datetime.date.fromisoformat(l)-dd).days)<=2 for l in loc): m+=1
    hit+=m; miss+=len(nd)-m
    print('%-7s %12d %14d %9.0f%%'%(s,len(nd),m,100*m/len(nd)))
tot=hit+miss
if tot:
    p=hit/tot
    se=math.sqrt(p*(1-p)/tot)
    print()
    print('  overall %d/%d = %.0f%%   95%% CI [%.0f%%, %.0f%%]'%(hit,tot,100*p,100*max(0,p-1.96*se),100*min(1,p+1.96*se)))

print()
print('='*96)
print('B. INDEPENDENT CHECK — do located days show abnormal MOVES? (move never used to select)')
print('='*96)
print('%-7s %10s %12s %14s %12s %9s'%('sym','n located','located |mv|%','random hi-vol%','ordinary%','ratio'))
rng=np.random.default_rng(7); ratios=[]
for s in sorted(BARS):
    loc=locate(s)
    if len(loc)<8: continue
    rows=BARS[s]; c=np.array([r['c'] for r in rows]); v=np.array([r['v'] for r in rows])
    lr=np.zeros(len(c)); lr[1:]=np.log(c[1:]/c[:-1])
    li=set(i for i,_,_ in loc)
    locmv=np.array([abs(lr[i])*100 for i in li if i>0])
    # random days matched on volume percentile but NOT on earnings
    relv=np.array([v[i]/v[max(i-60,0):i].mean() if i>=60 and v[max(i-60,0):i].mean()>0 else 0 for i in range(len(v))])
    thr=np.percentile([relv[i] for i in li if i<len(relv)],25) if li else 2
    pool=[i for i in range(60,len(lr)) if i not in li and relv[i]>=thr]
    if len(pool)<20 or len(locmv)<8: continue
    pick=rng.choice(pool,size=min(len(pool),200),replace=False)
    hivol=np.array([abs(lr[i])*100 for i in pick])
    ordn=np.array([abs(lr[i])*100 for i in range(1,len(lr)) if i not in li])
    ratios.append(locmv.mean()/max(hivol.mean(),1e-9))
    print('%-7s %10d %12.2f%% %13.2f%% %11.2f%% %9.2f'%(s,len(locmv),locmv.mean(),hivol.mean(),ordn.mean(),locmv.mean()/max(hivol.mean(),1e-9)))
if ratios:
    r=np.array(ratios)
    print()
    print('  located days move %.2fx as much as VOLUME-MATCHED non-located days (median %.2f)'%(r.mean(),np.median(r)))
    print('  ratio > 1 in %d/%d names'%(int((r>1).sum()),len(r)))
    print()
    if r.mean()>1.3:
        print('  >>> Located days are genuinely special even versus other high-volume days.')
        print('      The locator is finding events, not just busy sessions.')
    else:
        print('  >>> Located days look like ordinary high-volume days. Locator NOT validated.')

"""Panel 3 showed AAPL corr(pre5,post30)=+0.445 -- implausibly large. Likely cause: OVERLAPPING
article windows. With ~12 articles/day, article A's post-30m window overlaps article B's pre-5m
window, which induces correlation mechanically.

Control: keep only ISOLATED articles (no other article for that symbol within +/-60 minutes)."""
import os
import json,math,sys,io,datetime,urllib.request,time
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
K=os.environ['ALPACA_API_KEY']; S=os.environ['ALPACA_SECRET_KEY']
HDR={'APCA-API-KEY-ID':K,'APCA-API-SECRET-KEY':S}
SYMS=['NVDA','TSLA','AAPL','AMD','SPY']; START,END='2026-05-01','2026-08-28'
def q(u,t=3):
    for _ in range(t):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=HDR),timeout=60))
        except Exception: time.sleep(1.5)
    return None
def news(s):
    out,tok=[],None
    for _ in range(60):
        u=f'https://data.alpaca.markets/v1beta1/news?symbols={s}&start={START}T00:00:00Z&end={END}T23:59:00Z&limit=50'
        if tok: u+=f'&page_token={tok}'
        d=q(u)
        if not d: break
        out+=d.get('news',[]); tok=d.get('next_page_token')
        if not tok: break
    return out
def bars(s):
    out,tok=[],None
    while True:
        u=f'https://data.alpaca.markets/v2/stocks/{s}/bars?timeframe=1Min&feed=sip&start={START}T13:00:00Z&end={END}T20:30:00Z&limit=10000&adjustment=all'
        if tok: u+=f'&page_token={tok}'
        d=q(u)
        if not d: break
        out+=d.get('bars') or []; tok=d.get('next_page_token')
        if not tok: break
    return out
print(f'{"sym":>6} {"all n":>7} {"isolated n":>11} {"corr5 all":>11} {"corr5 iso":>11} '
      f'{"corr30 all":>12} {"corr30 iso":>12} {"t(iso30)":>10}')
for s in SYMS:
    nw=news(s); bb=bars(s)
    if not bb: continue
    ts=np.array([datetime.datetime.fromisoformat(b['t'].replace('Z','+00:00')).timestamp() for b in bb])
    px=np.array([b['c'] for b in bb])
    def pa(t):
        i=np.searchsorted(ts,t)-1
        return px[i] if 0<=i<len(px) else None
    times=sorted(datetime.datetime.fromisoformat(a['created_at'].replace('Z','+00:00')).timestamp() for a in nw)
    ta=np.array(times)
    rows=[]
    for t in times:
        nearby=np.sum((ta>t-3600)&(ta<t+3600))-1
        a0,a1,a2,a3=pa(t-300),pa(t),pa(t+300),pa(t+1800)
        if None in (a0,a1,a2,a3) or min(a0,a1,a2,a3)<=0: continue
        rows.append((nearby, math.log(a1/a0)*1e4, math.log(a2/a1)*1e4, math.log(a3/a1)*1e4))
    if len(rows)<50: continue
    R=np.array(rows)
    iso=R[R[:,0]==0]
    def cc(M,j):
        if len(M)<30: return float('nan'),0
        c=np.corrcoef(M[:,1],M[:,j])[0,1]
        n=len(M); t_=c*math.sqrt((n-2)/max(1-c*c,1e-9))
        return c,t_
    c5a,_=cc(R,2); c5i,_=cc(iso,2); c30a,_=cc(R,3); c30i,t30i=cc(iso,3)
    print(f'{s:>6} {len(R):>7} {len(iso):>11} {c5a:>+11.3f} {c5i:>+11.3f} '
          f'{c30a:>+12.3f} {c30i:>+12.3f} {t30i:>10.2f}')
print("""
'iso' = only articles with NO other article for that symbol within +/-60 minutes.
If the correlation collapses once windows stop overlapping, it was an artifact of clustering.""")

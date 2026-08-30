"""Definitive SPY test: price the spread with REAL implied volatility at both ends.

No IV assumption remains. VIX is the market's ATM implied volatility for SPX/SPY, measured
daily since 1992. Entry IV = VIX on the signal date. Exit IV = VIX three sessions later.
Both observed.

This removes the single quantity that made the two previous models disagree by $467/contract.
"""
import json,sys,io,math,datetime,urllib.request,urllib.parse,http.cookiejar,csv
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'
jar=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def get(u,ref=None):
    r=urllib.request.Request(u); r.add_header('User-Agent',UA)
    if ref: r.add_header('Referer',ref)
    return op.open(r,timeout=60).read().decode('utf-8','replace')
try: get('https://fc.yahoo.com')
except Exception: pass
cr=get('https://query1.finance.yahoo.com/v1/test/getcrumb',ref='https://finance.yahoo.com/').strip()
end=int(datetime.datetime.now(datetime.timezone.utc).timestamp()); start=end-34*365*86400
def series(tk):
    u=('https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(tk)
       +'?period1={}&period2={}&interval=1d&crumb={}'.format(start,end,urllib.parse.quote(cr)))
    c=json.loads(get(u,ref='https://finance.yahoo.com/'))
    res=c['chart']['result'][0]; ts=res['timestamp']; q=res['indicators']['quote'][0]
    out={}
    for i,t in enumerate(ts):
        v=q['close'][i]
        if v: out[datetime.datetime.fromtimestamp(t,datetime.timezone.utc).date().isoformat()]=float(v)
    return out
VIX=series('^VIX')
try: VXN=series('^VXN')
except Exception: VXN={}
print('VIX %d sessions, VXN %d sessions'%(len(VIX),len(VXN)))

RATE,HOLD,DTE0,WIDTH=0.045,3,12,0.05
FR={'SPY':4.0,'QQQ':16.0}; SPOT_NOW={'SPY':769.35,'QQQ':716.43}
def ncdf(x): return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
def bsput(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T))
    return K*math.exp(-r*T)*ncdf(-(d1-s*math.sqrt(T)))-S*ncdf(-d1)
def nw_t(x,lag):
    x=np.asarray(x,float); nn=len(x)
    if nn<8: return float('nan')
    m=x.mean(); e=x-m; s=float(e@e)/nn
    for k in range(1,min(lag,nn-1)+1): s+=2.0*(1.0-k/(lag+1.0))*(float(e[k:]@e[:-k])/nn)
    return m/math.sqrt(s/nn) if s>0 else float('nan')
BASE='C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
def run(sym,ivmap):
    rows=list(csv.DictReader(open(BASE+'/'+sym+'.csv',encoding='utf-8')))
    dts=[r['date'] for r in rows]
    cl=np.array([float(r['adj_close']) for r in rows]); vo=np.array([float(r['volume']) for r in rows])
    n=len(cl); r_=np.zeros(n); r_[1:]=np.log(cl[1:]/cl[:-1])
    scale=SPOT_NOW[sym]/cl[-1]; out=[]
    for i in range(25,n-HOLD):
        d,d3=dts[i],dts[i+HOLD]
        if d not in ivmap or d3 not in ivmap: continue
        rv=r_[i-19:i+1].std(ddof=1)
        if not np.isfinite(rv) or rv<=0: continue
        st=math.log(cl[i]/cl[i-5])/(rv*math.sqrt(5))
        vx=vo[i]/max(np.mean(vo[i-19:i+1]),1.0)
        if st>=-2.5 or vx<1.4: continue
        S0,S1=cl[i]*scale,cl[i+HOLD]*scale
        iv0,iv1=ivmap[d]/100.0,ivmap[d3]/100.0
        Ks,Kl=S0,S0*(1-WIDTH); T0,T1=DTE0/365.0,max((DTE0-HOLD)/365.0,1e-4)
        c0=bsput(S0,Ks,T0,RATE,iv0)-bsput(S0,Kl,T0,RATE,iv0)
        c1=bsput(S1,Ks,T1,RATE,iv1)-bsput(S1,Kl,T1,RATE,iv1)
        if c0<=0: continue
        out.append(dict(date=d,gross=(c0-c1)*100,net=(c0-c1)*100-2*FR[sym],credit=c0*100,
                        iv0=iv0,iv1=iv1,move=(S1/S0-1)*100))
    return out
print()
print('='*100)
print('SPREAD PRICED WITH REAL IMPLIED VOLATILITY AT BOTH ENDS (VIX / VXN)')
print('='*100)
print('%-7s %5s %9s %9s %10s %10s %9s %9s %8s %7s'%('sym','n','IV entry','IV exit','credit $','gross $','fric $','NET $','t','win%'))
book=[]
for sym,mp in (('SPY',VIX),('QQQ',VXN)):
    if not mp: continue
    tr=run(sym,mp)
    if len(tr)<8: print('%-7s %5d (thin)'%(sym,len(tr))); continue
    nt=np.array([t['net'] for t in tr])
    print('%-7s %5d %9.3f %9.3f %10.0f %10.0f %9.0f %9.0f %8.2f %6.1f%%'%(
        sym,len(tr),np.mean([t['iv0'] for t in tr]),np.mean([t['iv1'] for t in tr]),
        np.mean([t['credit'] for t in tr]),np.mean([t['gross'] for t in tr]),2*FR[sym],
        nt.mean(),nw_t(nt,HOLD),100*(nt>0).mean()))
    book+=tr
if book:
    b=np.array([t['net'] for t in book])
    print()
    print('='*100); print('COMBINED BOOK'); print('='*100)
    print('  n=%d  NET %+.0f $/contract  t=%.2f  win %.1f%%  median %+.0f'%(
        len(b),b.mean(),nw_t(b,HOLD),100*(b>0).mean(),np.median(b)))
    print('  worst %+.0f   p10 %+.0f   p25 %+.0f   p75 %+.0f   p90 %+.0f'%(
        b.min(),np.percentile(b,10),np.percentile(b,25),np.percentile(b,75),np.percentile(b,90)))
    print('  frequency %.1f signals/yr across both names'%(len(b)/30.0))
    print()
    print('  %-14s %6s %10s %8s'%('era','n','NET $','win%'))
    for lab,a_,b_ in [('1993-2002','1993','2003'),('2003-2009','2003','2010'),
                      ('2010-2019','2010','2020'),('2020-2026','2020','2027')]:
        g=[t['net'] for t in book if a_<=t['date'][:4]<b_]
        if len(g)<4: print('  %-14s %6d (thin)'%(lab,len(g))); continue
        x=np.array(g); print('  %-14s %6d %10.0f %7.1f%%'%(lab,len(x),x.mean(),100*(x>0).mean()))

"""What does IMPLIED volatility actually do in the 3 days after a capitulation event?

Everything now hinges on this. A bull put spread is short vega: if IV falls over the hold it
wins, if IV rises it loses. Two models disagreed by $467/contract purely on this assumption.

VIX is the market's ATM implied volatility for SPY, with history to 1990 - so this is directly
measurable rather than assumable. Pulled from Yahoo, the same feed the engine uses.
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
u=('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote('^VIX')
   + '?period1={}&period2={}&interval=1d&crumb={}'.format(start,end,urllib.parse.quote(cr)))
c=json.loads(get(u,ref='https://finance.yahoo.com/'))
res=c['chart']['result'][0]; ts=res['timestamp']; q=res['indicators']['quote'][0]
VIX={}
for i,t in enumerate(ts):
    v=q['close'][i]
    if v: VIX[datetime.datetime.fromtimestamp(t,datetime.timezone.utc).date().isoformat()]=float(v)
print('VIX sessions: %d   %s -> %s'%(len(VIX),min(VIX),max(VIX)))

BASE='C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
rows=list(csv.DictReader(open(BASE+'/SPY.csv',encoding='utf-8')))
dts=[r['date'] for r in rows]
cl=np.array([float(r['adj_close']) for r in rows]); vo=np.array([float(r['volume']) for r in rows])
n=len(cl); r_=np.zeros(n); r_[1:]=np.log(cl[1:]/cl[:-1])

def nw_t(x,lag):
    x=np.asarray(x,float); nn=len(x)
    if nn<8: return float('nan')
    m=x.mean(); e=x-m; s=float(e@e)/nn
    for k in range(1,min(lag,nn-1)+1): s+=2.0*(1.0-k/(lag+1.0))*(float(e[k:]@e[:-k])/nn)
    return m/math.sqrt(s/nn) if s>0 else float('nan')

groups={'capitulation (z<-2.5, vol>1.4x)':[], 'any 2.5-sigma down':[], 'all days':[]}
for i in range(25,n-4):
    d=dts[i]
    if d not in VIX: continue
    d3=dts[i+3]
    if d3 not in VIX: continue
    rv=r_[i-19:i+1].std(ddof=1)
    if not np.isfinite(rv) or rv<=0: continue
    st=math.log(cl[i]/cl[i-5])/(rv*math.sqrt(5))
    vx=vo[i]/max(np.mean(vo[i-19:i+1]),1.0)
    chg=(VIX[d3]/VIX[d]-1.0)*100
    groups['all days'].append((chg,VIX[d]))
    if st<-2.5: groups['any 2.5-sigma down'].append((chg,VIX[d]))
    if st<-2.5 and vx>=1.4: groups['capitulation (z<-2.5, vol>1.4x)'].append((chg,VIX[d]))

print()
print('='*96)
print('CHANGE IN VIX OVER THE 3 SESSIONS AFTER THE SIGNAL')
print('  negative = implied volatility FALLS = a short-vega credit spread WINS')
print('='*96)
print('%-34s %7s %11s %11s %9s %9s'%('condition','n','mean %','median %','t','VIX at entry'))
for k,v in groups.items():
    if len(v)<20: continue
    a=np.array([x[0] for x in v]); lv=np.array([x[1] for x in v])
    print('%-34s %7d %10.2f%% %10.2f%% %9.2f %9.1f'%(k,len(a),a.mean(),np.median(a),nw_t(a,3),lv.mean()))
cap=np.array([x[0] for x in groups['capitulation (z<-2.5, vol>1.4x)']])
allr=np.array([x[0] for x in groups['all days']])
if len(cap)>20:
    d_=cap.mean()-allr.mean()
    se=math.sqrt(cap.var(ddof=1)/len(cap)+allr.var(ddof=1)/len(allr))
    print()
    print('  capitulation minus all-days: %+.2f pct-points  t=%.2f'%(d_,d_/se))
    print('  share of capitulation events where VIX FELL: %.1f%%'%(100*(cap<0).mean()))
    print()
    print('  percentiles of the VIX change after capitulation:')
    for p in (5,25,50,75,95): print('     p%-3d %+7.2f%%'%(p,np.percentile(cap,p)))

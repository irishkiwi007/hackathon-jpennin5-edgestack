import json,math,os,subprocess,sys,io,datetime
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
A=r'C:\Users\Lenovo\go\bin\alpaca.exe'; env=dict(os.environ)
def run(a):
    r=subprocess.run([A]+a+['--quiet'],capture_output=True,text=True,env=env)
    if r.returncode!=0: return None
    try: return json.loads(r.stdout)
    except Exception: return None
SYMS=['NVDA','TSLA','AAPL','AMD','MSFT','AMZN','META','GOOGL','NFLX','SPY']
EXPS=['2026-09-04','2026-09-11','2026-09-18']
print('Cost to express a 5-day DIRECTIONAL view. Move needed just to clear the bid-ask.')
print(f'{"sym":>7} {"spot":>9} {"exp":>12} {"ATM IV":>8} | {"single opt":>11} {"move bp":>9} | {"debit sprd":>11} {"move bp":>9}')
for s in SYMS:
    b=run(['data','bars','--symbol',s,'--timeframe','1Day','--start','2026-08-26','--end','2026-08-29T00:00:00Z','--adjustment','all'])
    if not b or not b.get('bars'): continue
    spot=b['bars'][-1]['c']
    done=False
    for e in EXPS:
        if done: break
        ch=run(['data','option','chain','--underlying-symbol',s,'--feed','indicative','--expiration-date',e,
                '--limit','300','--strike-price-gte',str(round(spot*0.96,0)),'--strike-price-lte',str(round(spot*1.08,0))])
        if not ch or not ch.get('snapshots'): continue
        calls={}
        ivs=[]
        for k,v in ch['snapshots'].items():
            if k[-9]!='C': continue
            q=v.get('latestQuote') or {}; d=(v.get('greeks') or {}).get('delta'); iv=v.get('impliedVolatility')
            if not q.get('bp') or not q.get('ap') or q['ap']<=q['bp'] or d is None: continue
            calls[int(k[-8:])/1000]=(q['bp'],q['ap'],d)
            if iv and 0.40<abs(d)<0.60: ivs.append(iv)
        if len(calls)<4: continue
        ks=sorted(calls)
        atm=min(ks,key=lambda x:abs(calls[x][2]-0.50))
        bp,ap,d1=calls[atm]
        single_rt=ap-bp
        single_move=single_rt/abs(d1)/spot*1e4
        up=[x for x in ks if x>atm+spot*0.015]
        if not up: continue
        k2=up[0]; b2,a2,d2=calls[k2]
        sprd_rt=(ap-bp)+(a2-b2); nd=abs(d1-d2)
        if nd<0.02: continue
        sprd_move=sprd_rt/nd/spot*1e4
        print(f'{s:>7} {spot:>9.2f} {e:>12} {(sum(ivs)/len(ivs)*100 if ivs else 0):>7.1f}% | '
              f'{single_rt*100:>10.0f}$ {single_move:>9.1f} | {sprd_rt*100:>10.0f}$ {sprd_move:>9.1f}')
        done=True
print("""
'move bp' = how far the underlying must travel before the position covers its own bid-ask.
Compare against the news-spike edge (raw excess |5d move| was +1.47% = 147bp, but the DIRECTIONAL
edge is the continuation score, which is far smaller).""")

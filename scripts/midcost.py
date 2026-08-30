import json,math,os,subprocess,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
A=r'C:\Users\Lenovo\go\bin\alpaca.exe'; env=dict(os.environ)
def run(a):
    r=subprocess.run([A]+a+['--quiet'],capture_output=True,text=True,env=env)
    if r.returncode!=0: return None
    try: return json.loads(r.stdout)
    except Exception: return None
SYMS=['PCAR','CSX','EMR','ZBH','DGX','TSCO','ULTA','DPZ','NTRS','ZION','AKAM','NTAP',
      'WDC','NUE','STLD','PKG','DVN','HAL','AEE','NI','EXPD','JBHT']
EXPS=['2026-09-18','2026-10-16']
print('Mid-cap option cost: SPY move needed just to clear the bid-ask on a long ATM call')
print(f'{"sym":>7} {"spot":>9} {"ATM IV":>8} {"bid":>7} {"ask":>7} {"spr%mid":>9} {"move bp":>9} {"verdict":>12}')
ok=[]
for s in SYMS:
    b=run(['data','bars','--symbol',s,'--timeframe','1Day','--start','2026-08-26','--end','2026-08-29T00:00:00Z','--adjustment','all'])
    if not b or not b.get('bars'): continue
    spot=b['bars'][-1]['c']; done=False
    for e in EXPS:
        if done: break
        ch=run(['data','option','chain','--underlying-symbol',s,'--feed','indicative','--expiration-date',e,
                '--limit','200','--strike-price-gte',str(round(spot*0.94,0)),'--strike-price-lte',str(round(spot*1.06,0))])
        if not ch or not ch.get('snapshots'): continue
        best=None
        for k,v in ch['snapshots'].items():
            if k[-9]!='C': continue
            q=v.get('latestQuote') or {}; d=(v.get('greeks') or {}).get('delta'); iv=v.get('impliedVolatility')
            if not q.get('bp') or not q.get('ap') or q['ap']<=q['bp'] or d is None: continue
            if 0.40<abs(d)<0.60:
                mid=(q['bp']+q['ap'])/2
                cand=(q['bp'],q['ap'],d,iv,mid,(q['ap']-q['bp'])/mid)
                if best is None or cand[5]<best[5]: best=cand
        if best:
            bp,ap,d,iv,mid,pct=best
            move=(ap-bp)/abs(d)/spot*1e4
            v='TRADEABLE' if move<40 else ('marginal' if move<100 else 'reject')
            if move<40: ok.append(s)
            print(f'{s:>7} {spot:>9.2f} {(iv or 0)*100:>7.1f}% {bp:>7.2f} {ap:>7.2f} {pct*100:>8.1f}% {move:>9.1f} {v:>12}')
            done=True
    if not done: print(f'{s:>7} {spot:>9.2f}  (no usable chain)')
print(f'\ntradeable at <40bp: {len(ok)} -> {ok}')
print('compare: NVDA 3.5bp, SPY 3.1bp, AMZN 12.2bp for the same structure')

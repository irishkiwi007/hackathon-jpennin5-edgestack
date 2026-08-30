"""If intraday oscillations are real, can OPTIONS capture them?

Three costs stack up:
  1. the SPY move must be large enough to move the option meaningfully
  2. the option bid-ask must be crossed - twice per leg, on entry and exit
  3. free-tier option quotes are 15 MINUTES DELAYED, so at the moment of a micro-oscillation you
     cannot see what you are paying

Measures the real numbers from the live chain rather than assuming them.
"""
import json, math, os, subprocess, sys, io, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


b = run(['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day',
         '--start', '2026-08-26', '--end', '2026-08-29T00:00:00Z'])
spot = b['bars'][-1]['c']
print(f'SPY spot {spot:.2f}\n')

# nearest expiries = highest gamma, what an intraday trader would use
EXPS = ['2026-08-31', '2026-09-01', '2026-09-02', '2026-09-04']
print('=' * 100)
print('OPTION TRANSACTION COST BY EXPIRY — near-the-money, live chain')
print('=' * 100)
print(f'{"expiry":>12} {"DTE":>4} {"strike":>7} {"bid":>7} {"ask":>7} {"mid":>7} '
      f'{"spread":>7} {"spr % of mid":>13} {"delta":>7}')
rows = []
for e in EXPS:
    ch = run(['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
              '--expiration-date', e, '--limit', '80',
              '--strike-price-gte', str(int(spot - 4)), '--strike-price-lte', str(int(spot + 4))])
    if not ch or not ch.get('snapshots'):
        print(f'{e:>12}  (no chain)')
        continue
    dte = (datetime.date.fromisoformat(e) - datetime.date(2026, 8, 28)).days
    best = None
    for k, v in ch['snapshots'].items():
        q = v.get('latestQuote') or {}
        d_ = (v.get('greeks') or {}).get('delta')
        bp, ap = q.get('bp'), q.get('ap')
        if not bp or not ap or ap <= bp or d_ is None:
            continue
        if 0.40 < abs(d_) < 0.60:
            mid = (bp + ap) / 2
            cand = dict(k=int(k[-8:]) / 1000, bp=bp, ap=ap, mid=mid,
                        spr=ap - bp, pct=(ap - bp) / mid, d=d_, cp=k[-9])
            if best is None or cand['pct'] < best['pct']:
                best = cand
    if not best:
        print(f'{e:>12} {dte:>4}  (no ATM quote)')
        continue
    rows.append((e, dte, best))
    print(f'{e:>12} {dte:>4} {best["k"]:>7.0f} {best["bp"]:>7.2f} {best["ap"]:>7.2f} '
          f'{best["mid"]:>7.2f} {best["spr"]:>7.2f} {best["pct"]*100:>12.1f}% {best["d"]:>7.3f}')

print('\n' + '=' * 100)
print('WHAT SPY MOVE IS NEEDED TO BREAK EVEN?')
print('=' * 100)
print('single ATM option, one round trip (buy at ask, sell at bid):')
print(f'{"expiry":>12} {"DTE":>4} {"delta":>7} {"round-trip $":>13} {"SPY move needed":>17} '
      f'{"in bp":>8}')
for e, dte, o in rows:
    rt = o['spr']                      # cross once each way = full spread
    need = rt / abs(o['d'])            # points of SPY
    print(f'{e:>12} {dte:>4} {abs(o["d"]):>7.3f} {rt*100:>12.0f}$ {need:>16.3f} '
          f'{need/spot*10000:>8.1f}')

print('\ndefined-risk VERTICAL SPREAD (2 legs, so 2 spreads crossed each way):')
print(f'{"expiry":>12} {"DTE":>4} {"net delta":>10} {"round-trip $":>13} '
      f'{"SPY move needed":>17} {"in bp":>8}')
for e, dte, o in rows:
    ch = run(['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
              '--expiration-date', e, '--limit', '120',
              '--strike-price-gte', str(int(spot - 1)), '--strike-price-lte', str(int(spot + 7))])
    if not ch:
        continue
    legs = {}
    for k, v in ch['snapshots'].items():
        if k[-9] != o['cp']:
            continue
        q = v.get('latestQuote') or {}
        d_ = (v.get('greeks') or {}).get('delta')
        if q.get('bp') and q.get('ap') and q['ap'] > q['bp'] and d_ is not None:
            legs[int(k[-8:]) / 1000] = (q['bp'], q['ap'], d_)
    ks = sorted(legs)
    k1 = min(ks, key=lambda x: abs(x - o['k']))
    up = [x for x in ks if x > k1 + 2]
    if not up:
        continue
    k2 = up[0]
    rt = (legs[k1][1] - legs[k1][0]) + (legs[k2][1] - legs[k2][0])
    nd = abs(legs[k1][2] - legs[k2][2])
    if nd < 0.01:
        continue
    need = rt / nd
    print(f'{e:>12} {dte:>4} {nd:>10.3f} {rt*100:>12.0f}$ {need:>16.3f} '
          f'{need/spot*10000:>8.1f}')

print("""
Compare the 'in bp' column against the measured size of a 1-minute SPY midquote move.
If the required move is larger than a typical oscillation, the structure cannot capture it
no matter how well timed.""")

print('\n' + '=' * 100)
print('THE DATA-DELAY PROBLEM')
print('=' * 100)
q = run(['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
         '--expiration-date', EXPS[0], '--limit', '4',
         '--strike-price-gte', str(int(spot)), '--strike-price-lte', str(int(spot + 2))])
if q and q.get('snapshots'):
    for k, v in list(q['snapshots'].items())[:2]:
        qq = v.get('latestQuote') or {}
        print(f'  {k}  quote timestamp: {qq.get("t")}')
print(f'  wall clock now:  {datetime.datetime.now(datetime.timezone.utc).isoformat()}')
print("""
Free-tier option quotes come from the INDICATIVE feed, delayed 15 minutes. An oscillation that
lasts minutes will be over before its price is visible. Paper fills execute against real-time
quotes, so the fill is real - but the decision is made blind, and no limit price can be set
sensibly. The underlying (IEX) is real-time; the options are not.""")

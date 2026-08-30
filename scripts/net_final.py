"""Net expectancy with the calm-bond overlay, and the CURRENT live regime.

The engine CSVs stop at 2026-05-01, so the regime state for Monday has to be computed from live
TLT data. Everything else uses the validated construction:

    calm  =  TLT 21-day stdev  <  its own 90-day mean, 1.5% hysteresis
"""
import os
import io, json, math, sys, time, datetime, urllib.request
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
TOL, TLT_STD_LB, VOL_LB = 0.015, 21, 90

_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

FR = json.load(open('friction_screen.json'))
DELTA = 0.35        # a ~ATM 5%-wide bull put spread captures roughly a third of the move

print()
print('=' * 104)
print('NET EXPECTANCY per contract — calm regime only, by friction budget')
print('  gross = move% x spot x delta x 100 ;  cost = 2 x one-way friction (quoted at mid)')
print('=' * 104)
print('{:<12} {:>6} {:>7} {:>9} {:>7} {:>7} {:>10} {:>9} {:>10} {:>10}'.format(
    'budget', 'names', 'n', 'move%', 't', 'win%', 'gross $', 'fric $', 'NET $', 'sig/5d'))
best = None
for budget in (10, 20, 35, 60, 100, 10 ** 9):
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    g = [r for r in EV if r['sym'] in names and r['vol']]
    if len(g) < 40:
        continue
    raw = np.array([r['f3'] for r in g])
    spots = np.array([r['spot'] for r in g])
    e = np.array([r['f3'] - BASEM[r['sym']] for r in g])
    gross = float(np.mean(raw / 100.0 * spots * DELTA * 100))
    fr = float(np.median([FR[s]['friction'] for s in names if FR[s]]))
    net = gross - 2 * fr
    per5 = len(g) / 19.1 / 252 * 5
    lab = 'any' if budget > 1e8 else '<= ${}'.format(budget)
    print('{:<12} {:>6} {:>7} {:>9.3f} {:>7.2f} {:>6.1f}% {:>10.0f} {:>9.0f} {:>10.0f} {:>10.2f}'
          .format(lab, len(names), len(g), raw.mean(), nw_t(e, HOLD),
                  (raw > 0).mean() * 100, gross, fr, net, per5))
    if net > 0 and (best is None or net * per5 > best[0]):
        best = (net * per5, lab, len(names), len(g), raw.mean(), net, per5)

if best:
    print()
    print('  best expected-value-per-window cell: {} ({} names)'.format(best[1], best[2]))
    print('  {:+.0f} $/contract x {:.2f} signals per 5 sessions = {:+.0f} $ per contract '
          'per contest window'.format(best[5], best[6], best[0]))

print()
print('=' * 104)
print('CURRENT REGIME — computed from live TLT (engine CSVs stop 2026-05-01)')
print('=' * 104)


def q(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(0.6)
    return None


start = (datetime.date.today() - datetime.timedelta(days=420)).isoformat()
d = q('https://data.alpaca.markets/v2/stocks/TLT/bars?timeframe=1Day&feed=sip'
      '&start={}&limit=10000&adjustment=all'.format(start))
bars = (d or {}).get('bars') or []
print('  TLT sessions pulled: {}  ({} -> {})'.format(
    len(bars), bars[0]['t'][:10] if bars else '-', bars[-1]['t'][:10] if bars else '-'))
if len(bars) > TLT_STD_LB + VOL_LB:
    closes = [float(b['c']) for b in bars]
    dts = [b['t'][:10] for b in bars]
    stds = []
    for i in range(TLT_STD_LB, len(closes) + 1):
        w = closes[i - TLT_STD_LB:i]
        m = sum(w) / len(w)
        stds.append(math.sqrt(sum((x - m) ** 2 for x in w) / (len(w) - 1)))
    state = False
    hist = []
    for j in range(VOL_LB, len(stds) + 1):
        window = stds[j - VOL_LB:j]
        now, avg = window[-1], sum(window) / len(window)
        state = (now < avg * (1 - TOL)) if not state else (now <= avg * (1 + TOL))
        hist.append((dts[TLT_STD_LB - 1 + j - 1], state, now, avg))
    for dt, st, now, avg in hist[-8:]:
        print('    {}  {:<8}  21d sd {:.3f}  vs 90d mean {:.3f}   ratio {:.3f}'.format(
            dt, 'CALM' if st else 'STRESSED', now, avg, now / avg if avg else 0))
    last = hist[-1]
    print()
    print('  >>> REGIME FOR MONDAY: {} <<<'.format('CALM' if last[1] else 'STRESSED'))
    print('  {}'.format('Overlay is PERMISSIVE - capitulation signals may be taken.'
                        if last[1] else
                        'Overlay is BLOCKING - capitulation signals measure ~0 in this regime.'))
    n_calm = sum(1 for h in hist[-60:] if h[1])
    print('  last 60 sessions: {} calm, {} stressed'.format(n_calm, 60 - n_calm))

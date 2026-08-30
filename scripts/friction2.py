"""Option 2: find a structure whose EDGE survives its FRICTION.

Baseline problem: bull put spread ATM/-5%, 8-21 DTE, closed after 3 sessions.
  gross +$37.8/contract, friction ~$140 round trip -> deeply negative.

Levers, in order of expected impact:

  1. HOLD TO EXPIRY. An OTM short put that expires worthless needs no closing trade at all.
     That removes the exit haircut outright - half the friction, for free.
  2. LONGER DTE. Credit grows faster than the bid/ask widens, so credit-per-dollar-of-friction
     improves. Costs drift from the tested 3-day hold.
  3. MONEYNESS. OTM options are cheaper in absolute terms, so their absolute spread is tighter -
     but the credit falls too. Only the RATIO matters.

The diagnostic is credit / friction. A structure needs credit >> friction before any edge can
survive, and the current one has credit/friction ~ 2.9 at entry - which a round trip erases.
"""
import os
import json, sys, io, math, time, datetime, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'

# the liquid core only - the illiquid tail was 20-40x more expensive to trade
UNIVERSE = ['SPY', 'QQQ', 'IWM', 'HYG', 'XLP', 'XLE', 'XLF', 'XLI', 'XLV', 'XLK',
            'EEM', 'EFA', 'GDX', 'KRE', 'SOXX', 'SMH']


def q(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.5)
    return None


today = datetime.date.today()
spot = {}
d = q(DATA + '/v2/stocks/bars/latest?symbols=' + ','.join(UNIVERSE) + '&feed=iex')
for s, b in (d or {}).get('bars', {}).items():
    spot[s] = float(b['c'])

# pull one wide chain per symbol covering every DTE bucket we want to test
CH = {}
for sym in UNIVERSE:
    if sym not in spot:
        continue
    lo = (today + datetime.timedelta(days=5)).isoformat()
    hi = (today + datetime.timedelta(days=75)).isoformat()
    c = q('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
          '&expiration_date_lte={}&type=put&limit=1000&status=active'
          .format(PAPER, sym, lo, hi))
    rows = (c or {}).get('option_contracts') or []
    S = spot[sym]
    rows = [x for x in rows if x.get('tradable')
            and 0.80 * S <= float(x['strike_price']) <= 1.02 * S]
    if not rows:
        continue
    occ = [x['symbol'] for x in rows]
    snaps = {}
    for i in range(0, len(occ), 100):
        sd = q(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[i:i + 100]))
        for k, v in (sd or {}).get('snapshots', {}).items():
            qt = v.get('latestQuote') or {}
            b_, a_ = float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0)
            if b_ > 0 and a_ >= b_:
                snaps[k] = (b_, a_)
    byexp = defaultdict(dict)
    for x in rows:
        if x['symbol'] in snaps:
            byexp[x['expiration_date']][float(x['strike_price'])] = snaps[x['symbol']]
    if byexp:
        CH[sym] = byexp
print('chains for {} symbols'.format(len(CH)))


def nearest(ks, target):
    return min(ks, key=lambda k: abs(k - target)) if ks else None


def spread_for(sym, exp, short_pct, width_pct):
    """Return (credit_mid, friction, width) for a bull put spread at these offsets."""
    S = spot[sym]
    ks = sorted(CH[sym][exp])
    sk = nearest(ks, S * (1 + short_pct))
    if sk is None:
        return None
    below = [k for k in ks if k < sk]
    lk = nearest(below, S * (1 + short_pct - width_pct))
    if lk is None or lk >= sk:
        return None
    sb, sa = CH[sym][exp][sk]
    lb, la = CH[sym][exp][lk]
    credit_mid = 0.5 * (sb + sa) - 0.5 * (lb + la)
    friction = 0.5 * ((sa - sb) + (la - lb))     # half-spread on each leg = cost to cross once
    width = sk - lk
    if credit_mid <= 0 or width <= 0:
        return None
    return credit_mid, friction, width


DTE_BUCKETS = [(5, 12, '~1wk'), (13, 24, '~3wk'), (25, 45, '~5wk'), (46, 75, '~9wk')]
print()
print('=' * 100)
print('LEVER 2+3: DTE x MONEYNESS — credit per dollar of one-way friction')
print('  round trip needs credit/friction > 2 just to break even on costs alone')
print('=' * 100)
print('{:<8} {:<12} {:>7} {:>10} {:>10} {:>12} {:>12}'.format(
    'DTE', 'short strike', 'n', 'credit', 'friction', 'cred/fric', 'cred/width'))
best = []
for lo_d, hi_d, dlab in DTE_BUCKETS:
    for short_pct, mlab in ((0.0, 'ATM'), (-0.03, '3% OTM'), (-0.05, '5% OTM')):
        cs, fs, ws = [], [], []
        for sym in CH:
            for exp in CH[sym]:
                dte = (datetime.date.fromisoformat(exp) - today).days
                if not (lo_d <= dte <= hi_d):
                    continue
                r = spread_for(sym, exp, short_pct, 0.05)
                if r:
                    cs.append(r[0]); fs.append(r[1]); ws.append(r[2])
                break
        if len(cs) < 5:
            continue
        c, f, w = np.mean(cs), np.mean(fs), np.mean(ws)
        ratio = c / f if f > 0 else 0
        best.append((ratio, dlab, mlab, c, f, w, len(cs)))
        print('{:<8} {:<12} {:>7} {:>10.2f} {:>10.2f} {:>12.2f} {:>11.1%}'.format(
            dlab, mlab, len(cs), c, f, ratio, c / w))

print()
print('=' * 100)
print('LEVER 1: HOLD TO EXPIRY — what it saves')
print('=' * 100)
if best:
    best.sort(reverse=True)
    r, dlab, mlab, c, f, w, n = best[0]
    print('  best credit/friction structure: {} {}  credit ${:.0f}/contract, '
          'one-way friction ${:.0f}'.format(dlab, mlab, c * 100, f * 100))
    print()
    print('  {:<34} {:>12} {:>12} {:>12}'.format('exit policy', 'friction $', 'vs credit', 'verdict'))
    for lab, mult in (('close after 3 sessions', 2.0), ('hold to expiry (OTM, no close)', 1.0)):
        fr = f * 100 * mult
        print('  {:<34} {:>12.0f} {:>11.0f}% {:>12}'.format(
            lab, fr, 100 * fr / (c * 100), 'crushes it' if fr > 0.5 * c * 100 else 'survivable'))

print()
print('=' * 100)
print('BASELINE for comparison — what the agent does today')
print('=' * 100)
cs, fs = [], []
for sym in CH:
    for exp in sorted(CH[sym]):
        dte = (datetime.date.fromisoformat(exp) - today).days
        if 8 <= dte <= 21:
            r = spread_for(sym, exp, 0.0, 0.05)
            if r:
                cs.append(r[0]); fs.append(r[1])
            break
if cs:
    c, f = np.mean(cs), np.mean(fs)
    print('  ATM/-5%, 8-21 DTE, closed at 3 sessions:')
    print('    credit ${:.0f}   round-trip friction ${:.0f}   ratio {:.2f}'.format(
        c * 100, f * 200, c / (2 * f)))
    print('    gross edge was +$37.8/contract -> net {:+.0f}'.format(37.8 - f * 200))

print()
print('=' * 100)
print('PER-SYMBOL, best structure — where is friction actually payable?')
print('=' * 100)
if best:
    _, dlab, mlab, *_ = best[0]
    short_pct = {'ATM': 0.0, '3% OTM': -0.03, '5% OTM': -0.05}[mlab]
    lo_d, hi_d = next((a, b) for a, b, l in DTE_BUCKETS if l == dlab)
    print('{:<8} {:>10} {:>10} {:>12} {:>14}'.format(
        'sym', 'credit $', 'fric $', 'cred/fric', 'net if +1.6%'))
    rows = []
    for sym in sorted(CH):
        for exp in sorted(CH[sym]):
            dte = (datetime.date.fromisoformat(exp) - today).days
            if lo_d <= dte <= hi_d:
                r = spread_for(sym, exp, short_pct, 0.05)
                if r:
                    rows.append((sym, r[0] * 100, r[1] * 100, r[0] / r[1] if r[1] else 0))
                break
    for sym, c, f, ratio in sorted(rows, key=lambda x: -x[3]):
        print('{:<8} {:>10.0f} {:>10.0f} {:>12.2f} {:>14.0f}'.format(sym, c, f, ratio, c - f))

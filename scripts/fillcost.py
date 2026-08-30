"""What does the agent's CONSERVATIVE fill actually cost, on real chains?

spread_builder prices the credit as (short bid - long ask): the worst realistic fill. Every
backtest so far used trade prices near mid. If the bid/ask haircut is large, live expectancy is
materially below the backtest - and if the conservative credit falls below the 12%-of-width gate,
the agent never trades at all.

This builds the EXACT spread the agent would build, on live chains, and compares.
"""
import os
import json, sys, io, math, time, datetime, urllib.request, urllib.parse
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'
MIN_CREDIT_TO_WIDTH = 0.12
UNIVERSE = ['SPY', 'QQQ', 'IWM', 'SOXX', 'XLV', 'XLP', 'XLE', 'XLF', 'XLI', 'XLU', 'XLY',
            'XLK', 'XLB', 'XLRE', 'XLC', 'HYG', 'FDN', 'IGV', 'SMH', 'XBI', 'IBB', 'KRE',
            'XOP', 'GDX', 'EEM', 'EFA', 'FXI', 'EWZ', 'XRT', 'XME', 'ITB', 'VNQ', 'ARKK']


def q(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.6)
    return None


today = datetime.date.today()
lo = (today + datetime.timedelta(days=8)).isoformat()
hi = (today + datetime.timedelta(days=21)).isoformat()

spot = {}
d = q(DATA + '/v2/stocks/bars/latest?symbols=' + ','.join(UNIVERSE) + '&feed=iex')
for s, b in (d or {}).get('bars', {}).items():
    spot[s] = float(b['c'])
print('spots for {} symbols'.format(len(spot)))

rows = []
for sym in UNIVERSE:
    if sym not in spot:
        continue
    S = spot[sym]
    c = q('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
          '&expiration_date_lte={}&type=put&limit=500&status=active'
          .format(PAPER, sym, lo, hi))
    contracts = (c or {}).get('option_contracts') or []
    if not contracts:
        continue
    exps = sorted({x['expiration_date'] for x in contracts})
    if not exps:
        continue
    exp = exps[0]
    chain = [x for x in contracts
             if x['expiration_date'] == exp and x.get('tradable')
             and 0.85 * S <= float(x['strike_price']) <= 1.05 * S]
    if len(chain) < 2:
        continue
    occ = [x['symbol'] for x in chain]
    snaps = {}
    for i in range(0, len(occ), 100):
        sd = q(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[i:i + 100]))
        for k, v in (sd or {}).get('snapshots', {}).items():
            qt = v.get('latestQuote') or {}
            snaps[k] = (float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0))
    by_strike = {}
    for x in chain:
        k = float(x['strike_price'])
        b, a = snaps.get(x['symbol'], (0.0, 0.0))
        if b > 0 and a >= b:
            by_strike[k] = (x['symbol'], b, a)
    if len(by_strike) < 2:
        continue
    strikes = sorted(by_strike)
    short_k = min(strikes, key=lambda k: abs(k - S))
    below = [k for k in strikes if k < short_k]
    if not below:
        continue
    long_k = min(below, key=lambda k: abs(k - S * 0.95))
    sname, sb, sa = by_strike[short_k]
    lname, lb, la = by_strike[long_k]
    width = short_k - long_k
    if width <= 0:
        continue
    cons = sb - la                     # conservative: sell the bid, buy the ask
    mid = 0.5 * (sb + sa) - 0.5 * (lb + la)
    rows.append(dict(sym=sym, spot=S, exp=exp, sk=short_k, lk=long_k, width=width,
                     cons=cons, mid=mid,
                     s_spread=(sa - sb), l_spread=(la - lb),
                     s_mid=0.5 * (sb + sa), l_mid=0.5 * (lb + la)))

print('built {} spreads\n'.format(len(rows)))
print('=' * 104)
print('CONSERVATIVE FILL vs MID — the exact spread the agent would build')
print('=' * 104)
print('{:<6} {:>8} {:>7} {:>9} {:>9} {:>9} {:>9} {:>8} {:>8}'.format(
    'sym', 'spot', 'width', 'mid cr', 'cons cr', 'haircut', 'cons/w', 'mid/w', 'gate'))
n_pass_c = n_pass_m = 0
for r in sorted(rows, key=lambda r: r['sym']):
    cw = r['cons'] / r['width']
    mw = r['mid'] / r['width']
    okc = cw >= MIN_CREDIT_TO_WIDTH
    okm = mw >= MIN_CREDIT_TO_WIDTH
    n_pass_c += okc
    n_pass_m += okm
    print('{:<6} {:>8.2f} {:>7.2f} {:>9.2f} {:>9.2f} {:>9.2f} {:>8.1%} {:>7.1%} {:>8}'.format(
        r['sym'], r['spot'], r['width'], r['mid'], r['cons'], r['mid'] - r['cons'],
        cw, mw, 'PASS' if okc else 'fail'))

if rows:
    hc = np.array([r['mid'] - r['cons'] for r in rows])
    cw = np.array([r['cons'] / r['width'] for r in rows])
    mw = np.array([r['mid'] / r['width'] for r in rows])
    w = np.array([r['width'] for r in rows])
    print()
    print('  mean haircut  ${:.2f}/share  = ${:.0f}/contract'.format(hc.mean(), hc.mean() * 100))
    print('  haircut as a share of the mid credit: {:.1%}'.format(
        hc.sum() / max(sum(r['mid'] for r in rows), 1e-9)))
    print('  credit/width   conservative {:.1%}   mid {:.1%}'.format(cw.mean(), mw.mean()))
    print('  clears the {:.0%} gate:  conservative {}/{}   mid {}/{}'.format(
        MIN_CREDIT_TO_WIDTH, n_pass_c, len(rows), n_pass_m, len(rows)))
    print()
    print('  ROUND TRIP: entry haircut + exit haircut = ${:.0f}/contract of pure friction,'
          .format(hc.mean() * 200))
    print('  against a historical mean of +$37.8/contract for this structure.')

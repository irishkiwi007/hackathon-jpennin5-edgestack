"""Does the capitulation shape hold on individual names, across the full large-cap universe?

Two open problems this addresses at once:
  1. Restricting ETFs to the low-friction core (SPY/QQQ/IWM/...) leaves very few signals.
  2. The earlier 105-name single-stock test was weaker than ETFs (+0.914%, t=2.19 vs +1.646%,
     t=5.42) - but 105 names is a small, hand-picked slice. 500 names is a real test.

Universe is built from Alpaca's own asset list: US equities that are tradable, optionable and
liquid. That is a better universe for this purpose than exact index membership - a name we
cannot trade options on is useless regardless of whether it is in the index.
"""
import os
import json, sys, io, math, os, time, datetime, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'
CACHE = 'sp500_bars.json'
UNIV_CACHE = 'sp500_univ.json'
START = '2016-01-01'


def q(u, tries=4, timeout=90):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=timeout))
        except Exception:
            time.sleep(0.8)
    return None


# ---- universe: tradable, optionable, liquid --------------------------------------------
if os.path.exists(UNIV_CACHE):
    UNIV = json.load(open(UNIV_CACHE))
else:
    assets = q(PAPER + '/v2/assets?status=active&asset_class=us_equity', timeout=180) or []
    cand = [a['symbol'] for a in assets
            if a.get('tradable') and a.get('status') == 'active'
            and 'has_options' in (a.get('attributes') or [])
            and a.get('exchange') in ('NASDAQ', 'NYSE', 'ARCA', 'AMEX')
            and '.' not in a['symbol'] and '/' not in a['symbol']
            and len(a['symbol']) <= 5]
    print('optionable candidates: {}'.format(len(cand)))
    # rank by recent dollar volume, keep the top 500
    dv = {}
    for i in range(0, len(cand), 100):
        ch = cand[i:i + 100]
        d = q(DATA + '/v2/stocks/bars?symbols=' + ','.join(ch) +
              '&timeframe=1Day&feed=sip&start=2026-06-01&limit=10000&adjustment=all')
        for sym, rows in (d or {}).get('bars', {}).items():
            if len(rows) > 20:
                dv[sym] = float(np.median([r['c'] * r['v'] for r in rows]))
        if (i // 100) % 5 == 0:
            print('  ranked {}/{}'.format(min(i + 100, len(cand)), len(cand)))
    UNIV = [s for s, _ in sorted(dv.items(), key=lambda kv: -kv[1])[:500]]
    json.dump(UNIV, open(UNIV_CACHE, 'w'))
print('universe: {} liquid optionable names'.format(len(UNIV)))

# ---- bars -------------------------------------------------------------------------------
D = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
todo = [s for s in UNIV if s not in D]
print('fetching {} new symbols'.format(len(todo)))
for i in range(0, len(todo), 100):
    ch = todo[i:i + 100]
    got, tok = defaultdict(list), None
    while True:
        u = (DATA + '/v2/stocks/bars?symbols=' + ','.join(ch) +
             '&timeframe=1Day&feed=sip&start=' + START + '&limit=10000&adjustment=all')
        if tok:
            u += '&page_token=' + tok
        d = q(u, timeout=180)
        if not d:
            break
        for sym, rows in (d.get('bars') or {}).items():
            got[sym] += rows
        tok = d.get('next_page_token')
        if not tok:
            break
    for sym in ch:
        D[sym] = [{'t': b['t'][:10], 'c': b['c'], 'v': b['v']} for b in got.get(sym, [])]
    json.dump(D, open(CACHE, 'w'))
    print('  pulled {}/{}'.format(min(i + 100, len(todo)), len(todo)))

U = [s for s in UNIV if len(D.get(s, [])) > 900]
print('with usable history: {}'.format(len(U)))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 15:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


HOLD = 3
ROWS = []
BASE = {}
for s in U:
    b = D[s]
    c = np.array([x['c'] for x in b], float)
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    if n < 60 or (c <= 0).any():
        continue
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    fwd = [math.log(c[i + HOLD] / c[i]) * 100 for i in range(25, n - HOLD)]
    if not fwd:
        continue
    BASE[s] = float(np.mean(fwd))
    for i in range(25, n - HOLD):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        stretch = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        volx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if stretch >= -1.0:
            continue                                    # keep the file small
        ROWS.append(dict(sym=s, date=dt[i], stretch=stretch, volx=volx,
                         f3=math.log(c[i + HOLD] / c[i]) * 100))
print('conditioned observations: {}'.format(len(ROWS)))
YRS = 10.6


def stat(g):
    if len(g) < 40:
        return None
    e = np.array([r['f3'] - BASE[r['sym']] for r in g])
    raw = np.array([r['f3'] for r in g])
    return dict(n=len(g), exc=e.mean(), t=nw_t(e, HOLD), raw=raw.mean(),
                win=(raw > 0).mean() * 100)


print()
print('=' * 104)
print('S&P-SCALE SINGLE NAMES — volume cells at stretch < -2.5, DISJOINT')
print('  ETF benchmark: 1.4-1.8x +0.721%/t2.67 | 1.8-2.5x +1.897%/t4.32 | >2.5x +1.312%/t3.96')
print('=' * 104)
print('{:<18} {:>7} {:>10} {:>10} {:>8} {:>8} {:>9}'.format(
    'volume cell', 'n', 'raw%', 'excess%', 't', 'win%', 'sig/yr'))
for lab, lo, hi in [('<1.0', 0, 1.0), ('1.0-1.4', 1.0, 1.4), ('1.4-1.8', 1.4, 1.8),
                    ('1.8-2.5', 1.8, 2.5), ('2.5-4.0', 2.5, 4.0), ('>4.0', 4.0, 1e9)]:
    g = [r for r in ROWS if r['stretch'] < -2.5 and lo <= r['volx'] < hi]
    s_ = stat(g)
    if not s_:
        print('{:<18} {:>7}  (thin)'.format(lab, len(g)))
        continue
    print('{:<18} {:>7} {:>10.3f} {:>10.3f} {:>8.2f} {:>7.1f}% {:>9.0f}'.format(
        lab, s_['n'], s_['raw'], s_['exc'], s_['t'], s_['win'], s_['n'] / YRS))

print()
print('=' * 104)
print('IS THE VOLUME PEAK THE SAME SHAPE?  (stretch depth x volume)')
print('=' * 104)
print('{:<16}'.format('stretch') + ''.join('{:>16}'.format(v) for v in
                                           ('vol 1.4-1.8', 'vol 1.8-2.5', 'vol >2.5')))
for slab, slo, shi in [('-3.5 or worse', -99, -3.5), ('-3.5..-3.0', -3.5, -3.0),
                       ('-3.0..-2.5', -3.0, -2.5), ('-2.5..-2.0', -2.5, -2.0),
                       ('-2.0..-1.5', -2.0, -1.5)]:
    line = '{:<16}'.format(slab)
    for vlo, vhi in ((1.4, 1.8), (1.8, 2.5), (2.5, 1e9)):
        g = [r for r in ROWS if slo <= r['stretch'] < shi and vlo <= r['volx'] < vhi]
        s_ = stat(g)
        line += '{:>16}'.format('{:+.2f}% t{:.1f}'.format(s_['raw'], s_['t']) if s_
                                else '-')
    print(line)

print()
print('=' * 104)
print('BY ERA — tier FULL equivalent (stretch<-2.5, vol 1.8-2.5x)')
print('=' * 104)
g = [r for r in ROWS if r['stretch'] < -2.5 and 1.8 <= r['volx'] < 2.5]
s_ = stat(g)
if s_:
    print('  OVERALL n={}  raw {:+.3f}%  excess {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
        s_['n'], s_['raw'], s_['exc'], s_['t'], s_['win']))
    print('  -> {:.0f} signals/yr, {:.2f}/day, {:.1f} expected in a 5-session window'.format(
        s_['n'] / YRS, s_['n'] / YRS / 252, s_['n'] / YRS / 252 * 5))
    print()
    print('{:<14} {:>7} {:>10} {:>8} {:>8}'.format('era', 'n', 'raw%', 't', 'win%'))
    npos = ntot = 0
    for lab, a, b in [('2016-2017', '2016', '2018'), ('2018-2019', '2018', '2020'),
                      ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                      ('2024-2026', '2024', '2027')]:
        gg = [r for r in g if a <= r['date'][:4] < b]
        st = stat(gg)
        if not st:
            print('{:<14} {:>7}  (thin)'.format(lab, len(gg)))
            continue
        ntot += 1; npos += 1 if st['raw'] > 0 else 0
        print('{:<14} {:>7} {:>10.3f} {:>8.2f} {:>7.1f}%'.format(
            lab, st['n'], st['raw'], st['t'], st['win']))
    print('\n  positive in {}/{} eras'.format(npos, ntot))

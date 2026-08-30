"""Invert the search: find directional edges that fire when trailing volatility is LOW.

The unifying finding was that IV/RV is 0.657 in turbulent conditions and 1.085 in calm ones
(corr = -0.684, t = -4.78). Every strategy tested so far fired into the turbulent bucket, where
options are cheapest relative to what the stock then does - so buying was expensive in absolute
terms and selling was cheap in relative terms.

This scans the opposite regime. A signal that fires when trailing RV is LOW gets:
  - options that are genuinely rich (IV/RV 1.085), so short premium is paid properly
  - lower absolute risk, since the name is quiet

Candidate directional edges, scanned in the low-RV regime only, in BOTH directions:
  - stretch (the same 5-day z-score, up and down)
  - volatility COMPRESSION (RV falling vs its own history)
  - volume
  - trend (position vs 50-day mean)

Reported as forward 3- and 10-day returns so the right structure and tenor can be chosen after.
"""
import io, json, math, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = json.load(open('sp500_bars.json'))
FR = json.load(open('friction_screen.json'))
BONDS = {'TLT','IEF','SHY','AGG','BND','TIP','LQD','HYG','JNK','MUB','VTEB','BSV','BIV','BLV',
         'VCIT','VCSH','IGSB','SHV','BIL','SGOV','TLH','EDV','VGIT','VGSH','VGLT','SCHO','SCHR',
         'MBB','EMB','PFF','SRLN','BKLN','FLOT','USFR','TFLO','STIP','VTIP','SPTL','SPTS','SPIB'}
LEV = {'TQQQ','SQQQ','SOXL','SOXS','SPXL','SPXS','SPXU','UPRO','SDS','SSO','QLD','QID','TNA',
       'TZA','LABU','LABD','YINN','YANG','FAS','FAZ','ERX','ERY','NUGT','DUST','JNUG','JDST',
       'BOIL','KOLD','UCO','SCO','GUSH','DRIP','UVXY','VXX','SVXY','VIXY','TSLL','NVDL','CONL',
       'MSTU','MSTX','BITX','ETHU','USD','TMF','TMV','TYD','TYO'}
NAMES = [s for s in D if len(D.get(s, [])) > 900 and s not in BONDS and s not in LEV]
print('universe: {}'.format(len(NAMES)))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 15:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


ROWS, BASE3, BASE10 = [], {}, {}
for s in NAMES:
    b = D[s]
    c = np.array([x['c'] for x in b], float)
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    if n < 300 or (c <= 0).any():
        continue
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    rv = np.full(n, np.nan)
    for i in range(20, n):
        rv[i] = r[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
    # each name's own RV history, so "low vol" is relative to the name not the market
    valid = rv[np.isfinite(rv)]
    if len(valid) < 200:
        continue
    q33, q67 = np.percentile(valid, [33, 67])
    f3 = [math.log(c[i + 3] / c[i]) * 100 for i in range(60, n - 10)]
    f10 = [math.log(c[i + 10] / c[i]) * 100 for i in range(60, n - 10)]
    if not f3:
        continue
    BASE3[s], BASE10[s] = float(np.mean(f3)), float(np.mean(f10))
    ma50 = np.convolve(c, np.ones(50) / 50, mode='valid')
    for i in range(60, n - 10):
        if not np.isfinite(rv[i]) or rv[i] <= 0:
            continue
        regime = 'low' if rv[i] < q33 else ('high' if rv[i] > q67 else 'mid')
        rv_prev = rv[i - 20] if np.isfinite(rv[i - 20]) else np.nan
        ROWS.append(dict(
            sym=s, date=dt[i], rv=rv[i], regime=regime,
            stretch=math.log(c[i] / c[i - 5]) / (rv[i] / math.sqrt(252) * math.sqrt(5)),
            volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
            compress=(rv[i] / rv_prev) if np.isfinite(rv_prev) and rv_prev > 0 else np.nan,
            trend=(c[i] / ma50[i - 49] - 1.0) if i - 49 < len(ma50) else np.nan,
            f3=math.log(c[i + 3] / c[i]) * 100,
            f10=math.log(c[i + 10] / c[i]) * 100))
print('observations: {}'.format(len(ROWS)))

LOW = [r for r in ROWS if r['regime'] == 'low']
print('low-RV regime observations: {} ({:.0f}%)'.format(len(LOW), 100 * len(LOW) / len(ROWS)))


def stat(g, key):
    if len(g) < 120:
        return None
    base = BASE3 if key == 'f3' else BASE10
    raw = np.array([r[key] for r in g])
    e = np.array([r[key] - base[r['sym']] for r in g])
    lag = 3 if key == 'f3' else 10
    return dict(n=len(g), raw=raw.mean(), exc=e.mean(), t=nw_t(e, lag),
                win=100 * (raw > 0).mean())


def sweep(name, key, buckets, rows):
    print()
    print('  ' + name)
    print('  {:<22} {:>7} {:>9} {:>7} {:>7}   {:>9} {:>7}'.format(
        '', 'n', 'f3 exc%', 't', 'win%', 'f10 exc%', 't'))
    for lab, lo, hi in buckets:
        g = [r for r in rows if np.isfinite(r[key]) and lo <= r[key] < hi]
        a, b = stat(g, 'f3'), stat(g, 'f10')
        if not a:
            continue
        print('  {:<22} {:>7} {:>9.3f} {:>7.2f} {:>6.1f}%   {:>9.3f} {:>7.2f}'.format(
            lab, a['n'], a['exc'], a['t'], a['win'],
            b['exc'] if b else float('nan'), b['t'] if b else float('nan')))


print()
print('=' * 100)
print('LOW-RV REGIME ONLY — where IV/RV is 1.085 and short premium is paid properly')
print('=' * 100)
sweep('5-day stretch', 'stretch',
      [('z < -2', -99, -2), ('-2..-1', -2, -1), ('-1..-0.3', -1, -0.3), ('flat', -0.3, 0.3),
       ('0.3..1', 0.3, 1), ('1..2', 1, 2), ('z > 2', 2, 99)], LOW)
sweep('volatility compression (RV now / RV 20d ago)', 'compress',
      [('collapsing <0.7', 0, 0.7), ('0.7-0.9', 0.7, 0.9), ('0.9-1.1', 0.9, 1.1),
       ('1.1-1.4', 1.1, 1.4), ('expanding >1.4', 1.4, 99)], LOW)
sweep('trend (vs 50-day mean)', 'trend',
      [('below -5%', -99, -0.05), ('-5..-1%', -0.05, -0.01), ('-1..1%', -0.01, 0.01),
       ('1..5%', 0.01, 0.05), ('above 5%', 0.05, 99)], LOW)
sweep('volume', 'volx',
      [('<0.8x', 0, 0.8), ('0.8-1.0', 0.8, 1.0), ('1.0-1.4', 1.0, 1.4),
       ('1.4-2.0', 1.4, 2.0), ('>2.0x', 2.0, 99)], LOW)

print()
print('=' * 100)
print('CONTRAST — the same stretch sweep in the HIGH-RV regime (where we have been fishing)')
print('=' * 100)
HIGH = [r for r in ROWS if r['regime'] == 'high']
sweep('5-day stretch, HIGH-RV regime', 'stretch',
      [('z < -2', -99, -2), ('-2..-1', -2, -1), ('flat', -0.3, 0.3),
       ('1..2', 1, 2), ('z > 2', 2, 99)], HIGH)

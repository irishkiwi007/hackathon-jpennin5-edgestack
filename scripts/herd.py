"""OVERSHOOT AND REVERSE — testing the herd-psychology thesis on ETFs.

Thesis: real information arrives only occasionally. Between arrivals, herding pushes price past
fair value; the move then retraces. Symmetric for bad news. The edge is TIMING THE TURN.

Design
  stretch = N-day return divided by trailing realized volatility. Regime- and instrument-
            comparable, so a 3% move in a calm tape and a 3% move in a panic are not confused.
  Forward returns at 1/3/5/10 days, reported RAW (drift included - the strategy earns drift too)
  and as EXCESS over that instrument's own unconditional mean for the same horizon.
  Newey-West t-stats (lag = horizon) because daily sampling of h-day forward returns overlaps.
"""
import csv, math, io, sys, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = 'C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
ETFS = ['SPY', 'QQQ', 'SOXX', 'TLT', 'HYG', 'XLP', 'XLV', 'FDN']
HOR = [1, 3, 5, 10]
rng = np.random.default_rng(11)


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    d = [r['date'] for r in rows]
    o = np.array([float(r['open']) for r in rows])
    h = np.array([float(r['high']) for r in rows])
    l = np.array([float(r['low']) for r in rows])
    c = np.array([float(r['adj_close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    return d, o, h, l, c, v


def nw_t(x, lag):
    """Newey-West t-stat for the mean of x."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 20:
        return float('nan')
    m = x.mean()
    e = x - m
    g0 = float(e @ e) / n
    s = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float(e[k:] @ e[:-k]) / n
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if s <= 0:
        return float('nan')
    return m / math.sqrt(s / n)


DATA = {}
for s in ETFS:
    DATA[s] = load(s)


def build(sym, look=5, volwin=20):
    d, o, h, l, c, v = DATA[sym]
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / c[:-1])
    rv = np.full(n, np.nan)
    for i in range(volwin, n):
        rv[i] = r[i - volwin + 1:i + 1].std(ddof=1)
    rows = []
    for i in range(max(volwin, look) + 2, n - max(HOR) - 1):
        if not np.isfinite(rv[i]) or rv[i] <= 0:
            continue
        ret_n = math.log(c[i] / c[i - look])
        stretch = ret_n / (rv[i] * math.sqrt(look))
        # exhaustion candidates
        streak = 0
        for k in range(i, max(i - 15, 0), -1):
            if np.sign(r[k]) == np.sign(r[i]) and r[k] != 0:
                streak += 1
            else:
                break
        streak *= int(np.sign(r[i])) if r[i] != 0 else 0
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr = np.mean([max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1]))
                       for k in range(i - 19, i + 1)])
        rowd = dict(i=i, date=d[i], stretch=stretch, streak=streak,
                    accel=(math.log(c[i] / c[i - 3]) / (rv[i] * math.sqrt(3)))
                          - (math.log(c[i - 3] / c[i - 10]) / (rv[i] * math.sqrt(7))),
                    rangex=tr / atr if atr > 0 else np.nan,
                    volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
                    gap=(math.log(o[i] / c[i - 1]) / rv[i]) if o[i] > 0 else np.nan)
        for hz in HOR:
            rowd['f%d' % hz] = math.log(c[i + hz] / c[i])
        rows.append(rowd)
    return rows


ALL = {s: build(s) for s in ETFS}
print('rows per ETF: ' + '  '.join('%s=%d' % (s, len(ALL[s])) for s in ETFS))

print()
print('=' * 104)
print('1. DOES AN OVERSHOOT REVERSE?   5-day stretch -> forward return')
print('   RAW includes market drift. EXCESS is vs that ETF own unconditional mean.')
print('=' * 104)
BUCK = [('deep down  z<-2', -99, -2), ('down  -2..-1', -2, -1), ('mild dn -1..-0.3', -1, -0.3),
        ('flat -0.3..0.3', -0.3, 0.3), ('mild up 0.3..1', 0.3, 1), ('up  1..2', 1, 2),
        ('extended up z>2', 2, 99)]
POOL = []
for s in ETFS:
    for r_ in ALL[s]:
        r_ = dict(r_)
        r_['sym'] = s
        POOL.append(r_)
BASEM = {}
for hz in HOR:
    for s in ETFS:
        BASEM[(s, hz)] = float(np.mean([r_['f%d' % hz] for r_ in ALL[s]]))

hdr = '{:<20} {:>6}'.format('5-day stretch', 'n')
for hz in HOR:
    hdr += ' {:>10}{:>7}'.format('f%d raw%%' % hz, 't')
print(hdr)
for lab, lo, hi in BUCK:
    g = [r_ for r_ in POOL if lo <= r_['stretch'] < hi]
    if len(g) < 150:
        continue
    line = '{:<20} {:>6}'.format(lab, len(g))
    for hz in HOR:
        ex = np.array([r_['f%d' % hz] - BASEM[(r_['sym'], hz)] for r_ in g])
        raw = np.array([r_['f%d' % hz] for r_ in g])
        line += ' {:>10.3f}{:>7.2f}'.format(raw.mean() * 100, nw_t(ex, hz))
    print(line)
print('   (t-stat is on the EXCESS over each ETF own mean; the raw % column keeps drift in)')

print()
print('=' * 104)
print('2. IS IT SYMMETRIC?  per-ETF, extended-up vs deep-down, 5-day forward EXCESS')
print('=' * 104)
print('{:>6} {:>8} {:>12} {:>7}   {:>8} {:>12} {:>7}'.format(
    'ETF', 'n up>2', 'up f5 exc%', 't', 'n dn<-2', 'dn f5 exc%', 't'))
up_pos = dn_pos = tot = 0
for s in ETFS:
    rs = ALL[s]
    u = [r_ for r_ in rs if r_['stretch'] > 2]
    dn = [r_ for r_ in rs if r_['stretch'] < -2]
    if len(u) < 40 or len(dn) < 40:
        continue
    ue = np.array([r_['f5'] - BASEM[(s, 5)] for r_ in u])
    de = np.array([r_['f5'] - BASEM[(s, 5)] for r_ in dn])
    tot += 1
    up_pos += 1 if ue.mean() < 0 else 0     # reversal after up = negative excess
    dn_pos += 1 if de.mean() > 0 else 0     # reversal after down = positive excess
    print('{:>6} {:>8} {:>12.3f} {:>7.2f}   {:>8} {:>12.3f} {:>7.2f}'.format(
        s, len(u), ue.mean() * 100, nw_t(ue, 5), len(dn), de.mean() * 100, nw_t(de, 5)))
print()
print('  reversal-after-UP   (negative excess) in {}/{} ETFs'.format(up_pos, tot))
print('  reversal-after-DOWN (positive excess) in {}/{} ETFs'.format(dn_pos, tot))

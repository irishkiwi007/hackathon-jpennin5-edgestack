"""Two things needed before shipping:
  1. A SIZING LADDER. Edge comes in tiers; size by measured historical odds (Kelly-capped).
  2. A COMPLEMENTARY SIGNAL to raise the fire rate: cross-sectional. When a high-beta ETF is
     dumped far harder than its own benchmark, does the RELATIVE gap close? That fires on
     rotation, not just on market-wide selloffs, so it should not cluster the same way.
"""
import json, sys, io, math
from collections import defaultdict
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = json.load(open('wide_bars.json'))
UNIV = [s for s, v in D.items() if len(v) > 900]


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 20: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


HOR = [3, 5]
ROWS = defaultdict(list)
SER = {}
for s in UNIV:
    b = D[s]
    c = np.array([x['c'] for x in b]); v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]; n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    SER[s] = (dt, c, r)
    for i in range(25, n - max(HOR) - 1):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0: continue
        row = dict(sym=s, date=dt[i], stretch=math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5)),
                   volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0), rv=rv)
        for hz in HOR: row['f%d' % hz] = math.log(c[i + hz] / c[i])
        ROWS[s].append(row)
POOL = [r for s in UNIV for r in ROWS[s]]
BASEM = {(s, hz): float(np.mean([r['f%d' % hz] for r in ROWS[s]])) for s in UNIV for hz in HOR}


def stat(g, hz=3):
    if len(g) < 50: return None
    e = np.array([r['f%d' % hz] - BASEM[(r['sym'], hz)] for r in g])
    raw = np.array([r['f%d' % hz] for r in g])
    return dict(n=len(g), exc=e.mean() * 100, t=nw_t(e, hz), raw=raw.mean() * 100,
                win=(raw > 0).mean() * 100, sd=raw.std(ddof=1) * 100)


TIERS = [('A  z<-2.5 & vol>1.8x', lambda r: r['stretch'] < -2.5 and r['volx'] > 1.8),
         ('B  z<-2.5 & vol 1.4-1.8', lambda r: r['stretch'] < -2.5 and 1.4 < r['volx'] <= 1.8),
         ('C  z<-2.0 & vol>1.8x', lambda r: -2.5 <= r['stretch'] < -2.0 and r['volx'] > 1.8),
         ('D  z<-2.0 & vol 1.4-1.8', lambda r: -2.5 <= r['stretch'] < -2.0 and 1.4 < r['volx'] <= 1.8),
         ('E  z<-2.0 & vol<1.4 (skip)', lambda r: r['stretch'] < -2.0 and r['volx'] <= 1.4)]
print('=' * 104)
print('SIZING LADDER — 3-day hold, 50 ETFs 2016-2026.  Kelly on the measured win rate.')
print('=' * 104)
print('{:<28} {:>6} {:>9} {:>8} {:>7} {:>8} {:>9} {:>9}'.format(
    'tier', 'n', 'raw%', 'win%', 't', 'sd%', 'sig/yr', 'Kelly f*'))
for lab, f in TIERS:
    g = [r for r in POOL if f(r)]
    s_ = stat(g)
    if not s_: 
        print('{:<28} {:>6}  (thin)'.format(lab, len(g))); continue
    p = s_['win'] / 100.0
    # payoff ratio from mean win vs mean loss
    raw = np.array([r['f3'] for r in g])
    W = raw[raw > 0].mean() if (raw > 0).any() else 0
    L = abs(raw[raw <= 0].mean()) if (raw <= 0).any() else 1
    b = W / L if L > 0 else 0
    kel = (p * b - (1 - p)) / b if b > 0 else 0
    print('{:<28} {:>6} {:>9.3f} {:>7.1f}% {:>7.2f} {:>8.2f} {:>9.0f} {:>9.3f}'.format(
        lab, s_['n'], s_['raw'], s_['win'], s_['t'], s_['sd'], s_['n'] / 10.6, max(kel, 0)))

print()
print('=' * 104)
print('ERA STABILITY of tier A   (z<-2.5, vol>1.8x)')
print('=' * 104)
print('{:<12} {:>6} {:>10} {:>7} {:>8}'.format('period', 'n', 'raw%', 't', 'win%'))
for lab, a, b_ in [('2016-2017', '2016', '2018'), ('2018-2019', '2018', '2020'),
                   ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                   ('2024-2026', '2024', '2027')]:
    g = [r for r in POOL if r['stretch'] < -2.5 and r['volx'] > 1.8 and a <= r['date'][:4] < b_]
    s_ = stat(g)
    if not s_:
        print('{:<12} {:>6}  (thin)'.format(lab, len(g))); continue
    print('{:<12} {:>6} {:>10.3f} {:>7.2f} {:>7.1f}%'.format(lab, s_['n'], s_['raw'], s_['t'], s_['win']))

print()
print('=' * 104)
print('COMPLEMENTARY SIGNAL — cross-sectional: high-beta ETF dumped vs its own benchmark')
print('=' * 104)
PAIRS = [('SOXX', 'QQQ'), ('SMH', 'QQQ'), ('XBI', 'IBB'), ('ARKK', 'QQQ'), ('KRE', 'XLF'),
         ('XHB', 'XLY'), ('OIH', 'XLE'), ('XOP', 'XLE'), ('IGV', 'XLK'), ('JETS', 'XLI'),
         ('TAN', 'XLU'), ('EWZ', 'EEM'), ('FXI', 'EEM'), ('XME', 'XLB')]
CS = []
for hi, lo in PAIRS:
    if hi not in SER or lo not in SER: continue
    dh, ch, rh = SER[hi]; dl, cl, rl = SER[lo]
    idx = {d: i for i, d in enumerate(dl)}
    for i in range(25, len(dh) - 6):
        j = idx.get(dh[i])
        if j is None or j < 25: continue
        sp = rh[i - 4:i + 1].sum() - rl[j - 4:j + 1].sum()      # 5-day relative move
        sd = (rh[i - 19:i + 1] - rl[max(j - 19, 0):j + 1][-20:]).std(ddof=1) \
            if j >= 19 else np.nan
        if not np.isfinite(sd) or sd <= 0: continue
        z = sp / (sd * math.sqrt(5))
        fwd = float(np.sum(rh[i + 1:i + 4]) - np.sum(rl[j + 1:j + 4]))
        CS.append(dict(pair=hi + '/' + lo, z=z, fwd=fwd))
print('  pair-observations {}'.format(len(CS)))
mu = float(np.mean([r['fwd'] for r in CS]))
print('{:<26} {:>7} {:>14} {:>8}'.format('relative 5-day move', 'n', 'fwd3 rel excess%', 't'))
for lab, lo_, hi_ in [('z<-2 (dumped hard)', -99, -2), ('-2..-1', -2, -1), ('-1..1', -1, 1),
                      ('1..2', 1, 2), ('z>2 (ripped)', 2, 99)]:
    g = [r for r in CS if lo_ <= r['z'] < hi_]
    if len(g) < 60: continue
    e = np.array([r['fwd'] - mu for r in g])
    print('{:<26} {:>7} {:>14.3f} {:>8.2f}'.format(lab, len(g), e.mean() * 100, nw_t(e, 3)))
print()
print('  A positive number after "dumped hard" means the laggard closes the gap (pairs mean-revert).')

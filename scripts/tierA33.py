"""Is tier A (z<-2.5, volume>1.8x) a real effect or a bet on the 2024-2026 dip-buying regime?
The 50-ETF set only reaches 2016. The engine's 8 ETFs reach 1993. Same tier definition, 33 years.
"""
import csv, sys, io, math
from collections import defaultdict
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = 'C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
ETFS = ['SPY', 'QQQ', 'SOXX', 'HYG', 'XLP', 'XLV', 'FDN']     # TLT dropped: no mechanism


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 15: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


ROWS = defaultdict(list)
for s in ETFS:
    rows = list(csv.DictReader(open(BASE + '/' + s + '.csv', encoding='utf-8')))
    c = np.array([float(r['adj_close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    dt = [r['date'] for r in rows]; n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    for i in range(25, n - 6):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0: continue
        ROWS[s].append(dict(sym=s, date=dt[i],
                            stretch=math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5)),
                            volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
                            f3=math.log(c[i + 3] / c[i]), f5=math.log(c[i + 5] / c[i])))
POOL = [r for s in ETFS for r in ROWS[s]]
BASEM = {(s, h): float(np.mean([r['f%d' % h] for r in ROWS[s]])) for s in ETFS for h in (3, 5)}
print('7 ETFs, {} observations, 1993-2026'.format(len(POOL)))

TA = lambda r: r['stretch'] < -2.5 and r['volx'] > 1.8
g = [r for r in POOL if TA(r)]
raw = np.array([r['f3'] for r in g])
e = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in g])
print('\nTIER A over 33 years:  n={}  raw {:+.3f}%  excess {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
    len(g), raw.mean() * 100, e.mean() * 100, nw_t(e, 3), (raw > 0).mean() * 100))

print()
print('=' * 92)
print('TIER A BY ERA — 33 years.  Is it one regime or many?')
print('=' * 92)
print('{:<24} {:>5} {:>10} {:>10} {:>7} {:>8}'.format('era', 'n', 'raw%', 'excess%', 't', 'win%'))
ERAS = [('1993-1999', '1993', '2000'), ('2000-2002 dotcom', '2000', '2003'),
        ('2003-2007', '2003', '2008'), ('2008-2009 GFC', '2008', '2010'),
        ('2010-2015', '2010', '2016'), ('2016-2019', '2016', '2020'),
        ('2020-2021 covid', '2020', '2022'), ('2022-2023 hikes', '2022', '2024'),
        ('2024-2026', '2024', '2027')]
npos = nsig = ntot = 0
for lab, a, b in ERAS:
    gg = [r for r in g if a <= r['date'][:4] < b]
    if len(gg) < 12:
        print('{:<24} {:>5}   (thin)'.format(lab, len(gg))); continue
    rw = np.array([r['f3'] for r in gg])
    ex = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in gg])
    t = nw_t(ex, 3); ntot += 1
    npos += 1 if ex.mean() > 0 else 0
    nsig += 1 if t > 1.5 else 0
    print('{:<24} {:>5} {:>10.3f} {:>10.3f} {:>7.2f} {:>7.1f}%'.format(
        lab, len(gg), rw.mean() * 100, ex.mean() * 100, t, (rw > 0).mean() * 100))
print('\n  positive in {}/{} eras with enough events;  t>1.5 in {}'.format(npos, ntot, nsig))

print()
print('=' * 92)
print('DROP-ONE-ERA — how much of the result is any single period?')
print('=' * 92)
print('{:<24} {:>5} {:>10} {:>7}'.format('excluding...', 'n', 'excess%', 't'))
for lab, a, b in ERAS:
    gg = [r for r in g if not (a <= r['date'][:4] < b)]
    ex = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in gg])
    print('{:<24} {:>5} {:>10.3f} {:>7.2f}'.format(lab, len(gg), ex.mean() * 100, nw_t(ex, 3)))

print()
print('=' * 92)
print('VOLUME CUT re-checked on 33 years, DISJOINT cells, z<-2.5')
print('=' * 92)
print('{:<22} {:>5} {:>10} {:>10} {:>7} {:>8}'.format('cell', 'n', 'raw%', 'excess%', 't', 'win%'))
for lab, lo, hi in [('vol <1.0', 0, 1.0), ('vol 1.0-1.4', 1.0, 1.4), ('vol 1.4-1.8', 1.4, 1.8),
                    ('vol 1.8-2.5', 1.8, 2.5), ('vol >2.5', 2.5, 1e9)]:
    gg = [r for r in POOL if r['stretch'] < -2.5 and lo <= r['volx'] < hi]
    if len(gg) < 25: 
        print('{:<22} {:>5}  (thin)'.format(lab, len(gg))); continue
    rw = np.array([r['f3'] for r in gg])
    ex = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in gg])
    print('{:<22} {:>5} {:>10.3f} {:>10.3f} {:>7.2f} {:>7.1f}%'.format(
        lab, len(gg), rw.mean() * 100, ex.mean() * 100, nw_t(ex, 3), (rw > 0).mean() * 100))

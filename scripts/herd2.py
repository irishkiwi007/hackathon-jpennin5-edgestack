"""The down-reversal is strong (8/8 ETFs, t=5.06 at 3 days). Two questions decide if it is usable.

  A. ERA STABILITY. Deep selloffs cluster in 2008, 2020, 2022. If the effect is only crises it is
     not a strategy, it is three events.
  B. TIMING THE TURN. Within deep-down days, which exhaustion signal identifies the bottom?
     Capitulation hypothesis: the turn comes when selling CLIMAXES - range explodes, volume
     surges, price gaps down. Panic ends when the last holder sells.

Plus a surrogate check: shuffled returns have no reversal, so a real effect must beat them.
"""
import csv, math, io, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
exec(open('herd_common.py').read())

print('=' * 106)
print('A. ERA STABILITY — deep-down (z<-2) 3-day forward EXCESS return, by era, pooled across ETFs')
print('=' * 106)
ERAS = [('1993-1999 late 90s', '1993', '2000'), ('2000-2002 dotcom bust', '2000', '2003'),
        ('2003-2007 expansion', '2003', '2008'), ('2008-2009 GFC', '2008', '2010'),
        ('2010-2015 QE era', '2010', '2016'), ('2016-2019 pre-covid', '2016', '2020'),
        ('2020-2021 covid+melt', '2020', '2022'), ('2022-2023 hike cycle', '2022', '2024'),
        ('2024-2026 current', '2024', '2027')]
print('{:<26} {:>6} {:>13} {:>7} {:>13} {:>7}'.format('era', 'n', 'f3 excess%', 't', 'f5 excess%', 't'))
nsig = npos = 0
for lab, a, b in ERAS:
    g = [r for r in POOL if r['stretch'] < -2 and a <= r['date'][:4] < b]
    if len(g) < 30:
        print('{:<26} {:>6}   (too few)'.format(lab, len(g)))
        continue
    e3 = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in g])
    e5 = np.array([r['f5'] - BASEM[(r['sym'], 5)] for r in g])
    t3 = nw_t(e3, 3)
    npos += 1 if e3.mean() > 0 else 0
    nsig += 1 if t3 > 1.5 else 0
    print('{:<26} {:>6} {:>13.3f} {:>7.2f} {:>13.3f} {:>7.2f}'.format(
        lab, len(g), e3.mean() * 100, t3, e5.mean() * 100, nw_t(e5, 5)))
print()
print('  positive in {} eras, t>1.5 in {}'.format(npos, nsig))

# surrogate
print()
print('=' * 106)
print('SURROGATE — same pipeline on shuffled returns (no reversal can exist)')
print('=' * 106)
rng = np.random.default_rng(5)
sur = []
for _ in range(300):
    vals = []
    for s in ETFS:
        rs = ALL[s]
        f = np.array([r['f3'] for r in rs])
        st = np.array([r['stretch'] for r in rs])
        perm = rng.permutation(len(f))
        sel = f[perm][st < -2]           # break the link between stretch and forward return
        if len(sel):
            vals.append(sel.mean() - BASEM[(s, 3)])
    if vals:
        sur.append(np.mean(vals))
s = np.array(sur) * 100
real = np.mean([np.mean([r['f3'] - BASEM[(x, 3)] for r in ALL[x] if r['stretch'] < -2])
                for x in ETFS]) * 100
lo, hi = np.percentile(s, [2.5, 97.5])
print('  real deep-down f3 excess  {:+.3f}%'.format(real))
print('  surrogate mean            {:+.3f}%   95% band [{:+.3f}, {:+.3f}]'.format(s.mean(), lo, hi))
print('  verdict: {}'.format('REAL — outside the band' if real > hi else 'inside band, not real'))

print()
print('=' * 106)
print('B. TIMING THE TURN — within deep-down days (z<-2), which exhaustion signal marks the bottom?')
print('=' * 106)
DEEP = [r for r in POOL if r['stretch'] < -2]
print('  deep-down sample: {} events'.format(len(DEEP)))
print()
SIGS = [('streak (consec down days)', 'streak', [('-1 (first dn day)', -1.5, -0.5),
                                                 ('-2', -2.5, -1.5), ('-3', -3.5, -2.5),
                                                 ('-4 or worse', -99, -3.5)]),
        ('range expansion (TR/ATR)', 'rangex', [('compressed <0.9', 0, 0.9),
                                                ('normal 0.9-1.3', 0.9, 1.3),
                                                ('expanded 1.3-1.8', 1.3, 1.8),
                                                ('CLIMAX >1.8', 1.8, 99)]),
        ('volume surge (vs 20d)', 'volx', [('light <1.0', 0, 1.0), ('normal 1.0-1.4', 1.0, 1.4),
                                           ('heavy 1.4-2.0', 1.4, 2.0), ('CLIMAX >2.0', 2.0, 99)]),
        ('gap (z-scored)', 'gap', [('gap down <-1', -99, -1.0), ('-1..-0.3', -1.0, -0.3),
                                   ('flat -0.3..0.3', -0.3, 0.3), ('gap up >0.3', 0.3, 99)]),
        ('acceleration', 'accel', [('decelerating >0.5', 0.5, 99), ('-0.5..0.5', -0.5, 0.5),
                                   ('accelerating -1.5..-0.5', -1.5, -0.5),
                                   ('FREEFALL <-1.5', -99, -1.5)])]
for name, key, buckets in SIGS:
    print('  ' + name)
    print('  {:<28} {:>6} {:>13} {:>7} {:>13} {:>7}'.format('', 'n', 'f3 excess%', 't', 'f5 excess%', 't'))
    for lab, lo_, hi_ in buckets:
        g = [r for r in DEEP if np.isfinite(r[key]) and lo_ <= r[key] < hi_]
        if len(g) < 40:
            continue
        e3 = np.array([r['f3'] - BASEM[(r['sym'], 3)] for r in g])
        e5 = np.array([r['f5'] - BASEM[(r['sym'], 5)] for r in g])
        print('  {:<28} {:>6} {:>13.3f} {:>7.2f} {:>13.3f} {:>7.2f}'.format(
            lab, len(g), e3.mean() * 100, nw_t(e3, 3), e5.mean() * 100, nw_t(e5, 5)))
    print()

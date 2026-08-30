"""Frequency vs edge. z<-2 fires ~4x/year/ETF - a 5-day contest could see zero signals.
Loosening the stretch threshold trades edge for signal count. Find the usable corner.

Also: does the volume filter survive era-by-era, and is the combined signal real per-ETF?
"""
import csv, math, io, sys
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
exec(open('herd_common.py').read())

def stat(g, hz):
    if len(g) < 30:
        return None
    e = np.array([r['f%d' % hz] - BASEM[(r['sym'], hz)] for r in g])
    raw = np.array([r['f%d' % hz] for r in g])
    return dict(n=len(g), exc=e.mean() * 100, t=nw_t(e, hz), raw=raw.mean() * 100,
                win=(raw > 0).mean() * 100)

YEARS = (2026 - 1993) + 0.3
print('=' * 108)
print('FREQUENCY vs EDGE — stretch threshold x volume filter, 3-day hold')
print('  per-ETF-year = how often one ETF fires. 8 ETFs in the book multiplies that.')
print('=' * 108)
print('{:<12} {:<16} {:>6} {:>12} {:>12} {:>7} {:>7} {:>7}'.format(
    'stretch', 'volume', 'n', 'per ETF-yr', 'f3 excess%', 't', 'raw%', 'win%'))
best = []
for zth in (-2.5, -2.0, -1.5, -1.0, -0.75):
    for vlab, vlo in (('any', 0.0), ('>1.2x', 1.2), ('>1.4x', 1.4), ('>1.6x', 1.6)):
        g = [r for r in POOL if r['stretch'] < zth and np.isfinite(r['volx']) and r['volx'] > vlo]
        s = stat(g, 3)
        if not s:
            continue
        per = s['n'] / len(ETFS) / YEARS
        print('{:<12} {:<16} {:>6} {:>12.1f} {:>12.3f} {:>7.2f} {:>7.3f} {:>6.1f}%'.format(
            'z < %.2f' % zth, vlab, s['n'], per, s['exc'], s['t'], s['raw'], s['win']))
        best.append((zth, vlo, vlab, s, per))
    print()

print('=' * 108)
print('ERA STABILITY of the combined signal   (z<-1.0, volume>1.4x, 3-day hold)')
print('=' * 108)
ERAS = [('1993-1999', '1993', '2000'), ('2000-2002', '2000', '2003'), ('2003-2007', '2003', '2008'),
        ('2008-2009', '2008', '2010'), ('2010-2015', '2010', '2016'), ('2016-2019', '2016', '2020'),
        ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'), ('2024-2026', '2024', '2027')]
print('{:<12} {:>6} {:>13} {:>7} {:>9} {:>8}'.format('era', 'n', 'f3 excess%', 't', 'raw%', 'win%'))
npos = 0
for lab, a, b in ERAS:
    g = [r for r in POOL if r['stretch'] < -1.0 and np.isfinite(r['volx']) and r['volx'] > 1.4
         and a <= r['date'][:4] < b]
    s = stat(g, 3)
    if not s:
        print('{:<12} {:>6}  (thin)'.format(lab, len(g)))
        continue
    npos += 1 if s['exc'] > 0 else 0
    print('{:<12} {:>6} {:>13.3f} {:>7.2f} {:>9.3f} {:>7.1f}%'.format(
        lab, s['n'], s['exc'], s['t'], s['raw'], s['win']))
print('\n  positive in {} of 9 eras'.format(npos))

print()
print('=' * 108)
print('PER-ETF   (z<-1.0, volume>1.4x, 3-day hold)')
print('=' * 108)
print('{:<8} {:>6} {:>13} {:>7} {:>9} {:>8} {:>12}'.format(
    'ETF', 'n', 'f3 excess%', 't', 'raw%', 'win%', 'per yr'))
npos = 0
for s_ in ETFS:
    g = [r for r in ALL[s_] if r['stretch'] < -1.0 and np.isfinite(r['volx']) and r['volx'] > 1.4]
    for r in g:
        r['sym'] = s_
    st = stat(g, 3)
    if not st:
        continue
    npos += 1 if st['exc'] > 0 else 0
    yrs = len(ALL[s_]) / 252.0
    print('{:<8} {:>6} {:>13.3f} {:>7.2f} {:>9.3f} {:>7.1f}% {:>12.1f}'.format(
        s_, st['n'], st['exc'], st['t'], st['raw'], st['win'], st['n'] / yrs))
print('\n  positive in {} of {} ETFs'.format(npos, len(ETFS)))

print()
print('=' * 108)
print('EXIT HORIZON   (z<-1.0, volume>1.4x)')
print('=' * 108)
print('{:<10} {:>6} {:>13} {:>7} {:>9} {:>8}'.format('hold', 'n', 'excess%', 't', 'raw%', 'win%'))
for hz in HOR:
    g = [r for r in POOL if r['stretch'] < -1.0 and np.isfinite(r['volx']) and r['volx'] > 1.4]
    s = stat(g, hz)
    print('{:<10} {:>6} {:>13.3f} {:>7.2f} {:>9.3f} {:>7.1f}%'.format(
        '%d days' % hz, s['n'], s['exc'], s['t'], s['raw'], s['win']))

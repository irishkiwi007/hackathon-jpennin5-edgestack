"""Deep dive on the coverage-spike phenomenon, and the switch the strategy needs.

Design question: fade the small reversions on quiet/mild-delta names, follow the trend when the
delta is large. That requires establishing WHERE the switch sits and whether it is stable.

Reuses newscache.json.
"""
import json, math, sys, io, os
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
LOOK = 20
cache = json.load(open('newscache.json'))
print(f'symbols cached: {list(cache)}')

ROWS = []
for s, D in cache.items():
    bars = D['bars']
    cnt = D['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 21):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        dayret = math.log(px[i] / px[i - 1])
        z_day = dayret / (rv / math.sqrt(252))
        r = dict(sym=s, date=dts[i], nz=(counts[i] - mu) / sd, rv=rv,
                 past1=dayret, past5=math.log(px[i] / px[i - 5]), zday=z_day)
        for h in (1, 2, 3, 5, 10, 20):
            if i + h < n:
                r[f'f{h}'] = math.log(px[i + h] / px[i])
                r[f'a{h}'] = abs(r[f'f{h}'])
        ROWS.append(r)
print(f'observations: {len(ROWS)}\n')


def cont(g, fk):
    """excess vs bucket baseline, split by prior direction. Returns dict."""
    base = np.mean([r[fk] for r in g if fk in r])
    up = [r for r in g if r.get('past5', 0) > 0 and fk in r]
    dn = [r for r in g if r.get('past5', 0) <= 0 and fk in r]
    o = {}
    for k, gg in (('up', up), ('dn', dn)):
        if len(gg) < 30:
            o[k] = None
            continue
        v = np.array([r[fk] for r in gg])
        e = v.mean() - base
        o[k] = (e, e / (v.std(ddof=1) / math.sqrt(len(v))), len(gg))
    return o


print('=' * 104)
print('1. WHERE IS THE SWITCH? continuation score by news_z, finer buckets')
print('   score = (up excess) - (down excess).  positive = continuation, negative = reversion')
print('=' * 104)
EDGES = [(-9, -0.5), (-0.5, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0),
         (2.0, 2.5), (2.5, 3.5), (3.5, 99)]
print(f'{"news_z":<14} {"n":>6} | ' + ' '.join(f'{"f"+str(h):>9}' for h in (1, 2, 3, 5, 10)))
for lo, hi in EDGES:
    g = [r for r in ROWS if lo <= r['nz'] < hi]
    if len(g) < 80:
        continue
    cells = []
    for h in (1, 2, 3, 5, 10):
        o = cont(g, f'f{h}')
        if o['up'] and o['dn']:
            cells.append(f'{(o["up"][0]-o["dn"][0])*100:>+9.3f}')
        else:
            cells.append(f'{"-":>9}')
    print(f'{f"{lo:+.1f} to {hi:+.1f}":<14} {len(g):>6} | ' + ' '.join(cells))
print('  (units: % — the spread between how up-moves and down-moves behave)')

print('\n' + '=' * 104)
print('2. HOW LONG DOES THE VOLATILITY EFFECT LAST?')
print('=' * 104)
print(f'{"news_z":<16} {"n":>6} | ' + ' '.join(f'{"|f"+str(h)+"|":>9}' for h in (1, 2, 3, 5, 10, 20)))
for lab, sel in (('quiet nz<0', lambda r: r['nz'] < 0),
                 ('mild 0-1.5', lambda r: 0 <= r['nz'] < 1.5),
                 ('spike >1.5', lambda r: r['nz'] >= 1.5),
                 ('big >3', lambda r: r['nz'] >= 3)):
    g = [r for r in ROWS if sel(r)]
    if len(g) < 60:
        continue
    cells = []
    for h in (1, 2, 3, 5, 10, 20):
        v = [r[f'a{h}'] for r in g if f'a{h}' in r]
        allv = [r[f'a{h}'] for r in ROWS if f'a{h}' in r]
        cells.append(f'{(np.mean(v)/np.mean(allv)):>9.3f}')
    print(f'{lab:<16} {len(g):>6} | ' + ' '.join(cells))
print('  ratio vs unconditional. >1 = bigger moves. Watch how fast it decays toward 1.0')

print('\n' + '=' * 104)
print('3. DOES THE SPIKE NEED TO COINCIDE WITH A PRICE MOVE?')
print('   splitting spike days by whether that day itself moved (|z of daily return|)')
print('=' * 104)
sp = [r for r in ROWS if r['nz'] >= 1.5]
qz = np.percentile([abs(r['zday']) for r in sp], [33, 67])
print(f'{"spike sub-bucket":<26} {"n":>6} {"|fwd5| ratio":>13} {"cont score f5":>15} '
      f'{"cont score f1":>15}')
for lab, sel in (('quiet spike (|z|<p33)', lambda r: abs(r['zday']) < qz[0]),
                 ('mid', lambda r: qz[0] <= abs(r['zday']) < qz[1]),
                 ('violent spike (>p67)', lambda r: abs(r['zday']) >= qz[1])):
    g = [r for r in sp if sel(r)]
    if len(g) < 40:
        continue
    allv = np.mean([r['a5'] for r in ROWS if 'a5' in r])
    rat = np.mean([r['a5'] for r in g if 'a5' in r]) / allv
    o5, o1 = cont(g, 'f5'), cont(g, 'f1')
    c5 = (o5['up'][0] - o5['dn'][0]) * 100 if o5['up'] and o5['dn'] else float('nan')
    c1 = (o1['up'][0] - o1['dn'][0]) * 100 if o1['up'] and o1['dn'] else float('nan')
    print(f'{lab:<26} {len(g):>6} {rat:>13.3f} {c5:>+15.3f} {c1:>+15.3f}')

print('\n' + '=' * 104)
print('4. THE PROPOSED STRATEGY SPLIT — fade the mild, follow the big')
print('=' * 104)
for lab, sel in (('FADE zone  nz < 1.0', lambda r: r['nz'] < 1.0),
                 ('FOLLOW zone nz >= 2.0', lambda r: r['nz'] >= 2.0)):
    g = [r for r in ROWS if sel(r)]
    print(f'\n{lab}   n={len(g)}')
    for h in (1, 3, 5):
        o = cont(g, f'f{h}')
        if not (o['up'] and o['dn']):
            continue
        ue, ut, un = o['up']
        de, dt, dn_ = o['dn']
        print(f'   f{h:<3} up n={un:>5} {ue*100:>+7.3f}% t={ut:>6.2f} | '
              f'down n={dn_:>5} {de*100:>+7.3f}% t={dt:>6.2f} | '
              f'score {(ue-de)*100:>+7.3f}%')

print('\n' + '=' * 104)
print('5. PER-SYMBOL CONSISTENCY OF THE CONTINUATION SCORE (nz>=1.5, f5)')
print('=' * 104)
bysym = defaultdict(list)
for r in ROWS:
    bysym[r['sym']].append(r)
print(f'{"sym":>7} {"n spike":>8} {"cont score":>12} {"up t":>7} {"dn t":>7}')
signs = []
for s, rs in sorted(bysym.items()):
    g = [r for r in rs if r['nz'] >= 1.5]
    if len(g) < 60:
        print(f'{s:>7} {len(g):>8}  (thin)')
        continue
    o = cont(g, 'f5')
    if not (o['up'] and o['dn']):
        print(f'{s:>7} {len(g):>8}  (thin split)')
        continue
    sc = (o['up'][0] - o['dn'][0]) * 100
    signs.append(sc)
    print(f'{s:>7} {len(g):>8} {sc:>+12.3f} {o["up"][1]:>7.2f} {o["dn"][1]:>7.2f}')
if signs:
    print(f'\npositive (continuation) in {sum(1 for x in signs if x>0)} of {len(signs)} symbols')
    print('Consistent sign across symbols is the test that has failed everything else here.')

"""Elliott Wave / Fibonacci — the falsifiable parts, tested on our own data.

Classic EWT is not directly testable: wave counts are relabelled after the fact. But three of its
sub-claims ARE falsifiable, and two of them connect to findings already established here.

  CLAIM 1  Retracements cluster at 0.382 / 0.500 / 0.618 of the prior swing.
           (Batchelor & Ramyar 2005 found no such clustering in the Dow. Replicating.)
  CLAIM 2  Impulse/correction alternation - a large swing is followed by a smaller counter-swing,
           i.e. retracement depth is PREDICTABLE from the prior swing.
  CLAIM 3  Self-similarity - the same structure at every timescale.
           (Our swing-duration work already found heavy-tailed, scale-free durations, which is
           consistent with this. Testing swing SIZE the same way.)

Every test is run against surrogates built by shuffling the actual returns - a random walk also
produces swings, retracements and apparent structure.
"""
import csv, math, io, sys, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'
rows = list(csv.DictReader(open(f'{BASE}\\SPY.csv', encoding='utf-8')))
d = [datetime.date.fromisoformat(r['date']) for r in rows]
C = np.array([float(r['adj_close']) for r in rows])
r = np.diff(np.log(C))
rng = np.random.default_rng(17)
print(f'SPY {len(C)} sessions {d[0]} -> {d[-1]}')


def zigzag(price, thresh):
    piv = []
    ext_i, ext_p, direction = 0, price[0], 0
    for i in range(1, len(price)):
        p = price[i]
        if direction == 0:
            if p >= ext_p * (1 + thresh):
                direction, ext_i, ext_p = 1, i, p
            elif p <= ext_p * (1 - thresh):
                direction, ext_i, ext_p = -1, i, p
            elif p > ext_p or p < ext_p:
                ext_i, ext_p = i, p
        elif direction == 1:
            if p > ext_p:
                ext_i, ext_p = i, p
            elif p <= ext_p * (1 - thresh):
                piv.append(ext_i)
                direction, ext_i, ext_p = -1, i, p
        else:
            if p < ext_p:
                ext_i, ext_p = i, p
            elif p >= ext_p * (1 + thresh):
                piv.append(ext_i)
                direction, ext_i, ext_p = 1, i, p
    return piv


def retracements(price, thresh):
    """For each completed swing, the NEXT counter-swing as a fraction of it."""
    piv = zigzag(price, thresh)
    out = []
    for k in range(1, len(piv) - 1):
        a, b, c = price[piv[k - 1]], price[piv[k]], price[piv[k + 1]]
        leg = b - a
        back = c - b
        if leg == 0:
            continue
        ratio = -back / leg          # positive = a genuine retracement
        if 0.05 < ratio < 3.0:
            out.append(ratio)
    return np.array(out)


print('\n' + '=' * 92)
print('CLAIM 1 — do retracements cluster at 0.382 / 0.500 / 0.618?')
print('=' * 92)
FIB = [0.382, 0.500, 0.618]
BAND = 0.02
for th in (0.02, 0.03, 0.05):
    real = retracements(C, th)
    if len(real) < 60:
        continue
    # surrogate: same daily returns, order destroyed
    sur_hits = {f: [] for f in FIB}
    for _ in range(300):
        sp = np.exp(np.concatenate([[math.log(C[0])], np.cumsum(rng.permutation(r))]))
        sr = retracements(sp, th)
        if len(sr) < 30:
            continue
        for f in FIB:
            sur_hits[f].append(np.mean(np.abs(sr - f) < BAND))
    print(f'\nthreshold {th*100:.0f}%   n={len(real)} retracements')
    print(f'  {"level":>8} {"real hit%":>11} {"surrogate%":>12} {"95% band":>18} {"":>8}')
    for f in FIB:
        rh = np.mean(np.abs(real - f) < BAND) * 100
        sh = np.array(sur_hits[f]) * 100
        lo, hi = np.percentile(sh, [2.5, 97.5])
        flag = 'OUTSIDE' if (rh < lo or rh > hi) else ''
        print(f'  {f:>8.3f} {rh:>10.2f}% {sh.mean():>11.2f}% [{lo:>6.2f},{hi:>6.2f}] {flag:>8}')
    # is ANY level special? compare fib bands against all other equally-wide bands
    grid = np.arange(0.10, 1.20, 2 * BAND)
    dens = [np.mean(np.abs(real - g) < BAND) * 100 for g in grid]
    order = np.argsort(dens)[::-1]
    top = [(round(float(grid[i]), 3), round(dens[i], 2)) for i in order[:6]]
    print(f'  densest retracement bands overall: {top}')
    print(f'  -> Fibonacci levels rank: ' +
          ', '.join(f'{f}={int(np.where(np.argsort(dens)[::-1] == np.argmin(np.abs(grid - f)))[0][0]) + 1}'
                    for f in FIB) + f' of {len(grid)}')

print('\n' + '=' * 92)
print('CLAIM 2 — is retracement DEPTH predictable from the prior swing?')
print('=' * 92)
for th in (0.02, 0.03, 0.05):
    piv = zigzag(C, th)
    legs, rets = [], []
    for k in range(1, len(piv) - 1):
        a, b, c = C[piv[k - 1]], C[piv[k]], C[piv[k + 1]]
        if a == 0 or b == a:
            continue
        legpct = abs((b - a) / a)
        ratio = -(c - b) / (b - a)
        if 0.05 < ratio < 3.0:
            legs.append(legpct)
            rets.append(ratio)
    if len(legs) < 60:
        continue
    legs, rets = np.array(legs), np.array(rets)
    cc = np.corrcoef(legs, rets)[0, 1]
    t = cc * math.sqrt((len(legs) - 2) / max(1 - cc * cc, 1e-9))
    print(f'threshold {th*100:.0f}%  n={len(legs)}  corr(prior swing size, retracement depth) '
          f'= {cc:+.3f}  t={t:+.2f}')
    q = np.percentile(legs, [33, 67])
    for lab, m in (('small prior swing', legs < q[0]), ('mid', (legs >= q[0]) & (legs < q[1])),
                   ('large prior swing', legs >= q[1])):
        print(f'    {lab:<20} n={m.sum():>4}  mean retracement {rets[m].mean():.3f}  '
              f'median {np.median(rets[m]):.3f}')

print('\n' + '=' * 92)
print('CLAIM 3 — self-similarity: is swing SIZE scale-free?')
print('=' * 92)
print(f'{"threshold":>10} {"n swings":>9} {"mean size":>10} {"median":>9} {"CV":>7} '
      f'{"surrogate CV":>13}')
for th in (0.01, 0.02, 0.03, 0.05, 0.08):
    piv = zigzag(C, th)
    if len(piv) < 12:
        continue
    sz = np.abs(np.diff(C[piv]) / C[piv[:-1]])
    cv = sz.std(ddof=1) / sz.mean()
    scv = []
    for _ in range(120):
        sp = np.exp(np.concatenate([[math.log(C[0])], np.cumsum(rng.permutation(r))]))
        spv = zigzag(sp, th)
        if len(spv) > 12:
            s2 = np.abs(np.diff(sp[spv]) / sp[spv[:-1]])
            scv.append(s2.std(ddof=1) / s2.mean())
    print(f'{th*100:>9.0f}% {len(sz):>9} {sz.mean()*100:>9.2f}% {np.median(sz)*100:>8.2f}% '
          f'{cv:>7.2f} {np.mean(scv):>13.2f}')
print("""
If swing size scales proportionally with the threshold and CV stays constant across scales, the
structure is self-similar - which is the one EWT claim our earlier work already supports.""")

"""Claim 2 re-test. The raw result (corr = -0.53, t = -16.5) is almost certainly MECHANICAL.

The zigzag requires every swing to exceed `thresh`. So the ratio next/prior is bounded below by
thresh/prior_size. A small prior swing forces a high minimum ratio; a large prior swing permits a
tiny one. That alone manufactures a negative correlation with no market structure whatsoever.

The test: run the identical pipeline on surrogates (shuffled returns = random walk, same volatility,
zero structure). If the surrogate reproduces the correlation, the finding is an artifact.
"""
import csv, math, io, sys, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = 'C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
rows = list(csv.DictReader(open(BASE + '/SPY.csv', encoding='utf-8')))
C = np.array([float(r['adj_close']) for r in rows])
r = np.diff(np.log(C))
rng = np.random.default_rng(23)


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
            else:
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


def corr_leg_ret(price, thresh):
    piv = zigzag(price, thresh)
    legs, rets = [], []
    for k in range(1, len(piv) - 1):
        a, b, c = price[piv[k - 1]], price[piv[k]], price[piv[k + 1]]
        if a == 0 or b == a:
            continue
        ratio = -(c - b) / (b - a)
        if 0.05 < ratio < 3.0:
            legs.append(abs((b - a) / a))
            rets.append(ratio)
    if len(legs) < 40:
        return None
    return float(np.corrcoef(legs, rets)[0, 1]), len(legs)


print('=' * 94)
print('CLAIM 2 vs SURROGATE — is the impulse/correction relationship real or mechanical?')
print('=' * 94)
print('{:>10} {:>8} {:>12} {:>14} {:>20} {:>10}'.format(
    'threshold', 'n', 'real corr', 'surrogate', '95% band', 'verdict'))
for th in (0.02, 0.03, 0.05):
    real = corr_leg_ret(C, th)
    sur = []
    for _ in range(400):
        sp = np.exp(np.concatenate([[math.log(C[0])], np.cumsum(rng.permutation(r))]))
        v = corr_leg_ret(sp, th)
        if v:
            sur.append(v[0])
    s = np.array(sur)
    lo, hi = np.percentile(s, [2.5, 97.5])
    verdict = 'REAL' if (real[0] < lo or real[0] > hi) else 'ARTIFACT'
    print('{:>9.0f}% {:>8} {:>+12.3f} {:>+14.3f} [{:>+6.3f},{:>+6.3f}] {:>10}'.format(
        th * 100, real[1], real[0], s.mean(), lo, hi, verdict))

print()
print('=' * 94)
print('CONTROL — the same test with the mechanical floor REMOVED')
print('  Only swings comfortably above threshold on BOTH sides, so neither side is')
print('  pinned against the zigzag minimum.')
print('=' * 94)


def corr_clean(price, thresh, mult):
    piv = zigzag(price, thresh)
    legs, rets = [], []
    for k in range(1, len(piv) - 1):
        a, b, c = price[piv[k - 1]], price[piv[k]], price[piv[k + 1]]
        if a == 0 or b == a:
            continue
        L = abs((b - a) / a)
        R = abs((c - b) / b)
        ratio = -(c - b) / (b - a)
        # both legs must clear thresh*mult, so the floor binds on neither
        if L < thresh * mult or R < thresh * mult:
            continue
        if 0.05 < ratio < 3.0:
            legs.append(L)
            rets.append(ratio)
    if len(legs) < 40:
        return None
    return float(np.corrcoef(legs, rets)[0, 1]), len(legs)


print('{:>10} {:>6} {:>8} {:>12} {:>14} {:>20} {:>10}'.format(
    'threshold', 'mult', 'n', 'real corr', 'surrogate', '95% band', 'verdict'))
for th in (0.02, 0.03):
    for mult in (2.0, 3.0):
        real = corr_clean(C, th, mult)
        if not real:
            continue
        sur = []
        for _ in range(400):
            sp = np.exp(np.concatenate([[math.log(C[0])], np.cumsum(rng.permutation(r))]))
            v = corr_clean(sp, th, mult)
            if v:
                sur.append(v[0])
        if len(sur) < 50:
            continue
        s = np.array(sur)
        lo, hi = np.percentile(s, [2.5, 97.5])
        verdict = 'REAL' if (real[0] < lo or real[0] > hi) else 'ARTIFACT'
        print('{:>9.0f}% {:>6.1f} {:>8} {:>+12.3f} {:>+14.3f} [{:>+6.3f},{:>+6.3f}] {:>10}'.format(
            th * 100, mult, real[1], real[0], s.mean(), lo, hi, verdict))

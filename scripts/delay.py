"""What does entering a session LATE cost?

Free-tier SIP will not serve today's completed daily bar until after the close, so the agent
cannot compute the signal from today's close and also trade at today's close. Two options:

  A. enter at the signal day's CLOSE          <- what the study measured (needs same-day data)
  B. enter at the NEXT session's OPEN         <- what a post-close run can actually do
  C. enter at the NEXT session's CLOSE        <- a full session late

If B is close to A, run after the close and accept it. If B destroys the edge, the agent must
reconstruct today's bar intraday instead.
"""
import csv, io, math, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
ETFS = ['SPY', 'QQQ', 'SOXX', 'HYG', 'XLP', 'XLV', 'FDN']
HOLD = 3


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 15:
        return float('nan')
    m = x.mean()
    e = x - m
    s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


ROWS = []
for sym in ETFS:
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    c = np.array([float(r['adj_close']) for r in rows])
    o_raw = np.array([float(r['open']) for r in rows])
    c_raw = np.array([float(r['close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    n = len(c)
    # adjustment factor so the open is on the same basis as adj_close
    fac = np.where(c_raw > 0, c / np.maximum(c_raw, 1e-9), 1.0)
    o = o_raw * fac
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / c[:-1])
    for i in range(25, n - HOLD - 2):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        stretch = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        volx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if stretch >= -2.5 or volx < 1.4:
            continue
        tier = ('SMALL' if volx < 1.8 else ('FULL' if volx < 2.5 else 'MEDIUM'))
        ROWS.append(dict(
            sym=sym, tier=tier, volx=volx,
            A=math.log(c[i + HOLD] / c[i]) * 100,              # close -> close+3
            B=math.log(c[i + 1 + HOLD] / o[i + 1]) * 100,      # next open -> +3 sessions
            C=math.log(c[i + 1 + HOLD] / c[i + 1]) * 100,      # next close -> +3 sessions
            overnight=math.log(o[i + 1] / c[i]) * 100,         # the gap we would miss
            day1=math.log(c[i + 1] / c[i]) * 100,
        ))

print('tier-A-and-friends events: {}'.format(len(ROWS)))
print()
print('=' * 96)
print('COST OF ENTERING LATE  (all volume tiers, 3-session hold)')
print('=' * 96)
print('{:<40} {:>6} {:>10} {:>8} {:>8}'.format('entry timing', 'n', 'mean %', 'win %', 't'))
for key, lab in (('A', 'A. signal-day CLOSE (study)'),
                 ('B', 'B. NEXT OPEN (post-close run)'),
                 ('C', 'C. NEXT CLOSE (full session late)')):
    x = np.array([r[key] for r in ROWS])
    print('{:<40} {:>6} {:>10.3f} {:>7.1f}% {:>8.2f}'.format(
        lab, len(x), x.mean(), (x > 0).mean() * 100, nw_t(x, HOLD)))

print()
g = np.array([r['overnight'] for r in ROWS])
d1 = np.array([r['day1'] for r in ROWS])
print('  overnight gap we give up by waiting: {:+.3f}%  (t={:.2f})'.format(g.mean(), nw_t(g, 1)))
print('  full day-1 move we give up (option C): {:+.3f}%  (t={:.2f})'.format(
    d1.mean(), nw_t(d1, 1)))

print()
print('=' * 96)
print('BY TIER — does late entry hurt the good tier more?')
print('=' * 96)
print('{:<10} {:>6} {:>12} {:>12} {:>12} {:>10}'.format(
    'tier', 'n', 'A close %', 'B next-open %', 'C next-close %', 'B/A kept'))
for tier in ('SMALL', 'FULL', 'MEDIUM'):
    g2 = [r for r in ROWS if r['tier'] == tier]
    if len(g2) < 20:
        continue
    a = np.mean([r['A'] for r in g2])
    b = np.mean([r['B'] for r in g2])
    c2 = np.mean([r['C'] for r in g2])
    print('{:<10} {:>6} {:>12.3f} {:>12.3f} {:>12.3f} {:>9.0f}%'.format(
        tier, len(g2), a, b, c2, 100 * b / a if a else 0))

print()
print('=' * 96)
print('IF WE ENTER AT THE NEXT OPEN, IS A LONGER HOLD BETTER?')
print('=' * 96)
# recompute B with different holds
ROWS2 = defaultdict(list)
for sym in ETFS:
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    c = np.array([float(r['adj_close']) for r in rows])
    o_raw = np.array([float(r['open']) for r in rows])
    c_raw = np.array([float(r['close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    n = len(c)
    fac = np.where(c_raw > 0, c / np.maximum(c_raw, 1e-9), 1.0)
    o = o_raw * fac
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / c[:-1])
    for i in range(25, n - 12):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        stretch = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        volx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if stretch >= -2.5 or volx < 1.4:
            continue
        for h in (2, 3, 4, 5, 7):
            ROWS2[h].append(math.log(c[i + 1 + h] / o[i + 1]) * 100)
print('{:<22} {:>6} {:>10} {:>8} {:>8}'.format('hold from next open', 'n', 'mean %', 'win %', 't'))
for h in (2, 3, 4, 5, 7):
    x = np.array(ROWS2[h])
    print('{:<22} {:>6} {:>10.3f} {:>7.1f}% {:>8.2f}'.format(
        '{} sessions'.format(h), len(x), x.mean(), (x > 0).mean() * 100, nw_t(x, h)))

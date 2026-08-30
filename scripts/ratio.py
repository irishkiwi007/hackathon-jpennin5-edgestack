"""The variable that actually matters: SPOT / FRICTION, not friction alone.

Gross P&L per contract = move% x spot x delta x 100. Friction per contract is the option
bid/ask. So what decides viability is the RATIO of the two - and it is enormous for the
mega-liquid index ETFs, which combine a high share price with the tightest option markets
in existence:

    IWM   spot   296   friction  $9    ratio 115
    SPY   spot   769   friction  $4    ratio  90
    QQQ   spot   716   friction $16    ratio  36
    DIA   spot   535   friction $12    ratio  30
    SOXX  spot   508   friction $105   ratio   6
    XLV   spot   171   friction $40    ratio   3

Every prior universe cut was on friction alone, which mixed $50 stocks with $769 ETFs and
buried this. This tests the capitulation signal on the high-ratio names specifically, using the
33-year ETF history where the signal is strongest (t=5.42) rather than the 10-year single-name
set.
"""
import csv, io, json, math, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
HOLD, DELTA = 3, 0.35

# measured one-way crossing cost, ~1wk ATM 5%-wide put spread, live chains 2026-08-28
FRICTION = {'SPY': 4.0, 'QQQ': 16.0, 'IWM': 9.0, 'DIA': 12.0, 'SOXX': 105.0,
            'XLV': 40.0, 'XLP': 11.0, 'HYG': 3.0, 'FDN': 200.0}
# current spots for scaling historical prices to today's contract economics
SPOT_NOW = {'SPY': 769.35, 'QQQ': 716.43, 'IWM': 295.75, 'DIA': 535.06, 'SOXX': 508.62,
            'XLV': 171.16, 'XLP': 85.45, 'HYG': 79.74, 'FDN': 294.43}
ETFS = ['SPY', 'QQQ', 'SOXX', 'XLV', 'XLP', 'HYG', 'FDN']     # what the engine has 33y of


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    return ([r['date'] for r in rows],
            np.array([float(r['adj_close']) for r in rows]),
            np.array([float(r['volume']) for r in rows]))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 10:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


# TLT regime, so the validated calm overlay can be applied
tdates, tclose, _ = load('TLT')
tidx = {d: i for i, d in enumerate(tdates)}
stds = {}
for i in range(21, len(tclose)):
    w = tclose[i - 21:i]
    m = w.mean()
    stds[tdates[i]] = math.sqrt(((w - m) ** 2).sum() / 20)
CALM = {}
keys = [d for d in tdates if d in stds]
state = False
hist = []
for d in keys:
    hist.append(stds[d])
    hist[:] = hist[-90:]
    if len(hist) < 90:
        continue
    now, avg = hist[-1], sum(hist) / len(hist)
    state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
    CALM[d] = state
print('calm-regime days mapped: {}'.format(len(CALM)))

EV = []
for s in ETFS:
    dts, c, v = load(s)
    n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    for i in range(25, n - HOLD):
        d = dts[i]
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if st < -2.5 and vx >= 1.4:
            EV.append(dict(sym=s, date=d, stretch=st, volx=vx,
                           calm=CALM.get(d),
                           f3=math.log(c[i + HOLD] / c[i]) * 100))
print('capitulation events across {} ETFs, 33 years: {}'.format(len(ETFS), len(EV)))

print()
print('=' * 100)
print('PER-ETF ECONOMICS — using TODAY spot and TODAY measured friction')
print('=' * 100)
print('{:<7} {:>9} {:>10} {:>8} {:>6} {:>9} {:>7} {:>10} {:>10} {:>9}'.format(
    'sym', 'spot', 'friction', 'ratio', 'n', 'move%', 't', 'gross $', 'NET $', 'per yr'))
tot = []
for s in ETFS:
    g = [r for r in EV if r['sym'] == s]
    if len(g) < 8:
        continue
    raw = np.array([r['f3'] for r in g])
    fr = FRICTION.get(s)
    spot = SPOT_NOW.get(s)
    if fr is None or spot is None:
        continue
    gross = raw.mean() / 100.0 * spot * DELTA * 100
    net = gross - 2 * fr
    yrs = 33.3 if s in ('SPY',) else (27 if s in ('QQQ', 'XLP', 'XLV') else 20)
    tot.append((s, net, len(g) / yrs))
    print('{:<7} {:>9.2f} {:>10.0f} {:>8.0f} {:>6} {:>9.3f} {:>7.2f} {:>10.0f} {:>10.0f} {:>9.1f}'
          .format(s, spot, fr, spot * 100 / fr, len(g), raw.mean(), nw_t(raw, HOLD),
                  gross, net, len(g) / yrs))

print()
print('=' * 100)
print('THE HIGH-RATIO BOOK — SPY + QQQ + IWM-like only, with and without the calm overlay')
print('=' * 100)
HI = ['SPY', 'QQQ']          # engine has 33y for these; IWM/DIA not in the engine set
for lab, sel in (('all events', lambda r: True),
                 ('calm regime only', lambda r: r['calm'] is True)):
    g = [r for r in EV if r['sym'] in HI and sel(r)]
    if len(g) < 10:
        print('  {:<22} (thin: {})'.format(lab, len(g)))
        continue
    raw = np.array([r['f3'] for r in g])
    gross = float(np.mean([r['f3'] / 100.0 * SPOT_NOW[r['sym']] * DELTA * 100 for r in g]))
    fr = float(np.mean([FRICTION[r['sym']] for r in g]))
    net = gross - 2 * fr
    yrs = 27.0
    print('  {:<22} n={:<4} move {:+.3f}%  t={:.2f}  win {:.1f}%  gross ${:.0f}  '
          'fric ${:.0f}  NET ${:+.0f}  {:.1f}/yr'.format(
              lab, len(g), raw.mean(), nw_t(raw, HOLD), 100 * (raw > 0).mean(),
              gross, 2 * fr, net, len(g) / yrs))

print()
print('=' * 100)
print('SPY ALONE — 33 years, the single most tradeable option market in existence')
print('=' * 100)
for lab, sel in (('all capitulation events', lambda r: True),
                 ('calm regime only', lambda r: r['calm'] is True),
                 ('calm + volume 1.8-2.5x', lambda r: r['calm'] is True
                  and 1.8 <= r['volx'] < 2.5)):
    g = [r for r in EV if r['sym'] == 'SPY' and sel(r)]
    if len(g) < 8:
        print('  {:<26} (thin: {})'.format(lab, len(g)))
        continue
    raw = np.array([r['f3'] for r in g])
    gross = raw.mean() / 100.0 * SPOT_NOW['SPY'] * DELTA * 100
    net = gross - 2 * FRICTION['SPY']
    print('  {:<26} n={:<4} move {:+.3f}%  t={:.2f}  win {:.1f}%  gross ${:.0f}  '
          'NET ${:+.0f}  {:.2f}/yr'.format(
              lab, len(g), raw.mean(), nw_t(raw, HOLD), 100 * (raw > 0).mean(),
              gross, net, len(g) / 33.3))

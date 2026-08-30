"""Intraday overshoot-and-reverse, time-of-day normalised."""
import json, sys, io, math
from collections import defaultdict
from zoneinfo import ZoneInfo
import datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ET = ZoneInfo('America/New_York')
bars = json.load(open('inday_bars.json'))
ETFS = [s for s in ['SPY', 'QQQ', 'SOXX', 'XLV', 'HYG', 'XLP', 'FDN', 'IWM'] if s in bars]
K = 6            # lookback bars for stretch (30 min)
VOLWIN = 78      # trailing bars for realized volatility (one session)
HOR = [3, 6, 12]  # forward bars = 15 / 30 / 60 min


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 20:
        return float('nan')
    m = x.mean(); e = x - m
    s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


ROWS = defaultdict(list)
for s in ETFS:
    # RTH only, grouped by session
    sess = defaultdict(list)
    for b in bars[s]:
        dt = datetime.datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
        mins = dt.hour * 60 + dt.minute
        if 570 <= mins < 960:          # 09:30 .. 16:00
            sess[dt.date().isoformat()].append((mins, b))
    days = sorted(sess)
    # time-of-day baselines
    volsum = defaultdict(list)
    for d in days:
        for mins, b in sess[d]:
            if b['v'] > 0:
                volsum[mins].append(b['v'])
    volmed = {m: float(np.median(v)) for m, v in volsum.items() if len(v) > 30}
    # flat series with session boundaries
    allb, sid = [], []
    for di, d in enumerate(days):
        row = sorted(sess[d])
        for mins, b in row:
            allb.append((mins, b)); sid.append(di)
    n = len(allb)
    c = np.array([b['c'] for _, b in allb])
    v = np.array([b['v'] for _, b in allb])
    r = np.zeros(n); r[1:] = np.log(c[1:] / np.maximum(c[:-1], 1e-9))
    sid = np.array(sid)
    for i in range(VOLWIN + K, n - max(HOR) - 1):
        mins = allb[i][0]
        if mins not in volmed or volmed[mins] <= 0:
            continue
        if sid[i - K] != sid[i]:            # lookback must stay inside one session
            continue
        if sid[i + max(HOR)] != sid[i]:     # forward window must not cross the close
            continue
        rv = r[i - VOLWIN + 1:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        stretch = math.log(c[i] / c[i - K]) / (rv * math.sqrt(K))
        volx = v[i] / volmed[mins]
        d = dict(sym=s, stretch=stretch, volx=volx, mins=mins)
        for hz in HOR:
            d['f%d' % hz] = math.log(c[i + hz] / c[i])
        ROWS[s].append(d)
    print('{:<6} usable bars {}'.format(s, len(ROWS[s])))

POOL = [r for s in ETFS for r in ROWS[s]]
BASEM = {(s, hz): float(np.mean([r['f%d' % hz] for r in ROWS[s]])) for s in ETFS for hz in HOR}
print('\ntotal observations {}'.format(len(POOL)))


def stat(g, hz):
    if len(g) < 100:
        return None
    e = np.array([r['f%d' % hz] - BASEM[(r['sym'], hz)] for r in g])
    raw = np.array([r['f%d' % hz] for r in g])
    return dict(n=len(g), exc=e.mean() * 1e4, t=nw_t(e, hz), raw=raw.mean() * 1e4,
                win=(raw > 0).mean() * 100)


print()
print('=' * 100)
print('1. INTRADAY STRETCH -> FORWARD RETURN   (basis points, 30-min lookback)')
print('=' * 100)
print('{:<22} {:>8}'.format('30-min stretch', 'n') +
      ''.join(' {:>10}{:>7}'.format('f%dbar bp' % h, 't') for h in HOR))
for lab, lo, hi in [('deep down z<-2', -99, -2), ('down -2..-1', -2, -1),
                    ('mild -1..-0.3', -1, -0.3), ('flat', -0.3, 0.3),
                    ('mild up 0.3..1', 0.3, 1), ('up 1..2', 1, 2), ('extended up z>2', 2, 99)]:
    g = [r for r in POOL if lo <= r['stretch'] < hi]
    s_ = stat(g, HOR[0])
    if not s_:
        continue
    line = '{:<22} {:>8}'.format(lab, len(g))
    for hz in HOR:
        st = stat(g, hz)
        line += ' {:>10.2f}{:>7.2f}'.format(st['raw'], st['t'])
    print(line)

print()
print('=' * 100)
print('2. DOES THE VOLUME FILTER WORK INTRADAY TOO?   (deep down z<-2, forward 6 bars = 30 min)')
print('=' * 100)
print('{:<26} {:>8} {:>12} {:>7} {:>10} {:>8}'.format(
    'volume vs same-time-of-day', 'n', 'excess bp', 't', 'raw bp', 'win%'))
DEEP = [r for r in POOL if r['stretch'] < -2]
for lab, lo, hi in [('light <0.9', 0, 0.9), ('normal 0.9-1.3', 0.9, 1.3),
                    ('heavy 1.3-2.0', 1.3, 2.0), ('CLIMAX >2.0', 2.0, 1e9)]:
    g = [r for r in DEEP if lo <= r['volx'] < hi]
    s_ = stat(g, 6)
    if not s_:
        continue
    print('{:<26} {:>8} {:>12.2f} {:>7.2f} {:>10.2f} {:>7.1f}%'.format(
        lab, s_['n'], s_['exc'], s_['t'], s_['raw'], s_['win']))

print()
print('=' * 100)
print('3. FREQUENCY vs EDGE   (forward 6 bars = 30 min)')
print('=' * 100)
NDAYS = 560.0
print('{:<12} {:<12} {:>8} {:>11} {:>11} {:>7} {:>9} {:>7}'.format(
    'stretch', 'volume', 'n', 'sig/day', 'excess bp', 't', 'raw bp', 'win%'))
for zth in (-2.5, -2.0, -1.5):
    for vlab, vlo in (('any', 0.0), ('>1.3x', 1.3), ('>1.6x', 1.6), ('>2.0x', 2.0)):
        g = [r for r in POOL if r['stretch'] < zth and r['volx'] > vlo]
        s_ = stat(g, 6)
        if not s_:
            continue
        print('{:<12} {:<12} {:>8} {:>11.2f} {:>11.2f} {:>7.2f} {:>9.2f} {:>6.1f}%'.format(
            'z<%.1f' % zth, vlab, s_['n'], s_['n'] / NDAYS, s_['exc'], s_['t'],
            s_['raw'], s_['win']))
    print()

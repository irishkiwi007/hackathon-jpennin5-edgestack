import csv, math, io, sys, datetime
from collections import defaultdict
import numpy as np

BASE = 'C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/data/historical'
ETFS = ['SPY', 'QQQ', 'SOXX', 'TLT', 'HYG', 'XLP', 'XLV', 'FDN']
HOR = [1, 3, 5, 10]
rng = np.random.default_rng(11)


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    d = [r['date'] for r in rows]
    o = np.array([float(r['open']) for r in rows])
    h = np.array([float(r['high']) for r in rows])
    l = np.array([float(r['low']) for r in rows])
    c = np.array([float(r['adj_close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    return d, o, h, l, c, v


def nw_t(x, lag):
    """Newey-West t-stat for the mean of x."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 20:
        return float('nan')
    m = x.mean()
    e = x - m
    g0 = float(e @ e) / n
    s = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float(e[k:] @ e[:-k]) / n
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if s <= 0:
        return float('nan')
    return m / math.sqrt(s / n)


DATA = {}
for s in ETFS:
    DATA[s] = load(s)


def build(sym, look=5, volwin=20):
    d, o, h, l, c, v = DATA[sym]
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / c[:-1])
    rv = np.full(n, np.nan)
    for i in range(volwin, n):
        rv[i] = r[i - volwin + 1:i + 1].std(ddof=1)
    rows = []
    for i in range(max(volwin, look) + 2, n - max(HOR) - 1):
        if not np.isfinite(rv[i]) or rv[i] <= 0:
            continue
        ret_n = math.log(c[i] / c[i - look])
        stretch = ret_n / (rv[i] * math.sqrt(look))
        # exhaustion candidates
        streak = 0
        for k in range(i, max(i - 15, 0), -1):
            if np.sign(r[k]) == np.sign(r[i]) and r[k] != 0:
                streak += 1
            else:
                break
        streak *= int(np.sign(r[i])) if r[i] != 0 else 0
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr = np.mean([max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1]))
                       for k in range(i - 19, i + 1)])
        rowd = dict(i=i, date=d[i], stretch=stretch, streak=streak,
                    accel=(math.log(c[i] / c[i - 3]) / (rv[i] * math.sqrt(3)))
                          - (math.log(c[i - 3] / c[i - 10]) / (rv[i] * math.sqrt(7))),
                    rangex=tr / atr if atr > 0 else np.nan,
                    volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
                    gap=(math.log(o[i] / c[i - 1]) / rv[i]) if o[i] > 0 else np.nan)
        for hz in HOR:
            rowd['f%d' % hz] = math.log(c[i + hz] / c[i])
        rows.append(rowd)
    return rows


ALL = {s: build(s) for s in ETFS}
POOL = []
for s in ETFS:
    for r_ in ALL[s]:
        r_ = dict(r_); r_['sym'] = s; POOL.append(r_)
BASEM = {}
for hz in HOR:
    for s in ETFS:
        BASEM[(s, hz)] = float(np.mean([r_['f%d' % hz] for r_ in ALL[s]]))

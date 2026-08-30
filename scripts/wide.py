"""Frequency problem: the signal is daily-only, so more signals must come from more names.
Expanding 8 ETFs -> ~45. Also reports where every ETF sits RIGHT NOW, for Monday.
"""
import os
import json, os, sys, io, math, time, urllib.request, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
UNIV = ['SPY','QQQ','IWM','DIA','MDY','XLK','XLF','XLE','XLI','XLB','XLU','XLRE','XLC','XLY',
        'XLP','XLV','SOXX','SMH','IBB','XBI','ITB','XHB','KRE','XOP','OIH','GDX','FDN','IGV',
        'EFA','EEM','FXI','EWZ','EWJ','EWY','INDA','HYG','LQD','JNK','TLT','IEF','GLD','SLV',
        'USO','DBC','VNQ','ARKK','XRT','XME','JETS','TAN']
START, END = '2016-01-01', '2026-08-27'
CACHE = 'wide_bars.json'


def q(u, tries=4):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=90))
        except Exception:
            time.sleep(1.0)
    return None


D = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
todo = [s for s in UNIV if s not in D]
for i in range(0, len(todo), 20):
    chunk = todo[i:i + 20]
    got, tok = defaultdict(list), None
    while True:
        u = ('https://data.alpaca.markets/v2/stocks/bars?symbols={}&timeframe=1Day&feed=sip'
             '&start={}&end={}&limit=10000&adjustment=all').format(','.join(chunk), START, END)
        if tok:
            u += '&page_token=' + tok
        d = q(u)
        if not d:
            break
        for sy, rows in (d.get('bars') or {}).items():
            got[sy] += rows
        tok = d.get('next_page_token')
        if not tok:
            break
    for sy in chunk:
        D[sy] = [{'t': b['t'][:10], 'h': b['h'], 'l': b['l'], 'c': b['c'], 'v': b['v']}
                 for b in got.get(sy, [])]
    json.dump(D, open(CACHE, 'w'))
    print('pulled {}'.format(' '.join('{}:{}'.format(s, len(D[s])) for s in chunk)))

UNIV = [s for s in UNIV if len(D.get(s, [])) > 900]
print('\nuniverse with usable history: {}'.format(len(UNIV)))


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 20: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


HOR = [3, 5]
ROWS = defaultdict(list)
NOW = {}
for s in UNIV:
    b = D[s]
    c = np.array([x['c'] for x in b]); v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    for i in range(25, n):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0: continue
        stretch = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        volx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if i == n - 1:
            NOW[s] = (stretch, volx, dt[i])
            continue
        if i + max(HOR) >= n: continue
        row = dict(sym=s, date=dt[i], stretch=stretch, volx=volx)
        for hz in HOR: row['f%d' % hz] = math.log(c[i + hz] / c[i])
        ROWS[s].append(row)

POOL = [r for s in UNIV for r in ROWS[s]]
BASEM = {(s, hz): float(np.mean([r['f%d' % hz] for r in ROWS[s]])) for s in UNIV for hz in HOR}
print('observations {}  ({} ETFs, 2016-2026)'.format(len(POOL), len(UNIV)))


def stat(g, hz):
    if len(g) < 60: return None
    e = np.array([r['f%d' % hz] - BASEM[(r['sym'], hz)] for r in g])
    raw = np.array([r['f%d' % hz] for r in g])
    return dict(n=len(g), exc=e.mean() * 100, t=nw_t(e, hz), raw=raw.mean() * 100,
                win=(raw > 0).mean() * 100)


NY = 10.6
print()
print('=' * 100)
print('WIDE UNIVERSE — does the daily signal replicate on {} ETFs?  (3-day hold)'.format(len(UNIV)))
print('=' * 100)
print('{:<12} {:<10} {:>7} {:>11} {:>12} {:>7} {:>9} {:>7}'.format(
    'stretch', 'volume', 'n', 'sig/yr', 'excess%', 't', 'raw%', 'win%'))
for zth in (-2.5, -2.0, -1.5):
    for vlab, vlo in (('any', 0.0), ('>1.4x', 1.4), ('>1.8x', 1.8)):
        g = [r for r in POOL if r['stretch'] < zth and r['volx'] > vlo]
        s_ = stat(g, 3)
        if not s_: continue
        print('{:<12} {:<10} {:>7} {:>11.0f} {:>12.3f} {:>7.2f} {:>9.3f} {:>6.1f}%'.format(
            'z<%.1f' % zth, vlab, s_['n'], s_['n'] / NY, s_['exc'], s_['t'], s_['raw'], s_['win']))
    print()

print('=' * 100)
print('EXPECTED SIGNALS IN A 5-SESSION WINDOW')
print('=' * 100)
for zth, vlo, lab in ((-2.5, 1.4, 'z<-2.5 vol>1.4x'), (-2.0, 1.4, 'z<-2.0 vol>1.4x'),
                      (-1.5, 1.4, 'z<-1.5 vol>1.4x')):
    g = [r for r in POOL if r['stretch'] < zth and r['volx'] > vlo]
    per_day = len(g) / (NY * 252.0)
    print('  {:<22} {:>5.2f} signals/day  ->  {:>5.1f} expected in 5 sessions'.format(
        lab, per_day, per_day * 5))

print()
print('=' * 100)
print('CURRENT READINGS  (most recent session in the data)')
print('=' * 100)
rank = sorted(NOW.items(), key=lambda kv: kv[1][0])
print('{:<8} {:>10} {:>10} {:>12}   {}'.format('ETF', 'stretch', 'volume x', 'date', 'signal'))
for s, (st, vx, dtx) in rank[:12]:
    sig = 'FIRES' if (st < -1.5 and vx > 1.4) else ('watch' if st < -1.0 else '')
    print('{:<8} {:>10.2f} {:>10.2f} {:>12}   {}'.format(s, st, vx, dtx, sig))
print('  ... most stretched UP:')
for s, (st, vx, dtx) in rank[-4:]:
    print('{:<8} {:>10.2f} {:>10.2f} {:>12}'.format(s, st, vx, dtx))

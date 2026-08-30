"""Does the capitulation-reversal work on single stocks?

ETFs average away idiosyncratic panic; individual names should show MORE of it, and ~100 names
fire far more often than 50 ETFs. Also splits out the highest volume cells, where genuine
information (earnings) should live - the boundary condition that validated the mechanism on ETFs.
"""
import os
import json, os, sys, io, math, time, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
NAMES = ('AAPL MSFT NVDA AMZN META GOOGL TSLA AVGO AMD INTC MU QCOM TXN ADBE CRM ORCL CSCO IBM '
         'NOW PANW SNOW NFLX DIS CMCSA T VZ TMUS JPM BAC WFC GS MS C SCHW AXP BLK V MA PYPL '
         'COIN SQ JNJ PFE MRK ABBV LLY UNH CVS TMO ABT DHR BMY AMGN GILD XOM CVX COP SLB OXY '
         'PSX VLO WMT COST TGT HD LOW NKE SBUX MCD PG KO PEP PM MDLZ CL KMB BA CAT DE HON GE '
         'LMT RTX UPS FDX UNP CSX MMM EMR ETN LIN APD SHW NEM FCX DOW PLTR UBER ABNB SHOP '
         'MRNA RIVN LCID SOFI HOOD').split()
START, END = '2016-01-01', '2026-08-27'
CACHE = 'single_bars.json'


def q(u, tries=4):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=90))
        except Exception:
            time.sleep(1.0)
    return None


D = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
todo = [s for s in NAMES if s not in D]
for i in range(0, len(todo), 25):
    ch = todo[i:i + 25]
    got, tok = defaultdict(list), None
    while True:
        u = ('https://data.alpaca.markets/v2/stocks/bars?symbols={}&timeframe=1Day&feed=sip'
             '&start={}&end={}&limit=10000&adjustment=all').format(','.join(ch), START, END)
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
    for sy in ch:
        D[sy] = [{'t': b['t'][:10], 'c': b['c'], 'v': b['v']} for b in got.get(sy, [])]
    json.dump(D, open(CACHE, 'w'))
    print('pulled {} names'.format(len(ch)))

U = [s for s in NAMES if len(D.get(s, [])) > 900]
print('names with usable history: {}'.format(len(U)))


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


ROWS = defaultdict(list)
NOW = {}
for s in U:
    b = D[s]
    c = np.array([x['c'] for x in b])
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / np.maximum(c[:-1], 1e-9))
    for i in range(25, n):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if i >= n - 3:
            if i == n - 1:
                NOW[s] = (st, vx, dt[i])
            continue
        ROWS[s].append(dict(sym=s, date=dt[i], stretch=st, volx=vx,
                            f3=math.log(c[i + 3] / c[i])))

POOL = [r for s in U for r in ROWS[s]]
BASEM = {s: float(np.mean([r['f3'] for r in ROWS[s]])) for s in U}
print('observations {}'.format(len(POOL)))
YRS = 10.6


def stat(g):
    if len(g) < 40:
        return None
    e = np.array([r['f3'] - BASEM[r['sym']] for r in g])
    raw = np.array([r['f3'] for r in g])
    return dict(n=len(g), exc=e.mean() * 100, t=nw_t(e, 3), raw=raw.mean() * 100,
                win=(raw > 0).mean() * 100)


print()
print('=' * 100)
print('SINGLE STOCKS - volume cells at z<-2.5, DISJOINT   ({} names, 2016-2026)'.format(len(U)))
print('=' * 100)
print('{:<20} {:>6} {:>10} {:>10} {:>7} {:>8} {:>9}'.format(
    'volume cell', 'n', 'raw%', 'excess%', 't', 'win%', 'sig/yr'))
for lab, lo, hi in [('<1.0', 0, 1.0), ('1.0-1.4', 1.0, 1.4), ('1.4-1.8', 1.4, 1.8),
                    ('1.8-2.5', 1.8, 2.5), ('2.5-4.0', 2.5, 4.0), ('>4.0 earnings?', 4.0, 1e9)]:
    g = [r for r in POOL if r['stretch'] < -2.5 and lo <= r['volx'] < hi]
    s_ = stat(g)
    if not s_:
        print('{:<20} {:>6}  (thin)'.format(lab, len(g)))
        continue
    print('{:<20} {:>6} {:>10.3f} {:>10.3f} {:>7.2f} {:>7.1f}% {:>9.0f}'.format(
        lab, s_['n'], s_['raw'], s_['exc'], s_['t'], s_['win'], s_['n'] / YRS))

print()
print('=' * 100)
print('STRETCH DEPTH at volume 1.8-2.5x')
print('=' * 100)
print('{:<20} {:>6} {:>10} {:>10} {:>7} {:>8} {:>9}'.format(
    'stretch', 'n', 'raw%', 'excess%', 't', 'win%', 'sig/yr'))
for lab, lo, hi in [('z<-3.0', -99, -3.0), ('-3.0..-2.5', -3.0, -2.5),
                    ('-2.5..-2.0', -2.5, -2.0), ('-2.0..-1.5', -2.0, -1.5)]:
    g = [r for r in POOL if lo <= r['stretch'] < hi and 1.8 <= r['volx'] < 2.5]
    s_ = stat(g)
    if not s_:
        continue
    print('{:<20} {:>6} {:>10.3f} {:>10.3f} {:>7.2f} {:>7.1f}% {:>9.0f}'.format(
        lab, s_['n'], s_['raw'], s_['exc'], s_['t'], s_['win'], s_['n'] / YRS))

print()
print('=' * 100)
print('TIER A on single stocks (z<-2.5, vol 1.8-2.5x) - BY ERA')
print('=' * 100)
g = [r for r in POOL if r['stretch'] < -2.5 and 1.8 <= r['volx'] < 2.5]
s_ = stat(g)
print('  OVERALL  n={}  raw {:+.3f}%  t={:.2f}  win {:.1f}%  -> {:.0f}/yr, {:.2f}/day'.format(
    s_['n'], s_['raw'], s_['t'], s_['win'], s_['n'] / YRS, s_['n'] / YRS / 252))
print()
print('{:<14} {:>6} {:>10} {:>7} {:>8}'.format('era', 'n', 'raw%', 't', 'win%'))
npos = ntot = 0
for lab, a, b in [('2016-2017', '2016', '2018'), ('2018-2019', '2018', '2020'),
                  ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                  ('2024-2026', '2024', '2027')]:
    gg = [r for r in g if a <= r['date'][:4] < b]
    st = stat(gg)
    if not st:
        print('{:<14} {:>6}  (thin)'.format(lab, len(gg)))
        continue
    ntot += 1
    npos += 1 if st['raw'] > 0 else 0
    print('{:<14} {:>6} {:>10.3f} {:>7.2f} {:>7.1f}%'.format(
        lab, st['n'], st['raw'], st['t'], st['win']))
print()
print('  positive in {}/{} eras'.format(npos, ntot))
print('  expected signals in a 5-session window: {:.1f}'.format(s_['n'] / YRS / 252 * 5))

print()
print('CURRENT - names closest to firing')
rank = sorted(NOW.items(), key=lambda kv: kv[1][0])[:10]
for s, (st, vx, d_) in rank:
    flag = 'FIRES' if (st < -2.5 and 1.8 <= vx < 2.5) else ''
    print('  {:<7} {}  stretch {:>6.2f}   volume {:>5.2f}x   {}'.format(s, d_, st, vx, flag))

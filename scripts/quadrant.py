"""A portfolio of regime-conditional edges rather than one strategy.

We have established a 2x2 map of market conditions and only occupied one cell of it:

                        BONDS CALM              BONDS STRESSED
    IV/RV RICH     sell premium: +$27, t=3.19    +$21, t=1.38 (weak)
    IV/RV CHEAP    ???                            ???

The two unexplored cells are where implied volatility is CHEAP relative to realized - which by
the IV/RV finding is exactly where BUYING options should be favoured, the mirror of what we
already harvest.

This tests both directions in all four cells, priced with real implied volatility (VIX/VXN) at
both ends, so the comparison is like-for-like with the short-premium result:

    SHORT vol : bull put spread (what we already validated)
    LONG  vol : straddle - long ATM call + long ATM put, pure volatility exposure

If long vol pays in the cheap cells, the two halves cover each other's dead regimes and the
combined book fires far more often than either alone.
"""
import csv, io, json, math, sys, datetime, urllib.request, urllib.parse, http.cookiejar
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(u, ref=None):
    r = urllib.request.Request(u)
    r.add_header('User-Agent', UA)
    if ref:
        r.add_header('Referer', ref)
    return op.open(r, timeout=60).read().decode('utf-8', 'replace')


try:
    get('https://fc.yahoo.com')
except Exception:
    pass
cr = get('https://query1.finance.yahoo.com/v1/test/getcrumb',
         ref='https://finance.yahoo.com/').strip()
end = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
start = end - 34 * 365 * 86400


def yseries(tk):
    u = ('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(tk)
         + '?period1={}&period2={}&interval=1d&crumb={}'.format(
             start, end, urllib.parse.quote(cr)))
    c = json.loads(get(u, ref='https://finance.yahoo.com/'))
    res = c['chart']['result'][0]
    ts, q = res['timestamp'], res['indicators']['quote'][0]
    out = {}
    for i, t in enumerate(ts):
        v = q['close'][i]
        if v:
            out[datetime.datetime.fromtimestamp(
                t, datetime.timezone.utc).date().isoformat()] = float(v)
    return out


VIX = yseries('^VIX')
try:
    VXN = yseries('^VXN')
except Exception:
    VXN = {}
print('VIX {}  VXN {}'.format(len(VIX), len(VXN)))

BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
RATE, HOLD, DTE0, WIDTH = 0.045, 5, 14, 0.05
# one-way crossing, per contract per leg
LEG_FR = {'SPY': 2.0, 'QQQ': 8.0}
SPOT_NOW = {'SPY': 769.35, 'QQQ': 716.43}


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsput(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - s * math.sqrt(T))) - S * ncdf(-d1)


def bscall(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d1 - s * math.sqrt(T))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 12:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    return ([r['date'] for r in rows],
            np.array([float(r['adj_close']) for r in rows]))


td, tc = load('TLT')
stds = {}
for i in range(21, len(tc)):
    stds[td[i]] = float(np.std(tc[i - 21:i], ddof=1))
CALM = {}
hist, state = [], False
for d in [x for x in td if x in stds]:
    hist.append(stds[d]); hist[:] = hist[-90:]
    if len(hist) < 90:
        continue
    now, avg = hist[-1], sum(hist) / len(hist)
    state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
    CALM[d] = state


def build(sym, ivmap):
    dts, cl = load(sym)
    n = len(cl)
    r = np.zeros(n); r[1:] = np.log(cl[1:] / cl[:-1])
    scale = SPOT_NOW[sym] / cl[-1]
    fr = LEG_FR[sym]
    out = []
    for i in range(30, n - HOLD):
        d, dE = dts[i], dts[i + HOLD]
        if d not in ivmap or dE not in ivmap or d not in CALM:
            continue
        rv = r[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        iv0, iv1 = ivmap[d] / 100.0, ivmap[dE] / 100.0
        S0, S1 = cl[i] * scale, cl[i + HOLD] * scale
        T0, T1 = DTE0 / 365.0, max((DTE0 - HOLD) / 365.0, 1e-4)
        Ks, Kl = S0, S0 * (1 - WIDTH)
        c0 = bsput(S0, Ks, T0, RATE, iv0) - bsput(S0, Kl, T0, RATE, iv0)
        c1 = bsput(S1, Ks, T1, RATE, iv1) - bsput(S1, Kl, T1, RATE, iv1)
        short_net = (c0 - c1) * 100 - 4 * fr if c0 > 0 else None
        # long straddle: buy ATM call + ATM put, sell both back
        st0 = bscall(S0, S0, T0, RATE, iv0) + bsput(S0, S0, T0, RATE, iv0)
        st1 = bscall(S1, S0, T1, RATE, iv1) + bsput(S1, S0, T1, RATE, iv1)
        long_net = (st1 - st0) * 100 - 4 * fr
        out.append(dict(sym=sym, date=d, ivrv=iv0 / rv, iv=iv0, rv=rv,
                        calm=CALM.get(d), short_net=short_net, long_net=long_net,
                        straddle_cost=st0 * 100))
    return out


ALL = build('SPY', VIX) + (build('QQQ', VXN) if VXN else [])
ALL = [r for r in ALL if r['short_net'] is not None]
print('observations: {}'.format(len(ALL)))
qs = np.percentile([r['ivrv'] for r in ALL], [20, 80])
CHEAP, RICH = qs[0], qs[1]
print('IV/RV quintile cuts: cheap < {:.2f}, rich > {:.2f}'.format(CHEAP, RICH))


def cell(sel):
    g = [r for r in ALL if sel(r)]
    if len(g) < 60:
        return None
    s = np.array([r['short_net'] for r in g])
    l = np.array([r['long_net'] for r in g])
    return dict(n=len(g), s=s.mean(), st=nw_t(s, HOLD), sw=100 * (s > 0).mean(),
                l=l.mean(), lt=nw_t(l, HOLD), lw=100 * (l > 0).mean(),
                per_yr=len(g) / 30.0)


print()
print('=' * 104)
print('THE 2x2 MAP — short premium vs long volatility in every regime')
print('=' * 104)
print('{:<26} {:>6} {:>10} {:>7} {:>7}   {:>10} {:>7} {:>7} {:>8}'.format(
    'cell', 'n', 'SHORT $', 't', 'win%', 'LONG $', 't', 'win%', 'per yr'))
CELLS = [
    ('rich IV  + calm bonds', lambda r: r['ivrv'] >= RICH and r['calm'] is True),
    ('rich IV  + stressed', lambda r: r['ivrv'] >= RICH and r['calm'] is False),
    ('mid IV   + calm bonds', lambda r: CHEAP <= r['ivrv'] < RICH and r['calm'] is True),
    ('mid IV   + stressed', lambda r: CHEAP <= r['ivrv'] < RICH and r['calm'] is False),
    ('cheap IV + calm bonds', lambda r: r['ivrv'] < CHEAP and r['calm'] is True),
    ('cheap IV + stressed', lambda r: r['ivrv'] < CHEAP and r['calm'] is False),
]
res = {}
for lab, sel in CELLS:
    c = cell(sel)
    if not c:
        print('{:<26} (thin)'.format(lab))
        continue
    res[lab] = c
    print('{:<26} {:>6} {:>10.0f} {:>7.2f} {:>6.1f}%   {:>10.0f} {:>7.2f} {:>6.1f}% {:>8.0f}'
          .format(lab, c['n'], c['s'], c['st'], c['sw'], c['l'], c['lt'], c['lw'], c['per_yr']))

print()
print('=' * 104)
print('BEST ACTION PER CELL, and what a combined book looks like')
print('=' * 104)
tot_n = tot_pnl = 0
print('{:<26} {:>10} {:>10} {:>8} {:>10}'.format('cell', 'action', '$/trade', 't', 'per yr'))
for lab, sel in CELLS:
    c = res.get(lab)
    if not c:
        continue
    if c['st'] > c['lt'] and c['s'] > 0:
        act, val, t = 'SELL', c['s'], c['st']
    elif c['l'] > 0:
        act, val, t = 'BUY VOL', c['l'], c['lt']
    else:
        act, val, t = 'stand aside', 0.0, 0.0
    if act != 'stand aside' and t > 1.5:
        tot_n += c['n']; tot_pnl += c['n'] * val
    print('{:<26} {:>10} {:>10.0f} {:>8.2f} {:>10.0f}'.format(lab, act, val, t, c['per_yr']))
if tot_n:
    print()
    print('  combined book (cells with t>1.5 only): {:.0f} trades/yr at {:+.0f} $/contract'
          .format(tot_n / 30.0, tot_pnl / tot_n))
    print('  vs rich+calm alone: 54 trades/yr at +27')

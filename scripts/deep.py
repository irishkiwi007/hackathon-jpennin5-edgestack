"""Is the deep-stretch single-name cell usable?

The 479-name scan says the strong cell is stretch < -3.5 with volume 1.8-2.5x (+3.64%, t=4.2),
not the ETF cell of -2.5 / 1.8-2.5x (+0.661%, t=2.14). Two things decide whether that is a
strategy or a data-mined corner:

  1. DROP-ONE-ERA. The shallow cell was outright negative in 2020-2021. If the deep cell shares
     that, it is a regime bet regardless of its t-stat.
  2. FRICTION. Single-name options are generally wider than SPY/IWM. An edge of +3.6% on a $150
     stock is worth ~$540 of underlying move, but the spread has to be crossable.

Also checks whether leveraged ETFs (SOXL/TQQQ/UPRO/SPXU) are contaminating the sample - they are
3x products and do not belong in a single-name study.
"""
import os
import json, sys, io, math, os, time, datetime, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'
HOLD = 3
YRS = 10.6

# ETFs and leveraged products present in the top-500-by-dollar-volume list
ETF_LIKE = {'SPY','QQQ','IWM','SMH','SOXX','VOO','TQQQ','SOXL','SPXU','UPRO','VNQ','DIA','XLF',
            'XLE','XLK','XLV','XLI','XLP','XLU','XLY','XLB','XLC','XLRE','HYG','LQD','TLT','IEF',
            'GLD','SLV','USO','EEM','EFA','FXI','EWZ','ARKK','KRE','XBI','IBB','GDX','XOP','XME',
            'ITB','XHB','XRT','JETS','TAN','FDN','IGV','SPXL','SQQQ','TZA','TNA','LABU','YINN',
            'MSTU','MSTX','CONL','NVDL','TSLL','BITX','ETHU','USD','SSO','QLD','UVXY','VXX','SVXY',
            'SH','PSQ','DOG','RWM','TWM','SDS','QID','SPXS','FAS','FAZ','ERX','ERY','DRIP','GUSH',
            'JNUG','DUST','NUGT','BOIL','KOLD','UNG','UCO','SCO','VIXY','VIXM','SPY'}

D = json.load(open('sp500_bars.json'))
U = [s for s in D if len(D.get(s, [])) > 900]
SINGLES = [s for s in U if s not in ETF_LIKE]
print('total {} | ETF-like removed {} | single names {}'.format(
    len(U), len(U) - len(SINGLES), len(SINGLES)))


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 15: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


ROWS, BASE = [], {}
for s in SINGLES:
    b = D[s]
    c = np.array([x['c'] for x in b], float)
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    if n < 60 or (c <= 0).any():
        continue
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    fwd = [math.log(c[i + HOLD] / c[i]) * 100 for i in range(25, n - HOLD)]
    if not fwd: continue
    BASE[s] = float(np.mean(fwd))
    for i in range(25, n - HOLD):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0: continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        if st >= -2.5: continue
        ROWS.append(dict(sym=s, date=dt[i], stretch=st, spot=float(c[i]),
                         volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
                         f3=math.log(c[i + HOLD] / c[i]) * 100))
print('deep observations (single names only): {}'.format(len(ROWS)))


def stat(g):
    if len(g) < 30: return None
    e = np.array([r['f3'] - BASE[r['sym']] for r in g])
    raw = np.array([r['f3'] for r in g])
    return dict(n=len(g), exc=e.mean(), t=nw_t(e, HOLD), raw=raw.mean(),
                win=(raw > 0).mean() * 100)


CELLS = [('stretch<-3.5, vol 1.8-2.5', lambda r: r['stretch'] < -3.5 and 1.8 <= r['volx'] < 2.5),
         ('stretch<-3.5, vol 1.4-2.5', lambda r: r['stretch'] < -3.5 and 1.4 <= r['volx'] < 2.5),
         ('stretch<-3.5, vol >1.8',    lambda r: r['stretch'] < -3.5 and r['volx'] >= 1.8),
         ('stretch<-3.0, vol 1.8-4.0', lambda r: r['stretch'] < -3.0 and 1.8 <= r['volx'] < 4.0),
         ('stretch<-2.5, vol 2.5-4.0', lambda r: r['stretch'] < -2.5 and 2.5 <= r['volx'] < 4.0)]
print()
print('=' * 100)
print('CANDIDATE CELLS — single names only, ETFs and leveraged products removed')
print('=' * 100)
print('{:<30} {:>7} {:>10} {:>10} {:>8} {:>8} {:>9}'.format(
    'cell', 'n', 'raw%', 'excess%', 't', 'win%', 'per 5d'))
for lab, f in CELLS:
    g = [r for r in ROWS if f(r)]
    s_ = stat(g)
    if not s_:
        print('{:<30} {:>7}  (thin)'.format(lab, len(g))); continue
    print('{:<30} {:>7} {:>10.3f} {:>10.3f} {:>8.2f} {:>7.1f}% {:>9.1f}'.format(
        lab, s_['n'], s_['raw'], s_['exc'], s_['t'], s_['win'], s_['n'] / YRS / 252 * 5))

print()
print('=' * 100)
print('DROP-ONE-ERA on the best cell — the test the shallow cell failed')
print('=' * 100)
ERAS = [('2016-2017','2016','2018'),('2018-2019','2018','2020'),('2020-2021','2020','2022'),
        ('2022-2023','2022','2024'),('2024-2026','2024','2027')]
for lab, f in CELLS[:3]:
    g = [r for r in ROWS if f(r)]
    s_ = stat(g)
    if not s_: continue
    print('\n  {}   overall n={} raw {:+.3f}% t={:.2f}'.format(lab, s_['n'], s_['raw'], s_['t']))
    print('  {:<16} {:>6} {:>10} {:>8} {:>8}'.format('era', 'n', 'raw%', 't', 'win%'))
    npos = ntot = 0
    for elab, a, b in ERAS:
        gg = [r for r in g if a <= r['date'][:4] < b]
        st = stat(gg)
        if not st:
            print('  {:<16} {:>6}  (thin)'.format(elab, len(gg))); continue
        ntot += 1; npos += 1 if st['raw'] > 0 else 0
        print('  {:<16} {:>6} {:>10.3f} {:>8.2f} {:>7.1f}%'.format(
            elab, st['n'], st['raw'], st['t'], st['win']))
    print('  {:<16} positive in {}/{} eras'.format('', npos, ntot))
    print('  {:<16} {:>6} {:>10} {:>8}'.format('EXCLUDING era', 'n', 'raw%', 't'))
    for elab, a, b in ERAS:
        gg = [r for r in g if not (a <= r['date'][:4] < b)]
        st = stat(gg)
        if st:
            print('  {:<16} {:>6} {:>10.3f} {:>8.2f}'.format(elab, st['n'], st['raw'], st['t']))

print()
print('=' * 100)
print('WHICH NAMES FIRE MOST? (best cell) — and can their options be crossed?')
print('=' * 100)
g = [r for r in ROWS if r['stretch'] < -3.5 and 1.8 <= r['volx'] < 2.5]
cnt = defaultdict(int)
for r in g: cnt[r['sym']] += 1
top = sorted(cnt.items(), key=lambda kv: -kv[1])[:18]
print('  most frequent firers: ' + ', '.join('{}({})'.format(s, n) for s, n in top))
syms = [s for s, _ in top]


def q(u, tries=2):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.5)
    return None


today = datetime.date.today()
lo = (today + datetime.timedelta(days=8)).isoformat()
hi = (today + datetime.timedelta(days=14)).isoformat()
sp = {}
d = q(DATA + '/v2/stocks/bars/latest?symbols=' + ','.join(syms) + '&feed=iex')
for s, b in (d or {}).get('bars', {}).items():
    sp[s] = float(b['c'])
print()
print('{:<8} {:>9} {:>10} {:>10} {:>12} {:>14}'.format(
    'sym', 'spot', 'credit $', 'fric $', 'cred/fric', 'net if edge $'))
fr_all = []
for s in syms:
    if s not in sp: continue
    S = sp[s]
    c = q('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
          '&expiration_date_lte={}&type=put&limit=400&status=active'.format(PAPER, s, lo, hi))
    rows = [x for x in ((c or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.88 * S <= float(x['strike_price']) <= 1.03 * S]
    if len(rows) < 2: continue
    exps = sorted({x['expiration_date'] for x in rows})
    rows = [x for x in rows if x['expiration_date'] == exps[0]]
    occ = [x['symbol'] for x in rows]
    snaps = {}
    for i in range(0, len(occ), 100):
        sd = q(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[i:i + 100]))
        for k, v2 in (sd or {}).get('snapshots', {}).items():
            qt = v2.get('latestQuote') or {}
            b_, a_ = float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0)
            if b_ > 0 and a_ >= b_: snaps[k] = (b_, a_)
    byk = {}
    for x in rows:
        if x['symbol'] in snaps: byk[float(x['strike_price'])] = snaps[x['symbol']]
    if len(byk) < 2: continue
    ks = sorted(byk)
    sk = min(ks, key=lambda k: abs(k - S))
    below = [k for k in ks if k < sk]
    if not below: continue
    lk = min(below, key=lambda k: abs(k - S * 0.95))
    sb, sa = byk[sk]; lb, la = byk[lk]
    cr = (0.5 * (sb + sa) - 0.5 * (lb + la)) * 100
    fr = 0.5 * ((sa - sb) + (la - lb)) * 100
    if cr <= 0 or fr <= 0: continue
    fr_all.append(fr)
    print('{:<8} {:>9.2f} {:>10.0f} {:>10.0f} {:>12.1f} {:>14.0f}'.format(
        s, S, cr, fr, cr / fr, cr - 2 * fr))
if fr_all:
    print()
    print('  median single-name friction ${:.0f}/contract one-way, ${:.0f} round trip'.format(
        float(np.median(fr_all)), float(np.median(fr_all)) * 2))
    print('  (ETF liquid core for comparison: IWM $2, SPY $4, QQQ $16)')

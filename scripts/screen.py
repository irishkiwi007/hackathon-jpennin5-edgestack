"""Screen the whole 479-name universe on FRICTION, then measure the signal on what survives.

Established so far:
  - the deep single-name cell (stretch<-3.5, vol 1.4-2.5x) is robust: +2.969%, t=4.64,
    drop-one-era t 3.65-4.53
  - median single-name option friction is $146 round trip, which erases it
  - but friction is bimodal: AAPL $25, SLB $19 vs UNP $318, SE $215

So the question is not "ETFs or single names" but "which names can actually be traded". This
screens every name on live option friction, then re-measures the signal on the survivors and
reports the resulting signal frequency - the number that decides whether a 5-session contest
sees any trades at all.
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
CACHE = 'friction_screen.json'

# bond funds have no mechanism (+0.012%, t=0.11, win 45.7%) - exclude by ticker, including the
# muni funds that leaked through the earlier ETF filter
BONDS = {'TLT','IEF','SHY','AGG','BND','TIP','LQD','HYG','JNK','MUB','VTEB','BSV','BIV','BLV',
         'VCIT','VCSH','IGSB','SHV','BIL','SGOV','TLH','EDV','VGIT','VGSH','VGLT','SCHO','SCHR',
         'MBB','EMB','PFF','SRLN','BKLN','FLOT','USFR','TFLO','STIP','VTIP','SPTL','SPTS','SPIB'}
LEVERAGED = {'TQQQ','SQQQ','SOXL','SOXS','SPXL','SPXS','SPXU','UPRO','SDS','SSO','QLD','QID',
             'TNA','TZA','LABU','LABD','YINN','YANG','FAS','FAZ','ERX','ERY','NUGT','DUST',
             'JNUG','JDST','BOIL','KOLD','UCO','SCO','GUSH','DRIP','UVXY','VXX','SVXY','VIXY',
             'TSLL','NVDL','CONL','MSTU','MSTX','BITX','ETHU','USD','TMF','TMV','TYD','TYO'}


def q(u, tries=2, timeout=45):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=timeout))
        except Exception:
            time.sleep(0.4)
    return None


D = json.load(open('sp500_bars.json'))
U = [s for s in D if len(D.get(s, [])) > 900 and s not in BONDS and s not in LEVERAGED]
print('universe after removing bond funds and leveraged products: {}'.format(len(U)))

# ---- friction screen on live chains -----------------------------------------------------
FR = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
todo = [s for s in U if s not in FR]
print('screening {} names on live option friction...'.format(len(todo)))
today = datetime.date.today()
lo = (today + datetime.timedelta(days=8)).isoformat()
hi = (today + datetime.timedelta(days=16)).isoformat()

spot = {}
for i in range(0, len(U), 100):
    d = q(DATA + '/v2/stocks/bars/latest?symbols=' + ','.join(U[i:i + 100]) + '&feed=iex')
    for s, b in (d or {}).get('bars', {}).items():
        spot[s] = float(b['c'])

for n_done, s in enumerate(todo, 1):
    if s not in spot:
        FR[s] = None
        continue
    S = spot[s]
    c = q('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
          '&expiration_date_lte={}&type=put&limit=400&status=active'.format(PAPER, s, lo, hi))
    rows = [x for x in ((c or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.90 * S <= float(x['strike_price']) <= 1.03 * S]
    if len(rows) < 2:
        FR[s] = None
    else:
        exps = sorted({x['expiration_date'] for x in rows})
        rows = [x for x in rows if x['expiration_date'] == exps[0]]
        occ = [x['symbol'] for x in rows]
        snaps = {}
        for i in range(0, len(occ), 100):
            sd = q(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[i:i + 100]))
            for k, v2 in (sd or {}).get('snapshots', {}).items():
                qt = v2.get('latestQuote') or {}
                b_, a_ = float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0)
                if b_ > 0 and a_ >= b_:
                    snaps[k] = (b_, a_)
        byk = {}
        for x in rows:
            if x['symbol'] in snaps:
                byk[float(x['strike_price'])] = snaps[x['symbol']]
        if len(byk) < 2:
            FR[s] = None
        else:
            ks = sorted(byk)
            sk = min(ks, key=lambda k: abs(k - S))
            below = [k for k in ks if k < sk]
            if not below:
                FR[s] = None
            else:
                lk = min(below, key=lambda k: abs(k - S * 0.95))
                sb, sa = byk[sk]; lb, la = byk[lk]
                cr = (0.5 * (sb + sa) - 0.5 * (lb + la)) * 100
                fr = 0.5 * ((sa - sb) + (la - lb)) * 100
                FR[s] = {'spot': S, 'credit': cr, 'friction': fr,
                         'ratio': (cr / fr) if fr > 0 else 0.0}
    if n_done % 50 == 0:
        json.dump(FR, open(CACHE, 'w'))
        print('  {}/{}'.format(n_done, len(todo)))
json.dump(FR, open(CACHE, 'w'))

ok = {s: v for s, v in FR.items() if v and v['friction'] > 0 and v['credit'] > 0}
print('names with a quotable spread: {}'.format(len(ok)))
fr = np.array([v['friction'] for v in ok.values()])
print('friction distribution ($/contract one-way): p10 {:.0f}  median {:.0f}  p90 {:.0f}'.format(
    np.percentile(fr, 10), np.median(fr), np.percentile(fr, 90)))

# ---- signal on the survivors -------------------------------------------------------------
def build_rows(names):
    rows, base = [], {}
    for s in names:
        b = D.get(s) or []
        if len(b) < 900:
            continue
        c = np.array([x['c'] for x in b], float)
        v = np.array([x['v'] for x in b], float)
        dt = [x['t'] for x in b]
        n = len(c)
        if (c <= 0).any():
            continue
        r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
        fwd = [math.log(c[i + HOLD] / c[i]) * 100 for i in range(25, n - HOLD)]
        if not fwd:
            continue
        base[s] = float(np.mean(fwd))
        for i in range(25, n - HOLD):
            rv = r[i - 19:i + 1].std(ddof=1)
            if not np.isfinite(rv) or rv <= 0:
                continue
            st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
            if st >= -3.0:
                continue
            rows.append(dict(sym=s, date=dt[i], stretch=st, spot=float(c[i]),
                             volx=v[i] / max(np.mean(v[i - 19:i + 1]), 1.0),
                             f3=math.log(c[i + HOLD] / c[i]) * 100))
    return rows, base


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 15: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


print()
print('=' * 104)
print('SIGNAL vs FRICTION BUDGET — cell: stretch<-3.5, volume 1.4-2.5x, 3-session hold')
print('  "net" applies the round-trip crossing cost against a spread capturing ~35% of the move')
print('=' * 104)
print('{:<26} {:>6} {:>7} {:>9} {:>8} {:>8} {:>9} {:>11} {:>10}'.format(
    'friction budget', 'names', 'n', 'raw%', 't', 'win%', 'per 5d', 'gross $/ct', 'net $/ct'))
for lab, cap in (('<= $10 one-way', 10), ('<= $20', 20), ('<= $35', 35),
                 ('<= $60', 60), ('<= $100', 100), ('any', 10 ** 9)):
    names = [s for s, v in ok.items() if v['friction'] <= cap]
    if len(names) < 5:
        continue
    rows, base = build_rows(names)
    g = [r for r in rows if r['stretch'] < -3.5 and 1.4 <= r['volx'] < 2.5]
    if len(g) < 30:
        print('{:<26} {:>6} {:>7}  (thin)'.format(lab, len(names), len(g)))
        continue
    raw = np.array([r['f3'] for r in g])
    e = np.array([r['f3'] - base[r['sym']] for r in g])
    # gross per contract: 35% of the underlying move, on 100 shares at the median spot
    spots = np.array([r['spot'] for r in g])
    gross = float(np.mean(raw / 100.0 * spots * 0.35 * 100))
    med_fr = float(np.median([ok[s]['friction'] for s in names]))
    print('{:<26} {:>6} {:>7} {:>9.3f} {:>8.2f} {:>7.1f}% {:>9.1f} {:>11.0f} {:>10.0f}'.format(
        lab, len(names), len(g), raw.mean(), nw_t(e, HOLD), (raw > 0).mean() * 100,
        len(g) / YRS / 252 * 5, gross, gross - 2 * med_fr))

print()
print('=' * 104)
print('THE TRADEABLE LIST — friction <= $20 one-way, sorted by credit/friction')
print('=' * 104)
cheap = sorted([(s, v) for s, v in ok.items() if v['friction'] <= 20],
               key=lambda kv: -kv[1]['ratio'])
print('  {} names'.format(len(cheap)))
for i in range(0, min(len(cheap), 60), 3):
    chunk = cheap[i:i + 3]
    print('   ' + '   '.join('{:<6} ${:>7.0f}/${:<4.0f} r{:>5.1f}'.format(
        s, v['credit'], v['friction'], v['ratio']) for s, v in chunk))

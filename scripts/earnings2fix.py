"""EDGE CLASS 6, corrected.

The first attempt produced an implied/realized ratio of 10.8x (JNJ at 43x), which is impossible.
Two errors, both inflating it:

  1. REALIZED was measured on the wrong day. Yahoo's `earningsHistory.quarter` is the fiscal
     quarter-END date, not the announcement date, so the "reaction" was a semi-random session.
  2. IMPLIED was measured over the wrong horizon. A straddle expiring 11-45 days out prices the
     TOTAL move over its life, including ordinary volatility - not the one-day earnings jump.

Both fixed here:

  REALIZED: earnings sessions are DETECTED from the price/volume signature - an abnormal absolute
            move on abnormal volume, recurring roughly quarterly. This avoids Yahoo's date
            semantics entirely and is verifiable against the known ~4-per-year cadence.
  IMPLIED:  the earnings jump is isolated from ordinary volatility. A straddle over N days with
            ordinary daily vol s implies a total move of ~0.8 * s * sqrt(N). The jump component
            is what the straddle prices ABOVE that.

            implied_total^2  ~  ordinary^2 + jump^2   ->   jump = sqrt(total^2 - ordinary^2)
"""
import os
import json, sys, io, math, time, datetime, urllib.request, urllib.parse, http.cookiejar
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'


def aget(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(0.5)
    return None


NAMES = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'AMD', 'AVGO', 'ORCL',
         'CRM', 'ADBE', 'NFLX', 'INTC', 'MU', 'QCOM', 'TXN', 'NOW', 'PANW', 'SHOP',
         'JPM', 'BAC', 'WFC', 'GS', 'MS', 'DIS', 'WMT', 'COST', 'HD', 'LOW',
         'NKE', 'SBUX', 'MCD', 'PG', 'KO', 'PEP', 'JNJ', 'PFE', 'MRK', 'ABBV',
         'LLY', 'UNH', 'XOM', 'CVX', 'CAT', 'BA', 'GE', 'UBER', 'V', 'MA']
today = datetime.date.today()
st = (today - datetime.timedelta(days=1500)).isoformat()

BARS = {}
for i in range(0, len(NAMES), 20):
    ch = NAMES[i:i + 20]
    tok = None
    acc = defaultdict(list)
    while True:
        u = (DATA + '/v2/stocks/bars?symbols=' + ','.join(ch)
             + '&timeframe=1Day&feed=sip&start=' + st + '&limit=10000&adjustment=all')
        if tok:
            u += '&page_token=' + tok
        d = aget(u)
        if not d:
            break
        for sy, rows in (d.get('bars') or {}).items():
            acc[sy] += rows
        tok = d.get('next_page_token')
        if not tok:
            break
    for sy in ch:
        if acc.get(sy):
            BARS[sy] = [{'t': b['t'][:10], 'c': float(b['c']), 'v': float(b['v'])}
                        for b in acc[sy]]
print('daily bars for {} names'.format(len(BARS)))


def detect_earnings(sym):
    """Sessions with an abnormal move AND abnormal volume, thinned to ~quarterly cadence."""
    rows = BARS.get(sym) or []
    if len(rows) < 300:
        return []
    c = np.array([r['c'] for r in rows])
    v = np.array([r['v'] for r in rows])
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / c[:-1])
    cand = []
    for i in range(60, n):
        sd = r[i - 60:i].std(ddof=1)
        av = v[i - 60:i].mean()
        if sd <= 0 or av <= 0:
            continue
        z = abs(r[i]) / sd
        vz = v[i] / av
        if z > 2.0 and vz > 1.5:
            cand.append((i, z * vz, abs(r[i]) * 100))
    # thin: keep the strongest candidate in any 40-session neighbourhood
    cand.sort(key=lambda x: -x[1])
    kept, used = [], set()
    for i, score, mv in cand:
        if any(abs(i - j) < 40 for j in used):
            continue
        used.add(i)
        kept.append((i, mv))
    kept.sort()
    return kept


print()
print('=' * 100)
print('STEP 1 — detected earnings sessions, sanity-checked against the ~4/year cadence')
print('=' * 100)
DET = {}
print('{:<7} {:>9} {:>10} {:>13} {:>13} {:>12}'.format(
    'sym', 'detected', 'per year', 'mean move%', 'median move%', 'spacing'))
ok = 0
for s in sorted(BARS):
    k = detect_earnings(s)
    if len(k) < 6:
        continue
    yrs = len(BARS[s]) / 252.0
    per = len(k) / yrs
    mv = np.array([x[1] for x in k])
    gaps = np.diff([x[0] for x in k])
    DET[s] = k
    flag = '' if 2.5 <= per <= 6.0 else '  <-- off-cadence'
    ok += 1 if 2.5 <= per <= 6.0 else 0
    print('{:<7} {:>9} {:>10.1f} {:>12.2f}% {:>12.2f}% {:>11.0f}{}'.format(
        s, len(k), per, mv.mean(), float(np.median(mv)), float(np.median(gaps)), flag))
print('\n  {}/{} names detect at a plausible quarterly cadence (2.5-6 per year)'.format(
    ok, len(DET)))

print()
print('=' * 100)
print('STEP 2 — IMPLIED jump vs REALIZED jump')
print('  implied total move from the straddle; ordinary volatility removed to isolate the jump')
print('=' * 100)
print('{:<7} {:>7} {:>7} {:>10} {:>10} {:>10} {:>11} {:>9}'.format(
    'sym', 'DTE', 'spot', 'straddle%', 'ordinary%', 'jump imp%', 'jump real%', 'imp/real'))
rows_out = []
for sym in sorted(DET):
    rows = BARS[sym]
    c = np.array([r['c'] for r in rows])
    lr = np.diff(np.log(c))
    # ordinary daily volatility EXCLUDING detected earnings sessions
    ex = set()
    for i, _ in DET[sym]:
        ex.update(range(max(i - 1, 0), min(i + 2, len(lr))))
    ordin = np.array([lr[i] for i in range(len(lr)) if i not in ex])
    if len(ordin) < 200:
        continue
    sd_daily = ordin.std(ddof=1)
    spot = c[-1]
    cc = aget('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
              '&expiration_date_lte={}&limit=800&status=active'.format(
                  PAPER, sym, (today + datetime.timedelta(days=3)).isoformat(),
                  (today + datetime.timedelta(days=45)).isoformat()))
    cand = [x for x in ((cc or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.98 * spot <= float(x['strike_price']) <= 1.02 * spot]
    if len(cand) < 2:
        continue
    exps = sorted({x['expiration_date'] for x in cand})
    picked = None
    for e in exps:
        sub = [x for x in cand if x['expiration_date'] == e]
        occ = [x['symbol'] for x in sub]
        snaps = {}
        for k in range(0, len(occ), 100):
            sd_ = aget(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[k:k + 100]))
            for kk, vv in (sd_ or {}).get('snapshots', {}).items():
                qt = vv.get('latestQuote') or {}
                b_, a_ = float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0)
                if b_ > 0 and a_ >= b_:
                    snaps[kk] = 0.5 * (b_ + a_)
        byk = defaultdict(dict)
        for x in sub:
            if x['symbol'] in snaps:
                byk[float(x['strike_price'])][x['type']] = snaps[x['symbol']]
        best = None
        for K, leg in byk.items():
            if 'call' in leg and 'put' in leg:
                if best is None or abs(K - spot) < abs(best[0] - spot):
                    best = (K, leg['call'] + leg['put'])
        if best:
            picked = (e, best[1])
            break
    if not picked:
        continue
    exp, straddle = picked
    dte = (datetime.date.fromisoformat(exp) - today).days
    sessions = max(int(dte * 252 / 365), 1)
    total_imp = straddle / spot * 100
    # a straddle prices roughly 0.8 * sigma_total for a lognormal
    sigma_total = total_imp / 0.8
    ordinary = sd_daily * math.sqrt(sessions) * 100
    jump_imp = math.sqrt(max(sigma_total ** 2 - ordinary ** 2, 0.0))
    jump_real = float(np.mean([x[1] for x in DET[sym]]))
    if jump_imp <= 0.05:
        continue
    rows_out.append((sym, jump_imp, jump_real))
    print('{:<7} {:>7} {:>7.0f} {:>9.2f}% {:>9.2f}% {:>9.2f}% {:>10.2f}% {:>9.2f}'.format(
        sym, dte, spot, total_imp, ordinary, jump_imp, jump_real, jump_imp / jump_real))

if len(rows_out) >= 8:
    imp = np.array([r[1] for r in rows_out])
    rea = np.array([r[2] for r in rows_out])
    d = imp - rea
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
    print()
    print('  n={}  mean implied jump {:.2f}%   mean realized jump {:.2f}%'.format(
        len(rows_out), imp.mean(), rea.mean()))
    print('  implied minus realized {:+.2f} pct-points   t={:.2f}'.format(d.mean(), t))
    print('  implied exceeded realized in {}/{} names'.format(int((d > 0).sum()), len(d)))
    print('  ratio: mean {:.2f}   median {:.2f}'.format(
        float(np.mean(imp / rea)), float(np.median(imp / rea))))
    print()
    if t > 2 and np.mean(imp / rea) > 1.15:
        print('  >>> Options price a LARGER earnings jump than these names deliver.')
    elif t < -2:
        print('  >>> Options UNDERPRICE the jump - buying would be favoured.')
    else:
        print('  >>> No significant gap at this sample size.')
else:
    print('\n  too few names with both a detected cadence and a quotable straddle')

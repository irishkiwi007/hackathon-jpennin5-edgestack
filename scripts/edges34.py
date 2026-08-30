"""EDGE CLASSES 4 and 5, both structurally distinct from what we already have.

  4. VIX TERM STRUCTURE (VIX vs VIX3M). Contango (near < far) is the normal, calm state;
     backwardation (near > far) marks stress. Well documented as a regime signal for equity
     returns and for short-volatility risk. Distinct from our calm-bond filter because it is
     measured inside the volatility market rather than in bonds - so it may be a better filter,
     or an independent one that stacks.

  5. TIME-SERIES MOMENTUM. One of the most robust anomalies across asset classes
     (Moskowitz-Ooi-Pedersen): an asset's own past 12-month return predicts its next month.
     Completely independent of volatility premium, overnight drift and calendar structure.

Both measured in the underlying, so neither needs an option pricing model - which given how
badly those have behaved is the point.
"""
import csv, io, json, math, sys, datetime, urllib.request, urllib.parse, http.cookiejar
from collections import defaultdict
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


def ys(tk):
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


VIX = ys('^VIX')
VIX3M = {}
for tk in ('^VIX3M', '^VXV'):
    try:
        s = ys(tk)
        if len(s) > 500:
            VIX3M = s
            print('term-structure far leg: {} ({} sessions)'.format(tk, len(s)))
            break
    except Exception:
        continue
if not VIX3M:
    print('no VIX3M/VXV available - term structure test skipped')

BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    d = [r['date'] for r in rows]
    o = np.array([float(r['open']) for r in rows])
    c = np.array([float(r['close']) for r in rows])
    ac = np.array([float(r['adj_close']) for r in rows])
    fac = np.where(c > 0, ac / np.maximum(c, 1e-9), 1.0)
    return d, o * fac, ac


def nw_t(x, lag=1):
    x = np.asarray(x, float)
    n = len(x)
    if n < 15:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


def ann(m, n=252):
    return ((1 + m / 100.0) ** n - 1) * 100


dts, op_, cl = load('SPY')
n = len(cl)
idx = {d: i for i, d in enumerate(dts)}

if VIX3M:
    print()
    print('=' * 104)
    print('EDGE 4: VIX TERM STRUCTURE  (VIX / VIX3M)')
    print('=' * 104)
    rows = []
    for i in range(1, n - 21):
        d = dts[i]
        if d not in VIX or d not in VIX3M or VIX3M[d] <= 0:
            continue
        ts_ = VIX[d] / VIX3M[d]
        rows.append(dict(i=i, date=d, ts=ts_,
                         f1=math.log(cl[i + 1] / cl[i]) * 100,
                         f5=math.log(cl[i + 5] / cl[i]) * 100,
                         f21=math.log(cl[i + 21] / cl[i]) * 100,
                         on=math.log(op_[i + 1] / cl[i]) * 100))
    print('  observations: {}   {} -> {}'.format(len(rows), rows[0]['date'], rows[-1]['date']))
    b1 = float(np.mean([r['f1'] for r in rows]))
    b21 = float(np.mean([r['f21'] for r in rows]))
    print()
    print('  {:<28} {:>7} {:>12} {:>8} {:>13} {:>8} {:>12}'.format(
        'term structure', 'n', 'fwd 1d%', 't', 'fwd 21d%', 't', 'ann (1d)'))
    for lab, lo, hi in [('deep contango <0.85', 0, 0.85), ('contango 0.85-0.92', 0.85, 0.92),
                        ('flat 0.92-1.00', 0.92, 1.00),
                        ('backwardation 1.00-1.10', 1.00, 1.10),
                        ('deep backwardation >1.10', 1.10, 9)]:
        g = [r for r in rows if lo <= r['ts'] < hi]
        if len(g) < 60:
            continue
        a1 = np.array([r['f1'] for r in g])
        a21 = np.array([r['f21'] for r in g])
        print('  {:<28} {:>7} {:>11.4f}% {:>8.2f} {:>12.3f}% {:>8.2f} {:>11.2f}%'.format(
            lab, len(g), a1.mean(), nw_t(a1 - b1), a21.mean(), nw_t(a21 - b21, 21),
            ann(a1.mean())))
    print()
    print('  As a FILTER vs the calm-bond overlay - are they the same signal?')
    td, _, tcl = load('TLT')
    stds = {}
    for i in range(21, len(tcl)):
        stds[td[i]] = float(np.std(tcl[i - 21:i], ddof=1))
    CALM, hist, state = {}, [], False
    for d in [x for x in td if x in stds]:
        hist.append(stds[d]); hist[:] = hist[-90:]
        if len(hist) < 90:
            continue
        now, avg = hist[-1], sum(hist) / len(hist)
        state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
        CALM[d] = state
    both = [r for r in rows if r['date'] in CALM]
    ct = np.array([1.0 if r['ts'] < 0.95 else 0.0 for r in both])
    cb = np.array([1.0 if CALM[r['date']] else 0.0 for r in both])
    if len(ct) > 100:
        print('    agreement between "contango" and "calm bonds": {:.0f}%'.format(
            100 * np.mean(ct == cb)))
        print('    correlation: {:+.3f}'.format(float(np.corrcoef(ct, cb)[0, 1])))
        print('    -> low correlation means they are INDEPENDENT filters that can stack.')

print()
print('=' * 104)
print('EDGE 5: TIME-SERIES MOMENTUM — own 12-month return predicts the next month')
print('=' * 104)
ETFS = ['SPY', 'QQQ', 'SOXX', 'XLV', 'XLP', 'HYG', 'FDN', 'TLT']
print('{:<8} {:>7} {:>14} {:>8} {:>14} {:>8} {:>10}'.format(
    'sym', 'n', 'up-trend f21%', 't', 'down-trend f21%', 't', 'spread'))
npos = tot = 0
for s in ETFS:
    try:
        d2, o2, c2 = load(s)
    except OSError:
        continue
    m = len(c2)
    if m < 600:
        continue
    up, dn = [], []
    for i in range(252, m - 21):
        past = c2[i] / c2[i - 252] - 1.0
        fwd = math.log(c2[i + 21] / c2[i]) * 100
        (up if past > 0 else dn).append(fwd)
    if len(up) < 100 or len(dn) < 100:
        continue
    u, dv = np.array(up), np.array(dn)
    df = u.mean() - dv.mean()
    se = math.sqrt(u.var(ddof=1) / len(u) + dv.var(ddof=1) / len(dv))
    tot += 1
    npos += 1 if df > 0 else 0
    print('{:<8} {:>7} {:>13.3f}% {:>8.2f} {:>13.3f}% {:>8.2f} {:>+9.3f}%'.format(
        s, len(up) + len(dv), u.mean(), nw_t(u, 21), dv.mean(), nw_t(dv, 21), df))
print('\n  up-trend beat down-trend in {}/{} ETFs'.format(npos, tot))

print()
print('=' * 104)
print('DO THE EDGES OVERLAP? — correlation of daily signal states on SPY')
print('=' * 104)
sig = {}
for i in range(252, n - 21):
    d = dts[i]
    row = {}
    row['momentum'] = 1.0 if cl[i] / cl[i - 252] - 1 > 0 else 0.0
    if VIX3M and d in VIX and d in VIX3M and VIX3M[d] > 0:
        row['contango'] = 1.0 if VIX[d] / VIX3M[d] < 0.95 else 0.0
    dt = datetime.date.fromisoformat(d)
    row['month'] = dt.month
    sig[d] = row
keys = [k for k in ('momentum', 'contango') if any(k in v for v in sig.values())]
common = [d for d in sig if all(k in sig[d] for k in keys)]
if len(common) > 500 and len(keys) > 1:
    M = np.array([[sig[d][k] for k in keys] for d in common])
    C = np.corrcoef(M.T)
    print('  {:<14}'.format('') + ''.join('{:>12}'.format(k) for k in keys))
    for a_i, k in enumerate(keys):
        print('  {:<14}'.format(k) + ''.join('{:>12.3f}'.format(C[a_i][b_i])
                                             for b_i in range(len(keys))))
    print()
    print('  Near-zero correlation between signal states means the edges fire at different')
    print('  times and can be combined without simply doubling one bet.')

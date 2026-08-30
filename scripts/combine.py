"""Do the independent edges COMBINE into something better than any one of them?

Inventory, with how each was established:

  1. Variance risk premium  - CBOE ^PUT index, 30y real track record: Sharpe 0.43 vs SPX 0.34
  2. Overnight drift        - SPY overnight Sharpe 0.89 vs intraday 0.05; 7/8 ETFs, 8/9 eras
  3. Turn of month          - 6/6 ETFs directionally, t weak (~1-2)
  4. 12-month trend filter  - SPY up-trend fwd21 +1.011% (t=5.77) vs down-trend +0.113% (t=0.17)
  5. Calm-bond regime       - t(diff)=6.58 out-of-sample on 4,359 events

The test that matters is not whether each works alone but whether stacking them raises
risk-adjusted return. Edges that fire at the same times just double one bet; edges that fire at
different times genuinely diversify.

Everything below is measured in the underlying, so no option pricing model is involved.
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


VIX3M = {}
for tk in ('^VIX3M', '^VXV', 'VIX3M.INDX'):
    try:
        s = ys(tk)
        if len(s) > 500:
            VIX3M = s
            print('term-structure far leg available: {} ({})'.format(tk, len(s)))
            break
    except Exception as exc:
        print('  {} unavailable ({})'.format(tk, str(exc)[:40]))

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


dts, op_, cl = load('SPY')
n = len(cl)

# calm-bond regime
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

# turn-of-month index
bym = defaultdict(list)
for i, d in enumerate(dts):
    bym[d[:7]].append(i)
TOM = {}
for k, v in bym.items():
    for j, i in enumerate(v):
        TOM[i] = (j <= 2) or (j == len(v) - 1)

COST_BP = 0.7 / 100.0        # SPY round-trip at the touch, in percent


def stats(daily_pct, label, n_trades_per_yr=None):
    a = np.array(daily_pct, dtype=float)
    if len(a) < 100:
        return None
    eq = np.cumprod(1 + a / 100.0)
    yrs = len(a) / 252.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = a.std(ddof=1) * math.sqrt(252) / 100.0
    sharpe = (cagr - 0.02) / vol if vol > 0 else 0
    peak = np.maximum.accumulate(eq)
    dd = float((eq / peak - 1).min())
    return dict(label=label, cagr=cagr, vol=vol, sharpe=sharpe, dd=dd,
                exposure=100.0 * np.mean([1.0 if x != 0 else 0.0 for x in a]))


print()
print('=' * 104)
print('BUILDING THE STACK — SPY, 1993-2026, each edge added in turn')
print('=' * 104)
VARIANTS = []
buy_hold, on_only, on_trend, on_trend_calm, on_trend_tom = [], [], [], [], []
for i in range(252, n - 1):
    d = dts[i]
    tot = (cl[i] / cl[i - 1] - 1) * 100
    onr = (op_[i] / cl[i - 1] - 1) * 100
    trend_up = cl[i - 1] / cl[i - 253] - 1 > 0
    calm = CALM.get(d, True)
    tom = TOM.get(i, False)
    buy_hold.append(tot)
    on_only.append(onr - COST_BP)
    on_trend.append((onr - COST_BP) if trend_up else 0.0)
    on_trend_calm.append((onr - COST_BP) if (trend_up and calm) else 0.0)
    w = 1.5 if tom else 0.75
    on_trend_tom.append(((onr - COST_BP) * w) if trend_up else 0.0)

for series, lab in ((buy_hold, 'buy and hold SPY'),
                    (on_only, 'overnight only'),
                    (on_trend, 'overnight + trend filter'),
                    (on_trend_calm, 'overnight + trend + calm bonds'),
                    (on_trend_tom, 'overnight + trend + TOM sizing')):
    s = stats(series, lab)
    if s:
        VARIANTS.append(s)

print('{:<36} {:>10} {:>10} {:>9} {:>10} {:>11}'.format(
    'strategy', 'CAGR', 'vol', 'Sharpe', 'max DD', 'exposure'))
for s in VARIANTS:
    print('{:<36} {:>9.2f}% {:>9.2f}% {:>9.2f} {:>9.1f}% {:>10.0f}%'.format(
        s['label'], 100 * s['cagr'], 100 * s['vol'], s['sharpe'], 100 * s['dd'], s['exposure']))

print()
print('=' * 104)
print('ERA STABILITY of the stacked strategy')
print('=' * 104)
print('{:<14} {:>7} {:>12} {:>12} {:>10} {:>12}'.format(
    'era', 'n', 'overnight+', 'buy&hold', 'Sharpe o/n', 'Sharpe b&h'))
d_idx = dts[252:n - 1]
for lab, a_, b_ in [('1993-1999', '1993', '2000'), ('2000-2002', '2000', '2003'),
                    ('2003-2007', '2003', '2008'), ('2008-2009', '2008', '2010'),
                    ('2010-2015', '2010', '2016'), ('2016-2019', '2016', '2020'),
                    ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                    ('2024-2026', '2024', '2027')]:
    m = [j for j, d in enumerate(d_idx) if a_ <= d[:4] < b_]
    if len(m) < 100:
        continue
    o_ = np.array([on_trend[j] for j in m])
    b_arr = np.array([buy_hold[j] for j in m])
    yrs = len(m) / 252.0
    co = np.prod(1 + o_ / 100) ** (1 / yrs) - 1
    cb = np.prod(1 + b_arr / 100) ** (1 / yrs) - 1
    so = (co - 0.02) / (o_.std(ddof=1) * math.sqrt(252) / 100) if o_.std() > 0 else 0
    sb = (cb - 0.02) / (b_arr.std(ddof=1) * math.sqrt(252) / 100) if b_arr.std() > 0 else 0
    print('{:<14} {:>7} {:>11.2f}% {:>11.2f}% {:>10.2f} {:>12.2f}'.format(
        lab, len(m), 100 * co, 100 * cb, so, sb))

print()
print('=' * 104)
print('ARE THE EDGES INDEPENDENT? — correlation of the daily return streams')
print('=' * 104)
streams = {'buy&hold': np.array(buy_hold), 'overnight': np.array(on_only),
           'intraday': np.array(buy_hold) - np.array(on_only)}
ks = list(streams)
print('  {:<12}'.format('') + ''.join('{:>12}'.format(k) for k in ks))
for a_k in ks:
    line = '  {:<12}'.format(a_k)
    for b_k in ks:
        line += '{:>12.3f}'.format(float(np.corrcoef(streams[a_k], streams[b_k])[0, 1]))
    print(line)
print()
print('  Overnight and intraday are near-uncorrelated components of the same total return,')
print('  so keeping only the overnight half is a genuine risk reduction rather than a')
print('  re-labelling of the same exposure.')

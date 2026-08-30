"""Recompute the core result with a CALIBRATED implied-volatility surface.

Earlier runs used VIX directly as ATM implied volatility with no skew. Ground truth from live
quotes shows that overstates an ATM/-5% SPY put spread credit by 141% ($967 modelled vs $401
real). Two separate errors were folded together:

  1. VIX is a 30-day OTM-weighted strip, not ATM IV. Backing out the live ATM put ($4.23 at
     9 DTE) gives ATM IV ~ 0.088 against VIX 0.187, so ATM_IV ~ VIX x 0.47.
  2. Skew was ignored, so the long (further OTM) leg was priced too cheaply, inflating credit.

Both corrections applied here. The RELATIVE ranking of regimes should survive - the bias was
uniform across them - but the LEVEL needs restating.
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
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
RATE, VIX_TO_ATM, LEG_FR, SPOT_NOW = 0.045, 0.47, 4.0, 769.35
SKEW_X = [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06]
SKEW_Y = [1.63, 1.35, 1.15, 1.00, 0.85, 0.90, 1.12]


def sk(m):
    return float(np.interp(m, SKEW_X, SKEW_Y))


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsp(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - s * math.sqrt(T))) - S * ncdf(-d1)


def bsc(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d1 - s * math.sqrt(T))


def px(S, K, T, ivatm, cp):
    return (bsp if cp == 'P' else bsc)(S, K, T, RATE, ivatm * sk(K / S - 1.0))


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
    return [r['date'] for r in rows], np.array([float(r['adj_close']) for r in rows])


td, tc = load('TLT')
stds = {}
for i in range(21, len(tc)):
    stds[td[i]] = float(np.std(tc[i - 21:i], ddof=1))
CALM, hist, state = {}, [], False
for d in [x for x in td if x in stds]:
    hist.append(stds[d]); hist[:] = hist[-90:]
    if len(hist) < 90:
        continue
    now, avg = hist[-1], sum(hist) / len(hist)
    state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
    CALM[d] = state

dts, cl = load('SPY')
n = len(cl)
rr = np.zeros(n); rr[1:] = np.log(cl[1:] / cl[:-1])
scale = SPOT_NOW / cl[-1]

S, T = 769.28, 9 / 365.0
ivatm = 0.187 * VIX_TO_ATM
mod = (px(S, S, T, ivatm, 'P') - px(S, S * 0.95, T, ivatm, 'P')) * 100
print('CALIBRATION CHECK   ATM/-5% SPY put spread, 9 DTE, VIX 18.71')
print('  modelled credit  ${:.0f}'.format(mod))
print('  real quoted      $401')
print('  error            {:+.0f}%'.format(100 * (mod / 401 - 1)))
print()

HOLD, DTE = 5, 14
EV = []
for i in range(30, n - HOLD - 1):
    d = dts[i]
    dE = dts[i + HOLD]
    if d not in VIX or dE not in VIX or d not in CALM:
        continue
    rv = rr[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
    if rv <= 0:
        continue
    EV.append(dict(i=i, date=d, ivrv=(VIX[d] / 100.0) / rv, calm=CALM[d],
                   iv0=VIX[d] / 100.0 * VIX_TO_ATM, iv1=VIX[dE] / 100.0 * VIX_TO_ATM))
print('sessions: {}'.format(len(EV)))


def pnl(e, so, w, structure='put'):
    i = e['i']
    S0, S1 = cl[i] * scale, cl[i + HOLD] * scale
    T0, T1 = DTE / 365.0, max((DTE - HOLD) / 365.0, 1e-4)
    wd = S0 * w
    Kps = S0 * (1 + so)
    Kpl = Kps - wd
    c0 = px(S0, Kps, T0, e['iv0'], 'P') - px(S0, Kpl, T0, e['iv0'], 'P')
    c1 = px(S1, Kps, T1, e['iv1'], 'P') - px(S1, Kpl, T1, e['iv1'], 'P')
    legs = 2
    if structure == 'condor':
        Kcs = S0 * (1 - so)
        Kcl = Kcs + wd
        c0 += px(S0, Kcs, T0, e['iv0'], 'C') - px(S0, Kcl, T0, e['iv0'], 'C')
        c1 += px(S1, Kcs, T1, e['iv1'], 'C') - px(S1, Kcl, T1, e['iv1'], 'C')
        legs = 4
    if c0 <= 0:
        return None
    return (c0 - c1) * 100 - 2 * legs * LEG_FR, wd * 100 - c0 * 100


qs = np.percentile([e['ivrv'] for e in EV], [20, 80])
CHEAP, RICH = qs
print('IV/RV cuts: cheap<{:.2f}  rich>{:.2f}'.format(CHEAP, RICH))
print()
print('=' * 100)
print('RECALIBRATED — SPY put spread, ATM/-5%, 14 DTE, 5-session hold')
print('=' * 100)
print('{:<28} {:>7} {:>9} {:>9} {:>9} {:>7} {:>7}'.format(
    'regime', 'n', 'net $', 'risk $', 'ret/risk', 't', 'win%'))
for lab, sel in (('all sessions', lambda e: True),
                 ('calm bonds', lambda e: e['calm']),
                 ('calm + IV not cheap', lambda e: e['calm'] and e['ivrv'] >= CHEAP),
                 ('calm + IV rich', lambda e: e['calm'] and e['ivrv'] >= RICH),
                 ('stressed bonds', lambda e: not e['calm'])):
    rows = [pnl(e, 0.0, 0.05) for e in EV if sel(e)]
    rows = [r for r in rows if r]
    if len(rows) < 60:
        continue
    a = np.array([r[0] for r in rows])
    rk = float(np.mean([r[1] for r in rows]))
    print('{:<28} {:>7} {:>9.0f} {:>9.0f} {:>8.2f}% {:>7.2f} {:>6.1f}%'.format(
        lab, len(a), a.mean(), rk, 100 * a.mean() / rk, nw_t(a, HOLD), 100 * (a > 0).mean()))

print()
print('=' * 100)
print('CONDOR vs PUT SPREAD, recalibrated (calm + IV not cheap)')
print('=' * 100)
print('{:<30} {:>7} {:>9} {:>9} {:>9} {:>7} {:>7}'.format(
    'structure', 'n', 'net $', 'risk $', 'ret/risk', 't', 'win%'))
for lab, so, w, stc in (('put spread ATM/-5%', 0.0, 0.05, 'put'),
                        ('put spread 2%OTM/2w', -0.02, 0.02, 'put'),
                        ('condor 2% OTM, 2% wide', -0.02, 0.02, 'condor'),
                        ('condor 3% OTM, 2% wide', -0.03, 0.02, 'condor'),
                        ('condor 3% OTM, 3% wide', -0.03, 0.03, 'condor'),
                        ('condor 4% OTM, 3% wide', -0.04, 0.03, 'condor')):
    rows = [pnl(e, so, w, stc) for e in EV if e['calm'] and e['ivrv'] >= CHEAP]
    rows = [r for r in rows if r]
    if len(rows) < 60:
        continue
    a = np.array([r[0] for r in rows])
    rk = float(np.mean([r[1] for r in rows]))
    ann = (100 * a.mean() / rk) * (len(a) / 33.3) / 100
    print('{:<30} {:>7} {:>9.0f} {:>9.0f} {:>8.2f}% {:>7.2f} {:>6.1f}%'.format(
        lab, len(a), a.mean(), rk, 100 * a.mean() / rk, nw_t(a, HOLD), 100 * (a > 0).mean()))

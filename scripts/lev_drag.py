"""Two tests on leveraged ETFs.

  A. VOLATILITY DRAG as a directional edge. A 3x ETF's expected return is 3r - 3*sigma^2 (more
     generally L*r - L(L-1)/2 * sigma^2), so it bleeds in choppy markets. If that decay is large,
     persistent, and PREDICTABLE from current volatility, then selling calls / bear call spreads
     on leveraged ETFs has a directional edge that is structural rather than statistical.

  B. THE RICH-IV STRATEGY on leveraged names. Live measurement says leveraged options price at
     1.046 x (L x base IV) - essentially efficient - while spot/friction is 33x worse than SPY.
     Testing whether the higher premium compensates for the wider spread.

Implied volatility for the leveraged name is taken as L x the base index IV (VIX/VXN), which the
live check validated to within 5%.
"""
import os
import csv, io, json, math, sys, datetime, urllib.request, urllib.parse, http.cookiejar
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
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
start = end - 22 * 365 * 86400


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


PAIRS = [('TQQQ', 'QQQ', 3), ('SPXL', 'SPY', 3), ('UPRO', 'SPY', 3),
         ('SSO', 'SPY', 2), ('QLD', 'QQQ', 2), ('SOXL', 'SOXX', 3), ('TNA', 'IWM', 3)]
S = {}
for tk in sorted({x for p in PAIRS for x in p[:2]}):
    try:
        S[tk] = yseries(tk)
        print('{:<6} {} sessions'.format(tk, len(S[tk])))
    except Exception as e:
        print('{:<6} FAILED {}'.format(tk, str(e)[:40]))
VIX = yseries('^VIX')
try:
    VXN = yseries('^VXN')
except Exception:
    VXN = {}


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 10:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


print()
print('=' * 104)
print('A. VOLATILITY DRAG — does the leveraged ETF underperform L x the base, and is it')
print('   PREDICTABLE from volatility at the time?')
print('=' * 104)
print('{:<7} {:<6} {:>3} {:>7} {:>13} {:>13} {:>12} {:>9} {:>16}'.format(
    'lev', 'base', 'L', 'n', 'lev 21d ret%', 'L x base%', 'drag%', 't', 'corr(RV, drag)'))
for lev, base, L in PAIRS:
    if lev not in S or base not in S:
        continue
    common = sorted(set(S[lev]) & set(S[base]))
    if len(common) < 400:
        continue
    a = np.array([S[lev][d] for d in common])
    b = np.array([S[base][d] for d in common])
    rb = np.zeros(len(b)); rb[1:] = np.log(b[1:] / b[:-1])
    H = 21
    drags, rvs, levr = [], [], []
    for i in range(25, len(common) - H):
        rv = rb[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        lr = (a[i + H] / a[i] - 1.0) * 100
        br = (b[i + H] / b[i] - 1.0) * 100
        drags.append(lr - L * br)
        rvs.append(rv)
        levr.append(lr)
    if len(drags) < 200:
        continue
    d_ = np.array(drags); v_ = np.array(rvs)
    c = float(np.corrcoef(v_, d_)[0, 1])
    print('{:<7} {:<6} {:>3} {:>7} {:>12.2f}% {:>12.2f}% {:>11.2f}% {:>9.2f} {:>16.3f}'.format(
        lev, base, L, len(d_), float(np.mean(levr)),
        float(np.mean(levr)) - float(np.mean(d_)), d_.mean(), nw_t(d_, H), c))

print()
print('  drag% = leveraged return minus L x base return, over 21 sessions.')
print('  A large NEGATIVE drag that correlates NEGATIVELY with volatility is the structural')
print('  effect: the more volatile the tape, the more the leveraged product bleeds.')

print()
print('=' * 104)
print('B. IS THE DRAG TRADEABLE? — drag sorted by volatility at entry (TQQQ, 21-session hold)')
print('=' * 104)
lev, base, L = 'TQQQ', 'QQQ', 3
if lev in S and base in S:
    common = sorted(set(S[lev]) & set(S[base]))
    a = np.array([S[lev][d] for d in common])
    b = np.array([S[base][d] for d in common])
    rb = np.zeros(len(b)); rb[1:] = np.log(b[1:] / b[:-1])
    rows = []
    for i in range(25, len(common) - 21):
        rv = rb[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        rows.append(dict(rv=rv, drag=(a[i + 21] / a[i] - 1) * 100 - L * (b[i + 21] / b[i] - 1) * 100,
                         lev=(a[i + 21] / a[i] - 1) * 100, date=common[i]))
    qs = np.percentile([r['rv'] for r in rows], [25, 50, 75])
    print('  {:<24} {:>7} {:>11} {:>9} {:>14} {:>9}'.format(
        'base volatility', 'n', 'drag%', 't', 'lev return%', 't'))
    for lab, lo_, hi_ in [('calm  <{:.2f}'.format(qs[0]), 0, qs[0]),
                          ('{:.2f}-{:.2f}'.format(qs[0], qs[1]), qs[0], qs[1]),
                          ('{:.2f}-{:.2f}'.format(qs[1], qs[2]), qs[1], qs[2]),
                          ('turbulent >{:.2f}'.format(qs[2]), qs[2], 99)]:
        g = [r for r in rows if lo_ <= r['rv'] < hi_]
        if len(g) < 60:
            continue
        d_ = np.array([r['drag'] for r in g]); l_ = np.array([r['lev'] for r in g])
        print('  {:<24} {:>7} {:>10.2f}% {:>9.2f} {:>13.2f}% {:>9.2f}'.format(
            lab, len(g), d_.mean(), nw_t(d_, 21), l_.mean(), nw_t(l_, 21)))
    print()
    print('  If leveraged RETURN is significantly negative in the turbulent bucket, a bearish')
    print('  structure there has a directional edge. If only the DRAG is negative while the')
    print('  return is still positive, the base index rally more than offsets the bleed and')
    print('  there is nothing to short.')

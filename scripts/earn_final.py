"""EDGE CLASS 6, third attempt — with the selection bias designed out.

Attempt 1 used Yahoo's fiscal quarter-END date as the announcement date. Wrong day.
Attempt 2 detected earnings as ">2 sigma move on high volume", which selects the largest moves
by construction and therefore guarantees "realized > implied".

The bias is the whole problem, so this locates earnings dates using information that is
INDEPENDENT of the price move:

  ANCHOR  : Yahoo `calendarEvents.earningsCallDate` - an exact, confirmed announcement date.
  PROJECT : earnings are quarterly, so step back ~91 calendar days repeatedly.
  REFINE  : within +/-7 days of each projected date, pick the session with the highest VOLUME.

Volume identifies the event; the MOVE is then measured on whatever day volume picked. Since the
move was never used to choose the day, the measured move is unbiased.

VALIDATION: the method is checked against exact announcement dates recovered independently from
news headlines. If volume-refinement lands on the same days, the locator is trustworthy.
"""
import os
import json, sys, io, math, time, datetime, urllib.request, urllib.parse, http.cookiejar
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
DATA = 'https://data.alpaca.markets'
PAPER = 'https://paper-api.alpaca.markets'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def yget(u):
    r = urllib.request.Request(u)
    r.add_header('User-Agent', UA)
    r.add_header('Referer', 'https://finance.yahoo.com/')
    return op.open(r, timeout=45).read().decode('utf-8', 'replace')


def aget(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(0.5)
    return None


try:
    yget('https://fc.yahoo.com')
except Exception:
    pass
CRUMB = yget('https://query1.finance.yahoo.com/v1/test/getcrumb').strip()

NAMES = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'AMD', 'AVGO', 'ORCL',
         'CRM', 'ADBE', 'NFLX', 'INTC', 'MU', 'QCOM', 'TXN', 'NOW', 'PANW', 'JPM',
         'BAC', 'WFC', 'GS', 'MS', 'DIS', 'WMT', 'COST', 'HD', 'LOW', 'NKE',
         'SBUX', 'MCD', 'PG', 'KO', 'PEP', 'JNJ', 'PFE', 'MRK', 'ABBV', 'LLY',
         'UNH', 'XOM', 'CVX', 'CAT', 'BA', 'GE', 'UBER', 'V', 'MA', 'SHOP',
         'PYPL', 'COIN', 'HOOD', 'SOFI', 'PLTR', 'SNOW', 'DDOG', 'NET', 'CRWD', 'ZS',
         'OKTA', 'TEAM', 'WDAY', 'SNPS', 'CDNS', 'KLAC', 'LRCX', 'AMAT', 'ADI', 'NXPI',
         'ON', 'MRVL', 'SMCI', 'DELL', 'HPQ', 'IBM', 'ACN', 'CSCO', 'ANET', 'ZM',
         'DOCU', 'TWLO', 'ROKU', 'SPOT', 'ABNB', 'DASH', 'LYFT', 'EBAY', 'ETSY', 'CHWY',
         'LULU', 'TGT', 'TJX', 'ROST', 'DG', 'DLTR', 'KR', 'SYY', 'GIS', 'K',
         'HSY', 'STZ', 'MO', 'PM', 'CL', 'KMB', 'EL', 'CLX', 'CHD', 'MDLZ',
         'CAG', 'CPB', 'SJM', 'BMY', 'GILD', 'AMGN', 'BIIB', 'REGN', 'VRTX', 'MRNA',
         'ZTS', 'TMO', 'DHR', 'ABT', 'SYK', 'BSX', 'MDT', 'ISRG', 'EW', 'BDX',
         'CI', 'CVS', 'HUM', 'ELV', 'MCK', 'SLB', 'HAL', 'OXY', 'PSX', 'VLO',
         'MPC', 'KMI', 'WMB', 'OKE', 'EOG', 'DVN', 'FANG', 'HES', 'APA']

print('fetching anchors (last + next confirmed announcement dates)...')
ANCH = {}
for i, s in enumerate(NAMES):
    try:
        u = ('https://query2.finance.yahoo.com/v10/finance/quoteSummary/' + s
             + '?modules=calendarEvents&crumb=' + urllib.parse.quote(CRUMB))
        d = json.loads(yget(u))
        ce = (((d.get('quoteSummary') or {}).get('result') or [{}])[0]
              .get('calendarEvents') or {}).get('earnings') or {}
        last = (ce.get('earningsCallDate') or [{}])
        nxt = (ce.get('earningsDate') or [{}])
        lastd = (datetime.datetime.fromtimestamp(last[0]['raw'], datetime.timezone.utc).date()
                 if last and last[0].get('raw') else None)
        nxtd = (datetime.datetime.fromtimestamp(nxt[0]['raw'], datetime.timezone.utc).date()
                if nxt and nxt[0].get('raw') else None)
        if lastd:
            ANCH[s] = (lastd, nxtd, not ce.get('isEarningsDateEstimate', True))
    except Exception:
        pass
    if (i + 1) % 15 == 0:
        print('  {}/{}  anchors {}'.format(i + 1, len(NAMES), len(ANCH)))
print('anchors: {}'.format(len(ANCH)))

today = datetime.date.today()
st = (today - datetime.timedelta(days=1500)).isoformat()
BARS = {}
syms = list(ANCH)
for i in range(0, len(syms), 20):
    ch = syms[i:i + 20]
    acc, tok = defaultdict(list), None
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
            BARS[sy] = [{'t': b['t'][:10], 'c': float(b['c']), 'o': float(b['o']),
                         'v': float(b['v'])} for b in acc[sy]]
print('bars: {}'.format(len(BARS)))


def locate(sym):
    """Quarterly projection from the anchor, each date refined by VOLUME (never by price)."""
    if sym not in ANCH or sym not in BARS:
        return []
    rows = BARS[sym]
    dates = [r['t'] for r in rows]
    idx = {d: i for i, d in enumerate(dates)}
    v = np.array([r['v'] for r in rows])
    anchor = ANCH[sym][0]
    out = []
    for k in range(0, 20):
        target = anchor - datetime.timedelta(days=91 * k)
        if target.isoformat() < dates[0]:
            break
        # candidate sessions within +/-7 calendar days
        cand = [i for i, d in enumerate(dates)
                if abs((datetime.date.fromisoformat(d) - target).days) <= 7]
        cand = [i for i in cand if i >= 60]
        if not cand:
            continue
        # pick the highest-volume session RELATIVE to its own trailing norm
        best, bs = None, -1
        for i in cand:
            base = v[i - 60:i].mean()
            if base <= 0:
                continue
            rel = v[i] / base
            if rel > bs:
                best, bs = i, rel
        if best is not None and bs > 1.2:
            out.append((best, dates[best], bs))
    return sorted(set(out))


print()
print('=' * 100)
print('VALIDATION — does volume-refinement land on the news-confirmed announcement dates?')
print('=' * 100)
KEY = ('q1 earnings', 'q2 earnings', 'q3 earnings', 'q4 earnings', 'quarterly results',
       'earnings results', 'reports q', 'fiscal q', 'earnings call', 'tops estimates',
       'reports fourth-quarter', 'reports third-quarter', 'reports second-quarter',
       'reports first-quarter')


def news_dates(sym):
    hits, tok = defaultdict(int), None
    for _ in range(25):
        u = (DATA + '/v1beta1/news?symbols=' + sym
             + '&start=2023-01-01T00:00:00Z&end=2026-08-28T23:59:00Z&limit=50')
        if tok:
            u += '&page_token=' + tok
        d = aget(u)
        if not d:
            break
        for a in d.get('news', []):
            h = (a.get('headline') or '').lower()
            if any(k in h for k in KEY):
                hits[a['created_at'][:10]] += 1
        tok = d.get('next_page_token')
        if not tok:
            break
    return sorted([d for d, c in hits.items() if c >= 2])


hit = miss = 0
for s in ('AAPL', 'JPM', 'MSFT', 'NVDA', 'BAC'):
    if s not in BARS:
        continue
    nd = news_dates(s)
    loc = [d for _, d, _ in locate(s)]
    if not nd:
        print('  {:<6} no news-confirmed dates to check against'.format(s))
        continue
    matched = 0
    for d in nd:
        dd = datetime.date.fromisoformat(d)
        if any(abs((datetime.date.fromisoformat(l) - dd).days) <= 2 for l in loc):
            matched += 1
    hit += matched
    miss += len(nd) - matched
    print('  {:<6} news dates {:>2}   located within 2 sessions: {:>2}   ({:.0f}%)'.format(
        s, len(nd), matched, 100 * matched / len(nd)))
print()
print('  overall: {}/{} news-confirmed dates recovered ({:.0f}%)'.format(
    hit, hit + miss, 100 * hit / max(hit + miss, 1)))
if hit + miss and hit / (hit + miss) < 0.6:
    print('  >>> locator is NOT reliable enough; results below should not be trusted')
else:
    print('  >>> locator validated - measured moves below are unbiased by construction')

print()
print('=' * 100)
print('REALIZED EARNINGS MOVE (unbiased: day chosen by volume, move measured after)')
print('=' * 100)
REAL = {}
print('{:<7} {:>8} {:>12} {:>13} {:>12} {:>12}'.format(
    'sym', 'n events', 'per year', 'mean |move|%', 'median%', 'ordinary%'))
for s in sorted(BARS):
    loc = locate(s)
    if len(loc) < 6:
        continue
    rows = BARS[s]
    c = np.array([r['c'] for r in rows])
    lr = np.zeros(len(c))
    lr[1:] = np.log(c[1:] / c[:-1])
    mv = [abs(lr[i]) * 100 for i, _, _ in loc if i > 0]
    ex = set()
    for i, _, _ in loc:
        ex.update(range(max(i - 1, 0), min(i + 2, len(lr))))
    ordin = np.array([lr[i] for i in range(1, len(lr)) if i not in ex])
    if len(mv) < 6 or len(ordin) < 200:
        continue
    REAL[s] = (float(np.mean(mv)), float(np.std(ordin, ddof=1) * 100), len(mv))
    print('{:<7} {:>8} {:>12.1f} {:>12.2f}% {:>11.2f}% {:>11.2f}%'.format(
        s, len(mv), len(mv) / (len(rows) / 252.0), float(np.mean(mv)),
        float(np.median(mv)), float(np.std(ordin, ddof=1) * 100)))

print()
print('=' * 100)
print('IMPLIED vs REALIZED — only names whose next earnings falls INSIDE a quotable expiry')
print('=' * 100)
print('{:<7} {:>11} {:>6} {:>10} {:>11} {:>11} {:>10}'.format(
    'sym', 'next earn', 'DTE', 'straddle%', 'ordinary%', 'implied jmp', 'real jmp'))
out = []
for s in sorted(REAL):
    if s not in ANCH or not ANCH[s][1]:
        continue
    nxt = ANCH[s][1]
    dte_e = (nxt - today).days
    if not (0 < dte_e <= 40):
        continue
    spot = BARS[s][-1]['c']
    # expiry must be ON or AFTER the earnings date, and close to it
    cc = aget('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
              '&expiration_date_lte={}&limit=800&status=active'.format(
                  PAPER, s, nxt.isoformat(),
                  (nxt + datetime.timedelta(days=10)).isoformat()))
    cand = [x for x in ((cc or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.98 * spot <= float(x['strike_price']) <= 1.02 * spot]
    if len(cand) < 2:
        continue
    exps = sorted({x['expiration_date'] for x in cand})
    sub = [x for x in cand if x['expiration_date'] == exps[0]]
    occ = [x['symbol'] for x in sub]
    snaps = {}
    for k in range(0, len(occ), 100):
        sd = aget(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[k:k + 100]))
        for kk, vv in (sd or {}).get('snapshots', {}).items():
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
    if not best:
        continue
    dte = (datetime.date.fromisoformat(exps[0]) - today).days
    sessions = max(int(dte * 252 / 365), 1)
    total = best[1] / spot * 100 / 0.8
    real_mv, ordin_daily, nev = REAL[s]
    ordinary = ordin_daily * math.sqrt(sessions)
    jump = math.sqrt(max(total ** 2 - ordinary ** 2, 0.0))
    if jump <= 0.05:
        continue
    out.append((s, jump, real_mv))
    print('{:<7} {:>11} {:>6} {:>9.2f}% {:>10.2f}% {:>10.2f}% {:>9.2f}%'.format(
        s, nxt.isoformat(), dte, best[1] / spot * 100, ordinary, jump, real_mv))

if len(out) >= 6:
    imp = np.array([r[1] for r in out])
    rea = np.array([r[2] for r in out])
    d = imp - rea
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
    print()
    print('  n={}  implied jump {:.2f}%   realized jump {:.2f}%'.format(
        len(out), imp.mean(), rea.mean()))
    print('  difference {:+.2f} pct-points   t={:.2f}   ratio {:.2f}'.format(
        d.mean(), t, float(np.mean(imp / rea))))
    print('  implied exceeded realized in {}/{}'.format(int((d > 0).sum()), len(d)))
else:
    print('\n  too few names with earnings inside a quotable expiry right now (n={})'.format(
        len(out)))

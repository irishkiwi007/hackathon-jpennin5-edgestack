"""Follow-up on the coverage-spike result. Three fixes:

1. CONFOUND: the big-spike bucket had trailing RV of 40.6% vs ~35% elsewhere. Part of the larger
   forward move is simply "vol was already high". Normalise the forward move by what trailing vol
   predicts, so the test measures the news EXCESS.
2. POWER: only 35-45 spike days per symbol at nz>2, too few for the per-symbol sign check that has
   been the reliable noise detector. Lower the bar to nz>1.5 and report per symbol.
3. CACHE the pulls so iteration is cheap.
"""
import os
import json, math, sys, io, os, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
SYMS = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'MSFT', 'AMZN', 'META', 'SPY', 'GOOGL', 'NFLX']
START, END = '2024-08-01', '2026-08-28'
LOOK = 20
CACHE = 'newscache.json'


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.2)
    return None


cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for s in SYMS:
    if s in cache:
        continue
    cnt, tok = defaultdict(int), None
    for _ in range(900):
        u = (f'https://data.alpaca.markets/v1beta1/news?symbols={s}'
             f'&start={START}T00:00:00Z&end={END}T23:59:00Z&limit=50')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        for a in d.get('news', []):
            cnt[a['created_at'][:10]] += 1
        tok = d.get('next_page_token')
        if not tok:
            break
    bb, tok = [], None
    while True:
        u = (f'https://data.alpaca.markets/v2/stocks/{s}/bars?timeframe=1Day&feed=sip'
             f'&start={START}&end={END}&limit=10000&adjustment=all')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        bb += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    cache[s] = {'cnt': dict(cnt), 'bars': [{'t': b['t'][:10], 'c': b['c']} for b in bb]}
    json.dump(cache, open(CACHE, 'w'))
    print(f'cached {s}: {len(bb)} bars, {sum(cnt.values())} articles')

ROWS = []
for s in SYMS:
    if s not in cache:
        continue
    bars = cache[s]['bars']
    cnt = cache[s]['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 11):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        nz = (counts[i] - mu) / sd
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        exp5 = rv / math.sqrt(252) * math.sqrt(5)      # expected 5d move from trailing vol
        ROWS.append(dict(sym=s, nz=nz, rv=rv,
                         past5=math.log(px[i] / px[i - 5]),
                         f1=math.log(px[i + 1] / px[i]),
                         f5=math.log(px[i + 5] / px[i]),
                         f10=math.log(px[i + 10] / px[i]),
                         fv5=abs(math.log(px[i + 5] / px[i])),
                         norm5=abs(math.log(px[i + 5] / px[i])) / exp5))
print(f'\nobservations: {len(ROWS)}  symbols: {len(set(r["sym"] for r in ROWS))}')

BUCK = [('nz < 0 (quiet)', lambda r: r['nz'] < 0),
        ('0 - 1', lambda r: 0 <= r['nz'] < 1),
        ('1 - 2', lambda r: 1 <= r['nz'] < 2),
        ('2 - 3', lambda r: 2 <= r['nz'] < 3),
        ('nz > 3 (spike)', lambda r: r['nz'] >= 3)]

print('\n' + '=' * 104)
print('1. RAW vs VOL-NORMALISED forward move — does the news effect survive the vol confound?')
print('=' * 104)
allraw = np.mean([r['fv5'] for r in ROWS])
allnorm = np.mean([r['norm5'] for r in ROWS])
print(f'{"bucket":<18} {"n":>6} {"trail RV":>9} {"raw |fwd5|":>11} {"vs all":>8} {"t":>6} | '
      f'{"NORMALISED":>11} {"vs all":>8} {"t":>6}')
for lab, sel in BUCK:
    g = [r for r in ROWS if sel(r)]
    if len(g) < 40:
        continue
    raw = np.array([r['fv5'] for r in g])
    nor = np.array([r['norm5'] for r in g])
    er = raw.mean() - allraw
    tr = er / (raw.std(ddof=1) / math.sqrt(len(g)))
    en = nor.mean() - allnorm
    tn = en / (nor.std(ddof=1) / math.sqrt(len(g)))
    print(f'{lab:<18} {len(g):>6} {np.mean([r["rv"] for r in g])*100:>8.1f}% '
          f'{raw.mean()*100:>10.2f}% {er*100:>+7.2f}% {tr:>6.2f} | '
          f'{nor.mean():>11.3f} {en:>+8.3f} {tn:>6.2f}')
print("""
NORMALISED = |forward 5d move| divided by the move trailing vol predicts. If the gradient survives
here, the coverage spike carries information beyond "volatility was already elevated".""")

print('\n' + '=' * 104)
print('2. PER-SYMBOL SIGN CHECK — normalised forward move, spike (nz>1.5) vs rest')
print('=' * 104)
print(f'{"sym":>7} {"n spike":>8} {"spike norm":>11} {"rest norm":>10} {"ratio":>7} {"t":>7} '
      f'{"":>6}')
bysym = defaultdict(list)
for r in ROWS:
    bysym[r['sym']].append(r)
pos = 0
tot = 0
for s, rs in sorted(bysym.items()):
    sp = [r['norm5'] for r in rs if r['nz'] >= 1.5]
    rest = [r['norm5'] for r in rs if r['nz'] < 1.5]
    if len(sp) < 30:
        print(f'{s:>7} {len(sp):>8}  (too few)')
        continue
    sp, rest = np.array(sp), np.array(rest)
    diff = sp.mean() - rest.mean()
    t = diff / math.sqrt(sp.var(ddof=1) / len(sp) + rest.var(ddof=1) / len(rest))
    tot += 1
    if diff > 0:
        pos += 1
    print(f'{s:>7} {len(sp):>8} {sp.mean():>11.3f} {rest.mean():>10.3f} '
          f'{sp.mean()/rest.mean():>7.3f} {t:>7.2f} {"*" if abs(t)>1.9 else "":>6}')
print(f'\nsymbols where a coverage spike raised the normalised move: {pos} of {tot}')

print('\n' + '=' * 104)
print('3. TREND vs REVERSION after a spike — pooled, more power (nz>1.5)')
print('=' * 104)
for fk, lbl in (('f1', 'forward 1d'), ('f5', 'forward 5d'), ('f10', 'forward 10d')):
    for lab, sel in (('spike nz>1.5', lambda r: r['nz'] >= 1.5),
                     ('rest nz<1.5', lambda r: r['nz'] < 1.5)):
        g = [r for r in ROWS if sel(r)]
        base = np.mean([r[fk] for r in g])
        up = [r for r in g if r['past5'] > 0]
        dn = [r for r in g if r['past5'] <= 0]
        if len(up) < 40 or len(dn) < 40:
            continue
        uv = np.array([r[fk] for r in up])
        dv = np.array([r[fk] for r in dn])
        ue = uv.mean() - base
        ut = ue / (uv.std(ddof=1) / math.sqrt(len(uv)))
        de = dv.mean() - base
        dt = de / (dv.std(ddof=1) / math.sqrt(len(dv)))
        rd = ('up cont' if ue > 0 else 'up rev') + ' / ' + ('down cont' if de < 0 else 'down rev')
        print(f'{lbl:<12} {lab:<14} up n={len(up):>5} {ue*100:>+7.3f}% t={ut:>6.2f}   '
              f'down n={len(dn):>5} {de*100:>+7.3f}% t={dt:>6.2f}   {rd}')
    print()

"""ACTUAL SENTIMENT — Loughran-McDonald scoring of Benzinga article text.

Not article counts. Not arrival timing. The measured tone of the text.

LM is the finance-specific standard (Loughran & McDonald 2011, Journal of Finance) - built because
general-purpose lexicons misclassify financial language badly ("liability", "tax", "cost" are
negative in Harvard-IV but neutral in finance).

Pulls headline+summary for each article, scores polarity, aggregates to a daily per-symbol
sentiment, and tests whether it predicts returns - separately from the coverage-VOLUME effect
already established.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np
import pysentiment2 as ps

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
SYMS = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'MSFT', 'AMZN', 'META', 'GOOGL', 'NFLX', 'SPY']
START, END = '2024-08-01', '2026-08-28'
CACHE = 'sentcache.json'
LOOK = 20
lm = ps.LM()


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for s in SYMS:
    if s in cache:
        continue
    day = defaultdict(lambda: {'n': 0, 'pol': 0.0, 'pos': 0, 'neg': 0})
    tok = None
    for _ in range(500):
        u = (f'https://data.alpaca.markets/v1beta1/news?symbols={s}'
             f'&start={START}T00:00:00Z&end={END}T23:59:00Z&limit=50')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        for a in d.get('news', []):
            txt = (a.get('headline') or '') + '. ' + (a.get('summary') or '')
            sc = lm.get_score(lm.tokenize(txt))
            dt = a['created_at'][:10]
            e = day[dt]
            e['n'] += 1
            e['pol'] += float(sc['Polarity'])
            e['pos'] += int(sc['Positive'])
            e['neg'] += int(sc['Negative'])
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
    cache[s] = {'day': {k: v for k, v in day.items()},
                'bars': [{'t': b['t'][:10], 'c': b['c']} for b in bb]}
    json.dump(cache, open(CACHE, 'w'))
    print(f'scored {s}: {sum(v["n"] for v in day.values())} articles, {len(bb)} bars')

print(f'\nsymbols scored: {len(cache)}')

ROWS = []
for s, D in cache.items():
    bars = D['bars']
    day = D['day']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    n = len(px)
    cnt = np.array([day.get(d, {}).get('n', 0) for d in dts], dtype=float)
    pol = np.array([day.get(d, {}).get('pol', 0.0) for d in dts], dtype=float)
    neg = np.array([day.get(d, {}).get('neg', 0) for d in dts], dtype=float)
    pos = np.array([day.get(d, {}).get('pos', 0) for d in dts], dtype=float)
    for i in range(LOOK + 6, n - 11):
        if cnt[i] < 1:
            continue
        w = cnt[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        avg_pol = pol[i] / cnt[i]                       # mean polarity per article that day
        # sentiment z-score against the same name's own 20-day history
        hist = [pol[k] / cnt[k] for k in range(i - LOOK, i) if cnt[k] >= 1]
        if len(hist) < 8:
            continue
        hm, hs = float(np.mean(hist)), float(np.std(hist, ddof=1))
        if hs <= 0:
            continue
        ROWS.append(dict(sym=s, date=dts[i], nz=(cnt[i] - mu) / sd,
                         pol=avg_pol, polz=(avg_pol - hm) / hs,
                         negfrac=neg[i] / max(pos[i] + neg[i], 1),
                         f1=math.log(px[i + 1] / px[i]),
                         f3=math.log(px[i + 3] / px[i]),
                         f5=math.log(px[i + 5] / px[i]),
                         a5=abs(math.log(px[i + 5] / px[i]))))
print(f'observations: {len(ROWS)}')
if len(ROWS) < 300:
    print('insufficient'); sys.exit()

print(f'\npolarity distribution: mean {np.mean([r["pol"] for r in ROWS]):+.3f}  '
      f'sd {np.std([r["pol"] for r in ROWS]):.3f}')


def buckets(key, labels_edges):
    out = []
    for lab, lo, hi in labels_edges:
        g = [r for r in ROWS if lo <= r[key] < hi]
        if len(g) >= 60:
            out.append((lab, g))
    return out


print('\n' + '=' * 100)
print('1. DOES MEASURED TONE PREDICT DIRECTION?  (LM polarity, raw)')
print('=' * 100)
base = {k: np.mean([r[k] for r in ROWS]) for k in ('f1', 'f3', 'f5')}
print(f'{"bucket":<22} {"n":>6} ' + ' '.join(f'{k:>10}{"t":>7}' for k in ('f1', 'f3', 'f5')))
for lab, g in buckets('pol', [('very negative', -1.01, -0.5), ('negative', -0.5, -0.05),
                              ('neutral', -0.05, 0.05), ('positive', 0.05, 0.5),
                              ('very positive', 0.5, 1.01)]):
    line = f'{lab:<22} {len(g):>6} '
    for k in ('f1', 'f3', 'f5'):
        v = np.array([r[k] for r in g])
        e = v.mean() - base[k]
        t = e / (v.std(ddof=1) / math.sqrt(len(v)))
        line += f'{e*100:>+10.3f}{t:>7.2f}'
    print(line)

print('\n' + '=' * 100)
print('2. SENTIMENT SURPRISE — tone relative to that name\'s own recent tone')
print('=' * 100)
print(f'{"bucket":<22} {"n":>6} ' + ' '.join(f'{k:>10}{"t":>7}' for k in ('f1', 'f3', 'f5')))
for lab, g in buckets('polz', [('z < -1.5', -99, -1.5), ('-1.5 to -0.5', -1.5, -0.5),
                               ('-0.5 to 0.5', -0.5, 0.5), ('0.5 to 1.5', 0.5, 1.5),
                               ('z > 1.5', 1.5, 99)]):
    line = f'{lab:<22} {len(g):>6} '
    for k in ('f1', 'f3', 'f5'):
        v = np.array([r[k] for r in g])
        e = v.mean() - base[k]
        t = e / (v.std(ddof=1) / math.sqrt(len(v)))
        line += f'{e*100:>+10.3f}{t:>7.2f}'
    print(line)

print('\n' + '=' * 100)
print('3. TONE x COVERAGE VOLUME — does sentiment matter more when coverage spikes?')
print('=' * 100)
print(f'{"cell":<28} {"n":>6} {"fwd1 excess":>13} {"t":>7} {"fwd5 excess":>13} {"t":>7}')
for nlab, nsel in (('quiet nz<1', lambda r: r['nz'] < 1), ('spike nz>=1', lambda r: r['nz'] >= 1)):
    for plab, psel in (('negative tone', lambda r: r['pol'] < -0.05),
                       ('positive tone', lambda r: r['pol'] > 0.05)):
        g = [r for r in ROWS if nsel(r) and psel(r)]
        if len(g) < 60:
            continue
        line = f'{nlab + " / " + plab:<28} {len(g):>6}'
        for k in ('f1', 'f5'):
            v = np.array([r[k] for r in g])
            e = v.mean() - base[k]
            t = e / (v.std(ddof=1) / math.sqrt(len(v)))
            line += f' {e*100:>+13.3f} {t:>7.2f}'
        print(line)

print('\n' + '=' * 100)
print('4. PER-SYMBOL SIGN CHECK — does negative tone predict lower forward returns?')
print('=' * 100)
print(f'{"sym":>7} {"n neg":>7} {"n pos":>7} {"pos-neg fwd5":>14} {"t":>7}')
bysym = defaultdict(list)
for r in ROWS:
    bysym[r['sym']].append(r)
pos_cnt = tot = 0
for s, rs in sorted(bysym.items()):
    ng = np.array([r['f5'] for r in rs if r['pol'] < -0.05])
    pg = np.array([r['f5'] for r in rs if r['pol'] > 0.05])
    if len(ng) < 25 or len(pg) < 25:
        print(f'{s:>7} {len(ng):>7} {len(pg):>7}  (thin)')
        continue
    d = pg.mean() - ng.mean()
    t = d / math.sqrt(pg.var(ddof=1) / len(pg) + ng.var(ddof=1) / len(ng))
    tot += 1
    pos_cnt += 1 if d > 0 else 0
    print(f'{s:>7} {len(ng):>7} {len(pg):>7} {d*100:>+14.3f} {t:>7.2f}')
print(f'\npositive tone beat negative tone in {pos_cnt} of {tot} symbols')

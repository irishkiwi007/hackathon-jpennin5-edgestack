"""ATTENTION-ONSET STRATEGY.

Idea: on names that are normally IGNORED by the wires, go long the moment the first article lands,
and exit at the close of the first day article volume falls below the prior day - i.e. ride the
attention wave up and leave when it crests.

Requires a universe of sparsely-covered names. The 10 cached symbols are all heavily covered
(SPY 18,505 articles; NVDA 10,506), so a fresh universe is pulled here.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
START, END = '2024-08-01', '2026-08-28'
CACHE = 'attncache.json'

UNIV = ['PCAR', 'CSX', 'EMR', 'ETN', 'PH', 'ZBH', 'BAX', 'HOLX', 'DGX', 'LH',
        'TSCO', 'ULTA', 'DPZ', 'YUM', 'DRI', 'NTRS', 'ZION', 'CMA', 'RF', 'KEY',
        'AKAM', 'JNPR', 'NTAP', 'WDC', 'STX', 'NUE', 'STLD', 'PKG', 'IP', 'AVY',
        'DVN', 'APA', 'HAL', 'AEE', 'CMS', 'LNT', 'NI', 'EXPD', 'JBHT', 'CHRW']


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for s in UNIV:
    if s in cache:
        continue
    cnt, tok = defaultdict(int), None
    for _ in range(400):
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
    if not bb:
        continue
    cache[s] = {'cnt': dict(cnt), 'bars': [{'t': b['t'][:10], 'o': b['o'], 'c': b['c']} for b in bb]}
    json.dump(cache, open(CACHE, 'w'))
print(f'universe cached: {len(cache)}')

print('\n' + '=' * 96)
print('COVERAGE PROFILE — which names are genuinely quiet?')
print('=' * 96)
print(f'{"sym":>7} {"sessions":>9} {"articles":>9} {"mean/day":>9} {"zero-days %":>12}')
prof = {}
for s, D in sorted(cache.items()):
    dts = [b['t'] for b in D['bars']]
    c = np.array([D['cnt'].get(d, 0) for d in dts], dtype=float)
    prof[s] = (len(dts), c.sum(), c.mean(), (c == 0).mean() * 100)
    print(f'{s:>7} {len(dts):>9} {int(c.sum()):>9} {c.mean():>9.2f} {(c==0).mean()*100:>11.1f}%')

QUIET = [s for s, p in prof.items() if p[2] < 2.0 and p[3] > 30]
print(f'\nQUIET universe (mean < 2 articles/day AND >30% zero-days): {len(QUIET)}')
print(' ', QUIET)
if len(QUIET) < 6:
    QUIET = sorted(prof, key=lambda s: prof[s][2])[:15]
    print(f'  relaxed to the 15 quietest: {QUIET}')

MAXHOLD = 15
TR, BASE = [], []
for s in QUIET:
    D = cache[s]
    dts = [b['t'] for b in D['bars']]
    o = np.array([b['o'] for b in D['bars']])
    c = np.array([b['c'] for b in D['bars']])
    cnt = np.array([D['cnt'].get(d, 0) for d in dts], dtype=float)
    n = len(dts)
    for i in range(5, n - MAXHOLD - 2):
        # "first article hits the wires": today has coverage, the prior 3 sessions had none
        if not (cnt[i] >= 1 and cnt[i - 1] == 0 and cnt[i - 2] == 0 and cnt[i - 3] == 0):
            continue
        # exit: first day volume falls below the prior day
        ex = None
        for k in range(i + 1, min(i + 1 + MAXHOLD, n)):
            if cnt[k] < cnt[k - 1]:
                ex = k
                break
        if ex is None:
            ex = min(i + MAXHOLD, n - 1)
        hold = ex - i
        r_close = math.log(c[ex] / c[i])          # enter at close of trigger day
        r_open = math.log(c[ex] / o[i + 1]) if i + 1 < n else np.nan   # enter next open
        TR.append(dict(sym=s, date=dts[i], hold=hold, artic=cnt[i],
                       r_close=r_close, r_open=r_open))
        # matched baseline: same symbol, same holding length, offset by 40 sessions
        b0 = i - 40
        if b0 > 5 and b0 + hold < n:
            BASE.append(math.log(c[b0 + hold] / c[b0]))

print('\n' + '=' * 96)
print('ATTENTION-ONSET TRADES')
print('=' * 96)
if len(TR) < 30:
    print(f'only {len(TR)} triggers — insufficient'); sys.exit()
rc = np.array([t['r_close'] for t in TR])
ro = np.array([t['r_open'] for t in TR if np.isfinite(t['r_open'])])
hd = np.array([t['hold'] for t in TR])
bs = np.array(BASE)
print(f'triggers: {len(TR)}   median hold {np.median(hd):.0f} sessions '
      f'(mean {hd.mean():.1f}, max {hd.max()})')
print()
print(f'{"variant":<28} {"n":>6} {"mean %":>9} {"median %":>10} {"t vs 0":>8} '
      f'{"win%":>7} {"vs baseline":>12}')


def show(v, lab, base=None):
    if len(v) < 20:
        return
    t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    extra = ''
    if base is not None and len(base) > 20:
        d = v.mean() - base.mean()
        td = d / math.sqrt(v.var(ddof=1) / len(v) + base.var(ddof=1) / len(base))
        extra = f'{d*100:>+7.3f}% t={td:>5.2f}'
    print(f'{lab:<28} {len(v):>6} {v.mean()*100:>8.3f}% {np.median(v)*100:>9.3f}% '
          f'{t:>8.2f} {(v>0).mean()*100:>6.1f}% {extra:>12}')


show(rc, 'enter trigger close', bs)
show(ro, 'enter next open', bs)
show(bs, 'matched baseline (same hold)')

print('\n' + '=' * 96)
print('DOES THE ATTENTION-PEAK EXIT BEAT A FIXED HOLD?')
print('=' * 96)
FIX = defaultdict(list)
for s in QUIET:
    D = cache[s]
    dts = [b['t'] for b in D['bars']]
    c = np.array([b['c'] for b in D['bars']])
    cnt = np.array([D['cnt'].get(d, 0) for d in dts], dtype=float)
    n = len(dts)
    for i in range(5, n - MAXHOLD - 2):
        if not (cnt[i] >= 1 and cnt[i - 1] == 0 and cnt[i - 2] == 0 and cnt[i - 3] == 0):
            continue
        for h in (1, 2, 3, 5, 10):
            if i + h < n:
                FIX[h].append(math.log(c[i + h] / c[i]))
print(f'{"exit rule":<28} {"n":>6} {"mean %":>9} {"t":>8} {"win%":>7}')
show(rc, 'attention-peak exit')
for h in (1, 2, 3, 5, 10):
    show(np.array(FIX[h]), f'fixed {h}-day hold')

print('\n' + '=' * 96)
print('PER-SYMBOL (attention-peak exit)')
print('=' * 96)
bysym = defaultdict(list)
for t in TR:
    bysym[t['sym']].append(t['r_close'])
print(f'{"sym":>7} {"n":>5} {"mean %":>9} {"t":>7}')
pos = tot = 0
for s, v in sorted(bysym.items()):
    v = np.array(v)
    if len(v) < 10:
        continue
    tt = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    tot += 1
    pos += 1 if v.mean() > 0 else 0
    print(f'{s:>7} {len(v):>5} {v.mean()*100:>8.3f}% {tt:>7.2f}')
print(f'\npositive in {pos} of {tot} symbols')

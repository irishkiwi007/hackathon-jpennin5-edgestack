"""VALID version of the lag test.

The previous run compared a 4-week option's implied vol against a 1-day realised move ratio.
Not commensurable. This matches horizons properly:

  enter k days AFTER the spike, buy the straddle expiring ~7 sessions later,
  compare the ACTUAL move over exactly that window to the straddle's IMPLIED move.

  ratio = actual / implied.   Spike-lag group vs control, at each lag k.

If IV collapses faster than realised after a spike, some lag k shows ratio > control -> buy there.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time, random
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
LOOK = 20
LAGS = [0, 1, 2, 3, 5]
random.seed(9)


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open('newscache.json'))
CAND = []
for s, D in cache.items():
    bars, cnt = D['bars'], D['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 25):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        CAND.append(dict(sym=s, i=i, date=dts[i], nz=(counts[i] - mu) / sd, dts=dts, px=px))

spikes = [c for c in CAND if c['nz'] >= 2.0]
ctrl = [c for c in CAND if abs(c['nz']) < 0.5]
random.shuffle(ctrl)
SAMPLE = [(c, 'spike') for c in spikes] + [(c, 'control') for c in ctrl[:len(spikes)]]
print(f'spike {len(spikes)}, control {len(SAMPLE)-len(spikes)}')


def occ(sym, exp, cp, k):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


def grid(spot):
    out = set()
    for inc in (1.0, 2.5, 5.0):
        b = round(spot / inc) * inc
        for k in (-1, 0, 1):
            if b + k * inc > 0:
                out.add(round(b + k * inc, 2))
    return sorted(out)


plan, need = [], set()
for c, grp in SAMPLE:
    dts, i, px = c['dts'], c['i'], c['px']
    for lag in LAGS:
        e = i + lag
        if e + 12 >= len(dts):
            continue
        j = None
        for k2 in range(e + 5, min(e + 12, len(dts))):
            if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
                j = k2
                break
        if j is None:
            continue
        exp = datetime.date.fromisoformat(dts[j])
        ks = grid(float(px[e]))
        plan.append(dict(c=c, grp=grp, lag=lag, e=e, j=j, exp=exp, ks=ks))
        for kk in ks:
            need.add(occ(c['sym'], exp, 'C', kk))
            need.add(occ(c['sym'], exp, 'P', kk))
need = sorted(need)
print(f'plan {len(plan)} obs, {len(need)} contracts')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(x[-15:-13]), int(x[-13:-11]), int(x[-11:-9]))
                   for x in ch})
    u = ('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
         f'&timeframe=1Day&start={(min(exps)-datetime.timedelta(days=30)).isoformat()}'
         f'&end={(max(exps)+datetime.timedelta(days=1)).isoformat()}&limit=10000')
    d = q(u)
    if d and d.get('bars'):
        for sy, rows in d['bars'].items():
            for r in rows:
                PX[(sy, r['t'][:10])] = r['c']
    if (b // B) % 50 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}\n')

R = defaultdict(lambda: defaultdict(list))
for p in plan:
    c = p['c']
    dts, px = c['dts'], c['px']
    d0 = dts[p['e']]
    best = None
    for kk in p['ks']:
        cc = PX.get((occ(c['sym'], p['exp'], 'C', kk), d0))
        pp = PX.get((occ(c['sym'], p['exp'], 'P', kk), d0))
        if not cc or not pp or cc <= 0 or pp <= 0:
            continue
        if best is None or abs(kk - px[p['e']]) < abs(best[0] - px[p['e']]):
            best = (kk, cc + pp)
    if best is None:
        continue
    strike, straddle = best
    if abs(strike - px[p['e']]) / px[p['e']] > 0.03:
        continue
    implied = straddle / px[p['e']]
    actual = abs(math.log(px[p['j']] / px[p['e']]))
    if implied <= 0.001:
        continue
    R[p['grp']][p['lag']].append(actual / implied)

print('=' * 96)
print('MATCHED-HORIZON TEST — enter k days after the spike, ~7-session straddle held to expiry')
print('=' * 96)
print(f'{"lag":>6} | {"spike n":>8} {"ratio":>8} | {"ctrl n":>8} {"ratio":>8} | '
      f'{"diff":>8} {"t":>7} {"reading":>22}')
for lag in LAGS:
    a = np.array(R['spike'][lag])
    b = np.array(R['control'][lag])
    if len(a) < 40 or len(b) < 40:
        print(f'{lag:>6} |  (thin)')
        continue
    d_ = a.mean() - b.mean()
    t = d_ / math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    rd = ('BUY favoured' if d_ > 0 and abs(t) > 1.9 else
          'SELL favoured' if d_ < 0 and abs(t) > 1.9 else 'no edge')
    print(f'{lag:>6} | {len(a):>8} {a.mean():>8.3f} | {len(b):>8} {b.mean():>8.3f} | '
          f'{d_:>+8.3f} {t:>7.2f} {rd:>22}')
print("""
ratio = actual move / implied move over the SAME window. Comparing spike vs control at each lag
isolates whether the coverage event leaves options mispriced at that point in time.""")

print('\n' + '=' * 96)
print('ABSOLUTE LEVEL — is either group mispriced against 1.0?')
print('=' * 96)
print(f'{"lag":>6} {"group":>9} {"n":>7} {"ratio":>8} {"t vs 1":>8}')
for lag in LAGS:
    for g in ('spike', 'control'):
        v = np.array(R[g][lag])
        if len(v) < 40:
            continue
        t = (v.mean() - 1) / (v.std(ddof=1) / math.sqrt(len(v)))
        print(f'{lag:>6} {g:>9} {len(v):>7} {v.mean():>8.3f} {t:>8.2f}')

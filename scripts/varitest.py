"""HIGH-POWER version of the "is the coverage spike priced?" test.

The previous test compared the straddle price to |S_T - K| - a single endpoint draw. That is the
noisiest possible estimator of realised vol, and the power audit showed it could only detect an
edge of ~7.6% while the effect under test was ~2%. Underpowered by ~17x. Its t=0.54 was a failure
to reject, not evidence of correct pricing.

Fix: estimate realised volatility from the WHOLE PATH (sum of squared daily returns over the
option's life). At T=7 sessions that is ~2.6x less noisy, and it is the same quantity a variance
swap settles on.

    implied vol  ~ (straddle / S) / (0.8 * sqrt(T/252))
    realised vol = sqrt( sum(r_i^2) / T ) * sqrt(252)
    ratio        = realised / implied
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
random.seed(3)


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
    for i in range(LOOK + 6, n - 14):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        CAND.append(dict(sym=s, i=i, date=dts[i], nz=(counts[i] - mu) / sd,
                         spot=float(px[i]), dts=dts, px=px))
spikes = [c for c in CAND if c['nz'] >= 1.0]
rest = [c for c in CAND if c['nz'] < 1.0]
random.shuffle(rest)
SAMPLE = spikes + rest[:len(spikes) * 2]
print(f'{len(spikes)} spike + {len(SAMPLE)-len(spikes)} control')


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
for c in SAMPLE:
    dts, i = c['dts'], c['i']
    j = None
    for k2 in range(i + 5, min(i + 13, len(dts))):
        if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
            j = k2
            break
    if j is None:
        continue
    exp = datetime.date.fromisoformat(dts[j])
    ks = grid(c['spot'])
    plan.append(dict(c=c, j=j, exp=exp, ks=ks))
    for kk in ks:
        need.add(occ(c['sym'], exp, 'C', kk))
        need.add(occ(c['sym'], exp, 'P', kk))
need = sorted(need)
print(f'{len(plan)} events, {len(need)} contracts')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(x[-15:-13]), int(x[-13:-11]), int(x[-11:-9]))
                   for x in ch})
    u = ('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
         f'&timeframe=1Day&start={(min(exps)-datetime.timedelta(days=25)).isoformat()}'
         f'&end={(max(exps)+datetime.timedelta(days=1)).isoformat()}&limit=10000')
    d = q(u)
    if d and d.get('bars'):
        for sy, rows in d['bars'].items():
            for r in rows:
                PX[(sy, r['t'][:10])] = r['c']
    if (b // B) % 60 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}\n')

ROWS = []
for p in plan:
    c = p['c']
    d0 = c['date']
    dts, px = c['dts'], c['px']
    best = None
    for kk in p['ks']:
        cc = PX.get((occ(c['sym'], p['exp'], 'C', kk), d0))
        pp = PX.get((occ(c['sym'], p['exp'], 'P', kk), d0))
        if not cc or not pp or cc <= 0 or pp <= 0:
            continue
        if best is None or abs(kk - c['spot']) < abs(best[0] - c['spot']):
            best = (kk, cc + pp)
    if best is None:
        continue
    strike, straddle = best
    if abs(strike - c['spot']) / c['spot'] > 0.03:
        continue
    T = p['j'] - c['i']
    if T < 4:
        continue
    iv = (straddle / c['spot']) / (0.8 * math.sqrt(T / 252))
    seg = px[c['i']:p['j'] + 1]
    r = np.diff(np.log(seg))
    if len(r) < 4:
        continue
    rv_path = math.sqrt(float(np.sum(r ** 2)) / len(r)) * math.sqrt(252)
    rv_end = abs(math.log(seg[-1] / seg[0])) / math.sqrt(T / 252)   # endpoint estimator
    if iv <= 0:
        continue
    ROWS.append(dict(sym=c['sym'], nz=c['nz'], iv=iv,
                     rv_path=rv_path, rv_end=rv_end,
                     ratio_path=rv_path / iv, ratio_end=rv_end / iv))
print(f'usable: {len(ROWS)}')

sp = [r for r in ROWS if r['nz'] >= 1.0]
ct = [r for r in ROWS if r['nz'] < 1.0]
print(f'  spike {len(sp)}  control {len(ct)}\n')

print('=' * 100)
print('NOISE COMPARISON — path estimator vs endpoint estimator')
print('=' * 100)
for key, lab in (('ratio_path', 'PATH (sum r^2)'), ('ratio_end', 'ENDPOINT (|S_T-S_0|)')):
    v = np.array([r[key] for r in ROWS])
    print(f'{lab:<26} mean {v.mean():.3f}   sd {v.std(ddof=1):.3f}')
a = np.array([r['ratio_path'] for r in sp])
b = np.array([r['ratio_path'] for r in ct])
se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
print(f'\npath estimator standard error: {se:.4f}  -> minimum detectable diff '
      f'{1.96*se:+.4f}')
ae = np.array([r['ratio_end'] for r in sp])
be = np.array([r['ratio_end'] for r in ct])
see = math.sqrt(ae.var(ddof=1) / len(ae) + be.var(ddof=1) / len(be))
print(f'endpoint estimator standard error: {see:.4f}  -> minimum detectable diff '
      f'{1.96*see:+.4f}')
print(f'power gain: {see/se:.2f}x')

print('\n' + '=' * 100)
print('IS THE SPIKE PRICED?  (path-based realised vol / implied vol)')
print('=' * 100)
print(f'{"bucket":<20} {"n":>6} {"implied vol":>12} {"realised vol":>13} {"ratio":>8} '
      f'{"t vs 1":>8}')
BUCK = [('control nz<1', ct),
        ('spike 1-2', [r for r in ROWS if 1 <= r['nz'] < 2]),
        ('spike 2-3', [r for r in ROWS if 2 <= r['nz'] < 3]),
        ('spike >3', [r for r in ROWS if r['nz'] >= 3])]
for lab, g in BUCK:
    if len(g) < 30:
        continue
    iv = np.array([r['iv'] for r in g])
    rv = np.array([r['rv_path'] for r in g])
    rt = np.array([r['ratio_path'] for r in g])
    t = (rt.mean() - 1) / (rt.std(ddof=1) / math.sqrt(len(rt)))
    print(f'{lab:<20} {len(g):>6} {iv.mean()*100:>11.1f}% {rv.mean()*100:>12.1f}% '
          f'{rt.mean():>8.3f} {t:>8.2f}')

d = a.mean() - b.mean()
t = d / se
print(f'\nspike vs control:  {a.mean():.3f} vs {b.mean():.3f}   diff {d:+.4f}   t = {t:.2f}')
print(f'  -> {"SIGNIFICANT" if abs(t) > 1.96 else "not significant"}')

print('\n' + '=' * 100)
print('PER-SYMBOL')
print('=' * 100)
print(f'{"sym":>7} {"n spike":>8} {"spike":>8} {"control":>9} {"diff":>9} {"t":>7}')
bs = defaultdict(list)
for r in ROWS:
    bs[r['sym']].append(r)
pos = tot = 0
for s_, rs in sorted(bs.items()):
    aa = np.array([r['ratio_path'] for r in rs if r['nz'] >= 1.0])
    bb = np.array([r['ratio_path'] for r in rs if r['nz'] < 1.0])
    if len(aa) < 20 or len(bb) < 20:
        continue
    dd = aa.mean() - bb.mean()
    tt = dd / math.sqrt(aa.var(ddof=1) / len(aa) + bb.var(ddof=1) / len(bb))
    tot += 1
    pos += 1 if dd > 0 else 0
    print(f'{s_:>7} {len(aa):>8} {aa.mean():>8.3f} {bb.mean():>9.3f} {dd:>+9.3f} {tt:>7.2f}')
print(f'\nspike exceeded control in {pos} of {tot} symbols')

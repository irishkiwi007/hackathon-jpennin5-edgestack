"""Black-Scholes inversion, as originally specified.

For every coverage-spike day and every control day: take the ATM option price, invert Black-Scholes
to recover implied volatility, and compare IV on spike days to IV on control days.

This is a price-vs-price comparison. No realised outcome enters it, so the path noise that made the
previous test underpowered is absent entirely.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time, random
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K_ = os.environ['ALPACA_API_KEY']
S_ = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K_, 'APCA-API-SECRET-KEY': S_}
LOOK = 20
RATE = 0.045
random.seed(1)


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(S, K, T, r, sig, cp):
    if sig <= 0 or T <= 0:
        return max(0.0, (S - K) if cp == 'C' else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if cp == 'C':
        return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)
    return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)


def implied_vol(price, S, K, T, r, cp):
    """Bisection - robust, no derivative, no convergence failures."""
    intrinsic = max(0.0, (S - K * math.exp(-r * T)) if cp == 'C'
                    else (K * math.exp(-r * T) - S))
    if price <= intrinsic + 1e-6:
        return None
    lo, hi = 1e-4, 5.0
    if bs(S, K, T, r, hi, cp) < price:
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if bs(S, K, T, r, mid, cp) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    return 0.5 * (lo + hi)


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
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        CAND.append(dict(sym=s, i=i, date=dts[i], nz=(counts[i] - mu) / sd,
                         spot=float(px[i]), rv=rv, dts=dts, px=px))
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
fails = 0
for p in plan:
    c = p['c']
    d0 = c['date']
    S = c['spot']
    T = (p['exp'] - datetime.date.fromisoformat(d0)).days / 365.0
    if T <= 0:
        continue
    best = None
    for kk in p['ks']:
        cc = PX.get((occ(c['sym'], p['exp'], 'C', kk), d0))
        pp = PX.get((occ(c['sym'], p['exp'], 'P', kk), d0))
        if not cc or not pp or cc <= 0 or pp <= 0:
            continue
        if best is None or abs(kk - S) < abs(best[0] - S):
            best = (kk, cc, pp)
    if best is None:
        continue
    Kst, cpx, ppx = best
    if abs(Kst - S) / S > 0.03:
        continue
    ivc = implied_vol(cpx, S, Kst, T, RATE, 'C')
    ivp = implied_vol(ppx, S, Kst, T, RATE, 'P')
    ivs = [v for v in (ivc, ivp) if v and 0.03 < v < 3.0]
    if not ivs:
        fails += 1
        continue
    iv = sum(ivs) / len(ivs)
    ROWS.append(dict(sym=c['sym'], nz=c['nz'], iv=iv, rv=c['rv'],
                     ivrv=iv / c['rv'] if c['rv'] > 0 else np.nan,
                     nlegs=len(ivs)))
print(f'inverted: {len(ROWS)}   inversion failures: {fails}')
sp = [r for r in ROWS if r['nz'] >= 1.0]
ct = [r for r in ROWS if r['nz'] < 1.0]
print(f'  spike {len(sp)}  control {len(ct)}\n')

print('=' * 100)
print('BLACK-SCHOLES IMPLIED VOL — spike days vs control days')
print('=' * 100)
print(f'{"bucket":<20} {"n":>6} {"BS implied vol":>15} {"trailing RV":>13} {"IV/RV":>8} '
      f'{"t vs control":>13}')
cb = np.array([r['iv'] for r in ct])
cr = np.array([r['ivrv'] for r in ct if np.isfinite(r['ivrv'])])
BUCK = [('control nz<1', ct),
        ('spike 1-2', [r for r in ROWS if 1 <= r['nz'] < 2]),
        ('spike 2-3', [r for r in ROWS if 2 <= r['nz'] < 3]),
        ('spike >3', [r for r in ROWS if r['nz'] >= 3])]
for lab, g in BUCK:
    if len(g) < 30:
        continue
    iv = np.array([r['iv'] for r in g])
    rv = np.array([r['rv'] for r in g])
    rr = np.array([r['ivrv'] for r in g if np.isfinite(r['ivrv'])])
    if lab.startswith('control'):
        tt = float('nan')
    else:
        tt = (iv.mean() - cb.mean()) / math.sqrt(iv.var(ddof=1) / len(iv)
                                                 + cb.var(ddof=1) / len(cb))
    print(f'{lab:<20} {len(g):>6} {iv.mean()*100:>14.2f}% {rv.mean()*100:>12.2f}% '
          f'{rr.mean():>8.3f} {tt:>13.2f}')

print('\n' + '=' * 100)
print('THE KEY NUMBER — IV/RV, which strips out the vol-level confound')
print('=' * 100)
a = np.array([r['ivrv'] for r in sp if np.isfinite(r['ivrv'])])
b = np.array([r['ivrv'] for r in ct if np.isfinite(r['ivrv'])])
d = a.mean() - b.mean()
se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
t = d / se
print(f'  spike   IV/RV {a.mean():.4f}  (n={len(a)})')
print(f'  control IV/RV {b.mean():.4f}  (n={len(b)})')
print(f'  difference {d:+.4f}   se {se:.4f}   t = {t:.2f}')
print(f'  minimum detectable difference at 95%: {1.96*se:+.4f}')
print()
if abs(t) > 1.96:
    if d > 0:
        print('  => the market RAISES IV on spike days beyond the vol level. It reacts.')
    else:
        print('  => the market LOWERS relative IV on spike days. It under-reacts.')
else:
    print('  => no significant difference in relative IV.')

print('\n' + '=' * 100)
print('PER-SYMBOL (IV/RV, spike vs control)')
print('=' * 100)
print(f'{"sym":>7} {"n spike":>8} {"spike":>8} {"control":>9} {"diff":>9} {"t":>7}')
bs_ = defaultdict(list)
for r in ROWS:
    bs_[r['sym']].append(r)
pos = tot = 0
for s2, rs in sorted(bs_.items()):
    aa = np.array([r['ivrv'] for r in rs if r['nz'] >= 1.0 and np.isfinite(r['ivrv'])])
    bb = np.array([r['ivrv'] for r in rs if r['nz'] < 1.0 and np.isfinite(r['ivrv'])])
    if len(aa) < 20 or len(bb) < 20:
        continue
    dd = aa.mean() - bb.mean()
    tt = dd / math.sqrt(aa.var(ddof=1) / len(aa) + bb.var(ddof=1) / len(bb))
    tot += 1
    pos += 1 if dd > 0 else 0
    print(f'{s2:>7} {len(aa):>8} {aa.mean():>8.3f} {bb.mean():>9.3f} {dd:>+9.3f} {tt:>7.2f}')
print(f'\nIV/RV higher on spike days in {pos} of {tot} symbols')

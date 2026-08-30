"""IS THE COVERAGE SPIKE ALREADY PRICED INTO OPTIONS?

Avoids Black-Scholes inversion entirely. The ATM straddle price IS the market's expected move:

    implied move = (ATM call + ATM put) / spot
    actual move  = |log(spot_at_expiry / spot_at_entry)|
    ratio        = actual / implied

If the ratio is HIGHER on coverage-spike days, the market underprices those days -> edge in buying.
If the ratio is the SAME, the spike is fully priced -> no edge, you pay for what you receive.

Model-free. No rate assumption, no vol surface, no inversion.
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
random.seed(11)


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open('newscache.json'))
print(f'symbols: {list(cache)}')

# ---- build the candidate day list (option data starts 2024-01) ----
CAND = []
for s, D in cache.items():
    bars = D['bars']
    cnt = D['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 12):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        nz = (counts[i] - mu) / sd
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        CAND.append(dict(sym=s, i=i, date=dts[i], nz=nz, spot=float(px[i]), rv=rv,
                         dts=dts, px=px))

spikes = [c for c in CAND if c['nz'] >= 1.0]
rest = [c for c in CAND if c['nz'] < 1.0]
random.shuffle(rest)
SAMPLE = spikes + rest[:len(spikes) * 2]
print(f'candidates: {len(spikes)} spike + {len(SAMPLE)-len(spikes)} control = {len(SAMPLE)}')


def occ(sym, exp, cp, strike):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(strike*1000)):08d}'


def strike_grid(spot):
    """Plausible listed strikes near the money across common increments."""
    out = set()
    for inc in (1.0, 2.5, 5.0):
        base = round(spot / inc) * inc
        for k in (-1, 0, 1):
            v = base + k * inc
            if v > 0:
                out.add(round(v, 2))
    return sorted(out)


# target expiry: nearest Friday at least 5 sessions ahead
need = defaultdict(set)
plan = []
for c in SAMPLE:
    dts, i = c['dts'], c['i']
    j = None
    for k in range(i + 5, min(i + 13, len(dts))):
        if datetime.date.fromisoformat(dts[k]).weekday() == 4:
            j = k
            break
    if j is None:
        continue
    exp = datetime.date.fromisoformat(dts[j])
    ks = strike_grid(c['spot'])
    syms = [occ(c['sym'], exp, cp, kk) for kk in ks for cp in ('C', 'P')]
    plan.append(dict(c=c, j=j, exp=exp, ks=ks, syms=syms))
    for sy in syms:
        need[(c['sym'], exp)].add(sy)

allsyms = sorted({s for v in need.values() for s in v})
print(f'plan: {len(plan)} day-observations, {len(allsyms)} contracts to fetch')

PX = {}
B = 40
for b in range(0, len(allsyms), B):
    ch = allsyms[b:b + B]
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
    if (b // B) % 40 == 0:
        print(f'  {b+len(ch)}/{len(allsyms)}  marks={len(PX)}')
print(f'marks cached: {len(PX)}')

ROWS = []
for p in plan:
    c = p['c']
    d0 = c['date']
    dts, px = c['dts'], c['px']
    best = None
    for kk in p['ks']:
        cp_ = PX.get((occ(c['sym'], p['exp'], 'C', kk), d0))
        pp_ = PX.get((occ(c['sym'], p['exp'], 'P', kk), d0))
        if cp_ is None or pp_ is None or cp_ <= 0 or pp_ <= 0:
            continue
        # prefer the strike closest to spot
        if best is None or abs(kk - c['spot']) < abs(best[0] - c['spot']):
            best = (kk, cp_ + pp_)
    if best is None:
        continue
    strike, straddle = best
    if abs(strike - c['spot']) / c['spot'] > 0.03:
        continue
    implied = straddle / c['spot']
    actual = abs(math.log(px[p['j']] / px[c['i']]))
    if implied <= 0.001:
        continue
    ROWS.append(dict(sym=c['sym'], date=d0, nz=c['nz'], rv=c['rv'],
                     implied=implied, actual=actual, ratio=actual / implied))

print(f'\nusable observations: {len(ROWS)}')
if len(ROWS) < 200:
    print('insufficient'); sys.exit()

sp = [r for r in ROWS if r['nz'] >= 1.0]
re_ = [r for r in ROWS if r['nz'] < 1.0]
print(f'  spike {len(sp)}   control {len(re_)}')

print('\n' + '=' * 100)
print('IS THE SPIKE PRICED? actual move vs the straddle the market charged')
print('=' * 100)
print(f'{"bucket":<20} {"n":>6} {"implied move":>14} {"actual move":>13} {"ratio":>8} {"t vs 1":>8}')


def show(lab, g):
    if len(g) < 30:
        print(f'{lab:<20} {len(g):>6}  (thin)')
        return None
    imp = np.array([r['implied'] for r in g])
    act = np.array([r['actual'] for r in g])
    rat = np.array([r['ratio'] for r in g])
    t = (rat.mean() - 1) / (rat.std(ddof=1) / math.sqrt(len(rat)))
    print(f'{lab:<20} {len(g):>6} {imp.mean()*100:>13.2f}% {act.mean()*100:>12.2f}% '
          f'{rat.mean():>8.3f} {t:>8.2f}')
    return rat


BUCK = [('control nz<1', [r for r in ROWS if r['nz'] < 1.0]),
        ('spike 1-2', [r for r in ROWS if 1.0 <= r['nz'] < 2.0]),
        ('spike 2-3', [r for r in ROWS if 2.0 <= r['nz'] < 3.0]),
        ('spike >3', [r for r in ROWS if r['nz'] >= 3.0])]
rats = {}
for lab, g in BUCK:
    rats[lab] = show(lab, g)

print("""
ratio > 1 : the actual move EXCEEDED what the straddle charged -> buying was profitable
ratio < 1 : the straddle was expensive relative to what happened -> selling was profitable""")

print('\n' + '=' * 100)
print('THE DECISIVE COMPARISON — spike vs control')
print('=' * 100)
a = np.array([r['ratio'] for r in ROWS if r['nz'] >= 1.0])
b = np.array([r['ratio'] for r in ROWS if r['nz'] < 1.0])
diff = a.mean() - b.mean()
t = diff / math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
print(f'  spike   ratio {a.mean():.3f}  (n={len(a)})')
print(f'  control ratio {b.mean():.3f}  (n={len(b)})')
print(f'  difference {diff:+.3f}   t = {t:.2f}')
print()
if abs(t) < 1.9:
    print('  => NO significant difference. The coverage spike is ALREADY PRICED into the straddle.')
    print('     The bigger move is real, but you pay for it in advance. No edge.')
elif diff > 0:
    print('  => Spike days deliver MORE move than the straddle charged. Edge in BUYING premium.')
else:
    print('  => Spike days deliver LESS move than charged. Edge in SELLING premium.')

print('\n' + '=' * 100)
print('PER-SYMBOL (the sign-consistency test)')
print('=' * 100)
print(f'{"sym":>7} {"n spike":>8} {"spike ratio":>12} {"control":>9} {"diff":>8} {"t":>7}')
bysym = defaultdict(list)
for r in ROWS:
    bysym[r['sym']].append(r)
pos = tot = 0
for s, rs in sorted(bysym.items()):
    a_ = np.array([r['ratio'] for r in rs if r['nz'] >= 1.0])
    b_ = np.array([r['ratio'] for r in rs if r['nz'] < 1.0])
    if len(a_) < 20 or len(b_) < 20:
        print(f'{s:>7} {len(a_):>8}  (thin)')
        continue
    d_ = a_.mean() - b_.mean()
    t_ = d_ / math.sqrt(a_.var(ddof=1) / len(a_) + b_.var(ddof=1) / len(b_))
    tot += 1
    pos += 1 if d_ > 0 else 0
    print(f'{s:>7} {len(a_):>8} {a_.mean():>12.3f} {b_.mean():>9.3f} {d_:>+8.3f} {t_:>7.2f}')
print(f'\nspike ratio exceeded control in {pos} of {tot} symbols')

"""Earnings, retried — the strategy was discarded on numbers I had already called unreliable.

Two errors in the previous rejection:

  1. A strike-selection bug was identified (mean credit $1,270 vs mean risk $1,075 implies a
     $2,345 width, impossible for the intended structure) and the results were disclaimed - then
     the strategy was rejected using those same results.
  2. Only 4-leg structures were tested, costing 8 leg-crossings (~$384). The leg-count insight
     applied elsewhere in this session - fewer legs, far less friction - was never applied here.

Both fixed:
  - strikes must land within a tolerance of target or the case is skipped
  - low-leg-count structures are tested alongside the 4-leg ones:

      cash-secured put     1 leg   2 crossings
      short strangle       2 legs  4 crossings   (cash/margin secured)
      put credit spread    2 legs  4 crossings   (defined risk)
      iron condor          4 legs  8 crossings

Method is unchanged and still non-circular: IMPLIED from today's live chain, REALIZED from that
name's own volume-located earnings history.
"""
import json, sys, io, math, time, datetime, urllib.request, urllib.parse, http.cookiejar
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
_src = open('earn_final.py', encoding='utf-8').read().split(
    "print()\nprint('=' * 100)\nprint('VALIDATION")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

# ---- realized histories, gated on locator validation -------------------------------------
HIST = {}
for s in sorted(BARS):
    loc = locate(s)
    if len(loc) < 8:
        continue
    rows = BARS[s]
    c = np.array([r['c'] for r in rows])
    v = np.array([r['v'] for r in rows])
    lr = np.zeros(len(c))
    lr[1:] = np.log(c[1:] / c[:-1])
    li = set(i for i, _, _ in loc)
    relv = np.array([v[i] / v[max(i - 60, 0):i].mean()
                     if i >= 60 and v[max(i - 60, 0):i].mean() > 0 else 0
                     for i in range(len(v))])
    thr = np.percentile([relv[i] for i in li if i < len(relv)], 25) if li else 2
    pool = [i for i in range(60, len(lr)) if i not in li and relv[i] >= thr]
    if len(pool) < 20:
        continue
    locmv = np.array([abs(lr[i]) * 100 for i in li if i > 0])
    hivol = np.array([abs(lr[i]) * 100 for i in pool])
    if hivol.mean() <= 0 or locmv.mean() / hivol.mean() < 1.2:
        continue
    HIST[s] = np.array([lr[i] * 100 for i in li if i > 0])
print('names passing the locator validation gate: {}'.format(len(HIST)))

today = datetime.date.today()
LIVE = {}
for s in sorted(HIST):
    if s not in ANCH or not ANCH[s][1]:
        continue
    nxt = ANCH[s][1]
    if not (0 < (nxt - today).days <= 45):
        continue
    spot = BARS[s][-1]['c']
    cc = aget('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
              '&expiration_date_lte={}&limit=900&status=active'.format(
                  PAPER, s, nxt.isoformat(),
                  (nxt + datetime.timedelta(days=10)).isoformat()))
    cand = [x for x in ((cc or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.78 * spot <= float(x['strike_price']) <= 1.22 * spot]
    if len(cand) < 6:
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
                snaps[kk] = (0.5 * (b_ + a_), 0.5 * (a_ - b_))
    chain, halfs = defaultdict(dict), defaultdict(dict)
    for x in sub:
        if x['symbol'] in snaps:
            mid, half = snaps[x['symbol']]
            chain[float(x['strike_price'])][x['type']] = mid
            halfs[float(x['strike_price'])][x['type']] = half
    atm = None
    for K, leg in chain.items():
        if 'call' in leg and 'put' in leg:
            if atm is None or abs(K - spot) < abs(atm[0] - spot):
                atm = (K, leg['call'] + leg['put'])
    if not atm or len(chain) < 6:
        continue
    LIVE[s] = dict(spot=spot, chain=chain, halfs=halfs,
                   implied=atm[1] / spot * 100, nxt=nxt)
print('names with a live chain bracketing earnings: {}'.format(len(LIVE)))


def strike_at(chain, spot, pct, typ, tol=0.015):
    """Nearest listed strike to spot*(1+pct), but only if within `tol` of target."""
    target = spot * (1 + pct)
    ks = [k for k in chain if typ in chain[k]]
    if not ks:
        return None
    k = min(ks, key=lambda z: abs(z - target))
    return k if abs(k - target) / spot <= tol else None


print()
print('=' * 108)
print('STRUCTURES BY LEG COUNT — same edge, different friction')
print('=' * 108)
RES = defaultdict(list)
SKIP = defaultdict(int)
for s, L in sorted(LIVE.items()):
    spot, chain, halfs = L['spot'], L['chain'], L['halfs']
    imp = L['implied'] / 100.0
    moves = HIST[s]

    def h(k, typ):
        return halfs.get(k, {}).get(typ, 0.0) * 100

    # 1 leg: cash-secured put, short at -1x implied
    kp = strike_at(chain, spot, -imp, 'put')
    if kp:
        cred = chain[kp]['put'] * 100
        fr = 2 * h(kp, 'put')
        for mv in moves:
            ST = spot * (1 + mv / 100)
            pnl = cred - max(0.0, (kp - ST) * 100) - fr
            RES['1 leg  cash-secured put'].append((s, pnl, kp * 100 - cred, fr))
    else:
        SKIP['1 leg  cash-secured put'] += 1

    # 2 legs: short strangle at +/-1x implied
    kc = strike_at(chain, spot, imp, 'call')
    if kp and kc:
        cred = (chain[kp]['put'] + chain[kc]['call']) * 100
        fr = 2 * (h(kp, 'put') + h(kc, 'call'))
        for mv in moves:
            ST = spot * (1 + mv / 100)
            loss = max(0.0, (kp - ST) * 100) + max(0.0, (ST - kc) * 100)
            RES['2 legs short strangle'].append((s, cred - loss - fr, kp * 100 - cred, fr))
    else:
        SKIP['2 legs short strangle'] += 1

    # 2 legs: put credit spread, short -1x implied / long -2x
    kpl = strike_at(chain, spot, -2 * imp, 'put')
    if kp and kpl and kpl < kp:
        cred = (chain[kp]['put'] - chain[kpl]['put']) * 100
        width = (kp - kpl) * 100
        fr = 2 * (h(kp, 'put') + h(kpl, 'put'))
        if cred > 0:
            for mv in moves:
                ST = spot * (1 + mv / 100)
                loss = min(max(0.0, (kp - ST) * 100), width)
                RES['2 legs put credit spread'].append((s, cred - loss - fr, width - cred, fr))
    else:
        SKIP['2 legs put credit spread'] += 1

    # 4 legs: iron condor +/-1x short, +/-2x wings
    kcl = strike_at(chain, spot, 2 * imp, 'call')
    if kp and kc and kpl and kcl and kpl < kp and kcl > kc:
        cred = ((chain[kp]['put'] - chain[kpl]['put'])
                + (chain[kc]['call'] - chain[kcl]['call'])) * 100
        width = max((kp - kpl), (kcl - kc)) * 100
        fr = 2 * (h(kp, 'put') + h(kpl, 'put') + h(kc, 'call') + h(kcl, 'call'))
        if cred > 0 and width > cred:
            for mv in moves:
                ST = spot * (1 + mv / 100)
                loss = min(max(0.0, (kp - ST) * 100), width) + \
                    min(max(0.0, (ST - kc) * 100), width)
                RES['4 legs iron condor'].append((s, cred - loss - fr, width - cred, fr))
    else:
        SKIP['4 legs iron condor'] += 1

print('{:<28} {:>6} {:>9} {:>9} {:>9} {:>8} {:>9} {:>10} {:>9}'.format(
    'structure', 'n', 'mean $', 'median $', 'fric $', 'win%', 'ret/risk', 'worst $', 't'))
for k in ('1 leg  cash-secured put', '2 legs short strangle',
          '2 legs put credit spread', '4 legs iron condor'):
    v = RES.get(k) or []
    if len(v) < 30:
        print('{:<28} {:>6}   (too few; {} names skipped on strike tolerance)'.format(
            k, len(v), SKIP.get(k, 0)))
        continue
    a = np.array([x[1] for x in v])
    rk = float(np.mean([x[2] for x in v]))
    fr = float(np.mean([x[3] for x in v]))
    t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
    print('{:<28} {:>6} {:>9.0f} {:>9.0f} {:>9.0f} {:>7.1f}% {:>8.2f}% {:>10.0f} {:>9.2f}'.format(
        k, len(a), a.mean(), float(np.median(a)), fr, 100 * (a > 0).mean(),
        100 * a.mean() / rk if rk > 0 else 0, a.min(), t))

print()
print('=' * 108)
print('FRICTION AS A SHARE OF THE CREDIT COLLECTED')
print('=' * 108)
for k in ('1 leg  cash-secured put', '2 legs short strangle',
          '2 legs put credit spread', '4 legs iron condor'):
    v = RES.get(k) or []
    if len(v) < 30:
        continue
    fr = float(np.mean([x[3] for x in v]))
    a = np.array([x[1] for x in v])
    gross = a.mean() + fr
    print('  {:<28} friction ${:<7.0f} gross ${:<8.0f} net ${:<8.0f} '
          'friction eats {:.0f}% of gross'.format(
              k, fr, gross, a.mean(), 100 * fr / gross if gross > 0 else float('nan')))

best = None
for k, v in RES.items():
    if len(v) < 30:
        continue
    a = np.array([x[1] for x in v])
    if best is None or a.mean() > best[1]:
        best = (k, a.mean(), v)
if best:
    k, m, v = best
    a = np.array([x[1] for x in v])
    print()
    print('=' * 108)
    print('BEST: {}'.format(k))
    print('=' * 108)
    print('  mean {:+.0f} $/contract   tail: p1 {:+.0f}  p5 {:+.0f}  worst {:+.0f}'.format(
        a.mean(), float(np.percentile(a, 1)), float(np.percentile(a, 5)), a.min()))
    byn = defaultdict(list)
    for x in v:
        byn[x[0]].append(x[1])
    print('  {:<8} {:>5} {:>11} {:>9}'.format('sym', 'n', 'mean $', 'win%'))
    for sym in sorted(byn):
        arr = np.array(byn[sym])
        print('  {:<8} {:>5} {:>11.0f} {:>8.1f}%'.format(
            sym, len(arr), arr.mean(), 100 * (arr > 0).mean()))

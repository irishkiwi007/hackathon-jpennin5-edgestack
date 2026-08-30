"""Does the earnings overpricing survive as an actual TRADE, including the tail?

Knowing options imply ~1.33x the realized move is not the same as knowing the trade makes money.
A short-premium earnings structure has a fat left tail: most quarters pay the credit, occasional
surprises blow through the wings.

The test is deliberately NON-CIRCULAR:

    IMPLIED  -> today's live straddle for names reporting soon (the market's price)
    REALIZED -> that same name's own historical earnings moves, located by volume

Neither side is derived from the other, so a positive result is not baked in.

Structures tested, all defined-risk and Alpaca-legal (<=4 legs, every short covered):
  - IRON CONDOR: short strikes at +/- k x implied move, long wings further out
  - IRON BUTTERFLY: short strikes ATM, long wings at +/- implied move

Friction charged on all 8 leg-crossings at live-measured per-leg rates.
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

RATE = 0.045


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsp(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - s * math.sqrt(T))) - S * ncdf(-d1)


def bsc(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d1 - s * math.sqrt(T))


# ---- historical realized earnings moves, SIGNED, per name -------------------------------
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
    # validation gate: located days must move more than volume-matched non-located days
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
        continue                       # locator not trustworthy for this name - skip it
    signed = np.array([lr[i] * 100 for i in li if i > 0])
    ordn = np.array([lr[i] for i in range(1, len(lr)) if i not in li])
    HIST[s] = dict(moves=signed, ordinary=float(ordn.std(ddof=1) * 100), n=len(signed))
print('names passing the locator validation gate: {}'.format(len(HIST)))

# ---- live implied moves and per-leg friction --------------------------------------------
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
            if x.get('tradable') and 0.80 * spot <= float(x['strike_price']) <= 1.20 * spot]
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
    chain = defaultdict(dict)
    halfs = []
    for x in sub:
        if x['symbol'] in snaps:
            mid, half = snaps[x['symbol']]
            chain[float(x['strike_price'])][x['type']] = mid
            halfs.append(half * 100)
    atm = None
    for K, leg in chain.items():
        if 'call' in leg and 'put' in leg:
            if atm is None or abs(K - spot) < abs(atm[0] - spot):
                atm = (K, leg['call'] + leg['put'])
    if not atm or len(chain) < 6:
        continue
    LIVE[s] = dict(spot=spot, exp=exps[0], chain=chain, straddle=atm[1],
                   implied=atm[1] / spot * 100, half=float(np.median(halfs)),
                   dte=(datetime.date.fromisoformat(exps[0]) - today).days)
print('names with a live quotable chain bracketing earnings: {}'.format(len(LIVE)))


def nearest(chain, target, typ):
    ks = [k for k in chain if typ in chain[k]]
    return min(ks, key=lambda z: abs(z - target)) if ks else None


print()
print('=' * 104)
print('SIMULATED EARNINGS TRADES — live implied pricing vs each name own realized history')
print('=' * 104)
RESULTS = defaultdict(list)
for s, L in sorted(LIVE.items()):
    spot, chain = L['spot'], L['chain']
    imp = L['implied']
    h = HIST[s]
    for structure, short_k, wing_k in (('condor 1.0x/2.0x', 1.0, 2.0),
                                       ('condor 1.25x/2.5x', 1.25, 2.5),
                                       ('butterfly 0/1.5x', 0.0, 1.5)):
        ksp = nearest(chain, spot * (1 - short_k * imp / 100), 'put')
        ksc = nearest(chain, spot * (1 + short_k * imp / 100), 'call')
        klp = nearest(chain, spot * (1 - wing_k * imp / 100), 'put')
        klc = nearest(chain, spot * (1 + wing_k * imp / 100), 'call')
        if None in (ksp, ksc, klp, klc) or klp >= ksp or klc <= ksc:
            continue
        credit = ((chain[ksp]['put'] - chain[klp]['put'])
                  + (chain[ksc]['call'] - chain[klc]['call'])) * 100
        if credit <= 0:
            continue
        width = max(ksp - klp, klc - ksc) * 100
        risk = width - credit
        if risk <= 0:
            continue
        fric = 8 * L['half']
        for mv in h['moves']:
            ST = spot * (1 + mv / 100.0)
            pay = credit
            if ST < ksp:
                pay -= min((ksp - ST) * 100, ksp * 100 - klp * 100)
            elif ST > ksc:
                pay -= min((ST - ksc) * 100, klc * 100 - ksc * 100)
            RESULTS[structure].append(dict(sym=s, pnl=pay - fric, risk=risk,
                                           credit=credit, fric=fric, mv=mv))

print('{:<20} {:>7} {:>10} {:>10} {:>9} {:>8} {:>10} {:>11}'.format(
    'structure', 'n', 'mean $', 'median $', 'ret/risk', 'win%', 'worst $', 'p5 $'))
for k, v in RESULTS.items():
    if len(v) < 40:
        continue
    a = np.array([x['pnl'] for x in v])
    rk = float(np.mean([x['risk'] for x in v]))
    t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
    print('{:<20} {:>7} {:>10.0f} {:>10.0f} {:>8.2f}% {:>7.1f}% {:>10.0f} {:>11.0f}'.format(
        k, len(a), a.mean(), float(np.median(a)), 100 * a.mean() / rk,
        100 * (a > 0).mean(), a.min(), float(np.percentile(a, 5))))

best = None
for k, v in RESULTS.items():
    if len(v) < 40:
        continue
    a = np.array([x['pnl'] for x in v])
    if best is None or a.mean() > best[1]:
        best = (k, a.mean(), v)

if best:
    k, m, v = best
    a = np.array([x['pnl'] for x in v])
    rk = float(np.mean([x['risk'] for x in v]))
    t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
    print()
    print('=' * 104)
    print('BEST STRUCTURE: {}'.format(k))
    print('=' * 104)
    print('  n={}  mean {:+.0f} $/contract  t={:.2f}  win {:.1f}%'.format(
        len(a), a.mean(), t, 100 * (a > 0).mean()))
    print('  mean credit ${:.0f}   mean risk ${:.0f}   friction ${:.0f}'.format(
        float(np.mean([x['credit'] for x in v])), rk,
        float(np.mean([x['fric'] for x in v]))))
    print('  return on risk {:.2f}%'.format(100 * a.mean() / rk))
    print()
    print('  TAIL:')
    for p in (1, 5, 10, 25, 50, 75, 90):
        print('    p{:<3} {:+9.0f}'.format(p, float(np.percentile(a, p))))
    print('    worst {:+.0f}   ({:.1f}x the mean)'.format(a.min(), abs(a.min() / a.mean())))
    losers = a[a < 0]
    if len(losers):
        print('    losing trades {:.0f}%   mean loss {:+.0f}   win/loss size {:.2f}'.format(
            100 * len(losers) / len(a), losers.mean(),
            abs(a[a > 0].mean() / losers.mean()) if (a > 0).any() else 0))
    print()
    print('  PER NAME:')
    byn = defaultdict(list)
    for x in v:
        byn[x['sym']].append(x['pnl'])
    print('  {:<8} {:>6} {:>11} {:>10} {:>10}'.format('sym', 'n', 'mean $', 'win%', 'worst'))
    for sym in sorted(byn):
        arr = np.array(byn[sym])
        print('  {:<8} {:>6} {:>11.0f} {:>9.1f}% {:>10.0f}'.format(
            sym, len(arr), arr.mean(), 100 * (arr > 0).mean(), arr.min()))

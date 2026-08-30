"""Can a second position raise the hit rate of the drift-aligned core without killing its alpha?

Core problem: call debit 780/785 wins ~26% of the time. Over ~4 bets that is a 30% chance of
zero winners. Positive EV does not rescue a sample that thin.

Search: every pair (core, complement) at several weights, scored across all regime partitions.
A pair is only interesting if combined alpha stays positive in EVERY regime AND the hit rate
improves materially.

LIMITATION: calendars/diagonals are excluded. Their payoff cannot be computed from the
underlying's terminal price alone - the back leg still carries time value at the front expiry,
which needs a vol model. Noted rather than faked.
"""
import json, math, os, subprocess, sys, io, datetime, itertools

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
EXP, H = '2026-09-04', 5


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:200])
    return json.loads(r.stdout)


bars, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day', '--start', '2016-01-01',
         '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    bars += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break
bars.sort(key=lambda x: x['t'])
c = [x['c'] for x in bars]
dates = [datetime.date.fromisoformat(x['t'][:10]) for x in bars]
spot, N = c[-1], len(bars)
daily = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
rv20 = [None] * N
for i in range(21, N):
    r = daily[i - 20:i]
    m = sum(r) / len(r)
    rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
rv_now = rv20[-1]

REG = {'pre16-19': (datetime.date(2016, 1, 1), datetime.date(2019, 12, 31)),
       'cov20-22': (datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
       'rec23-26': (datetime.date(2023, 1, 1), datetime.date(2026, 12, 31)),
       'ALL': (datetime.date(2016, 1, 1), datetime.date(2026, 12, 31))}
SAMP = {k: [c[i + H] / c[i] - 1 for i in range(21, N - H) if lo <= dates[i] <= hi]
        for k, (lo, hi) in REG.items()}
SAMP['lowvol'] = [c[i + H] / c[i] - 1 for i in range(21, N - H)
                  if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25]
KEYS = list(SAMP)
NEUT = {k: [r - sum(v) / len(v) for r in v] for k, v in SAMP.items()}

snaps, tok = {}, None
while True:
    a = ['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
         '--expiration-date', EXP, '--limit', '500',
         '--strike-price-gte', str(int(spot * 0.90)), '--strike-price-lte', str(int(spot * 1.10))]
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    snaps.update(d.get('snapshots') or {})
    tok = d.get('next_page_token')
    if not tok:
        break
raw = {'C': {}, 'P': {}}
for k, v in snaps.items():
    q = v.get('latestQuote') or {}
    bp, ap = q.get('bp'), q.get('ap')
    dl = (v.get('greeks') or {}).get('delta')
    vg = (v.get('greeks') or {}).get('vega')
    if not bp or not ap or ap <= bp or dl is None:
        continue
    raw['C' if k[-9] == 'C' else 'P'][int(k[-8:]) / 1000] = {
        'bid': bp, 'ask': ap, 'mid': (bp + ap) / 2, 'delta': dl, 'vega': vg or 0.0}

bad = {'C': set(), 'P': set()}
for kind in ('C', 'P'):
    ks = sorted(raw[kind])
    for i in range(len(ks) - 1):
        a1, a2 = raw[kind][ks[i]], raw[kind][ks[i + 1]]
        if kind == 'C':
            v = a1['mid'] < a2['mid'] or abs(a1['delta']) < abs(a2['delta']) or a1['ask'] <= a2['bid']
        else:
            v = a1['mid'] > a2['mid'] or abs(a1['delta']) > abs(a2['delta']) or a2['ask'] <= a1['bid']
        if v:
            bad[kind].add(ks[i]); bad[kind].add(ks[i + 1])
C, P = {}, {}
for kind, dst in (('C', C), ('P', P)):
    for K, r in raw[kind].items():
        if K in bad[kind] or (r['ask'] - r['bid']) / r['mid'] > 0.35:
            continue
        dst[K] = r
print(f'spot {spot}  clean chain {len(C)}C/{len(P)}P')


def cost_of(legs):
    t = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        if K not in s:
            return None
        t += q * (s[K]['ask'] if q > 0 else s[K]['bid'])
    return t


def greeks(legs):
    d = v = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        d += q * s[K]['delta']
        v += q * s[K]['vega']
    return d, v


def pnl_series(legs, sample):
    cost = cost_of(legs)
    if cost is None:
        return None
    out = []
    for r in sample:
        S = spot * (1 + r)
        out.append(sum(q * (max(S - K, 0) if t == 'C' else max(K - S, 0))
                       for q, t, K in legs) - cost)
    return out


ckeys, pkeys = sorted(C), sorted(P)
nearC = lambda x: min(ckeys, key=lambda k: abs(k - x))
nearP = lambda x: min(pkeys, key=lambda k: abs(k - x))
near = nearP
c1 = nearC(spot * 1.014)
c2 = min([k for k in ckeys if k > c1], key=lambda k: abs(k - spot * 1.020), default=None)
if c2 is None:
    print('no upper call strike'); sys.exit()
CORE = [(1, 'C', c1), (-1, 'C', c2)]
if cost_of(CORE) is None:
    print('core unavailable'); sys.exit()
cd, cv = greeks(CORE)
print(f'CORE = call debit {CORE[0][2]:.0f}/{CORE[1][2]:.0f}  '
      f'cost ${cost_of(CORE)*100:.0f}  netD {cd:+.3f}  netVega {cv:+.3f}')

comps = []
for pct in (-0.03, -0.025, -0.02, -0.015, -0.01, 0.005, 0.01, 0.015):
    K = nearP(spot * (1 + pct))
    for w in (3, 5, 10):
        if K in P and K - w in P:
            comps.append((f'put credit {K:.0f}/{K-w:.0f}', [(-1, 'P', K), (1, 'P', K - w)]))
            comps.append((f'put debit {K:.0f}/{K-w:.0f}', [(1, 'P', K), (-1, 'P', K - w)]))
        Kc = nearC(spot * (1 + pct))
        if Kc in C and Kc + w in C:
            comps.append((f'call credit {Kc:.0f}/{Kc+w:.0f}', [(-1, 'C', Kc), (1, 'C', Kc + w)]))
for off in (0.010, 0.015, 0.020, 0.025):
    sp, sc = nearP(spot * (1 - off)), nearC(spot * (1 + off))
    for w in (5, 10):
        if sp - w in P and sc + w in C and sp in P and sc in C and sp != sc:
            comps.append((f'iron condor +/-{off*100:.1f}% w{w}',
                          [(1, 'P', sp - w), (-1, 'P', sp), (-1, 'C', sc), (1, 'C', sc + w)]))

base = {}
for k in KEYS:
    s = pnl_series(CORE, SAMP[k])
    sn = pnl_series(CORE, NEUT[k])
    base[k] = dict(ev=sum(s) / len(s), alpha=sum(sn) / len(sn),
                   risk=-min(s), win=sum(1 for x in s if x > 0) / len(s))
print(f'\nCORE alone (ALL): EV ${base["ALL"]["ev"]*100:.1f}  alpha ${base["ALL"]["alpha"]*100:.1f}  '
      f'risk ${base["ALL"]["risk"]*100:.0f}  WIN {base["ALL"]["win"]*100:.1f}%')
print(f'  worst-regime alpha/risk: {min(base[k]["alpha"]/base[k]["risk"] for k in KEYS):.3f}')
p0 = base['ALL']['win']
print(f'  P(zero winners in 4 bets) = {(1-p0)**4*100:.1f}%')

print('\n' + '=' * 104)
print('PAIRS: core + w x complement, scored on every regime')
print('=' * 104)
results = []
for name, legs in comps:
    if cost_of(legs) is None:
        continue
    gd, gv = greeks(legs)
    for w in (0.5, 1.0, 1.5, 2.0):
        per, ok = {}, True
        for k in KEYS:
            a = pnl_series(CORE, SAMP[k])
            b = pnl_series(legs, SAMP[k])
            an = pnl_series(CORE, NEUT[k])
            bn = pnl_series(legs, NEUT[k])
            if not a or not b:
                ok = False; break
            comb = [x + w * y for x, y in zip(a, b)]
            combn = [x + w * y for x, y in zip(an, bn)]
            risk = -min(comb)
            if risk <= 0.01:
                ok = False; break
            per[k] = dict(ev=sum(comb) / len(comb), alpha=sum(combn) / len(combn),
                          risk=risk, win=sum(1 for x in comb if x > 0) / len(comb))
        if not ok:
            continue
        worst_ar = min(per[k]['alpha'] / per[k]['risk'] for k in KEYS)
        if worst_ar <= 0:
            continue
        results.append((name, w, gv, per, worst_ar))

results.sort(key=lambda r: -r[3]['ALL']['win'])
print(f'{"complement":<26} {"w":>4} {"cVega":>7} {"WIN%":>7} {"vs core":>8} {"EV$":>8} '
      f'{"alpha$":>8} {"risk$":>7} {"worstA/R":>9} {"P(0 in 4)":>10}')
shown = 0
for name, w, gv, per, war in results:
    a = per['ALL']
    if shown >= 14:
        break
    shown += 1
    print(f'{name:<26} {w:>4.1f} {gv:>7.2f} {a["win"]*100:>6.1f}% '
          f'{(a["win"]-p0)*100:>+7.1f} {a["ev"]*100:>8.1f} {a["alpha"]*100:>8.1f} '
          f'{a["risk"]*100:>7.0f} {war:>9.3f} {(1-a["win"])**4*100:>9.1f}%')

print(f'\npairs keeping positive alpha in EVERY regime: {len(results)}')
if results:
    best = max(results, key=lambda r: r[3]['ALL']['win'])
    print(f'\nhighest hit-rate survivor: {best[0]} at weight {best[1]}')
    for k in KEYS:
        p = best[3][k]
        print(f'   {k:<9} EV ${p["ev"]*100:>7.1f}  alpha ${p["alpha"]*100:>7.1f}  '
              f'a/r {p["alpha"]/p["risk"]:>6.3f}  win {p["win"]*100:>5.1f}%')

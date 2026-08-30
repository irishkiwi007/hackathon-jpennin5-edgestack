"""Persist the regime-stable positive-alpha set, then split it by whether it works WITH or
AGAINST the market's natural drift.

Also closes the filter gap found earlier: a strike rejected for a wide spread previously skipped
the monotonicity check against its neighbours. Now monotonicity is checked on the FULL raw ladder
before any strike is dropped, so a bad quote poisons its neighbours as it should.
"""
import json, math, os, subprocess, sys, io, datetime

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

REG = {'pre-covid 16-19': (datetime.date(2016, 1, 1), datetime.date(2019, 12, 31)),
       'covid/inf 20-22': (datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
       'recent    23-26': (datetime.date(2023, 1, 1), datetime.date(2026, 12, 31)),
       'ALL       16-26': (datetime.date(2016, 1, 1), datetime.date(2026, 12, 31))}
SAMP = {k: [c[i + H] / c[i] - 1 for i in range(21, N - H) if lo <= dates[i] <= hi]
        for k, (lo, hi) in REG.items()}
SAMP['lowvol cond'] = [c[i + H] / c[i] - 1 for i in range(21, N - H)
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
    iv = v.get('impliedVolatility')
    if not bp or not ap or ap <= bp or dl is None or not iv:
        continue
    raw['C' if k[-9] == 'C' else 'P'][int(k[-8:]) / 1000] = {
        'bid': bp, 'ask': ap, 'mid': (bp + ap) / 2, 'delta': dl, 'iv': iv}

# ---- monotonicity checked on the FULL ladder first (closes the earlier gap) ----
bad = {'C': set(), 'P': set()}
for kind in ('C', 'P'):
    ks = sorted(raw[kind])
    for i in range(len(ks) - 1):
        lo_k, hi_k = ks[i], ks[i + 1]
        a1, a2 = raw[kind][lo_k], raw[kind][hi_k]
        if kind == 'C':
            viol = a1['mid'] < a2['mid'] or abs(a1['delta']) < abs(a2['delta']) \
                or a1['ask'] <= a2['bid']
        else:
            viol = a1['mid'] > a2['mid'] or abs(a1['delta']) > abs(a2['delta']) \
                or a2['ask'] <= a1['bid']
        if viol:
            bad[kind].add(lo_k)
            bad[kind].add(hi_k)

MAXSPR = 0.35
C, P = {}, {}
drop_spread = 0
for kind, dst in (('C', C), ('P', P)):
    for K, r in raw[kind].items():
        if K in bad[kind]:
            continue
        if (r['ask'] - r['bid']) / r['mid'] > MAXSPR:
            drop_spread += 1
            continue
        dst[K] = r

print(f'spot {spot}   expiry {EXP}')
print(f'raw {len(raw["C"])}C/{len(raw["P"])}P  ->  dropped {len(bad["C"])}C/{len(bad["P"])}P for '
      f'monotonicity or arb, {drop_spread} for wide spread')
print(f'CLEAN {len(C)}C/{len(P)}P')


def cost_of(legs):
    t = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        if K not in s:
            return None
        t += q * (s[K]['ask'] if q > 0 else s[K]['bid'])
    return t


def ndelta(legs):
    t = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        if K not in s:
            return None
        t += q * s[K]['delta']
    return t


def payoff(S, legs):
    return sum(q * (max(S - K, 0) if t == 'C' else max(K - S, 0)) for q, t, K in legs)


def stats(legs, sample):
    cost = cost_of(legs)
    if cost is None:
        return None
    pnl = [payoff(spot * (1 + r), legs) - cost for r in sample]
    ev = sum(pnl) / len(pnl)
    risk = -min(pnl)
    if risk <= 0.01:
        return None
    return ev, risk, sum(1 for x in pnl if x > 0) / len(pnl)


strikes = sorted(set(C) & set(P))
near = lambda x: min(strikes, key=lambda k: abs(k - x))
cands = []
for off in (0.010, 0.015, 0.020, 0.025):
    sp, sc = near(spot * (1 - off)), near(spot * (1 + off))
    for w in (3, 5, 8, 10):
        if sp - w in P and sc + w in C and sp in P and sc in C and sp != sc:
            cands.append((f'iron condor +/-{off*100:.1f}% w{w}',
                          [(1, 'P', sp - w), (-1, 'P', sp), (-1, 'C', sc), (1, 'C', sc + w)]))
atm = near(spot)
for w in (5, 8, 10, 15):
    if atm - w in P and atm + w in C and atm in P and atm in C:
        cands.append((f'iron butterfly w{w}',
                      [(1, 'P', atm - w), (-1, 'P', atm), (-1, 'C', atm), (1, 'C', atm + w)]))
for pct in (-0.03, -0.02, -0.015, -0.01, -0.005, 0.005, 0.01, 0.015, 0.02):
    K = near(spot * (1 + pct))
    for w in (3, 5, 10):
        if K in P and K - w in P:
            cands.append((f'put credit {K:.0f}/{K-w:.0f}', [(-1, 'P', K), (1, 'P', K - w)]))
            cands.append((f'put debit {K:.0f}/{K-w:.0f}', [(1, 'P', K), (-1, 'P', K - w)]))
        if K in C and K + w in C:
            cands.append((f'call credit {K:.0f}/{K+w:.0f}', [(-1, 'C', K), (1, 'C', K + w)]))
            cands.append((f'call debit {K:.0f}/{K+w:.0f}', [(1, 'C', K), (-1, 'C', K + w)]))

seen, rows = set(), []
for name, legs in cands:
    key = tuple(sorted(legs))
    if key in seen:
        continue
    seen.add(key)
    nd = ndelta(legs)
    per, ok = {}, True
    for k in KEYS:
        a1, a2 = stats(legs, SAMP[k]), stats(legs, NEUT[k])
        if not a1 or not a2:
            ok = False
            break
        per[k] = dict(ev=a1[0], risk=a1[1], win=a1[2], alpha=a2[0], ar=a2[0] / a1[1])
    if ok:
        rows.append(dict(name=name, legs=legs, nd=nd, per=per,
                         worst=min(per[k]['ar'] for k in KEYS)))

surv = sorted([r for r in rows if r['worst'] > 0], key=lambda r: -r['worst'])
print(f'\nregime-stable positive-alpha survivors: {len(surv)} of {len(rows)}\n')
print(f'{"structure":<26} {"netΔ":>7} {"worst α/r":>10} {"alpha$":>9} {"totEV$":>9} '
      f'{"drift":>9} {"win%":>7}')
print('-' * 82)
for r in surv:
    a = r['per']['ALL       16-26']
    drift = a['ev'] - a['alpha']
    print(f'{r["name"]:<26} {r["nd"]:>7.3f} {r["worst"]:>10.3f} {a["alpha"]*100:>9.1f} '
          f'{a["ev"]*100:>9.1f} {drift*100:>+9.1f} {a["win"]*100:>6.1f}%')

WITH = [r for r in surv if r['nd'] >= 0]
AGAINST = [r for r in surv if r['nd'] < 0]
print(f'\n{"="*82}')
print(f'WORKS WITH THE DRIFT (net delta >= 0): {len(WITH)}')
for r in WITH:
    a = r['per']['ALL       16-26']
    print(f'   {r["name"]:<26} netΔ {r["nd"]:+.3f}  alpha ${a["alpha"]*100:>6.1f}  '
          f'totEV ${a["ev"]*100:>6.1f}  (drift {a["ev"]-a["alpha"]:+.2f} x100)')
print(f'\nFIGHTS THE DRIFT (net delta < 0): {len(AGAINST)}')
for r in AGAINST:
    a = r['per']['ALL       16-26']
    print(f'   {r["name"]:<26} netΔ {r["nd"]:+.3f}  alpha ${a["alpha"]*100:>6.1f}  '
          f'totEV ${a["ev"]*100:>6.1f}  (drift {(a["ev"]-a["alpha"])*100:+.1f})')

out = 'alpha_survivors.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump([{k: v for k, v in r.items() if k != 'legs'} | {'legs': r['legs']}
               for r in surv], f, indent=2, default=str)
print(f'\npersisted {len(surv)} survivors -> {out}')

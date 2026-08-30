"""EV decomposition: total EV (drift included, the realistic measure) split into
  - beta component : what a delta-matched underlying position earns from drift alone
  - alpha residual : options-specific edge left over

Drift is NOT removed. It is real and the strategy will experience it. The question is whether a
structure is paying us for options skill or just for market exposure we could buy more cheaply.
"""
import json, math, os, subprocess, sys, io

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
c = [x['c'] for x in bars]
spot = c[-1]

rv20 = [None] * len(c)
for i in range(21, len(c)):
    r = [math.log(c[j] / c[j - 1]) for j in range(i - 19, i + 1)]
    m = sum(r) / len(r)
    rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
rv_now = rv20[-1]

uncond, lowvol = [], []
for i in range(21, len(c) - H):
    ret = c[i + H] / c[i] - 1
    uncond.append(ret)
    if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25:
        lowvol.append(ret)

mu_u = sum(uncond) / len(uncond)
mu_l = sum(lowvol) / len(lowvol)
print(f'spot {spot}   H={H}d   samples: lowvol {len(lowvol)}, all {len(uncond)}')
print(f'mean {H}-day return  — unconditional {mu_u*100:+.3f}%   low-vol-conditioned {mu_l*100:+.3f}%')
print(f'annualised drift     — unconditional {((1+mu_u)**(252/H)-1)*100:+.1f}%   '
      f'low-vol {((1+mu_l)**(252/H)-1)*100:+.1f}%')
print()
print('Note: conditioning on low vol SELECTS bull-market periods (the leverage effect is real,')
print('but the low-vol drift is the more aggressive assumption). Both are reported below.')

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

C, P = {}, {}
for k, v in snaps.items():
    q = v.get('latestQuote') or {}
    bp, ap = q.get('bp'), q.get('ap')
    dl = (v.get('greeks') or {}).get('delta')
    if not bp or not ap or ap <= bp:
        continue
    (C if k[-9] == 'C' else P)[int(k[-8:]) / 1000] = {'bid': bp, 'ask': ap, 'delta': dl or 0.0}


def cost_of(legs):
    t = 0.0
    for qty, kind, K in legs:
        side = C if kind == 'C' else P
        if K not in side:
            return None
        t += qty * (side[K]['ask'] if qty > 0 else side[K]['bid'])
    return t


def net_delta(legs):
    t = 0.0
    for qty, kind, K in legs:
        side = C if kind == 'C' else P
        if K not in side:
            return None
        t += qty * side[K]['delta']
    return t


def payoff(S, legs):
    return sum(q * (max(S - K, 0) if t == 'C' else max(K - S, 0)) for q, t, K in legs)


def decompose(legs, sample, mu):
    cost = cost_of(legs)
    nd = net_delta(legs)
    if cost is None or nd is None:
        return None
    pnl = [payoff(spot * (1 + r), legs) - cost for r in sample]
    ev = sum(pnl) / len(pnl)
    risk = -min(pnl)
    if risk <= 0.01:
        return None
    # what a delta-matched underlying position earns from drift alone, same notional convention
    beta_ev = nd * spot * mu
    return dict(ev=ev, risk=risk, nd=nd, beta=beta_ev, alpha=ev - beta_ev,
                win=sum(1 for x in pnl if x > 0) / len(pnl))


strikes = sorted(set(C) & set(P))


def near(x):
    return min(strikes, key=lambda k: abs(k - x))


cands = []
for pct in (-0.05, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03):
    K = near(spot * (1 + pct))
    for w in (3, 5, 10):
        if K in P and K - w in P:
            cands.append((f'put credit {K:.0f}/{K-w:.0f}', [(-1, 'P', K), (1, 'P', K - w)]))
            cands.append((f'put debit  {K:.0f}/{K-w:.0f}', [(1, 'P', K), (-1, 'P', K - w)]))
        if K in C and K + w in C:
            cands.append((f'call credit {K:.0f}/{K+w:.0f}', [(-1, 'C', K), (1, 'C', K + w)]))
            cands.append((f'call debit  {K:.0f}/{K+w:.0f}', [(1, 'C', K), (-1, 'C', K + w)]))
for wing in (5, 10):
    for off in (0.015, 0.02, 0.03):
        sp, sc = near(spot * (1 - off)), near(spot * (1 + off))
        if sp - wing in P and sc + wing in C and sp in P and sc in C:
            cands.append((f'iron condor {sp:.0f}/{sc:.0f} w{wing}',
                          [(1, 'P', sp - wing), (-1, 'P', sp), (-1, 'C', sc), (1, 'C', sc + wing)]))

for label, sample, mu in (('LOW-VOL CONDITIONED (drift included)', lowvol, mu_l),
                          ('UNCONDITIONAL (drift included)', uncond, mu_u)):
    print('\n' + '=' * 96)
    print(label)
    print('=' * 96)
    rows = []
    for name, legs in cands:
        r = decompose(legs, sample, mu)
        if r:
            rows.append((name, r))
    rows.sort(key=lambda x: -x[1]['ev'])
    print(f'{"structure":<28} {"net Δ":>7} {"total EV":>9} {"= beta":>9} {"+ alpha":>9} '
          f'{"alpha/risk":>11} {"win%":>7}')
    for name, r in rows[:12]:
        print(f'{name:<28} {r["nd"]:>7.2f} {r["ev"]*100:>9.1f} {r["beta"]*100:>9.1f} '
              f'{r["alpha"]*100:>9.1f} {r["alpha"]/r["risk"]:>11.3f} {r["win"]*100:>6.1f}%')

    pos = [x for x in rows if x[1]['alpha'] > 0]
    print(f'\n  structures with POSITIVE alpha (edge beyond beta): {len(pos)} of {len(rows)}')
    for name, r in sorted(pos, key=lambda x: -x[1]["alpha"] / x[1]["risk"])[:5]:
        print(f'    {name:<28} alpha ${r["alpha"]*100:>7.1f}  alpha/risk {r["alpha"]/r["risk"]:>6.3f}')

print('\nAll figures $ per 1-lot. Delta-matched benchmark uses INITIAL net delta (first-order).')
print('total EV is what you expect to earn. alpha is the part not explained by market exposure.')

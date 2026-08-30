"""Pure alpha search: structures that capture edge with minimal beta contamination,
tested for stability across distinct market regimes.

The user's criterion: if the alpha is present for a decade across different market structures,
it has a chance to show up in four days. Sub-period stability is the test that matters.
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
spot = c[-1]
N = len(c)

daily = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
rv20 = [None] * N
for i in range(21, N):
    r = daily[i - 20:i]
    m = sum(r) / len(r)
    rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
rv_now = rv20[-1]

REGIMES = {
    'pre-covid  2016-2019': (datetime.date(2016, 1, 1), datetime.date(2019, 12, 31)),
    'covid/infl 2020-2022': (datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
    'recent     2023-2026': (datetime.date(2023, 1, 1), datetime.date(2026, 12, 31)),
    'ALL        2016-2026': (datetime.date(2016, 1, 1), datetime.date(2026, 12, 31)),
    'lowvol-cond (all yrs)': None,
}


def sample_for(key):
    out = []
    for i in range(21, N - H):
        ret = c[i + H] / c[i] - 1
        if key == 'lowvol-cond (all yrs)':
            if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25:
                out.append(ret)
        else:
            lo, hi = REGIMES[key]
            if lo <= dates[i] <= hi:
                out.append(ret)
    return out


SAMPLES = {k: sample_for(k) for k in REGIMES}
for k, v in SAMPLES.items():
    mu = sum(v) / len(v)
    print(f'{k:<24} n={len(v):>5}  mean {H}d ret {mu*100:+.3f}%  '
          f'ann drift {((1+mu)**(252/H)-1)*100:+6.1f}%')

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
    bp, ap = q.get('bid' if False else 'bp'), q.get('ap')
    dl = (v.get('greeks') or {}).get('delta')
    if not bp or not ap or ap <= bp:
        continue
    (C if k[-9] == 'C' else P)[int(k[-8:]) / 1000] = {'bid': bp, 'ask': ap, 'delta': dl or 0.0}


def cost_of(legs):
    tt = 0.0
    for q, kind, K in legs:
        side = C if kind == 'C' else P
        if K not in side:
            return None
        tt += q * (side[K]['ask'] if q > 0 else side[K]['bid'])
    return tt


def net_delta(legs):
    tt = 0.0
    for q, kind, K in legs:
        side = C if kind == 'C' else P
        if K not in side:
            return None
        tt += q * side[K]['delta']
    return tt


def payoff(S, legs):
    return sum(q * (max(S - K, 0) if t == 'C' else max(K - S, 0)) for q, t, K in legs)


def score(legs, sample):
    cost = cost_of(legs)
    nd = net_delta(legs)
    if cost is None or nd is None:
        return None
    mu = sum(sample) / len(sample)
    pnl = [payoff(spot * (1 + r), legs) - cost for r in sample]
    ev = sum(pnl) / len(pnl)
    risk = -min(pnl)
    if risk <= 0.01:
        return None
    beta = nd * spot * mu
    return dict(ev=ev, alpha=ev - beta, risk=risk, nd=nd,
                ar=(ev - beta) / risk, win=sum(1 for x in pnl if x > 0) / len(pnl))


strikes = sorted(set(C) & set(P))


def near(x):
    return min(strikes, key=lambda k: abs(k - x))


cands = []
for off in (0.010, 0.015, 0.020, 0.025, 0.030):
    sp, sc = near(spot * (1 - off)), near(spot * (1 + off))
    for wing in (3, 5, 8, 10):
        if sp - wing in P and sc + wing in C and sp in P and sc in C:
            cands.append((f'iron condor -{off*100:.1f}%/+{off*100:.1f}% w{wing}',
                          [(1, 'P', sp - wing), (-1, 'P', sp), (-1, 'C', sc), (1, 'C', sc + wing)]))
atm = near(spot)
for wing in (5, 8, 10, 15):
    if atm - wing in P and atm + wing in C and atm in P and atm in C:
        cands.append((f'iron butterfly ATM w{wing}',
                      [(1, 'P', atm - wing), (-1, 'P', atm), (-1, 'C', atm), (1, 'C', atm + wing)]))
for pct in (-0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03):
    K = near(spot * (1 + pct))
    for w in (3, 5, 10):
        if K in P and K - w in P:
            cands.append((f'put credit {K:.0f}/{K-w:.0f}', [(-1, 'P', K), (1, 'P', K - w)]))
            cands.append((f'put debit  {K:.0f}/{K-w:.0f}', [(1, 'P', K), (-1, 'P', K - w)]))
        if K in C and K + w in C:
            cands.append((f'call credit {K:.0f}/{K+w:.0f}', [(-1, 'C', K), (1, 'C', K + w)]))
            cands.append((f'call debit  {K:.0f}/{K+w:.0f}', [(1, 'C', K), (-1, 'C', K + w)]))

DN = 0.12
print('\n' + '=' * 104)
print(f'NEAR-DELTA-NEUTRAL STRUCTURES (|net delta| < {DN}) — alpha/risk BY REGIME')
print('=' * 104)
keys = list(REGIMES)
rows = []
for name, legs in cands:
    nd = net_delta(legs)
    if nd is None or abs(nd) >= DN:
        continue
    per = {}
    ok = True
    for k in keys:
        r = score(legs, SAMPLES[k])
        if not r:
            ok = False
            break
        per[k] = r
    if ok:
        rows.append((name, nd, per))

rows.sort(key=lambda x: -min(x[2][k]['ar'] for k in keys))
hdr = f'{"structure":<30} {"netΔ":>6} ' + ' '.join(f'{k.split()[0][:9]:>10}' for k in keys)
print(hdr)
print('-' * len(hdr))
for name, nd, per in rows[:16]:
    cells = ' '.join(f'{per[k]["ar"]:>10.3f}' for k in keys)
    print(f'{name:<30} {nd:>6.2f} {cells}')

print(f'\n{"structure":<30} {"worst-regime alpha/risk":>24} {"ALL alpha $":>13} {"win% (ALL)":>12}')
survivors = [r for r in rows if min(r[2][k]['ar'] for k in keys) > 0]
for name, nd, per in survivors[:10]:
    worst = min(per[k]['ar'] for k in keys)
    a = per['ALL        2016-2026']
    print(f'{name:<30} {worst:>24.3f} {a["alpha"]*100:>12.1f} {a["win"]*100:>11.1f}%')
print(f'\nstructures with POSITIVE alpha in EVERY regime: {len(survivors)} of {len(rows)}')

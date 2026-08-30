"""Rank every legal defined-risk structure on the live chain by expected value under the
empirical distribution of SPY returns.

Selection is on historical edge over 2,679 sessions. Deployment length is irrelevant here.
"""
import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
EXP = '2026-09-04'
H = 5          # trading days from 2026-08-28 close to 2026-09-04 close
WIDTHS = (3, 5, 10)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:200])
    return json.loads(r.stdout)


# ---------- history ----------
bars, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day',
         '--start', '2016-01-01', '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
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


def demean(s):
    m = sum(s) / len(s)
    return [x - m for x in s]


SAMPLES = {
    'lowvol+drift': lowvol,
    'lowvol,no drift': demean(lowvol),
    'all+drift': uncond,
}
print(f'spot {spot}   RV20 {rv_now*100:.2f}%   H={H} trading days')
print(f'samples: lowvol {len(lowvol)}, unconditional {len(uncond)}')

# ---------- chain ----------
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
    if not bp or not ap or ap <= 0 or ap <= bp:
        continue
    strike = int(k[-8:]) / 1000
    rec = {'bid': bp, 'ask': ap, 'mid': (bp + ap) / 2}
    (C if k[-9] == 'C' else P)[strike] = rec
print(f'chain {EXP}: {len(C)} calls, {len(P)} puts two-sided\n')


def payoff_at(S, legs):
    """legs = [(qty, 'C'/'P', strike)]; qty>0 long. Returns intrinsic value of the package."""
    tot = 0.0
    for qty, kind, K in legs:
        intr = max(S - K, 0) if kind == 'C' else max(K - S, 0)
        tot += qty * intr
    return tot


def build(legs, conservative=True):
    """Net cost to open. Longs pay ask, shorts receive bid (conservative fill assumption)."""
    cost = 0.0
    for qty, kind, K in legs:
        side = C if kind == 'C' else P
        if K not in side:
            return None
        px = side[K]['ask'] if qty > 0 else side[K]['bid']
        if not conservative:
            px = side[K]['mid']
        cost += qty * px
    return cost


def evaluate(legs, sample):
    cost = build(legs)
    if cost is None:
        return None
    ST = [spot * (1 + r) for r in sample]
    pnl = [payoff_at(S, legs) - cost for S in ST]
    ev = sum(pnl) / len(pnl)
    worst = min(pnl)
    best = max(pnl)
    risk = -worst
    if risk <= 0.01:
        return None
    wins = sum(1 for x in pnl if x > 0) / len(pnl)
    return dict(cost=cost, ev=ev, risk=risk, best=best, win=wins, ev_risk=ev / risk)


cands = []
strikes = sorted(set(C) & set(P))


def near(target):
    return min(strikes, key=lambda k: abs(k - target)) if strikes else None


for pct in (-0.06, -0.05, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03, 0.04):
    K = near(spot * (1 + pct))
    if K is None:
        continue
    for w in WIDTHS:
        Klo, Khi = K - w, K + w
        # put credit spread: short K, long K-w
        if K in P and Klo in P:
            cands.append((f'put credit {K:.0f}/{Klo:.0f}', [(-1, 'P', K), (1, 'P', Klo)]))
        # put debit spread: long K, short K-w   (net short the far, expensive put)
        if K in P and Klo in P:
            cands.append((f'put debit  {K:.0f}/{Klo:.0f}', [(1, 'P', K), (-1, 'P', Klo)]))
        # call credit spread: short K, long K+w
        if K in C and Khi in C:
            cands.append((f'call credit {K:.0f}/{Khi:.0f}', [(-1, 'C', K), (1, 'C', Khi)]))
        # call debit
        if K in C and Khi in C:
            cands.append((f'call debit  {K:.0f}/{Khi:.0f}', [(1, 'C', K), (-1, 'C', Khi)]))

# iron condors, and broken-wing put butterflies
for wing in (5, 10):
    for off in (0.015, 0.02, 0.03):
        sp, sc = near(spot * (1 - off)), near(spot * (1 + off))
        if sp and sc and (sp - wing) in P and (sc + wing) in C and sp in P and sc in C:
            cands.append((f'iron condor {sp-wing:.0f}/{sp:.0f}/{sc:.0f}/{sc+wing:.0f}',
                          [(1, 'P', sp - wing), (-1, 'P', sp), (-1, 'C', sc), (1, 'C', sc + wing)]))
for body_off in (0.02, 0.025, 0.03):
    body = near(spot * (1 - body_off))
    for up in (5, 8):
        for dn in (10, 15, 20):
            if body and (body + up) in P and (body - dn) in P:
                cands.append((f'BW put fly {body-dn:.0f}/{body:.0f}x2/{body+up:.0f}',
                              [(1, 'P', body + up), (-2, 'P', body), (1, 'P', body - dn)]))

print('=' * 100)
print('RANKED BY EV/RISK  —  low-vol-conditioned sample WITH drift (the realistic measure)')
print('  fills assumed conservative: longs pay ask, shorts receive bid')
print('=' * 100)
scored = []
for name, legs in cands:
    r = evaluate(legs, SAMPLES['lowvol+drift'])
    if r:
        scored.append((name, legs, r))
scored.sort(key=lambda x: -x[2]['ev_risk'])

print(f'{"structure":<34} {"cost":>8} {"EV":>8} {"risk":>8} {"EV/risk":>8} {"win%":>7}')
for name, legs, r in scored[:14]:
    print(f'{name:<34} {r["cost"]*100:>8.0f} {r["ev"]*100:>8.1f} {r["risk"]*100:>8.0f} '
          f'{r["ev_risk"]:>8.3f} {r["win"]*100:>6.1f}%')

print('\n(cost/EV/risk in $ per 1-lot, 100 multiplier)')

print('\n' + '=' * 100)
print('ROBUSTNESS OF THE TOP CANDIDATES ACROSS SAMPLE DEFINITIONS')
print('=' * 100)
print(f'{"structure":<34} ' + ' '.join(f'{k:>17}' for k in SAMPLES))
for name, legs, _ in scored[:8]:
    cells = []
    for key, samp in SAMPLES.items():
        r = evaluate(legs, samp)
        cells.append(f'{r["ev_risk"]:>17.3f}' if r else f'{"-":>17}')
    print(f'{name:<34} ' + ' '.join(cells))
print('\na structure is only interesting if EV/risk stays positive in every column')

"""Pure-alpha search, with two fixes.

FIX 1 - arbitrage-consistency filter on the chain.
  The indicative feed is internally inconsistent in the far wings (non-monotone prices and
  deltas across strikes). Any "edge" found there is a data error. Reject violating strikes.

FIX 2 - correct alpha definition.
  total EV = expected P&L under the real-world distribution, drift INCLUDED. That is what
             the strategy earns and the user is right that it belongs.
  alpha    = EV under the drift-neutralised distribution. This is the part not explained by
             market exposure. Using a linear initial-delta benchmark (previous version) badly
             understates the drift sensitivity of CONVEX structures, which is why far-OTM call
             spreads showed fake alpha.
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

REG = {
    'pre-covid 16-19': (datetime.date(2016, 1, 1), datetime.date(2019, 12, 31)),
    'covid/inf 20-22': (datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
    'recent    23-26': (datetime.date(2023, 1, 1), datetime.date(2026, 12, 31)),
    'ALL       16-26': (datetime.date(2016, 1, 1), datetime.date(2026, 12, 31)),
}
SAMP = {}
for k, (lo, hi) in REG.items():
    SAMP[k] = [c[i + H] / c[i] - 1 for i in range(21, N - H) if lo <= dates[i] <= hi]
SAMP['lowvol cond'] = [c[i + H] / c[i] - 1 for i in range(21, N - H)
                       if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25]
KEYS = list(SAMP)
NEUTRAL = {k: [r - sum(v) / len(v) for r in v] for k, v in SAMP.items()}

# ---------- chain + consistency filter ----------
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
    if not bp or not ap or ap <= bp or not dl or not iv:
        continue
    raw['C' if k[-9] == 'C' else 'P'][int(k[-8:]) / 1000] = {
        'bid': bp, 'ask': ap, 'mid': (bp + ap) / 2, 'delta': dl, 'iv': iv}

MAXSPR = 0.35     # relative bid-ask cap
rej = {'spread': 0, 'monotone_px': 0, 'monotone_delta': 0, 'arb': 0}
clean = {'C': {}, 'P': {}}
for kind in ('C', 'P'):
    ks = sorted(raw[kind])
    for i, K in enumerate(ks):
        r = raw[kind][K]
        if (r['ask'] - r['bid']) / r['mid'] > MAXSPR:
            rej['spread'] += 1
            continue
        ok = True
        # calls must decrease in strike; puts must increase
        for j in (i - 1, i + 1):
            if 0 <= j < len(ks):
                K2, r2 = ks[j], raw[kind][ks[j]]
                lower = K < K2
                if kind == 'C':
                    if lower and r['mid'] < r2['mid']:
                        ok = False; rej['monotone_px'] += 1; break
                    if lower and abs(r['delta']) < abs(r2['delta']):
                        ok = False; rej['monotone_delta'] += 1; break
                else:
                    if lower and r['mid'] > r2['mid']:
                        ok = False; rej['monotone_px'] += 1; break
        if not ok:
            continue
        clean[kind][K] = r

# vertical-spread arbitrage: adjacent strikes must not allow a free credit
for kind in ('C', 'P'):
    ks = sorted(clean[kind])
    drop = set()
    for i in range(len(ks) - 1):
        lo, hi = ks[i], ks[i + 1]
        if kind == 'C':
            if clean[kind][lo]['ask'] <= clean[kind][hi]['bid']:
                drop.add(lo); drop.add(hi); rej['arb'] += 1
        else:
            if clean[kind][hi]['ask'] <= clean[kind][lo]['bid']:
                drop.add(lo); drop.add(hi); rej['arb'] += 1
    for K in drop:
        clean[kind].pop(K, None)

print(f'spot {spot}   expiry {EXP}')
print(f'raw strikes: {len(raw["C"])} calls, {len(raw["P"])} puts')
print(f'rejected -> wide spread {rej["spread"]}, non-monotone price {rej["monotone_px"]}, '
      f'non-monotone delta {rej["monotone_delta"]}, vertical arb {rej["arb"]}')
print(f'CLEAN: {len(clean["C"])} calls, {len(clean["P"])} puts')
C, P = clean['C'], clean['P']
for k, v in SAMP.items():
    mu = sum(v) / len(v)
    print(f'  {k:<16} n={len(v):>5}  ann drift {((1+mu)**(252/H)-1)*100:+6.1f}%')


def cost_of(legs):
    t = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        if K not in s:
            return None
        t += q * (s[K]['ask'] if q > 0 else s[K]['bid'])
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
if not strikes:
    print('\nno strikes survive on both sides — cannot build structures'); sys.exit()


def near(x):
    return min(strikes, key=lambda k: abs(k - x))


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
            cands.append((f'put debit  {K:.0f}/{K-w:.0f}', [(1, 'P', K), (-1, 'P', K - w)]))
        if K in C and K + w in C:
            cands.append((f'call credit {K:.0f}/{K+w:.0f}', [(-1, 'C', K), (1, 'C', K + w)]))
            cands.append((f'call debit  {K:.0f}/{K+w:.0f}', [(1, 'C', K), (-1, 'C', K + w)]))

seen, rows = set(), []
for name, legs in cands:
    key = tuple(sorted(legs))
    if key in seen:
        continue
    seen.add(key)
    per = {}
    ok = True
    for k in KEYS:
        a1 = stats(legs, SAMP[k])
        a2 = stats(legs, NEUTRAL[k])
        if not a1 or not a2:
            ok = False; break
        per[k] = dict(ev=a1[0], risk=a1[1], win=a1[2], alpha=a2[0], ar=a2[0] / a1[1])
    if ok:
        rows.append((name, per))

rows.sort(key=lambda x: -min(x[1][k]['ar'] for k in KEYS))
print('\n' + '=' * 100)
print('ALPHA/RISK BY REGIME  (alpha = EV under drift-neutralised distribution)')
print('=' * 100)
hdr = f'{"structure":<28} ' + ' '.join(f'{k[:11]:>13}' for k in KEYS)
print(hdr); print('-' * len(hdr))
for name, per in rows[:14]:
    print(f'{name:<28} ' + ' '.join(f'{per[k]["ar"]:>13.3f}' for k in KEYS))

surv = [r for r in rows if min(r[1][k]['ar'] for k in KEYS) > 0]
print(f'\npositive alpha in EVERY regime: {len(surv)} of {len(rows)}')
if surv:
    print(f'\n{"structure":<28} {"worst α/risk":>13} {"total EV$":>11} {"alpha$":>9} '
          f'{"risk$":>8} {"win%":>7}')
    for name, per in surv[:10]:
        a = per['ALL       16-26']
        print(f'{name:<28} {min(per[k]["ar"] for k in KEYS):>13.3f} {a["ev"]*100:>11.1f} '
              f'{a["alpha"]*100:>9.1f} {a["risk"]*100:>8.0f} {a["win"]*100:>6.1f}%')
else:
    print('\nNothing shows positive alpha in every regime once the chain is cleaned.')

"""Compare the option-implied (risk-neutral) distribution to the empirical distribution of SPY
returns, unconditionally and conditioned on the current low-vol regime.

Where empirical P >> implied P, the market is underpricing that outcome.
"""
import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def demean(sample):
    m = sum(sample) / len(sample)
    return [r - m for r in sample], m


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:300])
    return json.loads(r.stdout)


# ---------- 1. history ----------
bars = []
start = '2016-01-01'
while True:
    args = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day',
            '--start', start, '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
    d = run(args)
    b = d.get('bars') or []
    bars += b
    tok = d.get('next_page_token')
    if not tok or not b:
        break
    args += ['--page-token', tok]
    d = run(args)
    while True:
        b2 = d.get('bars') or []
        bars += b2
        tok = d.get('next_page_token')
        if not tok or not b2:
            break
        d = run(['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day',
                 '--start', start, '--end', '2026-08-29T00:00:00Z', '--limit', '10000',
                 '--page-token', tok])
    break

seen, clean = set(), []
for x in bars:
    if x['t'] not in seen:
        seen.add(x['t'])
        clean.append(x)
bars = sorted(clean, key=lambda x: x['t'])
c = [x['c'] for x in bars]
print(f'daily bars {len(bars)}  {bars[0]["t"][:10]} -> {bars[-1]["t"][:10]}  last {c[-1]}')

# trailing 20d close-to-close RV at each point
rv20 = [None] * len(c)
for i in range(21, len(c)):
    r = [math.log(c[j] / c[j - 1]) for j in range(i - 19, i + 1)]
    m = sum(r) / len(r)
    rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)

rv_now = rv20[-1]
print(f'current trailing 20d close-to-close RV: {rv_now*100:.2f}%')

# ---------- 2. empirical H-day return distributions ----------
H = 4  # trading days: Mon 31 Aug -> Fri 4 Sep judging
uncond, lowvol = [], []
band = (rv_now * 0.75, rv_now * 1.25)
for i in range(21, len(c) - H):
    ret = c[i + H] / c[i] - 1
    uncond.append(ret)
    if rv20[i] and band[0] <= rv20[i] <= band[1]:
        lowvol.append(ret)
print(f'{H}-day samples: unconditional {len(uncond)}, '
      f'low-vol-conditioned {len(lowvol)} (RV20 in {band[0]*100:.1f}-{band[1]*100:.1f}%)')
uncond_d, mu_u = demean(uncond)
lowvol_d, mu_l = demean(lowvol)
print(f'mean {H}-day drift removed: unconditional {mu_u*100:+.3f}%, low-vol {mu_l*100:+.3f}%')
print('(the risk-neutral measure is driftless by construction; comparing to a drifting')
print(' empirical distribution measures the equity risk premium, not a mispricing)')


def emp_p_beyond(sample, move):
    if move < 0:
        return sum(1 for r in sample if r <= move) / len(sample)
    return sum(1 for r in sample if r >= move) / len(sample)


# ---------- 3. risk-neutral P from the chain ----------
spot = c[-1]
EXP = '2026-09-04'
snaps = {}
tok = None
while True:
    args = ['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
            '--expiration-date', EXP, '--limit', '500',
            '--strike-price-gte', str(int(spot * 0.90)), '--strike-price-lte', str(int(spot * 1.10))]
    if tok:
        args += ['--page-token', tok]
    d = run(args)
    snaps.update(d.get('snapshots') or {})
    tok = d.get('next_page_token')
    if not tok:
        break

calls, puts = {}, {}
for k, v in snaps.items():
    q = v.get('latestQuote') or {}
    bp, ap = q.get('bp'), q.get('ap')
    if not bp or not ap or ap <= 0:
        continue
    mid = (bp + ap) / 2
    strike = int(k[-8:]) / 1000
    (calls if k[-9] == 'C' else puts)[strike] = mid

print(f'\nchain {EXP}: {len(calls)} calls, {len(puts)} puts with two-sided quotes')

ks = sorted(calls)
print(f'\n{"move":>7} {"strike":>8} | {"implied":>9} {"emp(all)":>9} {"emp(lowvol)":>12} | '
      f'{"ratio all":>10} {"ratio lv":>9}')
print('-' * 78)

rows = []
for pct in (-0.04, -0.03, -0.02, -0.015, -0.01, 0.01, 0.015, 0.02, 0.03):
    K = spot * (1 + pct)
    side = puts if pct < 0 else calls
    sks = sorted(side)
    near = [x for x in sks if abs(x - K) <= 6]
    if len(near) < 3:
        continue
    # finite difference of option price wrt strike -> risk-neutral tail probability
    lo = max([x for x in near if x <= K], default=None)
    hi = min([x for x in near if x > K], default=None)
    if lo is None or hi is None or hi == lo:
        continue
    dP = (side[hi] - side[lo]) / (hi - lo)
    q_imp = dP if pct < 0 else -dP        # P(S_T <= K) for puts, P(S_T >= K) for calls
    q_imp = min(max(q_imp, 1e-6), 1.0)
    e_all = emp_p_beyond(uncond_d, pct)
    e_lv = emp_p_beyond(lowvol_d, pct)
    if q_imp < 0.005:   # finite difference degenerate at this strike
        print(f'{pct*100:>6.1f}% {K:>8.0f} |   (implied prob too small to difference reliably)')
        continue
    rows.append((pct, K, q_imp, e_all, e_lv))
    print(f'{pct*100:>6.1f}% {K:>8.0f} | {q_imp*100:>8.2f}% {e_all*100:>8.2f}% {e_lv*100:>11.2f}% | '
          f'{e_all/q_imp:>10.2f} {e_lv/q_imp:>9.2f}')

print('\nratio > 1  => history says this happens MORE often than the market is charging for')
print('ratio < 1  => the market is charging MORE than history justifies')

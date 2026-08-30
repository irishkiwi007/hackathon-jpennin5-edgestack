"""Is the option skew in commodity ETFs different from equity indices - and is it mispriced?

The equity result (puts systematically overpriced) comes from one-sided institutional demand for
crash protection. Commodities have different hedging flows:
  - oil: producers hedge down, consumers hedge up -> two-sided
  - gold: crisis hedge -> calls can be bid in stress
  - nat gas: supply/weather shocks -> notorious CALL skew

If the skew runs the other way, "sell the overpriced wing" points at a different structure entirely.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
SYMS = ['SPY', 'QQQ', 'GLD', 'SLV', 'GDX', 'USO', 'UNG']
H = 5


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


print('=== does the CLI expose a split adjustment? ===')
h = subprocess.run([A, 'data', 'bars', '--help'], capture_output=True, text=True, env=env)
adj = [l.strip() for l in h.stdout.splitlines() if 'adjust' in l.lower()]
print('\n'.join(adj) if adj else '  (none found - bars may be RAW; reverse splits will corrupt USO/UNG)')


def bars(sym, adjustment='all'):
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', sym, '--timeframe', '1Day', '--start', '2016-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
        if adj:
            a += ['--adjustment', adjustment]
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        if not d:
            return None
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    out.sort(key=lambda x: x['t'])
    return out


print('\n' + '=' * 100)
print('SKEW: 25-delta risk reversal  RR25 = IV(25d call) - IV(25d put)')
print('=' * 100)
print(f'{"sym":>5} {"spot":>9} {"ATM IV":>8} {"IV 25d put":>11} {"IV 25d call":>12} '
      f'{"RR25":>8} {"skew shape":>22}')

EXPS = ['2026-09-18', '2026-09-30', '2026-10-16']
store = {}
for s in SYMS:
    b = bars(s)
    if not b:
        print(f'{s:>5}  (no bars)')
        continue
    spot = b[-1]['c']
    got = None
    for e in EXPS:
        ch = run(['data', 'option', 'chain', '--underlying-symbol', s, '--feed', 'indicative',
                  '--expiration-date', e, '--limit', '400',
                  '--strike-price-gte', str(round(spot * 0.80, 0)),
                  '--strike-price-lte', str(round(spot * 1.20, 0))])
        if ch and len(ch.get('snapshots') or {}) > 20:
            got = (e, ch['snapshots'])
            break
    if not got:
        print(f'{s:>5} {spot:>9.2f}  (no usable chain)')
        continue
    exp, snaps = got
    calls, puts = [], []
    for k, v in snaps.items():
        iv = v.get('impliedVolatility')
        d = (v.get('greeks') or {}).get('delta')
        q = v.get('latestQuote') or {}
        if not iv or d is None or not q.get('bp') or not q.get('ap'):
            continue
        (calls if k[-9] == 'C' else puts).append((abs(d), iv, int(k[-8:]) / 1000))
    if len(calls) < 3 or len(puts) < 3:
        print(f'{s:>5} {spot:>9.2f}  (thin greeks)')
        continue
    atm = [iv for d, iv, _ in calls + puts if 0.40 < d < 0.60]
    c25 = min(calls, key=lambda x: abs(x[0] - 0.25))
    p25 = min(puts, key=lambda x: abs(x[0] - 0.25))
    rr = c25[1] - p25[1]
    shape = 'PUT skew (equity-like)' if rr < -0.01 else (
        'CALL skew (commodity)' if rr > 0.01 else 'flat')
    store[s] = dict(spot=spot, bars=b, exp=exp, rr=rr, atm=sum(atm) / len(atm) if atm else None,
                    c25=c25, p25=p25)
    print(f'{s:>5} {spot:>9.2f} {(sum(atm)/len(atm) if atm else 0)*100:>7.1f}% '
          f'{p25[1]*100:>10.1f}% {c25[1]*100:>11.1f}% {rr*100:>+7.1f} {shape:>22}')

print("""
Equity indices carry persistent PUT skew - institutions pay up for crash protection, which is the
overpricing the earlier analysis found. A positive RR25 means the CALL side is the bid one.""")

print('\n' + '=' * 100)
print('IS THE SKEW JUSTIFIED? implied vs empirical tail frequency (drift removed)')
print('=' * 100)
for s, d in store.items():
    b = d['bars']
    c = [x['c'] for x in b]
    rets = [c[i + H] / c[i] - 1 for i in range(len(c) - H)]
    mu = sum(rets) / len(rets)
    rd = [r - mu for r in rets]
    dte = max((datetime.date.fromisoformat(d['exp']) - datetime.date(2026, 8, 28)).days, 1)
    scale = math.sqrt(H / 252) / math.sqrt(dte / 365)
    print(f'\n{s}  spot {d["spot"]:.2f}  ann drift {((1+mu)**(252/H)-1)*100:+.1f}%  '
          f'RR25 {d["rr"]*100:+.1f}  n={len(rets)}')
    print(f'   {"move":>7} {"implied P(N(d2) approx)":>24} {"empirical P":>13} {"emp/impl":>10}')
    for side, sgn in (('put', -1), ('call', +1)):
        iv = d['p25'][1] if side == 'put' else d['c25'][1]
        # 25-delta strike distance in this expiry, rescaled to our H-day horizon
        move = sgn * 0.674 * iv * math.sqrt(dte / 365) * scale
        # risk-neutral prob of exceeding, approx from the 25-delta convention
        q_imp = 0.25
        emp = (sum(1 for r in rd if r <= move) if sgn < 0 else sum(1 for r in rd if r >= move)) / len(rd)
        print(f'   {move*100:>+6.2f}% {q_imp*100:>23.1f}% {emp*100:>12.2f}% {emp/q_imp:>10.2f}')
print("""
emp/impl > 1 : that wing happens MORE often than its delta implies -> underpriced
emp/impl < 1 : overpriced. For SPY the put wing should read well below 1 (the known result).
NOTE: 25-delta is a rough proxy for risk-neutral probability; this is a screen, not a valuation.""")

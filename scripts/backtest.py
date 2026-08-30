"""Walk-forward backtest on REAL historical option prices.

Everything prior to this was cross-sectional EV: one chain snapshot scored against a historical
return distribution. This is different - it walks forward, builds the structure from the chain as
it was on each entry date, holds to expiry, and settles against SPY's actual close.

HARD LIMITS, stated up front:
  * Alpaca option history starts Feb 2024 -> ~2.5 years, ~130 weekly cycles, ONE regime.
    This backtest CANNOT validate regime stability. It can only test whether the edge shows up
    in real prices at all.
  * No historical bid/ask endpoint exists - only trade bars. Entry marks are trade-based, which
    understates cost. Slippage is applied explicitly and swept.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args, tries=2):
    for _ in range(tries):
        r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except Exception:
                return None
    return None


def spy_bars():
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day', '--start', '2024-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    out.sort(key=lambda x: x['t'])
    return out


bars = spy_bars()
dts = [datetime.date.fromisoformat(x['t'][:10]) for x in bars]
close = [x['c'] for x in bars]
idx = {d: i for i, d in enumerate(dts)}
print(f'SPY sessions {len(bars)}  {dts[0]} -> {dts[-1]}')


def occ(sym, exp, cp, strike):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(strike*1000)):08d}'


# entry every Monday; expiry = the Friday of that week (4 sessions later)
cycles = []
for i, d in enumerate(dts):
    if d.weekday() != 0:
        continue
    fri = d + datetime.timedelta(days=4)
    if fri not in idx:
        continue
    j = idx[fri]
    if j - i != 4:
        continue
    cycles.append((i, j))
print(f'clean Mon->Fri cycles: {len(cycles)}')

STRUCTS = {
    'call debit +1.4/+2.0': [(1, 'C', 1.014), (-1, 'C', 1.020)],
    'call debit +0.5/+1.5': [(1, 'C', 1.005), (-1, 'C', 1.015)],
    'put debit  -1.0/-2.0': [(1, 'P', 0.990), (-1, 'P', 0.980)],
    'put credit -2.0/-3.0': [(-1, 'P', 0.980), (1, 'P', 0.970)],
    'iron condor +/-2% w5': [(1, 'P', 0.970), (-1, 'P', 0.980),
                             (-1, 'C', 1.020), (1, 'C', 1.030)],
}

# collect every contract we need
need = {}
for i, j in cycles:
    S0, exp = close[i], dts[j]
    for nm, legs in STRUCTS.items():
        for q, cp, mult in legs:
            k = round(S0 * mult)
            need.setdefault((i, j), set()).add(occ('SPY', exp, cp, k))

allsyms = sorted({s for v in need.values() for s in v})
print(f'contracts to fetch: {len(allsyms)}')

PX = {}
B = 40
for b in range(0, len(allsyms), B):
    chunk = allsyms[b:b + B]
    exps = sorted({datetime.date(2000 + int(s[3:5]), int(s[5:7]), int(s[7:9])) for s in chunk})
    lo = min(exps) - datetime.timedelta(days=14)
    hi = max(exps) + datetime.timedelta(days=1)
    d = run(['data', 'option', 'bars', '--symbols', ','.join(chunk), '--timeframe', '1Day',
             '--start', lo.isoformat(), '--end', hi.isoformat(), '--limit', '10000'])
    if d and d.get('bars'):
        for s, rows in d['bars'].items():
            for r in rows:
                PX[(s, r['t'][:10])] = r['c']
    if (b // B) % 10 == 0:
        print(f'  fetched {b+len(chunk)}/{len(allsyms)}  cached marks {len(PX)}')
print(f'price marks cached: {len(PX)}')


def backtest(legs, slip_per_leg):
    trades = []
    for i, j in cycles:
        S0, ST, exp = close[i], close[j], dts[j]
        ed = dts[i].isoformat()
        cost, ok = 0.0, True
        for q, cp, mult in legs:
            K = round(S0 * mult)
            s = occ('SPY', exp, cp, K)
            p = PX.get((s, ed))
            if p is None:
                ok = False
                break
            # pay up when buying, receive less when selling
            cost += q * (p + slip_per_leg if q > 0 else p - slip_per_leg)
        if not ok:
            continue
        val = 0.0
        for q, cp, mult in legs:
            K = round(S0 * mult)
            val += q * (max(ST - K, 0) if cp == 'C' else max(K - ST, 0))
        trades.append((dts[i], (val - cost) * 100, cost * 100, ST / S0 - 1))
    return trades


def summarise(tr):
    if not tr:
        return None
    p = [t[1] for t in tr]
    n = len(p)
    tot = sum(p)
    mean = tot / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in p) / (n - 1)) if n > 1 else 0
    wins = sum(1 for x in p if x > 0)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    sharpe = (mean / sd * math.sqrt(52)) if sd else 0
    # Wilson lower bound on win rate
    z = 1.64
    ph = wins / n
    den = 1 + z * z / n
    lo = (ph + z * z / (2 * n) - z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / den
    return dict(n=n, tot=tot, mean=mean, sd=sd, win=ph, winlo=lo, sharpe=sharpe,
                mdd=mdd, best=max(p), worst=min(p),
                avgcost=sum(t[2] for t in tr) / n)


print('\n' + '=' * 104)
print('WALK-FORWARD BACKTEST — real option prices, Mon entry -> Fri expiry, 1 lot')
print('=' * 104)
for slip in (0.00, 0.02, 0.05):
    print(f'\n--- slippage ${slip*100:.0f}/leg (each way on entry) ---')
    print(f'{"structure":<24} {"n":>4} {"total$":>9} {"mean$":>8} {"sd$":>8} {"win%":>7} '
          f'{"win lo95":>9} {"Sharpe":>7} {"maxDD$":>9} {"worst$":>8}')
    for nm, legs in STRUCTS.items():
        s = summarise(backtest(legs, slip))
        if not s:
            print(f'{nm:<24}  (no trades)')
            continue
        print(f'{nm:<24} {s["n"]:>4} {s["tot"]:>9.0f} {s["mean"]:>8.1f} {s["sd"]:>8.1f} '
              f'{s["win"]*100:>6.1f}% {s["winlo"]*100:>8.1f}% {s["sharpe"]:>7.2f} '
              f'{s["mdd"]:>9.0f} {s["worst"]:>8.0f}')

print('\nSPY buy-and-hold over the same Mon->Fri cycles, for reference:')
r = [close[j] / close[i] - 1 for i, j in cycles]
m = sum(r) / len(r)
sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
print(f'  n={len(r)}  mean {m*100:+.3f}%/wk  sd {sd*100:.2f}%  '
      f'Sharpe {m/sd*math.sqrt(52):.2f}  win {sum(1 for x in r if x>0)/len(r)*100:.1f}%')

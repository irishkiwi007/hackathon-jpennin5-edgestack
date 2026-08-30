"""STAGE 2 — validate the vol-regime finding against REAL option prices (Alpaca, 2024-2026).

Stage 1 (33 yrs, underlying) said vol mean-reverts in both directions, so:
    LOW vol  -> forward vol rises -> BUY premium
    HIGH vol -> forward vol falls -> SELL premium

Test it on actual ATM straddles: does straddle P&L sort by the vol regime at entry?
Also splits on IV/RV at entry, which is the more direct driver.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


out, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day', '--start', '2023-10-01',
         '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    out += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break
out.sort(key=lambda x: x['t'])
dts = [datetime.date.fromisoformat(x['t'][:10]) for x in out]
close = [x['c'] for x in out]
idx = {d: i for i, d in enumerate(dts)}
N = len(close)
lr = [math.log(close[i] / close[i - 1]) for i in range(1, N)]
ANN = math.sqrt(252)


def rv20(i):
    if i < 21:
        return None
    s = lr[i - 20:i]
    m = sum(s) / len(s)
    return math.sqrt(sum((x - m) ** 2 for x in s) / 19) * ANN


print(f'SPY {N} sessions {dts[0]} -> {dts[-1]}')
rvs = [rv20(i) for i in range(N)]
valid = [x for x in rvs if x]
print(f'RV20 range over window: {min(valid)*100:.1f}% - {max(valid)*100:.1f}%  '
      f'median {sorted(valid)[len(valid)//2]*100:.1f}%')

HOLD = 21   # ~1 month, matching Stage 1


def occ(exp, cp, k):
    return f'SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


# entries: every Monday with a session ~HOLD later; expiry = that session
cycles = []
for i, d in enumerate(dts):
    if d.weekday() != 0 or i + HOLD >= N or i < 21:
        continue
    j = i + HOLD
    cycles.append((i, j))
print(f'cycles: {len(cycles)}')

need = set()
for i, j in cycles:
    k = round(close[i])
    for cp in ('C', 'P'):
        for dk in (-1, 0, 1):
            need.add(occ(dts[j], cp, k + dk))
need = sorted(need)
print(f'contracts: {len(need)}')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(s[3:5]), int(s[5:7]), int(s[7:9])) for s in ch})
    d = run(['data', 'option', 'bars', '--symbols', ','.join(ch), '--timeframe', '1Day',
             '--start', (min(exps) - datetime.timedelta(days=40)).isoformat(),
             '--end', (max(exps) + datetime.timedelta(days=1)).isoformat(), '--limit', '10000'])
    if d and d.get('bars'):
        for s, rows in d['bars'].items():
            for r in rows:
                PX[(s, r['t'][:10])] = r['c']
    if (b // B) % 12 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}')

SLIP = 0.05   # $/leg, straddles cross two legs


def straddle(i, j):
    S0, S1, exp, ed = close[i], close[j], dts[j], dts[i].isoformat()
    k = round(S0)
    cp_ = PX.get((occ(exp, 'C', k), ed))
    pp_ = PX.get((occ(exp, 'P', k), ed))
    if cp_ is None or pp_ is None:
        return None
    prem = cp_ + pp_
    payoff = abs(S1 - k)
    # long: pay prem + slippage, receive payoff.  short: receive prem - slippage, pay payoff
    long_pnl = (payoff - (prem + 2 * SLIP)) * 100
    short_pnl = ((prem - 2 * SLIP) - payoff) * 100
    return dict(prem=prem, k=k, S0=S0, S1=S1, payoff=payoff,
                long_pnl=long_pnl, short_pnl=short_pnl,
                iv_proxy=prem / S0 / math.sqrt(HOLD / 252) * 0.8)


res = []
for i, j in cycles:
    s = straddle(i, j)
    if not s:
        continue
    t = rvs[i]
    if not t:
        continue
    s['rv'] = t
    s['ivrv'] = s['iv_proxy'] / t
    s['date'] = dts[i]
    res.append(s)
print(f'\nstraddles priced: {len(res)}')

if len(res) < 20:
    print('insufficient data'); sys.exit()


def summarise(g, label):
    n = len(g)
    ls = [x['long_pnl'] for x in g]
    ss = [x['short_pnl'] for x in g]
    lm, sm = sum(ls) / n, sum(ss) / n
    lw = sum(1 for x in ls if x > 0) / n
    sw = sum(1 for x in ss if x > 0) / n
    return (f'{label:<26} {n:>4} {sum(x["rv"] for x in g)/n*100:>7.1f}% '
            f'{sum(x["ivrv"] for x in g)/n:>7.2f} '
            f'{lm:>10.0f} {lw*100:>7.1f}% {sm:>10.0f} {sw*100:>7.1f}%')


print('\n' + '=' * 104)
print('ATM STRADDLE OUTCOMES BY TRAILING-VOL TERCILE  (real prices, $5/leg slippage)')
print('=' * 104)
print(f'{"bucket":<26} {"n":>4} {"mean RV":>8} {"IV/RV":>7} '
      f'{"LONG mean$":>10} {"win%":>8} {"SHORT mean$":>10} {"win%":>8}')
byrv = sorted(res, key=lambda x: x['rv'])
t3 = len(byrv) // 3
print(summarise(byrv[:t3], 'LOW vol tercile'))
print(summarise(byrv[t3:2 * t3], 'MID vol tercile'))
print(summarise(byrv[2 * t3:], 'HIGH vol tercile'))
print(summarise(byrv, 'ALL'))

print('\n' + '=' * 104)
print('SAME, SPLIT ON IV/RV AT ENTRY (the more direct driver)')
print('=' * 104)
print(f'{"bucket":<26} {"n":>4} {"mean RV":>8} {"IV/RV":>7} '
      f'{"LONG mean$":>10} {"win%":>8} {"SHORT mean$":>10} {"win%":>8}')
byiv = sorted(res, key=lambda x: x['ivrv'])
print(summarise(byiv[:t3], 'IV cheap vs RV'))
print(summarise(byiv[t3:2 * t3], 'IV fair'))
print(summarise(byiv[2 * t3:], 'IV rich vs RV'))

print("""
Stage 1 (33 yrs) predicts: LONG premium should do better in the LOW-vol tercile,
SHORT premium better in the HIGH-vol tercile. Check whether real prices agree.""")

cur = rvs[-1]
pct = sum(1 for x in valid if x <= cur) / len(valid) * 100
print(f'\nCURRENT STATE: RV20 = {cur*100:.2f}%  ({pct:.0f}th pct of this window)')

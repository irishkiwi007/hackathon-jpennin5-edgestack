"""The significant finding is a SHORT ATM STRADDLE in low vol (t=3.62).
Alpaca bans it - two uncovered short legs are rejected.

The executable version is an IRON BUTTERFLY: short ATM straddle + long wings. The wings cost
money and cap the profit, so the question is whether the edge survives being made defined-risk.

Tests wing widths against the same vol-tercile split, on real prices.
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
N = len(close)
lr = [math.log(close[i] / close[i - 1]) for i in range(1, N)]
ANN = math.sqrt(252)


def rv20(i):
    if i < 21:
        return None
    s = lr[i - 20:i]
    m = sum(s) / len(s)
    return math.sqrt(sum((x - m) ** 2 for x in s) / 19) * ANN


rvs = [rv20(i) for i in range(N)]
HOLD = 21
WINGS = [5, 10, 15, 20, 30]


def occ(exp, cp, k):
    return f'SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


cycles = []
for i, d in enumerate(dts):
    if d.weekday() != 0 or i + HOLD + 7 >= N or i < 21:
        continue
    j = None
    for k in range(i + HOLD - 3, min(i + HOLD + 7, N)):
        if dts[k].weekday() == 4:
            j = k
            break
    if j:
        cycles.append((i, j))
print(f'cycles {len(cycles)}')

need = set()
for i, j in cycles:
    k0 = round(close[i])
    for cp in ('C', 'P'):
        for dk in (-3, -2, -1, 0, 1, 2, 3):
            need.add(occ(dts[j], cp, k0 + dk))
        for w in WINGS:
            for dk in (-1, 0, 1):
                need.add(occ(dts[j], 'C', k0 + w + dk))
                need.add(occ(dts[j], 'P', k0 - w + dk))
need = sorted(need)
print(f'contracts {len(need)}')

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
    if (b // B) % 20 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}')

SLIP = 0.05


def build(i, j, wing):
    S0, S1, exp, ed = close[i], close[j], dts[j], dts[i].isoformat()
    body = None
    for dk in (0, 1, -1, 2, -2, 3, -3):
        k = round(S0) + dk
        if PX.get((occ(exp, 'C', k), ed)) is not None and PX.get((occ(exp, 'P', k), ed)) is not None:
            body = k
            break
    if body is None:
        return None
    cu = cd = None
    for dk in (0, 1, -1):
        if cu is None and PX.get((occ(exp, 'C', body + wing + dk), ed)) is not None:
            cu = body + wing + dk
        if cd is None and PX.get((occ(exp, 'P', body - wing + dk), ed)) is not None:
            cd = body - wing + dk
    if cu is None or cd is None:
        return None
    # short body straddle (receive bid-ish), long wings (pay ask-ish)
    credit = (PX[(occ(exp, 'C', body), ed)] + PX[(occ(exp, 'P', body), ed)] - 2 * SLIP) \
        - (PX[(occ(exp, 'C', cu), ed)] + PX[(occ(exp, 'P', cd), ed)] + 2 * SLIP)
    if credit <= 0:
        return None
    intr = (max(S1 - body, 0) + max(body - S1, 0)) \
        - max(S1 - cu, 0) - max(cd - S1, 0)
    return (credit - intr) * 100


res = {w: [] for w in WINGS}
for i, j in cycles:
    t = rvs[i]
    if not t:
        continue
    for w in WINGS:
        p = build(i, j, w)
        if p is not None:
            res[w].append((t, p))

print('\n' + '=' * 100)
print('IRON BUTTERFLY (defined-risk version of the significant short straddle)')
print('=' * 100)
print(f'{"wing":>5} {"bucket":<12} {"n":>4} {"mean RV":>8} {"mean $":>9} {"win%":>7} '
      f'{"sd":>8} {"t":>6} {"worst$":>9} {"":>4}')
for w in WINGS:
    g = sorted(res[w], key=lambda x: x[0])
    if len(g) < 30:
        print(f'{w:>5}  (only {len(g)} trades)')
        continue
    t3 = len(g) // 3
    for lbl, sub in (('LOW vol', g[:t3]), ('MID vol', g[t3:2 * t3]),
                     ('HIGH vol', g[2 * t3:]), ('ALL', g)):
        p = [x[1] for x in sub]
        n = len(p)
        m = sum(p) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in p) / (n - 1)) if n > 1 else 0
        tt = m / (sd / math.sqrt(n)) if sd else 0
        print(f'{w:>5} {lbl:<12} {n:>4} {sum(x[0] for x in sub)/n*100:>7.1f}% {m:>9.0f} '
              f'{sum(1 for x in p if x>0)/n*100:>6.1f}% {sd:>8.0f} {tt:>6.2f} {min(p):>9.0f} '
              f'{"SIG" if abs(tt)>1.96 else "-":>4}')
    print()

print("""Compare against the NAKED short straddle in low vol: mean +$567, t=3.62.
If the iron butterfly's low-vol t collapses, the edge lives in the uncovered tail Alpaca forbids -
which would mean the significant result is not tradeable on the competition account.""")

"""We are in 2026, and 2026 favours long premium. Two things decide whether that is actionable:

1. Is the edge present in the MOST RECENT weeks, or did it live in early 2026 and already fade?
2. Does the IV/RV state PERSIST? If this week's reading predicts next week's, the current reading
   is tradeable information. If it flips randomly, knowing today's state tells you nothing.

Rebuilds the condor P&L from cached news/bars plus fresh option marks, then breaks it down by month
and measures persistence of the underlying vol-premium state.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
SLIP = 0.03


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


# ---------- SPY straddle ratio, weekly, full history since option data begins ----------
bars, tok = [], None
while True:
    u = ('https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day&feed=sip'
         '&start=2024-01-10&end=2026-08-28&limit=10000&adjustment=all')
    if tok:
        u += f'&page_token={tok}'
    d = q(u)
    if not d:
        break
    bars += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break
dts = [b['t'][:10] for b in bars]
px = np.array([b['c'] for b in bars])
n = len(px)


def occ(exp, cp, k):
    return f'SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


cyc = []
for i in range(25, n - 12):
    if datetime.date.fromisoformat(dts[i]).weekday() != 0:
        continue
    j = None
    for k2 in range(i + 5, min(i + 12, n)):
        if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
            j = k2
            break
    if j:
        cyc.append((i, j))

need = set()
for i, j in cyc:
    exp = datetime.date.fromisoformat(dts[j])
    for dk in (-2, -1, 0, 1, 2):
        need.add(occ(exp, 'C', round(px[i]) + dk))
        need.add(occ(exp, 'P', round(px[i]) + dk))
need = sorted(need)
PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(x[3:5]), int(x[5:7]), int(x[7:9])) for x in ch})
    u = ('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
         f'&timeframe=1Day&start={(min(exps)-datetime.timedelta(days=25)).isoformat()}'
         f'&end={(max(exps)+datetime.timedelta(days=1)).isoformat()}&limit=10000')
    d = q(u)
    if d and d.get('bars'):
        for sy, rows in d['bars'].items():
            for r in rows:
                PX[(sy, r['t'][:10])] = r['c']
print(f'SPY weekly cycles {len(cyc)}, marks {len(PX)}\n')

R = []
for i, j in cyc:
    exp = datetime.date.fromisoformat(dts[j])
    d0 = dts[i]
    k = None
    for dk in (0, 1, -1, 2, -2):
        kk = round(px[i]) + dk
        if PX.get((occ(exp, 'C', kk), d0)) and PX.get((occ(exp, 'P', kk), d0)):
            k = kk
            break
    if k is None:
        continue
    straddle = PX[(occ(exp, 'C', k), d0)] + PX[(occ(exp, 'P', k), d0)]
    settle = abs(px[j] - k)
    if straddle <= 0:
        continue
    R.append(dict(date=d0, month=d0[:7], implied=straddle / px[i],
                  actual=settle / px[i], ratio=settle / straddle,
                  long_pnl=(settle - straddle - 2 * SLIP) * 100))

print('=' * 96)
print('1. MONTH BY MONTH — is the edge in the RECENT weeks or did it fade?')
print('=' * 96)
print(f'{"month":<10} {"n":>4} {"implied":>9} {"actual":>9} {"ratio":>8} '
      f'{"long straddle $":>17} {"cum $":>9}')
bym = defaultdict(list)
for r in R:
    bym[r['month']].append(r)
cum = 0
for m in sorted(bym):
    if m < '2025-09':
        continue
    g = bym[m]
    im = np.mean([x['implied'] for x in g])
    am = np.mean([x['actual'] for x in g])
    pl = np.sum([x['long_pnl'] for x in g])
    cum += pl
    print(f'{m:<10} {len(g):>4} {im*100:>8.2f}% {am*100:>8.2f}% {am/im:>8.3f} '
          f'{pl:>17.0f} {cum:>9.0f}')

print('\n' + '=' * 96)
print('2. RECENT WINDOWS')
print('=' * 96)
print(f'{"window":<16} {"n":>4} {"mean ratio":>12} {"long $/trade":>14} {"t vs 0":>8}')
for lab, k in (('last 4 cycles', 4), ('last 8', 8), ('last 12', 12),
               ('last 20', 20), ('all 2026', None)):
    g = R[-k:] if k else [r for r in R if r['date'][:4] == '2026']
    if len(g) < 4:
        continue
    v = np.array([x['long_pnl'] for x in g])
    t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 2 else float('nan')
    print(f'{lab:<16} {len(g):>4} {np.mean([x["ratio"] for x in g]):>12.3f} '
          f'{v.mean():>14.1f} {t:>8.2f}')

print('\n' + '=' * 96)
print('3. DOES THE VOL-PREMIUM STATE PERSIST? (the question that makes it actionable)')
print('=' * 96)
rat = np.array([r['ratio'] for r in R])
for lag in (1, 2, 3, 4):
    if len(rat) > lag + 10:
        a, b = rat[:-lag], rat[lag:]
        c = np.corrcoef(a, b)[0, 1]
        print(f'  autocorrelation of weekly actual/implied at lag {lag}: {c:+.3f}')
print()
# does a rich/cheap reading predict the NEXT week's outcome?
med = np.median(rat)
nxt_after_cheap = [R[i + 1]['long_pnl'] for i in range(len(R) - 1) if R[i]['ratio'] > med]
nxt_after_rich = [R[i + 1]['long_pnl'] for i in range(len(R) - 1) if R[i]['ratio'] <= med]
for lab, v in (('after a CHEAP week (ratio>med)', nxt_after_cheap),
               ('after a RICH week (ratio<=med)', nxt_after_rich)):
    v = np.array(v)
    if len(v) < 20:
        continue
    t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    print(f'  next-week long straddle {lab:<34} n={len(v):>4} '
          f'mean {v.mean():>+8.1f}  t={t:>5.2f}')
print("""
  If 'after a cheap week' is materially better than 'after a rich week', the state persists and
  today's reading is tradeable. If they are the same, the regime is not predictable week to week
  and being 'in 2026' tells you nothing about next Monday.""")

# current live reading
print('\n' + '=' * 96)
print('4. CURRENT LIVE READING')
print('=' * 96)
lr = np.diff(np.log(px[-21:]))
rv20 = lr.std(ddof=1) * math.sqrt(252)
print(f'  SPY trailing RV20: {rv20*100:.2f}%')
print(f'  last 4 weekly ratios: ' + ', '.join(f'{r["ratio"]:.2f}' for r in R[-4:]))
print(f'  last 4 implied moves: ' + ', '.join(f'{r["implied"]*100:.2f}%' for r in R[-4:]))

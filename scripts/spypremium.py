"""Can we sell SPY premium for a small edge?

The straddle-ratio test showed SPY actual/implied = 0.638-0.740, implying IV/RV ~1.4. That is the
documented variance risk premium - NOT a data-mined discovery, so the multiple-testing correction
does not apply the way it does to everything else in this project.

But three things have to be checked before it means anything tradeable:
  1. Is the premium rich RIGHT NOW, or was that an average over a calm sample?
  2. What survives once it is made defined-risk (Alpaca bans naked short straddles)?
  3. How bad is the left tail - the mean can be positive while the trade is uninvestable
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


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
print(f'SPY {n} sessions {dts[0]} -> {dts[-1]}')


def occ(exp, cp, k):
    return f'SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


# weekly cycles: Monday entry -> Friday expiry ~2 weeks out
cyc = []
for i in range(25, n - 12):
    if datetime.date.fromisoformat(dts[i]).weekday() != 0:
        continue
    j = None
    for k2 in range(i + 8, min(i + 14, n)):
        if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
            j = k2
            break
    if j:
        cyc.append((i, j))
print(f'cycles: {len(cyc)}')

WINGS = [10, 20, 30]
need = set()
for i, j in cyc:
    exp = datetime.date.fromisoformat(dts[j])
    k0 = round(px[i])
    for dk in (-2, -1, 0, 1, 2):
        need.add(occ(exp, 'C', k0 + dk))
        need.add(occ(exp, 'P', k0 + dk))
    for w in WINGS:
        for dk in (-1, 0, 1):
            need.add(occ(exp, 'C', k0 + w + dk))
            need.add(occ(exp, 'P', k0 - w + dk))
need = sorted(need)
print(f'contracts: {len(need)}')

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
    if (b // B) % 30 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}\n')

SLIP = 0.03   # per leg, each way -- SPY ATM spread measured at $0.02-0.03
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
    c0 = PX[(occ(exp, 'C', k), d0)]
    p0 = PX[(occ(exp, 'P', k), d0)]
    straddle = c0 + p0
    settle = abs(px[j] - k)
    row = dict(date=d0, year=d0[:4], spot=float(px[i]), k=k, straddle=straddle,
               settle=settle, ratio=settle / straddle if straddle > 0 else np.nan,
               naked=(straddle - 2 * SLIP - settle) * 100)
    for w in WINGS:
        cu = pu = None
        for dk in (0, 1, -1):
            if cu is None and PX.get((occ(exp, 'C', k + w + dk), d0)):
                cu = k + w + dk
            if pu is None and PX.get((occ(exp, 'P', k - w + dk), d0)):
                pu = k - w + dk
        if cu is None or pu is None:
            row[f'bf{w}'] = None
            continue
        credit = straddle - PX[(occ(exp, 'C', cu), d0)] - PX[(occ(exp, 'P', pu), d0)] - 4 * SLIP
        payout = settle - max(px[j] - cu, 0) - max(pu - px[j], 0)
        row[f'bf{w}'] = (credit - payout) * 100
    R.append(row)

print('=' * 96)
print('1. IS THE PREMIUM RICH RIGHT NOW, OR ONLY ON AVERAGE?')
print('=' * 96)
print(f'{"period":<12} {"n":>5} {"implied move":>14} {"actual move":>13} {"ratio":>8} '
      f'{"implied IV/RV":>14}')
for yr in ('2024', '2025', '2026', 'ALL'):
    g = [r for r in R if yr == 'ALL' or r['year'] == yr]
    if len(g) < 8:
        continue
    im = np.mean([r['straddle'] / r['spot'] for r in g])
    am = np.mean([r['settle'] / r['spot'] for r in g])
    print(f'{yr:<12} {len(g):>5} {im*100:>13.2f}% {am*100:>12.2f}% {am/im:>8.3f} '
          f'{im/am:>14.2f}')
last = R[-12:]
im = np.mean([r['straddle'] / r['spot'] for r in last])
am = np.mean([r['settle'] / r['spot'] for r in last])
print(f'{"last 12":<12} {len(last):>5} {im*100:>13.2f}% {am*100:>12.2f}% {am/im:>8.3f} '
      f'{im/am:>14.2f}')

print('\n' + '=' * 96)
print('2. WHAT SURVIVES BEING MADE DEFINED-RISK?  (Alpaca bans naked short straddles)')
print('=' * 96)
print(f'{"structure":<22} {"n":>5} {"total $":>10} {"mean $":>9} {"sd":>9} {"t":>7} '
      f'{"win%":>7} {"worst $":>10} {"maxDD $":>10}')


def stat(vals, lab):
    v = np.array([x for x in vals if x is not None])
    if len(v) < 20:
        return
    m, sd = v.mean(), v.std(ddof=1)
    t = m / (sd / math.sqrt(len(v)))
    eq = np.cumsum(v)
    dd = float(np.min(eq - np.maximum.accumulate(eq)))
    print(f'{lab:<22} {len(v):>5} {v.sum():>10.0f} {m:>9.1f} {sd:>9.1f} {t:>7.2f} '
          f'{(v>0).mean()*100:>6.1f}% {v.min():>10.0f} {dd:>10.0f}')


stat([r['naked'] for r in R], 'naked straddle (N/A)')
for w in WINGS:
    stat([r.get(f'bf{w}') for r in R], f'iron butterfly w{w}')

print('\n' + '=' * 96)
print('3. THE LEFT TAIL — a positive mean is not enough')
print('=' * 96)
for lab, key in (('naked straddle', 'naked'), ('iron butterfly w30', 'bf30')):
    v = np.array([r[key] for r in R if r.get(key) is not None])
    if len(v) < 20:
        continue
    v2 = np.sort(v)
    print(f'{lab}:  mean {v.mean():+.0f}  median {np.median(v):+.0f}  '
          f'p5 {v2[int(.05*len(v2))]:+.0f}  p1 {v2[int(.01*len(v2))]:+.0f}  min {v2[0]:+.0f}')
    print(f'   worst 3 losses: {v2[:3].astype(int)}   '
          f'wipes out {abs(v2[0])/max(v.mean(),1e-9):.0f} average wins')

print("""
=================================================================================================
NOTE ON MULTIPLE TESTING: the variance risk premium is a 30+ year documented result (CBOE PUT
index, 1986-2015, Sharpe 0.67), not a hypothesis discovered by searching this data. The Bonferroni
correction applied elsewhere in this project does not apply to it in the same way. What DOES apply
is whether the defined-risk version keeps enough of it, and whether the tail is survivable.""")

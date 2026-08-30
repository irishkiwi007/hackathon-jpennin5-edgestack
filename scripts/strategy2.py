"""STRATEGY TEST: does a news-coverage screen improve defined-risk premium selling?

Thread: the variance risk premium shows up on ordinary days (actual/implied ~0.93) and vanishes on
coverage-spike days (~1.00). So a premium seller should be selective about WHEN it sells.

Tests an Alpaca-legal iron condor, weekly, across 10 names, and asks one question:
    does screening on news_z improve it, or is the screen worthless?

Everything defined-risk. Realistic slippage. Per-symbol breakdown. No naked legs anywhere.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
LOOK = 20
SLIP = 0.03          # per leg, each way
SHORT_EM = 1.0       # short strikes at 1.0x the trailing-vol expected move
WING_EM = 2.0        # long wings at 2.0x


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open('newscache.json'))
EV = []
for s, D in cache.items():
    bars, cnt = D['bars'], D['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 12):
        if datetime.date.fromisoformat(dts[i]).weekday() != 0:
            continue
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        j = None
        for k2 in range(i + 5, min(i + 12, n)):
            if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
                j = k2
                break
        if j is None:
            continue
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        if rv <= 0:
            continue
        em = px[i] * rv / math.sqrt(252) * math.sqrt(j - i)
        EV.append(dict(sym=s, i=i, j=j, date=dts[i], nz=(counts[i] - mu) / sd,
                       spot=float(px[i]), settle=float(px[j]), rv=rv, em=float(em),
                       exp=datetime.date.fromisoformat(dts[j])))
print(f'weekly events: {len(EV)}  symbols: {len(set(e["sym"] for e in EV))}')


def occ(sym, exp, cp, k):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


def near_strikes(target, spot):
    out = set()
    for inc in (1.0, 2.5, 5.0):
        b = round(target / inc) * inc
        for d in (-1, 0, 1):
            v = b + d * inc
            if v > spot * 0.5:
                out.add(round(v, 2))
    return sorted(out)


need = set()
for e in EV:
    for tgt, cp in ((e['spot'] + SHORT_EM * e['em'], 'C'),
                    (e['spot'] + WING_EM * e['em'], 'C'),
                    (e['spot'] - SHORT_EM * e['em'], 'P'),
                    (e['spot'] - WING_EM * e['em'], 'P')):
        for kk in near_strikes(tgt, e['spot']):
            need.add(occ(e['sym'], e['exp'], cp, kk))
need = sorted(need)
print(f'contracts: {len(need)}')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(x[-15:-13]), int(x[-13:-11]), int(x[-11:-9]))
                   for x in ch})
    u = ('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
         f'&timeframe=1Day&start={(min(exps)-datetime.timedelta(days=25)).isoformat()}'
         f'&end={(max(exps)+datetime.timedelta(days=1)).isoformat()}&limit=10000')
    d = q(u)
    if d and d.get('bars'):
        for sy, rows in d['bars'].items():
            for r in rows:
                PX[(sy, r['t'][:10])] = r['c']
    if (b // B) % 60 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}\n')


def pick(sym, exp, cp, target, d0, spot):
    best = None
    for kk in near_strikes(target, spot):
        p = PX.get((occ(sym, exp, cp, kk), d0))
        if p and p > 0:
            if best is None or abs(kk - target) < abs(best[0] - target):
                best = (kk, p)
    return best


TR = []
for e in EV:
    d0 = e['date']
    sc = pick(e['sym'], e['exp'], 'C', e['spot'] + SHORT_EM * e['em'], d0, e['spot'])
    lc = pick(e['sym'], e['exp'], 'C', e['spot'] + WING_EM * e['em'], d0, e['spot'])
    sp = pick(e['sym'], e['exp'], 'P', e['spot'] - SHORT_EM * e['em'], d0, e['spot'])
    lp = pick(e['sym'], e['exp'], 'P', e['spot'] - WING_EM * e['em'], d0, e['spot'])
    if None in (sc, lc, sp, lp):
        continue
    if not (lp[0] < sp[0] < sc[0] < lc[0]):
        continue
    mid_credit = (sc[1] + sp[1]) - (lc[1] + lp[1])
    if mid_credit <= 0:
        continue
    credit = mid_credit - 4 * SLIP          # SHORT condor: receive less
    debit = mid_credit + 4 * SLIP           # LONG condor: pay more
    ST = e['settle']
    payout = (max(ST - sc[0], 0) - max(ST - lc[0], 0)
              + max(sp[0] - ST, 0) - max(lp[0] - ST, 0))
    maxloss = max(lc[0] - sc[0], sp[0] - lp[0]) - credit
    TR.append(dict(sym=e['sym'], date=d0, nz=e['nz'], rv=e['rv'],
                   pnl=(credit - payout) * 100,
                   pnl_long=(payout - debit) * 100,
                   credit=credit * 100, maxloss=maxloss * 100,
                   ret=(credit - payout) / maxloss if maxloss > 0 else np.nan))
print(f'tradeable events: {len(TR)}\n')
if len(TR) < 200:
    print('insufficient'); sys.exit()


def stat(v, lab):
    v = np.array([x for x in v if np.isfinite(x)])
    if len(v) < 30:
        print(f'{lab:<28} {len(v):>5}  (thin)')
        return
    m, sd = v.mean(), v.std(ddof=1)
    t = m / (sd / math.sqrt(len(v)))
    eq = np.cumsum(v)
    dd = float(np.min(eq - np.maximum.accumulate(eq)))
    print(f'{lab:<28} {len(v):>5} {v.sum():>10.0f} {m:>8.1f} {t:>7.2f} '
          f'{(v>0).mean()*100:>6.1f}% {v.min():>9.0f} {dd:>9.0f}')


print('=' * 100)
print('0. SHORT vs LONG (the inverse) — slippage charged to BOTH sides')
print('=' * 100)
print(f'{"direction":<28} {"n":>5} {"total $":>10} {"mean":>8} {"t":>7} {"win%":>7} '
      f'{"worst":>9} {"maxDD":>9}')
stat([t['pnl'] for t in TR], 'SHORT condor (sell prem)')
stat([t['pnl_long'] for t in TR], 'LONG condor (buy prem)')
for yr in ('2024','2025','2026'):
    stat([t['pnl_long'] for t in TR if t['date'][:4]==yr], f'  LONG {yr}')
    stat([t['pnl'] for t in TR if t['date'][:4]==yr], f'  SHORT {yr}')
print()
print('  note: the long side is NOT simply the negative of the short side -')
print('  4 legs x $0.03 x 100 = $12/trade of slippage is charged AGAINST whichever side you take.')
print()

print('=' * 100)
print('1. DOES THE NEWS SCREEN HELP?  iron condor, short 1.0 EM / wings 2.0 EM')
print('=' * 100)
print(f'{"screen":<28} {"n":>5} {"total $":>10} {"mean":>8} {"t":>7} {"win%":>7} '
      f'{"worst":>9} {"maxDD":>9}')
stat([t['pnl'] for t in TR], 'ALL (no screen)')
for lab, sel in (('nz < -0.5 (very quiet)', lambda t: t['nz'] < -0.5),
                 ('nz < 0 (quiet)', lambda t: t['nz'] < 0),
                 ('nz < 0.5', lambda t: t['nz'] < 0.5),
                 ('nz < 1.0', lambda t: t['nz'] < 1.0),
                 ('nz >= 1.0 (noisy) EXCLUDED', lambda t: t['nz'] >= 1.0),
                 ('nz >= 2.0 (spike)', lambda t: t['nz'] >= 2.0)):
    stat([t['pnl'] for t in TR if sel(t)], lab)

print('\n' + '=' * 100)
print('2. RETURN ON RISK (normalises across names with different premium sizes)')
print('=' * 100)
print(f'{"screen":<28} {"n":>5} {"mean ret/risk":>14} {"t":>7} {"win%":>7}')
for lab, sel in (('ALL', lambda t: True),
                 ('nz < 0', lambda t: t['nz'] < 0),
                 ('nz < 1.0', lambda t: t['nz'] < 1.0),
                 ('nz >= 1.0', lambda t: t['nz'] >= 1.0)):
    v = np.array([t['ret'] for t in TR if sel(t) and np.isfinite(t['ret'])])
    if len(v) < 30:
        continue
    t_ = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    print(f'{lab:<28} {len(v):>5} {v.mean():>14.4f} {t_:>7.2f} {(v>0).mean()*100:>6.1f}%')

print('\n' + '=' * 100)
print('3. PER-SYMBOL (screened: nz < 1.0)')
print('=' * 100)
print(f'{"sym":>7} {"n":>5} {"total $":>10} {"mean":>8} {"t":>7} {"win%":>7}')
bysym = defaultdict(list)
for t in TR:
    if t['nz'] < 1.0:
        bysym[t['sym']].append(t['pnl'])
pos = 0
for s, v in sorted(bysym.items()):
    v = np.array(v)
    if len(v) < 25:
        print(f'{s:>7} {len(v):>5}  (thin)')
        continue
    t_ = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    pos += 1 if v.mean() > 0 else 0
    print(f'{s:>7} {len(v):>5} {v.sum():>10.0f} {v.mean():>8.1f} {t_:>7.2f} '
          f'{(v>0).mean()*100:>6.1f}%')
print(f'\nprofitable in {pos} of {len([1 for s,v in bysym.items() if len(v)>=25])} symbols')

print('\n' + '=' * 100)
print('4. YEAR BY YEAR (screened nz < 1.0) — is it decaying like the SPY premium?')
print('=' * 100)
print(f'{"year":>7} {"n":>5} {"total $":>10} {"mean":>8} {"t":>7}')
for yr in ('2024', '2025', '2026'):
    v = np.array([t['pnl'] for t in TR if t['nz'] < 1.0 and t['date'][:4] == yr])
    if len(v) < 25:
        continue
    t_ = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    print(f'{yr:>7} {len(v):>5} {v.sum():>10.0f} {v.mean():>8.1f} {t_:>7.2f}')

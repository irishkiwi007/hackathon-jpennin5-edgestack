"""How long do the IV gains last after a news-coverage spike - and do they decay FASTER or SLOWER
than the realised-vol gains?

This is the question that could still produce a trade. Already established:
    realised elevation decays  1.935 -> 1.704 -> 1.570 -> 1.382 -> 1.193 -> 1.121  (f1..f20)
If IV decays FASTER than that, buying premium a few days after the spike is favourable.
If IV decays SLOWER, selling at a lag is favourable.
If they decay together, there is nothing.

Method: for each spike day pick ONE expiry ~4 weeks out, then track that straddle's annualised
implied vol as it ages. One contract fetch yields the whole daily series.

    IV_t = (straddle_t / spot_t) / (0.8 * sqrt(DTE_t / 252))
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time, random
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
LOOK = 20
random.seed(5)


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


cache = json.load(open('newscache.json'))
CAND = []
for s, D in cache.items():
    bars, cnt = D['bars'], D['cnt']
    dts = [b['t'] for b in bars]
    px = np.array([b['c'] for b in bars])
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    n = len(px)
    for i in range(LOOK + 6, n - 25):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        CAND.append(dict(sym=s, i=i, date=dts[i], nz=(counts[i] - mu) / sd,
                         dts=dts, px=px))

spikes = [c for c in CAND if c['nz'] >= 2.0]
ctrl = [c for c in CAND if abs(c['nz']) < 0.5]
random.shuffle(ctrl)
SAMPLE = spikes + ctrl[:len(spikes)]
print(f'spike (nz>=2): {len(spikes)}   control (|nz|<0.5): {len(SAMPLE)-len(spikes)}')


def occ(sym, exp, cp, k):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


def grid(spot):
    out = set()
    for inc in (1.0, 2.5, 5.0):
        b = round(spot / inc) * inc
        for k in (-1, 0, 1):
            if b + k * inc > 0:
                out.add(round(b + k * inc, 2))
    return sorted(out)


plan, need = [], set()
for c in SAMPLE:
    dts, i, px = c['dts'], c['i'], c['px']
    # expiry ~4 weeks out so there is room to track 10 sessions
    j = None
    for k2 in range(i + 18, min(i + 28, len(dts))):
        if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
            j = k2
            break
    if j is None:
        continue
    exp = datetime.date.fromisoformat(dts[j])
    ks = grid(float(px[i]))
    plan.append(dict(c=c, exp=exp, ks=ks, jexp=j))
    for kk in ks:
        need.add(occ(c['sym'], exp, 'C', kk))
        need.add(occ(c['sym'], exp, 'P', kk))
need = sorted(need)
print(f'plan {len(plan)} events, {len(need)} contracts')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(x[-15:-13]), int(x[-13:-11]), int(x[-11:-9]))
                   for x in ch})
    u = ('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
         f'&timeframe=1Day&start={(min(exps)-datetime.timedelta(days=45)).isoformat()}'
         f'&end={(max(exps)+datetime.timedelta(days=1)).isoformat()}&limit=10000')
    d = q(u)
    if d and d.get('bars'):
        for sy, rows in d['bars'].items():
            for r in rows:
                PX[(sy, r['t'][:10])] = r['c']
    if (b // B) % 40 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}\n')

OFF = [0, 1, 2, 3, 5, 10]
res = defaultdict(lambda: defaultdict(list))
for p in plan:
    c = p['c']
    dts, i, px = c['dts'], c['i'], c['px']
    grp = 'spike' if c['nz'] >= 2.0 else 'control'
    # lock the strike using day 0
    strike = None
    for kk in p['ks']:
        if PX.get((occ(c['sym'], p['exp'], 'C', kk), dts[i])) and \
           PX.get((occ(c['sym'], p['exp'], 'P', kk), dts[i])):
            if strike is None or abs(kk - px[i]) < abs(strike - px[i]):
                strike = kk
    if strike is None or abs(strike - px[i]) / px[i] > 0.03:
        continue
    # baseline IV: same contract 5 sessions BEFORE the event
    def iv_at(idx):
        if idx < 0 or idx >= len(dts):
            return None
        d0 = dts[idx]
        cc = PX.get((occ(c['sym'], p['exp'], 'C', strike), d0))
        pp = PX.get((occ(c['sym'], p['exp'], 'P', strike), d0))
        if not cc or not pp or cc <= 0 or pp <= 0:
            return None
        dte = p['jexp'] - idx
        if dte < 4:
            return None
        return (cc + pp) / px[idx] / (0.8 * math.sqrt(dte / 252))
    base = iv_at(i - 5)
    if base is None or base <= 0:
        continue
    for o in OFF:
        v = iv_at(i + o)
        if v:
            res[grp][o].append(v / base)

print('=' * 96)
print('IMPLIED VOL AFTER A COVERAGE SPIKE — relative to the same contract 5 days prior')
print('=' * 96)
print(f'{"offset":>8} | ' + ' '.join(f'{g:>22}' for g in ('spike (nz>=2)', 'control (|nz|<0.5)')))
print(f'{"":>8} | ' + ' '.join(f'{"n":>6}{"IV ratio":>10}{"":>6}' for _ in range(2)))
for o in OFF:
    cells = []
    for g in ('spike', 'control'):
        v = res[g][o]
        cells.append(f'{len(v):>6}{np.mean(v):>10.3f}{"":>6}' if len(v) > 20
                     else f'{len(v):>6}{"-":>10}{"":>6}')
    print(f'{("t+" + str(o)):>8} | ' + ' '.join(cells))

print('\n' + '=' * 96)
print('THE COMPARISON THAT MATTERS — IV decay vs REALISED decay')
print('=' * 96)
REAL = {0: None, 1: 1.935, 2: 1.704, 3: 1.570, 5: 1.382, 10: 1.193}
print(f'{"offset":>8} {"IV elevation":>14} {"realised elevation":>20} {"IV / realised":>15} '
      f'{"reading":>22}')
sp0 = np.mean(res['spike'][0]) if len(res['spike'][0]) > 20 else None
for o in OFF:
    v = res['spike'][o]
    c_ = res['control'][o]
    if len(v) < 20 or len(c_) < 20 or REAL.get(o) is None:
        continue
    iv_el = np.mean(v) / np.mean(c_)
    rl = REAL[o]
    rat = iv_el / rl
    rd = ('IV cheap vs realised' if rat < 0.93 else
          'IV rich vs realised' if rat > 1.07 else 'in line')
    print(f'{("t+" + str(o)):>8} {iv_el:>14.3f} {rl:>20.3f} {rat:>15.3f} {rd:>22}')
print("""
IV elevation = spike-group IV ratio divided by control-group IV ratio (controls for general drift).
realised elevation comes from the earlier decay table (|f1|..|f10| for nz>3).
IV/realised < 1 means implied is not keeping up with what actually happens -> buying favoured.
IV/realised > 1 means implied is over-compensating -> selling favoured.""")

print('\n' + '=' * 96)
print('HALF-LIFE')
print('=' * 96)
for g in ('spike', 'control'):
    xs = [(o, np.mean(res[g][o])) for o in OFF if len(res[g][o]) > 20]
    if len(xs) < 4:
        continue
    peak = xs[0][1]
    print(f'{g:>8}: ' + '  '.join(f't+{o}={v:.3f}' for o, v in xs))

"""VIEW B — implied volatility aligned to the MINUTE an article printed.

News timestamps carry second precision; option minute bars exist. So the response can be measured
directly: recompute implied volatility every minute from that minute's spot and option price, align
every event to its article timestamp, and average.

Sparsity is the real constraint - a liquid ATM option trades in maybe half the minutes of a session
- so this uses the most liquid names and forward-fills within a tight window.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K_ = os.environ['ALPACA_API_KEY']
S_ = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K_, 'APCA-API-SECRET-KEY': S_}
RATE = 0.045
SYMS = ['NVDA', 'TSLA', 'AMD', 'AAPL', 'AMZN']
WIN = 90          # minutes either side
DAYS = 45         # sessions sampled


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.0)
    return None


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(S, K, T, r, sig, cp):
    if sig <= 0 or T <= 0:
        return max(0.0, (S - K) if cp == 'C' else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if cp == 'C':
        return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)
    return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)


def iv(price, S, K, T, r, cp):
    intr = max(0.0, (S - K * math.exp(-r * T)) if cp == 'C' else (K * math.exp(-r * T) - S))
    if price <= intr + 1e-6 or T <= 0:
        return None
    lo, hi = 1e-4, 5.0
    if bs(S, K, T, r, hi, cp) < price:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs(S, K, T, r, mid, cp) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def occ(sym, exp, cp, k):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


def grid_strikes(spot):
    out = set()
    for inc in (1.0, 2.5, 5.0):
        b = round(spot / inc) * inc
        for k in (-1, 0, 1):
            if b + k * inc > 0:
                out.add(round(b + k * inc, 2))
    return sorted(out)


cache = json.load(open('newscache.json'))
# recent sessions with data
days = sorted({d for s in SYMS if s in cache for d in
               [b['t'] for b in cache[s]['bars']] if d >= '2026-03-01'})[-DAYS:]
print(f'sessions: {len(days)}  {days[0]} -> {days[-1]}')

REL = defaultdict(list)     # minute offset -> list of iv ratios
nev = 0
for di, day in enumerate(days):
    for sym in SYMS:
        if sym not in cache:
            continue
        bars = cache[sym]['bars']
        dts = [b['t'] for b in bars]
        if day not in dts:
            continue
        i = dts.index(day)
        px_close = bars[i]['c']
        # next Friday expiry
        j = None
        for k2 in range(i + 3, min(i + 12, len(dts))):
            if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
                j = k2
                break
        if j is None:
            continue
        exp = datetime.date.fromisoformat(dts[j])
        # articles that day, RTH only
        nw = q(f'https://data.alpaca.markets/v1beta1/news?symbols={sym}'
               f'&start={day}T14:00:00Z&end={day}T19:00:00Z&limit=50')
        arts = [a for a in (nw or {}).get('news', [])] if nw else []
        if not arts:
            continue
        sm = q(f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&feed=sip'
               f'&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000&adjustment=all')
        if not sm or not sm.get('bars'):
            continue
        spot_by = {b['t'][11:16]: b['c'] for b in sm['bars']}
        ks = grid_strikes(px_close)
        syms = [occ(sym, exp, cp, k) for k in ks for cp in ('C', 'P')]
        om = defaultdict(dict)
        for z in range(0, len(syms), 20):
            d2 = q('https://data.alpaca.markets/v1beta1/options/bars?symbols=' +
                   ','.join(syms[z:z + 20]) +
                   f'&timeframe=1Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000')
            if d2 and d2.get('bars'):
                for sy, rows in d2['bars'].items():
                    for r in rows:
                        om[sy][r['t'][11:16]] = r['c']
        best, bn = None, 0
        for k in ks:
            n2 = min(len(om.get(occ(sym, exp, 'C', k), {})),
                     len(om.get(occ(sym, exp, 'P', k), {})))
            if n2 > bn:
                best, bn = k, n2
        if best is None or bn < 50:
            continue
        c_, p_ = occ(sym, exp, 'C', best), occ(sym, exp, 'P', best)
        T0 = (exp - datetime.date.fromisoformat(day)).days / 365.0

        def iv_at(hm):
            S = spot_by.get(hm)
            c = om[c_].get(hm)
            p = om[p_].get(hm)
            if S is None or c is None or p is None:
                return None
            a = iv(c, S, best, T0, RATE, 'C')
            b = iv(p, S, best, T0, RATE, 'P')
            vs = [x for x in (a, b) if x and 0.03 < x < 4.0]
            return sum(vs) / len(vs) if vs else None

        for a in arts:
            t = datetime.datetime.fromisoformat(a['created_at'].replace('Z', '+00:00'))
            # baseline = mean iv over t-90..t-30
            base = []
            for m in range(-WIN, -29):
                hm = (t + datetime.timedelta(minutes=m)).strftime('%H:%M')
                v = iv_at(hm)
                if v:
                    base.append(v)
            if len(base) < 12:
                continue
            b0 = float(np.mean(base))
            if b0 <= 0:
                continue
            got = 0
            for m in range(-WIN, WIN + 1):
                hm = (t + datetime.timedelta(minutes=m)).strftime('%H:%M')
                v = iv_at(hm)
                if v:
                    REL[m].append(v / b0)
                    got += 1
            if got > 40:
                nev += 1
    if (di + 1) % 10 == 0:
        print(f'  {di+1}/{len(days)} sessions, {nev} events')

print(f'\nevents with usable coverage: {nev}')
if nev < 20:
    print('insufficient'); sys.exit()

print('\n' + '=' * 96)
print('IMPLIED VOLATILITY vs MINUTES FROM THE ARTICLE PRINT')
print('  (1.000 = the t-90..t-30 baseline for that event)')
print('=' * 96)
print(f'{"minute":>8} {"n":>6} {"IV ratio":>10} {"change vs t-1":>15}')
prev = None
for m in list(range(-90, -20, 10)) + list(range(-20, 21, 2)) + list(range(25, 91, 10)):
    v = REL.get(m, [])
    if len(v) < 15:
        continue
    mm = float(np.mean(v))
    ch = '' if prev is None else f'{mm-prev:+15.4f}'
    print(f'{m:>+8} {len(v):>6} {mm:>10.4f} {ch:>15}')
    prev = mm

print('\n' + '=' * 96)
print('STEP OR RAMP?')
print('=' * 96)
def seg(a, b):
    vals = [np.mean(REL[m]) for m in range(a, b + 1) if len(REL.get(m, [])) >= 15]
    return float(np.mean(vals)) if vals else float('nan')
pre_far, pre_near = seg(-90, -31), seg(-30, -1)
post_imm, post_near, post_far = seg(0, 5), seg(6, 30), seg(31, 90)
print(f'  t-90..t-31 : {pre_far:.4f}')
print(f'  t-30..t-1  : {pre_near:.4f}   ({pre_near-pre_far:+.4f} vs earlier)')
print(f'  t+0..t+5   : {post_imm:.4f}   ({post_imm-pre_near:+.4f} <-- the instant response)')
print(f'  t+6..t+30  : {post_near:.4f}   ({post_near-post_imm:+.4f})')
print(f'  t+31..t+90 : {post_far:.4f}   ({post_far-post_near:+.4f})')
print("""
  Large jump at t+0..t+5 with flat wings  => STEP: the print is the event.
  Steady climb across all segments        => RAMP: it builds regardless of the print.
  Rise BEFORE t=0                         => the market moves first; the headline reports.""")

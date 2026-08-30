"""WHEN does implied volatility expand - at the moment the article prints, or gradually?

Minute option bars exist and news timestamps carry second precision, so this is directly
measurable. Two views:

  VIEW A: intraday implied-volatility path on news-volume-spike days vs control days, aligned to
          the session open. Shows whether the day's expansion is a step or a ramp.
  VIEW B: event study aligned to individual ARTICLE timestamps, minute by minute.

Implied volatility is recomputed each minute by Black-Scholes inversion using that minute's spot,
so the curve is not contaminated by the underlying simply moving.
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time, random
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K_ = os.environ['ALPACA_API_KEY']
S_ = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K_, 'APCA-API-SECRET-KEY': S_}
RATE = 0.045
LOOK = 20
random.seed(2)
SYMS = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'AMZN', 'META', 'MSFT', 'SPY']


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


# ---- pick spike and control days from the cached news counts ----
cache = json.load(open('newscache.json'))
EV = []
for s in SYMS:
    if s not in cache:
        continue
    D = cache[s]
    dts = [b['t'] for b in D['bars']]
    counts = np.array([D['cnt'].get(d, 0) for d in dts], dtype=float)
    px = np.array([b['c'] for b in D['bars']])
    n = len(dts)
    for i in range(LOOK + 6, n - 12):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        nz = (counts[i] - mu) / sd
        # only recent enough that minute option data exists, and a Friday expiry ahead
        if dts[i] < '2025-01-01':
            continue
        j = None
        for k2 in range(i + 3, min(i + 12, n)):
            if datetime.date.fromisoformat(dts[k2]).weekday() == 4:
                j = k2
                break
        if j is None:
            continue
        EV.append(dict(sym=s, date=dts[i], nz=nz, spot=float(px[i]),
                       exp=datetime.date.fromisoformat(dts[j])))

sp = sorted([e for e in EV if e['nz'] >= 2.0], key=lambda e: -e['nz'])[:60]
ct = [e for e in EV if abs(e['nz']) < 0.5]
random.shuffle(ct)
ct = ct[:60]
print(f'spike days {len(sp)}, control days {len(ct)}')


def strikes_near(spot):
    out = set()
    for inc in (1.0, 2.5, 5.0):
        b = round(spot / inc) * inc
        for k in (-1, 0, 1):
            if b + k * inc > 0:
                out.add(round(b + k * inc, 2))
    return sorted(out)


def occ(sym, exp, cp, k):
    return f'{sym}{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


def minute_stock(sym, day):
    d = q(f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&feed=sip'
          f'&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000&adjustment=all')
    if not d:
        return {}
    return {b['t'][11:16]: b['c'] for b in (d.get('bars') or [])}


def minute_opt(syms, day):
    out = defaultdict(dict)
    for i in range(0, len(syms), 20):
        ch = syms[i:i + 20]
        d = q('https://data.alpaca.markets/v1beta1/options/bars?symbols=' + ','.join(ch) +
              f'&timeframe=1Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=10000')
        if d and d.get('bars'):
            for sy, rows in d['bars'].items():
                for r in rows:
                    out[sy][r['t'][11:16]] = r['c']
    return out


GRID = [f'{13 + (m // 60):02d}:{m % 60:02d}' for m in range(30, 30 + 391)]
GRID = []
t0 = datetime.datetime(2000, 1, 1, 13, 30)
for k in range(391):
    GRID.append((t0 + datetime.timedelta(minutes=k)).strftime('%H:%M'))


def curve(e):
    sm = minute_stock(e['sym'], e['date'])
    if len(sm) < 200:
        return None
    ks = strikes_near(e['spot'])
    syms = [occ(e['sym'], e['exp'], cp, k) for k in ks for cp in ('C', 'P')]
    om = minute_opt(syms, e['date'])
    # choose the strike with the most minute coverage on both legs
    best, bestn = None, 0
    for k in ks:
        c_, p_ = occ(e['sym'], e['exp'], 'C', k), occ(e['sym'], e['exp'], 'P', k)
        nn = min(len(om.get(c_, {})), len(om.get(p_, {})))
        if nn > bestn:
            best, bestn = k, nn
    if best is None or bestn < 60:
        return None
    c_, p_ = occ(e['sym'], e['exp'], 'C', best), occ(e['sym'], e['exp'], 'P', best)
    T0 = (e['exp'] - datetime.date.fromisoformat(e['date'])).days / 365.0
    out, lastS, lastC, lastP = [], None, None, None
    for idx, hm in enumerate(GRID):
        lastS = sm.get(hm, lastS)
        lastC = om[c_].get(hm, lastC)
        lastP = om[p_].get(hm, lastP)
        if lastS is None or lastC is None or lastP is None:
            out.append(None)
            continue
        # FIX: a session spans 6.5h = 0.271 calendar days, not 1.0. The original decayed a
        # full day across the session, overstating theta ~3.7x and inflating implied volatility.
        T = max(T0 - (idx / 390.0) * (6.5 / 24.0) / 365.0, 1e-4)
        a = iv(lastC, lastS, best, T, RATE, 'C')
        b = iv(lastP, lastS, best, T, RATE, 'P')
        vs = [x for x in (a, b) if x and 0.03 < x < 4.0]
        out.append(sum(vs) / len(vs) if vs else None)
    return out


print('\nbuilding intraday implied-volatility curves...')
def collect(evs, lab):
    cur = []
    for i, e in enumerate(evs):
        c = curve(e)
        if c and sum(1 for x in c if x) > 200:
            cur.append(c)
        if (i + 1) % 15 == 0:
            print(f'  {lab} {i+1}/{len(evs)}  usable {len(cur)}')
    return cur


SP = collect(sp, 'spike')
CT = collect(ct, 'control')
print(f'usable curves: spike {len(SP)}, control {len(CT)}')
json.dump({'spike': SP, 'control': CT}, open('ivcurves_fixed.json', 'w'))


def norm_avg(curves):
    """normalise each curve by its own 09:30-10:00 average, then average across events"""
    rows = []
    for c in curves:
        base = [x for x in c[0:30] if x]
        if len(base) < 8:
            continue
        b = float(np.mean(base))
        if b <= 0:
            continue
        rows.append([(x / b) if x else np.nan for x in c])
    if not rows:
        return None
    A = np.array(rows, dtype=float)
    return np.nanmean(A, axis=0), len(rows)


rs, ns = norm_avg(SP)
rc, nc = norm_avg(CT)
print('\n' + '=' * 96)
print('VIEW A — intraday implied volatility, normalised to the 09:30-10:00 average')
print('=' * 96)
print(f'{"ET time":>9} {"spike":>9} {"control":>9} {"spike-control":>15}')
for k in range(0, 391, 15):
    hm = GRID[k]
    et = (datetime.datetime.strptime(hm, '%H:%M') - datetime.timedelta(hours=4)).strftime('%H:%M')
    if k < len(rs) and k < len(rc):
        print(f'{et:>9} {rs[k]:>9.4f} {rc[k]:>9.4f} {rs[k]-rc[k]:>+15.4f}')
print(f'\nspike curves n={ns}, control n={nc}')
print("""
A STEP at one minute = the expansion is an event. A steady RAMP = it builds through the session.""")

"""Long call vs call debit spread on the capitulation signal - with real option prices.

Plus the specific hypothesis: in a fear moment, equity skew steepens - PUTS get bid up hard while
CALLS lag. So the call we actually buy may be cheap relative to the headline volatility. If true,
the outright call is the better structure; if call IV is elevated too, the spread wins by selling
some of that back.

Alpaca options history starts Feb 2024, so this runs on tier events since then.
One API call per event (all legs, both dates in one range request) to keep it fast.
"""
import os
import json, os, sys, io, math, time, urllib.request, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
RATE = 0.045
HOLD = 3


def q(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.6)
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
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bs(S, K, T, r, mid, cp) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def occ(sym, exp, cp, k):
    return '{}{:%y%m%d}{}{:08d}'.format(sym, exp, cp, int(round(k * 1000)))


def inc_for(spot):
    return 1.0 if spot < 50 else (2.5 if spot < 200 else 5.0)


# ---------- build the event list from cached daily bars ----------
BARS = {}
for f in ('wide_bars.json', 'single_bars.json'):
    if os.path.exists(f):
        BARS.update(json.load(open(f)))
print('symbols with daily bars: {}'.format(len(BARS)))

EV, CTRL = [], []
for s, b in BARS.items():
    if len(b) < 900:
        continue
    c = np.array([x['c'] for x in b])
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / np.maximum(c[:-1], 1e-9))
    for i in range(25, n - HOLD - 1):
        if dt[i] < '2024-02-15':
            continue
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        rec = dict(sym=s, i=i, date=dt[i], spot=float(c[i]), stretch=st, volx=vx,
                   exit_date=dt[i + HOLD], S_T=float(c[i + HOLD]), rv=float(rv))
        if st < -2.5 and vx > 1.4:
            EV.append(rec)
        elif abs(st) < 0.5 and 0.8 < vx < 1.2:
            CTRL.append(rec)

EV.sort(key=lambda e: e['date'])
np.random.default_rng(7).shuffle(CTRL)
CTRL = CTRL[:500]
print('signal events since 2024-02: {}   control days sampled: {}'.format(len(EV), len(CTRL)))


def next_friday(d, mindays=8):
    d0 = datetime.date.fromisoformat(d)
    x = d0 + datetime.timedelta(days=mindays)
    while x.weekday() != 4:
        x += datetime.timedelta(days=1)
    return x


def legs_for(e):
    inc = inc_for(e['spot'])
    k_atm = round(e['spot'] / inc) * inc
    k_otm = round(e['spot'] * 1.03 / inc) * inc
    if k_otm <= k_atm:
        k_otm = k_atm + inc
    return k_atm, k_otm


def fetch(e):
    """One request: both call strikes, entry..exit window."""
    exp = next_friday(e['date'])
    ka, ko = legs_for(e)
    syms = [occ(e['sym'], exp, 'C', ka), occ(e['sym'], exp, 'C', ko),
            occ(e['sym'], exp, 'P', ka)]
    end = (datetime.date.fromisoformat(e['exit_date']) + datetime.timedelta(days=1)).isoformat()
    d = q('https://data.alpaca.markets/v1beta1/options/bars?symbols={}&timeframe=1Day'
          '&start={}&end={}&limit=200'.format(','.join(syms), e['date'], end))
    if not d or not d.get('bars'):
        return None
    out = {}
    for sy, rows in d['bars'].items():
        out[sy] = {x['t'][:10]: float(x['c']) for x in rows}
    return dict(exp=exp, ka=ka, ko=ko, syms=syms, px=out)


def evaluate(events, label, limit=400):
    res = []
    done = 0
    for e in events[:limit]:
        f = fetch(e)
        done += 1
        if done % 50 == 0:
            print('   {} {}/{}  usable {}'.format(label, done, min(limit, len(events)), len(res)))
        if not f:
            continue
        ca, co, pa = f['syms']
        d0, d1 = e['date'], e['exit_date']
        if d0 not in f['px'].get(ca, {}) or d1 not in f['px'].get(ca, {}):
            continue
        entry_a = f['px'][ca][d0]
        exit_a = f['px'][ca][d1]
        if entry_a <= 0.05:
            continue
        T = (f['exp'] - datetime.date.fromisoformat(d0)).days / 365.0
        civ = iv(entry_a, e['spot'], f['ka'], T, RATE, 'C')
        piv = None
        if d0 in f['px'].get(pa, {}) and f['px'][pa][d0] > 0.05:
            piv = iv(f['px'][pa][d0], e['spot'], f['ka'], T, RATE, 'P')
        row = dict(sym=e['sym'], date=d0, stretch=e['stretch'], volx=e['volx'],
                   civ=civ, piv=piv, rv_ann=e['rv'] * math.sqrt(252),
                   call_pl=(exit_a - entry_a) * 100.0, call_cost=entry_a * 100.0,
                   call_ret=(exit_a - entry_a) / entry_a)
        # debit spread: long ATM, short +3%
        if d0 in f['px'].get(co, {}) and d1 in f['px'].get(co, {}):
            e0, e1 = f['px'][co][d0], f['px'][co][d1]
            deb = (entry_a - e0) * 100.0
            if deb > 5.0:
                row['sp_pl'] = ((exit_a - e1) - (entry_a - e0)) * 100.0
                row['sp_cost'] = deb
                row['sp_ret'] = row['sp_pl'] / deb
        res.append(row)
    return res


print('\nfetching option prices...')
SIG = evaluate(EV, 'signal')
CON = evaluate(CTRL, 'control', limit=250)
json.dump({'sig': SIG, 'con': CON}, open('optstruct_out.json', 'w'))
print('\nusable: signal {}  control {}'.format(len(SIG), len(CON)))


def summ(rows, key_pl, key_cost, key_ret):
    g = [r for r in rows if key_pl in r and r[key_pl] is not None]
    if len(g) < 20:
        return None
    pl = np.array([r[key_pl] for r in g])
    cost = np.array([r[key_cost] for r in g])
    ret = np.array([r[key_ret] for r in g])
    return dict(n=len(g), pl=pl.mean(), t=pl.mean() / (pl.std(ddof=1) / math.sqrt(len(pl))),
                ret=ret.mean() * 100, win=(pl > 0).mean() * 100, cost=cost.mean(),
                total=pl.sum(), worst=pl.min())


print()
print('=' * 100)
print('1. THE IV HYPOTHESIS — is the CALL cheap in a fear moment?')
print('=' * 100)


def ivstat(rows, lab):
    cv = [r['civ'] for r in rows if r.get('civ')]
    pv = [r['piv'] for r in rows if r.get('piv')]
    rv = [r['rv_ann'] for r in rows if r.get('rv_ann')]
    both = [(r['civ'], r['piv'], r['rv_ann']) for r in rows
            if r.get('civ') and r.get('piv') and r.get('rv_ann')]
    if not both:
        return
    c_, p_, v_ = zip(*both)
    c_, p_, v_ = np.array(c_), np.array(p_), np.array(v_)
    print('  {:<22} n={:<5} call IV {:.3f}   put IV {:.3f}   skew(P-C) {:+.3f}   '
          'realized {:.3f}   callIV/RV {:.3f}'.format(
              lab, len(both), c_.mean(), p_.mean(), (p_ - c_).mean(), v_.mean(),
              (c_ / np.maximum(v_, 1e-6)).mean()))
    return c_, p_, v_


a = ivstat(SIG, 'SIGNAL (fear)')
b = ivstat(CON, 'CONTROL (calm)')
if a and b:
    sk_s = (a[1] - a[0])
    sk_c = (b[1] - b[0])
    ts = (sk_s.mean() - sk_c.mean()) / math.sqrt(sk_s.var(ddof=1) / len(sk_s)
                                                 + sk_c.var(ddof=1) / len(sk_c))
    rs = a[0] / np.maximum(a[2], 1e-6)
    rc = b[0] / np.maximum(b[2], 1e-6)
    tr = (rs.mean() - rc.mean()) / math.sqrt(rs.var(ddof=1) / len(rs) + rc.var(ddof=1) / len(rc))
    print()
    print('  skew (put IV - call IV)  signal {:+.3f} vs control {:+.3f}   t={:+.2f}'.format(
        sk_s.mean(), sk_c.mean(), ts))
    print('  call IV / realized vol   signal {:.3f} vs control {:.3f}   t={:+.2f}'.format(
        rs.mean(), rc.mean(), tr))
    print()
    print('  Skew wider on signal days => puts bid up more than calls, call relatively cheap.')
    print('  callIV/RV lower on signal days => the call is cheap vs what the stock actually does.')

print()
print('=' * 100)
print('2. STRUCTURE P&L — {} -day hold, one contract'.format(HOLD))
print('=' * 100)
print('{:<28} {:>6} {:>10} {:>9} {:>7} {:>8} {:>10} {:>9}'.format(
    'structure', 'n', 'mean $', 'cost $', 't', 'win%', 'return%', 'worst $'))
for lab, rows in (('SIGNAL  long ATM call', SIG), ('CONTROL long ATM call', CON)):
    s_ = summ(rows, 'call_pl', 'call_cost', 'call_ret')
    if s_:
        print('{:<28} {:>6} {:>10.1f} {:>9.1f} {:>7.2f} {:>7.1f}% {:>9.1f}% {:>9.0f}'.format(
            lab, s_['n'], s_['pl'], s_['cost'], s_['t'], s_['win'], s_['ret'], s_['worst']))
for lab, rows in (('SIGNAL  ATM/+3% spread', SIG), ('CONTROL ATM/+3% spread', CON)):
    s_ = summ(rows, 'sp_pl', 'sp_cost', 'sp_ret')
    if s_:
        print('{:<28} {:>6} {:>10.1f} {:>9.1f} {:>7.2f} {:>7.1f}% {:>9.1f}% {:>9.0f}'.format(
            lab, s_['n'], s_['pl'], s_['cost'], s_['t'], s_['win'], s_['ret'], s_['worst']))

print()
print('=' * 100)
print('3. BY VOLUME TIER  (signal days only)')
print('=' * 100)
print('{:<26} {:>6} {:>12} {:>7} {:>8} {:>12} {:>7} {:>8}'.format(
    'tier', 'n', 'call mean$', 't', 'win%', 'spread mean$', 't', 'win%'))
for lab, lo, hi in [('vol 1.4-1.8', 1.4, 1.8), ('vol 1.8-2.5', 1.8, 2.5), ('vol >2.5', 2.5, 1e9)]:
    g = [r for r in SIG if lo <= r['volx'] < hi]
    c_ = summ(g, 'call_pl', 'call_cost', 'call_ret')
    s_ = summ(g, 'sp_pl', 'sp_cost', 'sp_ret')
    line = '{:<26} {:>6}'.format(lab, len(g))
    line += ' {:>12.1f} {:>7.2f} {:>7.1f}%'.format(c_['pl'], c_['t'], c_['win']) if c_ else ' {:>12} {:>7} {:>8}'.format('-', '-', '-')
    line += ' {:>12.1f} {:>7.2f} {:>7.1f}%'.format(s_['pl'], s_['t'], s_['win']) if s_ else ' {:>12} {:>7} {:>8}'.format('-', '-', '-')
    print(line)

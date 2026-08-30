"""Validate the Black-Scholes premium model against REAL option prices.

The cash-secured put result rests entirely on modelled premiums: IV = trailing realized
volatility x 1.798. If that overstates what the market actually paid, the +$184/contract
evaporates. Alpaca has option history from Feb 2024, which covers a usable slice of the event
set, so the model can be checked directly.

For each recent capitulation event this fetches the actual ATM put that existed on that day and
compares the real traded price against what the model would have assumed.
"""
import os
import io, json, math, sys, time, datetime, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
DATA = 'https://data.alpaca.markets'
RATE, DTE_CAL, IVR = 0.045, 14, 1.798

_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

D2 = json.load(open('sp500_bars.json'))
FR = json.load(open('friction_screen.json'))


def q(u, tries=2):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.4)
    return None


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, T, r, sig):
    if sig <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - sig * math.sqrt(T))) - S * ncdf(-d1)


def implied(price, S, K, T, r):
    intr = max(0.0, K * math.exp(-r * T) - S)
    if price <= intr + 1e-6:
        return None
    lo, hi = 1e-4, 5.0
    if bs_put(S, K, T, r, hi) < price:
        return None
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        if bs_put(S, K, T, r, mid) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


SER = {}
for s in set(r['sym'] for r in EV):
    rows = D2.get(s) or []
    c = np.array([x['c'] for x in rows], float)
    if len(c) < 60 or (c <= 0).any():
        continue
    lr = np.zeros(len(c)); lr[1:] = np.log(c[1:] / c[:-1])
    SER[s] = (rows, c, lr, {rows[i]['t']: i for i in range(len(rows))})


def occ(sym, exp, k):
    return '{}{:%y%m%d}P{:08d}'.format(sym, exp, int(round(k * 1000)))


def next_friday(d, mindays=10):
    d0 = datetime.date.fromisoformat(d)
    x = d0 + datetime.timedelta(days=mindays)
    while x.weekday() != 4:
        x += datetime.timedelta(days=1)
    return x


def inc_for(s):
    return 1.0 if s < 50 else (2.5 if s < 200 else 5.0)


names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= 100}
cands = sorted([r for r in EV
                if r['sym'] in names and r['vol'] and r['date'] >= '2024-03-01'],
               key=lambda r: r['date'])
print('events since Feb 2024 in the tradeable, calm-regime set: {}'.format(len(cands)))

rows = []
for r in cands[:160]:
    sym, date, S = r['sym'], r['date'], r['spot']
    v = SER.get(sym)
    if not v:
        continue
    _, c, lr, idx = v
    i = idx.get(date)
    if i is None or i < 21:
        continue
    rv = lr[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
    if rv <= 0:
        continue
    exp = next_friday(date)
    inc = inc_for(S)
    K = round(S / inc) * inc
    o = occ(sym, exp, K)
    d = q('{}/v1beta1/options/bars?symbols={}&timeframe=1Day&start={}&end={}&limit=5'
          .format(DATA, o, date, date))
    bars = (d or {}).get('bars', {}).get(o) or []
    if not bars:
        continue
    real = float(bars[0]['c'])
    if real <= 0.02:
        continue
    T = (exp - datetime.date.fromisoformat(date)).days / 365.0
    model = bs_put(S, K, T, RATE, rv * IVR)
    real_iv = implied(real, S, K, T, RATE)
    if not real_iv:
        continue
    rows.append(dict(sym=sym, date=date, S=S, K=K, real=real, model=model,
                     rv=rv, real_iv=real_iv, ratio=real / model if model > 0 else 0,
                     iv_rv=real_iv / rv))
    if len(rows) % 20 == 0:
        print('  checked {}'.format(len(rows)))

print('\nvalidated on {} real contracts'.format(len(rows)))
if len(rows) < 15:
    print('insufficient overlap'); sys.exit()

real = np.array([r['real'] for r in rows])
model = np.array([r['model'] for r in rows])
ratio = np.array([r['ratio'] for r in rows])
ivrv = np.array([r['iv_rv'] for r in rows])

print()
print('=' * 96)
print('MODEL vs MARKET — was the assumed premium realistic?')
print('=' * 96)
print('  mean REAL premium   ${:.2f}/share'.format(real.mean()))
print('  mean MODEL premium  ${:.2f}/share'.format(model.mean()))
print('  real / model        {:.3f}   (median {:.3f})'.format(ratio.mean(), np.median(ratio)))
print()
print('  assumed IV/RV ratio : {:.3f}'.format(IVR))
print('  ACTUAL IV/RV ratio  : {:.3f}  (median {:.3f}, p25 {:.3f}, p75 {:.3f})'.format(
    ivrv.mean(), np.median(ivrv), np.percentile(ivrv, 25), np.percentile(ivrv, 75)))
print()
if ratio.mean() < 0.95:
    print('  >>> MODEL OVERSTATES the premium by {:.0%}. The cash-secured put result is'
          .format(1 - ratio.mean()))
    print('      inflated by roughly that much and must be rescaled.')
elif ratio.mean() > 1.05:
    print('  >>> MODEL UNDERSTATES the premium by {:.0%} - the result is conservative.'
          .format(ratio.mean() - 1))
else:
    print('  >>> MODEL IS ACCURATE to within 5%. The premium assumption holds.')

print()
print('  sample of individual contracts:')
print('  {:<12} {:<7} {:>9} {:>8} {:>9} {:>9} {:>8} {:>8}'.format(
    'date', 'sym', 'spot', 'strike', 'real $', 'model $', 'r/m', 'IV/RV'))
for r in rows[:14]:
    print('  {:<12} {:<7} {:>9.2f} {:>8.1f} {:>9.2f} {:>9.2f} {:>8.2f} {:>8.2f}'.format(
        r['date'], r['sym'], r['S'], r['K'], r['real'], r['model'], r['ratio'], r['iv_rv']))

print()
print('=' * 96)
print('RESCALED RESULT using the ACTUAL measured IV/RV')
print('=' * 96)
actual_ivr = float(np.median(ivrv))
print('  replacing assumed {:.3f} with measured {:.3f}'.format(IVR, actual_ivr))
scale = actual_ivr / IVR
print('  premium scales roughly linearly in IV, so premium x {:.3f}'.format(scale))
print()
print('  modelled signal-day P&L was +$184/contract with a +$137 random-day baseline.')
print('  Premium is the only positive term; the assignment loss is unchanged, so:')
for lab, base in (('signal days', 184.0), ('random days', 137.0)):
    prem_component = 300.0 if lab == 'signal days' else 260.0
    adj = base - prem_component * (1 - scale)
    print('    {:<14} {:+.0f} -> {:+.0f} $/contract'.format(lab, base, adj))
print()
print('  (indicative rescale only - the exact figure needs the full model rerun at the')
print('   measured ratio, but it bounds the direction and rough size of the correction)')

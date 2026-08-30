"""Cash-secured put, repriced correctly.

The previous run priced premiums from TODAY's chains - a calm tape. But this strategy sells puts
on panic days, when implied volatility is elevated (measured: ATM IV 0.652 on signal days vs
0.433 on calm days). That understates the premium received on exactly the days we trade, which
is why it showed put-selling as a -$63/contract loser - a result that contradicts the variance
risk premium and should not have been believed.

Fix: price each event with Black-Scholes using THAT event's own realized volatility, scaled by
the measured implied/realized ratio. Every event gets its own premium instead of one
market-wide constant.

  IV = RV_annualised x IV_RV_RATIO

IV_RV_RATIO is measured, not assumed: 1.798 on signal days (from the option-chain study), 1.671
on control days. Both are reported so the sensitivity is visible.
"""
import io, json, math, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

D2 = json.load(open('sp500_bars.json'))
FR = json.load(open('friction_screen.json'))
RATE = 0.045
DTE_CAL = 14           # ~10 trading sessions
IV_RV_SIGNAL = 1.798   # measured on news/panic days
IV_RV_CONTROL = 1.671  # measured on calm days
HALF_SPREAD_FRAC = {'ATM': 0.00057, '2% OTM': 0.00049,
                    '5% OTM': 0.00038, '8% OTM': 0.00032}   # of spot, live-measured


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, T, r, sig):
    if sig <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)


# realized volatility at each event, from the same bars the signal used
RV = {}
for s in set(r['sym'] for r in EV):
    rows = D2.get(s) or []
    c = np.array([x['c'] for x in rows], float)
    if len(c) < 40 or (c <= 0).any():
        continue
    lr = np.zeros(len(c))
    lr[1:] = np.log(c[1:] / c[:-1])
    idx = {rows[i]['t']: i for i in range(len(rows))}
    RV[s] = (lr, idx)


def rv_at(sym, date):
    v = RV.get(sym)
    if not v:
        return None
    lr, idx = v
    i = idx.get(date)
    if i is None or i < 21:
        return None
    sd = lr[i - 19:i + 1].std(ddof=1)
    return sd * math.sqrt(252) if sd > 0 else None


def forward_price(sym, date, sessions):
    rows = D2.get(sym) or []
    i = RV.get(sym, (None, {}))[1].get(date) if sym in RV else None
    if i is None:
        return None
    j = i + sessions
    return float(rows[j]['c']) if j < len(rows) else None


BUCKETS = [('ATM', 0.00), ('2% OTM', -0.02), ('5% OTM', -0.05), ('8% OTM', -0.08)]


def run(events, iv_ratio, label):
    out = {}
    for mlab, off in BUCKETS:
        pnl, otm_l, cash_l, prem_l = [], [], [], []
        for r in events:
            S0 = r['spot']
            rv = rv_at(r['sym'], r['date'])
            ST = forward_price(r['sym'], r['date'], 10)
            if not rv or ST is None or S0 <= 0:
                continue
            K = S0 * (1 + off)
            iv = rv * iv_ratio
            T = DTE_CAL / 365.0
            premium = bs_put(S0, K, T, RATE, iv)
            if premium <= 0.01:
                continue
            cross = HALF_SPREAD_FRAC[mlab] * S0
            if ST >= K:
                p, otm = premium - cross, True
            else:
                p, otm = premium - (K - ST) - 2 * cross, False
            pnl.append(p * 100.0)
            otm_l.append(otm)
            cash_l.append(K * 100.0)
            prem_l.append(premium * 100.0)
        if len(pnl) < 40:
            continue
        a = np.array(pnl)
        t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
        out[mlab] = dict(n=len(a), net=a.mean(), t=t, win=100 * (a > 0).mean(),
                         otm=100 * np.mean(otm_l), prem=float(np.mean(prem_l)),
                         cash=float(np.mean(cash_l)))
    return out


print()
print('=' * 106)
print('CASH-SECURED PUT, per-event Black-Scholes pricing at each name own volatility')
print('  premium uses IV = realized x {} on signal days (measured, not assumed)'.format(
    IV_RV_SIGNAL))
print('=' * 106)
for blab, budget in (('<= $60', 60), ('<= $100', 100), ('any', 10 ** 9)):
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    ev = [r for r in EV if r['sym'] in names and r['vol']]
    if len(ev) < 60:
        continue
    res = run(ev, IV_RV_SIGNAL, blab)
    if not res:
        continue
    print('\n  budget {}   ({} events in calm regime)'.format(blab, len(ev)))
    print('  {:<10} {:>6} {:>8} {:>9} {:>10} {:>10} {:>8} {:>12}'.format(
        'strike', 'n', 'OTM%', 'win%', 'premium $', 'NET $', 't', 'ret on cash'))
    for mlab, _ in BUCKETS:
        if mlab not in res:
            continue
        d = res[mlab]
        print('  {:<10} {:>6} {:>7.0f}% {:>8.1f}% {:>10.0f} {:>10.0f} {:>8.2f} {:>11.3f}%'.format(
            mlab, d['n'], d['otm'], d['win'], d['prem'], d['net'], d['t'],
            100 * d['net'] / d['cash']))

print()
print('=' * 106)
print('CONTROL — random days, same pricing model (isolates the SIGNAL from put-selling itself)')
print('=' * 106)
rng = np.random.default_rng(3)
ctrl = []
for s in list(FR):
    if not FR[s] or FR[s].get('friction', 1e9) > 100 or s not in RV:
        continue
    rows = D2.get(s) or []
    if len(rows) < 400:
        continue
    for _ in range(8):
        i = int(rng.integers(30, len(rows) - 14))
        ctrl.append(dict(sym=s, date=rows[i]['t'], spot=float(rows[i]['c'])))
res_c = run(ctrl, IV_RV_CONTROL, 'control')
names60 = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= 100}
res_s = run([r for r in EV if r['sym'] in names60 and r['vol']], IV_RV_SIGNAL, 'signal')
print('  {:<10} {:>22} {:>22} {:>14}'.format('strike', 'SIGNAL (calm regime)', 'CONTROL random',
                                             'difference'))
print('  {:<10} {:>22} {:>22} {:>14}'.format('', 'net$   win%    t', 'net$   win%    t', 'net$'))
for mlab, _ in BUCKETS:
    if mlab not in res_s or mlab not in res_c:
        continue
    a, b = res_s[mlab], res_c[mlab]
    print('  {:<10} {:>10.0f} {:>6.1f}% {:>5.2f} {:>10.0f} {:>6.1f}% {:>5.2f} {:>13.0f}'.format(
        mlab, a['net'], a['win'], a['t'], b['net'], b['win'], b['t'], a['net'] - b['net']))

print()
print('=' * 106)
print('SENSITIVITY — how much does the IV assumption drive this?')
print('=' * 106)
names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= 100}
ev = [r for r in EV if r['sym'] in names and r['vol']]
print('  {:<14} {:>12} {:>12} {:>12} {:>12}'.format(
    'IV / realized', 'ATM net$', '2% OTM', '5% OTM', '8% OTM'))
for ratio in (1.0, 1.2, 1.4, 1.6, 1.798, 2.0):
    res = run(ev, ratio, 'x')
    line = '  {:<14}'.format('{:.2f}x'.format(ratio))
    for mlab, _ in BUCKETS:
        line += '{:>12}'.format('{:+.0f}'.format(res[mlab]['net']) if mlab in res else '-')
    print(line)
print()
print('  1.00x means options are priced at exactly realized volatility - no variance risk')
print('  premium at all. That is the break-even assumption for this structure.')

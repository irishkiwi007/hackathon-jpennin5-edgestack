"""Is the cash-secured put result real, or a modelling artifact? Three checks.

  1. TAIL. Mean P&L is meaningless for a short put if the left tail is unbounded. What does the
     worst 1% look like, and what happens in a crisis window?
  2. VOLATILITY BIAS. The model prices from TRAILING 20-day realized volatility but pays off over
     the FORWARD 10 sessions. Volatility mean-reverts after a panic, so trailing > forward would
     flatter every result. Measured directly here.
  3. DRIFT DECOMPOSITION. At IV/RV = 1.0 the structure still nets +$51, which cannot be a
     variance premium. Isolating how much is simply "stocks went up 2016-2026".
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
RATE, DTE_CAL, IVR = 0.045, 14, 1.798
HALF = {'ATM': 0.00057, '2% OTM': 0.00049, '5% OTM': 0.00038, '8% OTM': 0.00032}


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, T, r, sig):
    if sig <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - sig * math.sqrt(T))) - S * ncdf(-d1)


SER = {}
for s in set(r['sym'] for r in EV):
    rows = D2.get(s) or []
    c = np.array([x['c'] for x in rows], float)
    if len(c) < 60 or (c <= 0).any():
        continue
    lr = np.zeros(len(c)); lr[1:] = np.log(c[1:] / c[:-1])
    SER[s] = (rows, c, lr, {rows[i]['t']: i for i in range(len(rows))})


def trade(sym, date, spot, off, iv_ratio, sessions=10):
    v = SER.get(sym)
    if not v:
        return None
    rows, c, lr, idx = v
    i = idx.get(date)
    if i is None or i < 21 or i + sessions >= len(c):
        return None
    rv_trail = lr[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
    rv_fwd = lr[i + 1:i + 1 + sessions].std(ddof=1) * math.sqrt(252) if sessions > 2 else None
    if rv_trail <= 0:
        return None
    K = spot * (1 + off)
    prem = bs_put(spot, K, DTE_CAL / 365.0, RATE, rv_trail * iv_ratio)
    if prem <= 0.01:
        return None
    ST = float(c[i + sessions])
    lab = {0.0: 'ATM', -0.02: '2% OTM', -0.05: '5% OTM', -0.08: '8% OTM'}[off]
    cross = HALF[lab] * spot
    if ST >= K:
        pnl = prem - cross
    else:
        pnl = prem - (K - ST) - 2 * cross
    return dict(pnl=pnl * 100.0, cash=K * 100.0, prem=prem * 100.0,
                rv_trail=rv_trail, rv_fwd=rv_fwd, ST=ST, K=K, spot=spot, date=date, sym=sym)


names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= 100}
SIG = [t for t in (trade(r['sym'], r['date'], r['spot'], 0.0, IVR)
                   for r in EV if r['sym'] in names and r['vol']) if t]
print('signal trades modelled: {}'.format(len(SIG)))

print()
print('=' * 100)
print('1. THE TAIL — mean P&L is meaningless for a short put if the left tail is unbounded')
print('=' * 100)
a = np.array([t['pnl'] for t in SIG])
cash = np.array([t['cash'] for t in SIG])
print('  mean {:+.0f}   median {:+.0f}   sd {:.0f}'.format(a.mean(), np.median(a), a.std(ddof=1)))
for p in (0.1, 1, 5, 25, 50, 75, 95):
    print('    p{:<5} {:>9.0f} $/contract   ({:+.2f}% of cash at risk)'.format(
        p, np.percentile(a, p), 100 * np.percentile(a, p) / cash.mean()))
worst = sorted(SIG, key=lambda t: t['pnl'])[:8]
print('\n  worst 8 trades:')
for t in worst:
    print('    {} {:<6} spot {:>8.2f} -> {:>8.2f} ({:+.1f}%)  premium {:>6.0f}  P&L {:>9.0f}'
          .format(t['date'], t['sym'], t['spot'], t['ST'],
                  100 * (t['ST'] / t['spot'] - 1), t['prem'], t['pnl']))
loss = a[a < 0]
print('\n  losing trades: {}/{} = {:.1f}%   mean loss {:.0f}   worst {:.0f}'.format(
    len(loss), len(a), 100 * len(loss) / len(a), loss.mean(), loss.min()))
print('  mean win {:.0f}  ->  win/loss ratio {:.2f}'.format(
    a[a > 0].mean(), abs(a[a > 0].mean() / loss.mean())))

print()
print('=' * 100)
print('2. VOLATILITY BIAS — is trailing volatility higher than what actually follows?')
print('=' * 100)
pairs = [(t['rv_trail'], t['rv_fwd']) for t in SIG if t['rv_fwd'] and t['rv_fwd'] > 0]
tr = np.array([p[0] for p in pairs]); fw = np.array([p[1] for p in pairs])
print('  n={}   trailing 20d RV {:.3f}   forward 10d RV {:.3f}   ratio {:.3f}'.format(
    len(pairs), tr.mean(), fw.mean(), tr.mean() / fw.mean()))
if tr.mean() > fw.mean():
    print('  Trailing exceeds forward by {:.1%}. Pricing off trailing therefore OVERSTATES the'
          .format(tr.mean() / fw.mean() - 1))
    print('  premium relative to what the stock actually did - the result is flattered.')
    print('  Re-running priced off FORWARD realized volatility (the honest, unknowable-in-advance')
    print('  benchmark) to bound how much of the edge survives:')
    fair = []
    for t in SIG:
        if not t['rv_fwd'] or t['rv_fwd'] <= 0:
            continue
        K = t['K']
        prem = bs_put(t['spot'], K, DTE_CAL / 365.0, RATE, t['rv_fwd'] * IVR)
        cross = HALF['ATM'] * t['spot']
        pnl = (prem - cross) if t['ST'] >= K else (prem - (K - t['ST']) - 2 * cross)
        fair.append(pnl * 100.0)
    f = np.array(fair)
    print('    priced off trailing RV : {:+.0f} $/contract'.format(a.mean()))
    print('    priced off forward RV  : {:+.0f} $/contract   <- removes the look-back bias'
          .format(f.mean()))

print()
print('=' * 100)
print('3. DRIFT DECOMPOSITION — how much is just "stocks went up"?')
print('=' * 100)
rng = np.random.default_rng(11)
ctrl = []
for s in list(names):
    if s not in SER:
        continue
    rows = SER[s][0]
    if len(rows) < 400:
        continue
    for _ in range(8):
        i = int(rng.integers(30, len(rows) - 14))
        t = trade(s, rows[i]['t'], float(rows[i]['c']), 0.0, IVR)
        if t:
            ctrl.append(t)
c = np.array([t['pnl'] for t in ctrl])
print('  {:<34} {:>10} {:>10} {:>8}'.format('', 'mean $', 'win %', 'n'))
print('  {:<34} {:>10.0f} {:>9.1f}% {:>8}'.format('SIGNAL days (calm regime)', a.mean(),
                                                  100 * (a > 0).mean(), len(a)))
print('  {:<34} {:>10.0f} {:>9.1f}% {:>8}'.format('RANDOM days (same universe)', c.mean(),
                                                  100 * (c > 0).mean(), len(c)))
print('  {:<34} {:>10.0f}'.format('SIGNAL ALPHA (difference)', a.mean() - c.mean()))
se = math.sqrt(a.var(ddof=1) / len(a) + c.var(ddof=1) / len(c))
print('  {:<34} {:>10.2f}'.format('t on the difference', (a.mean() - c.mean()) / se))

print()
print('=' * 100)
print('4. CRISIS BEHAVIOUR — what a bad period does to a short-put book')
print('=' * 100)
print('  {:<14} {:>7} {:>11} {:>11} {:>11} {:>11}'.format(
    'period', 'n', 'mean $', 'total $', 'worst $', 'win%'))
for lab, lo_, hi_ in [('2016-2017', '2016', '2018'), ('2018-2019', '2018', '2020'),
                      ('2020 H1 covid', '2020-01', '2020-07'), ('2020-2021', '2020', '2022'),
                      ('2022-2023', '2022', '2024'), ('2024-2026', '2024', '2027')]:
    g = [t['pnl'] for t in SIG if lo_ <= t['date'][:len(lo_)] < hi_]
    if len(g) < 10:
        print('  {:<14} {:>7}  (thin)'.format(lab, len(g))); continue
    x = np.array(g)
    print('  {:<14} {:>7} {:>11.0f} {:>11.0f} {:>11.0f} {:>10.1f}%'.format(
        lab, len(x), x.mean(), x.sum(), x.min(), 100 * (x > 0).mean()))

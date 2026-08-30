"""Price the bull put spread properly at both ends. No delta approximation, no uncapped gain.

The previous pass estimated gain as 0.35 x underlying move, which produced $440/contract on a
structure whose maximum possible gain is the ~$401 credit. A linear delta is wrong for a 1.7%
move on a 5%-wide spread, and it cannot express the cap at all.

This prices the spread with Black-Scholes at entry and again 3 sessions later:
  - entry IV from the name's own trailing realized volatility, scaled by the MEASURED
    regime-dependent IV/RV curve (turbulent 0.657, active 0.888, normal 1.056, calm 1.085)
  - exit IV re-derived the same way from the volatility that actually prevailed
  - time decay from the real day count
  - friction charged on all four leg crossings at the live-measured rate

That is a mark-to-market P&L, capped by construction, with the volatility regime and the
crossing cost both taken from measurement rather than assumption.
"""
import csv, io, math, sys
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
HOLD, RATE, DTE0 = 3, 0.045, 12
WIDTH_PCT = 0.05
FRICTION = {'SPY': 4.0, 'QQQ': 16.0, 'SOXX': 105.0, 'XLV': 40.0,
            'XLP': 11.0, 'HYG': 3.0, 'FDN': 200.0}
SPOT_NOW = {'SPY': 769.35, 'QQQ': 716.43, 'SOXX': 508.62, 'XLV': 171.16,
            'XLP': 85.45, 'HYG': 79.74, 'FDN': 294.43}


def iv_ratio(rv):
    """Measured IV/RV as a function of trailing realized volatility (28 live names)."""
    if rv < 0.15:
        return 1.085
    if rv < 0.25:
        return 1.056
    if rv < 0.40:
        return 0.888
    return 0.657


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - s * math.sqrt(T))) - S * ncdf(-d1)


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    return ([r['date'] for r in rows],
            np.array([float(r['adj_close']) for r in rows]),
            np.array([float(r['volume']) for r in rows]))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 8:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


RES = {}
for sym in FRICTION:
    try:
        dts, c, v = load(sym)
    except OSError:
        continue
    n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    scale = SPOT_NOW[sym] / c[-1]        # express historical prices at today's level
    trades = []
    for i in range(25, n - HOLD):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if st >= -2.5 or vx < 1.4:
            continue
        S0 = c[i] * scale
        S1 = c[i + HOLD] * scale
        rv_a = rv * math.sqrt(252)
        iv0 = rv_a * iv_ratio(rv_a)
        # exit volatility: realized over the holding window, same mapping
        rv_exit = r[i + 1:i + 1 + HOLD].std(ddof=1) * math.sqrt(252) if HOLD > 2 else rv_a
        if not np.isfinite(rv_exit) or rv_exit <= 0:
            rv_exit = rv_a
        iv1 = rv_exit * iv_ratio(rv_exit)
        K_s = S0
        K_l = S0 * (1 - WIDTH_PCT)
        T0 = DTE0 / 365.0
        T1 = max((DTE0 - HOLD) / 365.0, 1e-4)
        credit0 = bs_put(S0, K_s, T0, RATE, iv0) - bs_put(S0, K_l, T0, RATE, iv0)
        credit1 = bs_put(S1, K_s, T1, RATE, iv1) - bs_put(S1, K_l, T1, RATE, iv1)
        if credit0 <= 0:
            continue
        width = K_s - K_l
        gross = (credit0 - credit1) * 100.0            # capped by construction
        fr = 2 * FRICTION[sym]
        trades.append(dict(gross=gross, net=gross - fr, credit=credit0 * 100.0,
                           width=width * 100.0, maxgain=credit0 * 100.0,
                           move=(S1 / S0 - 1) * 100, date=dts[i], iv0=iv0))
    if len(trades) >= 8:
        RES[sym] = trades

print('=' * 104)
print('BULL PUT SPREAD, BLACK-SCHOLES PRICED AT BOTH ENDS (no delta approximation, gain capped)')
print('  entry/exit IV from the measured IV-RV curve; friction = 4 leg crossings, live rates')
print('=' * 104)
print('{:<7} {:>5} {:>9} {:>9} {:>9} {:>9} {:>8} {:>9} {:>8} {:>8}'.format(
    'sym', 'n', 'entry IV', 'credit $', 'maxgain', 'gross $', 'fric $', 'NET $', 't', 'win%'))
book = []
for sym, tr in sorted(RES.items(), key=lambda kv: -np.mean([t['net'] for t in kv[1]])):
    g = np.array([t['gross'] for t in tr])
    nt = np.array([t['net'] for t in tr])
    print('{:<7} {:>5} {:>9.3f} {:>9.0f} {:>9.0f} {:>9.0f} {:>8.0f} {:>9.0f} {:>8.2f} {:>7.1f}%'
          .format(sym, len(tr), float(np.mean([t['iv0'] for t in tr])),
                  float(np.mean([t['credit'] for t in tr])),
                  float(np.mean([t['maxgain'] for t in tr])),
                  g.mean(), 2 * FRICTION[sym], nt.mean(), nw_t(nt, HOLD),
                  100 * (nt > 0).mean()))
    if sym in ('SPY', 'QQQ'):
        book += tr

print()
print('=' * 104)
print('SANITY — is the modelled gain actually inside the cap?')
print('=' * 104)
for sym in ('SPY', 'QQQ'):
    if sym not in RES:
        continue
    tr = RES[sym]
    over = sum(1 for t in tr if t['gross'] > t['maxgain'] + 1e-6)
    frac = np.mean([t['gross'] / t['maxgain'] for t in tr])
    print('  {:<5} mean gain is {:.0%} of max possible; {} of {} exceed the cap'.format(
        sym, frac, over, len(tr)))

if book:
    b = np.array([t['net'] for t in book])
    print()
    print('=' * 104)
    print('SPY + QQQ BOOK')
    print('=' * 104)
    print('  n={}  NET {:+.0f} $/contract  t={:.2f}  win {:.1f}%  median {:+.0f}'.format(
        len(b), b.mean(), nw_t(b, HOLD), 100 * (b > 0).mean(), float(np.median(b))))
    print('  worst {:+.0f}   p10 {:+.0f}   p90 {:+.0f}'.format(
        b.min(), np.percentile(b, 10), np.percentile(b, 90)))
    print('  frequency: {:.1f} signals/year across the two names'.format(len(b) / 27.0))
    print()
    print('  {:<14} {:>6} {:>10} {:>8}'.format('era', 'n', 'NET $', 'win%'))
    for lab, a_, b_ in [('1999-2007', '1999', '2008'), ('2008-2012', '2008', '2013'),
                        ('2013-2019', '2013', '2020'), ('2020-2026', '2020', '2027')]:
        g = [t['net'] for t in book if a_ <= t['date'][:4] < b_]
        if len(g) < 5:
            print('  {:<14} {:>6}  (thin)'.format(lab, len(g)))
            continue
        x = np.array(g)
        print('  {:<14} {:>6} {:>10.0f} {:>7.1f}%'.format(lab, len(x), x.mean(),
                                                          100 * (x > 0).mean()))

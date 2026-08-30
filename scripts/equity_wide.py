"""The capitulation edge is starved on SPY alone - 24 events in 32 years.

In OPTIONS the universe had to stay tiny, because friction ran $50-400 per contract and only the
very tightest chains (SPY, QQQ) could carry it. In EQUITY that constraint disappears: crossing
costs ~1-3bp on any liquid ETF, so the whole universe becomes usable and the signal fires far
more often.

This runs the capitulation edge as an equity book across the wide ETF set, with:
  - the validated volume window (1.4x - 2.5x; the edge dies above 2.5x, "real news arrived")
  - the calm-bond regime filter (t(diff)=6.58 out-of-sample)
  - realistic per-name equity costs
  - position sizing across concurrent signals

Then combines it with the overnight+trend core to see whether a properly-fed capitulation sleeve
adds what the starved SPY-only version could not.
"""
import csv, io, json, math, sys, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
ETFS = ['SPY', 'QQQ', 'SOXX', 'XLV', 'XLP', 'HYG', 'FDN']
COST_BP = {'SPY': 0.01, 'QQQ': 0.01, 'SOXX': 0.03, 'XLV': 0.02,
           'XLP': 0.02, 'HYG': 0.02, 'FDN': 0.04}      # percent, round trip
HOLD = 3


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    d = [r['date'] for r in rows]
    o = np.array([float(r['open']) for r in rows])
    c = np.array([float(r['close']) for r in rows])
    ac = np.array([float(r['adj_close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    fac = np.where(c > 0, ac / np.maximum(c, 1e-9), 1.0)
    return d, o * fac, ac, v


td, _, tcl, _ = load('TLT')
stds = {}
for i in range(21, len(tcl)):
    stds[td[i]] = float(np.std(tcl[i - 21:i], ddof=1))
CALM, hist, state = {}, [], False
for d in [x for x in td if x in stds]:
    hist.append(stds[d]); hist[:] = hist[-90:]
    if len(hist) < 90:
        continue
    now, avg = hist[-1], sum(hist) / len(hist)
    state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
    CALM[d] = state

# collect capitulation events across the universe
EVENTS = defaultdict(list)          # date -> list of (sym, fwd3 pct)
COUNT = defaultdict(int)
ALLD = set()
for s in ETFS:
    d, o, c, v = load(s)
    n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    ALLD.update(d)
    for i in range(25, n - HOLD):
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if st < -2.5 and 1.4 <= vx < 2.5:
            fwd = (c[i + HOLD] / c[i] - 1) * 100 - COST_BP.get(s, 0.03)
            EVENTS[d[i]].append((s, fwd, CALM.get(d[i], True)))
            COUNT[s] += 1

print('capitulation events by ETF:')
for s in ETFS:
    print('   {:<6} {:>4}'.format(s, COUNT[s]))
tot = sum(COUNT.values())
print('   {:<6} {:>4}   ({:.1f}/yr across the book)'.format('TOTAL', tot, tot / 33.0))


def nw_t(x, lag=1):
    x = np.asarray(x, float)
    n = len(x)
    if n < 12:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


allev = [(dt, s, f, cm) for dt, lst in EVENTS.items() for s, f, cm in lst]
a = np.array([x[2] for x in allev])
calm_only = np.array([x[2] for x in allev if x[3]])
print()
print('=' * 100)
print('THE EDGE IN EQUITY, NET OF REAL COSTS')
print('=' * 100)
print('  all events        n={:<4} mean {:+.3f}%  win {:.1f}%  t={:.2f}'.format(
    len(a), a.mean(), 100 * (a > 0).mean(), nw_t(a, HOLD)))
print('  calm bonds only   n={:<4} mean {:+.3f}%  win {:.1f}%  t={:.2f}'.format(
    len(calm_only), calm_only.mean(), 100 * (calm_only > 0).mean(), nw_t(calm_only, HOLD)))

# ---- portfolio simulation ----------------------------------------------------------------
SPYd, SPYo, SPYc, SPYv = load('SPY')
n = len(SPYc)
r = np.zeros(n); r[1:] = np.log(SPYc[1:] / SPYc[:-1])
didx = {d: i for i, d in enumerate(SPYd)}


def simulate(cap_weight, use_calm, core_on=True):
    """core = overnight SPY when 12m trend up; sleeve = capitulation basket, equal weighted."""
    daily = []
    open_pos = []            # (days_left, weight, sym, entry_i)
    for i in range(253, n - 1):
        d = SPYd[i]
        ret = 0.0
        # core
        if core_on and SPYc[i] / SPYc[i - 252] - 1 > 0:
            ret += (SPYo[i + 1] / SPYc[i] - 1) * 100 - 0.01
        # sleeve: accrue each open position's return for THIS session.
        # entry is at the close of the signal day, so the first accrual must be the move
        # from the signal close to the next close - previously this was skipped, which
        # dropped the largest single day of the bounce.
        still = []
        for dl, w, sym, ei in open_pos:
            sd, so, sc, sv = SERIES[sym]
            j = SIDX[sym].get(d)
            if j is not None and j < len(sc) and j - 1 >= 0:
                ret += w * ((sc[j] / sc[j - 1] - 1) * 100)
            if dl > 1:
                still.append((dl - 1, w, sym, ei))
        open_pos = still
        # new signals
        todays = EVENTS.get(d, [])
        if use_calm:
            todays = [x for x in todays if x[2]]
        if todays and cap_weight > 0:
            w = cap_weight / len(todays)
            for sym, _, _ in todays:
                if sym in SERIES and d in SIDX[sym]:
                    open_pos.append((HOLD, w, sym, SIDX[sym][d]))
                    ret -= w * COST_BP.get(sym, 0.03)
        daily.append(ret)
    return daily


SERIES = {s: load(s) for s in ETFS}
SIDX = {s: {d: i for i, d in enumerate(SERIES[s][0])} for s in ETFS}


def perf(x, lab):
    a = np.array(x, dtype=float)
    eq = np.cumprod(1 + a / 100.0)
    yrs = len(a) / 252.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = a.std(ddof=1) * math.sqrt(252) / 100.0
    peak = np.maximum.accumulate(eq)
    return dict(label=lab, cagr=cagr, vol=vol, sharpe=(cagr - 0.02) / vol if vol > 0 else 0,
                dd=float((eq / peak - 1).min()))


print()
print('=' * 100)
print('PORTFOLIO — overnight+trend core, plus a properly-fed capitulation sleeve')
print('=' * 100)
print('{:<40} {:>9} {:>9} {:>9} {:>9}'.format('configuration', 'CAGR', 'vol', 'Sharpe', 'max DD'))
for lab, cw, uc, core in (('core only (overnight+trend)', 0.0, False, True),
                          ('core + sleeve 0.5x', 0.5, False, True),
                          ('core + sleeve 1.0x', 1.0, False, True),
                          ('core + sleeve 1.0x, calm only', 1.0, True, True),
                          ('core + sleeve 2.0x, calm only', 2.0, True, True),
                          ('sleeve only 1.0x', 1.0, False, False)):
    p = perf(simulate(cw, uc, core), lab)
    print('{:<40} {:>8.2f}% {:>8.2f}% {:>9.2f} {:>8.1f}%'.format(
        p['label'], 100 * p['cagr'], 100 * p['vol'], p['sharpe'], 100 * p['dd']))

print()
print('=' * 100)
print('ERA STABILITY — best configuration (core + sleeve 0.5x) vs buy and hold')
print('=' * 100)
best = simulate(0.5, False, True)
bh = [(SPYc[i + 1] / SPYc[i] - 1) * 100 for i in range(253, n - 1)]
ds = [SPYd[i] for i in range(253, n - 1)]
print('{:<14} {:>7} {:>12} {:>12} {:>11} {:>11} {:>10}'.format(
    'era', 'n', 'stack CAGR', 'b&h CAGR', 'stack Shrp', 'b&h Shrp', 'stack DD'))
wins = tot = 0
for lab, a_, b_ in [('1994-1999', '1994', '2000'), ('2000-2002', '2000', '2003'),
                    ('2003-2007', '2003', '2008'), ('2008-2009', '2008', '2010'),
                    ('2010-2015', '2010', '2016'), ('2016-2019', '2016', '2020'),
                    ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                    ('2024-2026', '2024', '2027')]:
    m = [k for k, d in enumerate(ds) if a_ <= d[:4] < b_]
    if len(m) < 100:
        continue
    f = np.array([best[k] for k in m]); b = np.array([bh[k] for k in m])
    yrs = len(m) / 252.0
    cf = np.prod(1 + f / 100) ** (1 / yrs) - 1
    cb = np.prod(1 + b / 100) ** (1 / yrs) - 1
    sf = (cf - 0.02) / (f.std(ddof=1) * math.sqrt(252) / 100) if f.std() > 0 else 0
    sb = (cb - 0.02) / (b.std(ddof=1) * math.sqrt(252) / 100) if b.std() > 0 else 0
    eqf = np.cumprod(1 + f / 100); ddf = float((eqf / np.maximum.accumulate(eqf) - 1).min())
    tot += 1; wins += 1 if sf > sb else 0
    print('{:<14} {:>7} {:>11.2f}% {:>11.2f}% {:>11.2f} {:>11.2f} {:>9.1f}%'.format(
        lab, len(m), 100 * cf, 100 * cb, sf, sb, 100 * ddf))
print('\n  beat buy-and-hold on Sharpe in {}/{} eras'.format(wins, tot))
f = np.array(best); b = np.array(bh)
print('  correlation with buy-and-hold: {:+.3f}'.format(float(np.corrcoef(f, b)[0, 1])))
print('  worst single day: stack {:+.2f}%   buy-and-hold {:+.2f}%'.format(f.min(), b.min()))
print('  best single day:  stack {:+.2f}%   buy-and-hold {:+.2f}%'.format(f.max(), b.max()))

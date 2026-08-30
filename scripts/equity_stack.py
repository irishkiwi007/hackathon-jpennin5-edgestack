"""The equity expression of every edge validated this session.

The recurring failure all session was not the edges - it was the wrapper. Retail option bid/ask
runs $50-400 per contract round trip, which is the same order as the edges themselves. SPY equity
crosses at roughly 1 basis point. So the same signals that died in options are directly
capturable here.

Edges being stacked, each established earlier:

  A. OVERNIGHT DRIFT     Sharpe 0.89 vs 0.05 intraday; 7/8 ETFs, 8/9 eras
  B. CAPITULATION BOUNCE +1.646% / 3 sessions, 68.1% win, t=5.42 over 33 years, surrogate-tested
  C. TREND FILTER        12-month trend up: fwd21 +1.011% (t=5.77) vs +0.113% (t=0.17)
  D. CALM-BOND REGIME    capitulation +1.553% calm vs +0.066% stressed, t(diff)=6.58 OOS
  E. VOLUME CEILING      capitulation edge dies above 2.5x volume ("real news arrived")

Costs charged at 1bp per round trip, which is conservative for SPY equity at the touch.
"""
import csv, io, math, sys, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
COST = 0.01          # percent, per round trip


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    d = [r['date'] for r in rows]
    o = np.array([float(r['open']) for r in rows])
    c = np.array([float(r['close']) for r in rows])
    ac = np.array([float(r['adj_close']) for r in rows])
    v = np.array([float(r['volume']) for r in rows])
    fac = np.where(c > 0, ac / np.maximum(c, 1e-9), 1.0)
    return d, o * fac, ac, v


def perf(daily_pct, label):
    a = np.array(daily_pct, dtype=float)
    if len(a) < 200:
        return None
    eq = np.cumprod(1 + a / 100.0)
    yrs = len(a) / 252.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = a.std(ddof=1) * math.sqrt(252) / 100.0
    peak = np.maximum.accumulate(eq)
    dd = float((eq / peak - 1).min())
    downside = a[a < 0]
    sortino = ((cagr - 0.02) / (downside.std(ddof=1) * math.sqrt(252) / 100.0)
               if len(downside) > 10 else float('nan'))
    return dict(label=label, cagr=cagr, vol=vol, dd=dd,
                sharpe=(cagr - 0.02) / vol if vol > 0 else 0, sortino=sortino,
                expo=100.0 * np.mean(np.abs(a) > 1e-12), eq=eq)


dts, op_, cl, vol_ = load('SPY')
n = len(cl)
r = np.zeros(n); r[1:] = np.log(cl[1:] / cl[:-1])

# calm-bond regime
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

# precompute signals
SIG = {}
for i in range(253, n - 1):
    rv = r[i - 19:i + 1].std(ddof=1)
    if not np.isfinite(rv) or rv <= 0:
        continue
    stretch = math.log(cl[i] / cl[i - 5]) / (rv * math.sqrt(5))
    volx = vol_[i] / max(np.mean(vol_[i - 19:i + 1]), 1.0)
    SIG[i] = dict(stretch=stretch, volx=volx,
                  trend=cl[i] / cl[i - 252] - 1 > 0,
                  calm=CALM.get(dts[i], True),
                  cap=(stretch < -2.5 and 1.4 <= volx < 2.5))

START = 253
IDX = [i for i in range(START, n - 1) if i in SIG]
print('SPY sessions used: {}  {} -> {}'.format(len(IDX), dts[IDX[0]], dts[IDX[-1]]))

# ---- strategy variants -------------------------------------------------------------------
def run(use_overnight, use_trend, use_calm, cap_boost, cap_days=3, base_w=1.0):
    out = []
    cap_left, cap_w = 0, 0.0
    for i in IDX:
        s = SIG[i]
        w = base_w
        if use_trend and not s['trend']:
            w = 0.0
        if use_calm and not s['calm']:
            w *= 0.5
        # capitulation: add exposure for the next cap_days sessions
        if cap_left > 0:
            w += cap_w
            cap_left -= 1
        if cap_boost > 0 and s['cap']:
            cap_left, cap_w = cap_days, cap_boost
        if use_overnight:
            ret = (op_[i + 1] / cl[i] - 1) * 100
        else:
            ret = (cl[i + 1] / cl[i] - 1) * 100
        out.append(w * ret - (COST if w > 0 else 0.0))
    return out


print()
print('=' * 108)
print('EQUITY STACK — each edge added in turn (SPY, 1993-2026, 1bp round-trip cost)')
print('=' * 108)
VAR = [
    ('buy and hold', dict(use_overnight=False, use_trend=False, use_calm=False, cap_boost=0)),
    ('A. overnight only', dict(use_overnight=True, use_trend=False, use_calm=False, cap_boost=0)),
    ('A+C. + trend filter', dict(use_overnight=True, use_trend=True, use_calm=False, cap_boost=0)),
    ('A+C+D. + calm scaling', dict(use_overnight=True, use_trend=True, use_calm=True, cap_boost=0)),
    ('A+C+B. + capitulation 1x', dict(use_overnight=True, use_trend=True, use_calm=False,
                                      cap_boost=1.0)),
    ('A+C+B. + capitulation 2x', dict(use_overnight=True, use_trend=True, use_calm=False,
                                      cap_boost=2.0)),
    ('full stack (all edges)', dict(use_overnight=True, use_trend=True, use_calm=True,
                                    cap_boost=2.0)),
    ('capitulation only, full day', dict(use_overnight=False, use_trend=False, use_calm=False,
                                         cap_boost=1.0, base_w=0.0)),
]
RES = []
print('{:<30} {:>9} {:>9} {:>9} {:>9} {:>9} {:>10}'.format(
    'strategy', 'CAGR', 'vol', 'Sharpe', 'Sortino', 'max DD', 'exposure'))
for lab, kw in VAR:
    p = perf(run(**kw), lab)
    if not p:
        continue
    RES.append(p)
    print('{:<30} {:>8.2f}% {:>8.2f}% {:>9.2f} {:>9.2f} {:>8.1f}% {:>9.0f}%'.format(
        p['label'], 100 * p['cagr'], 100 * p['vol'], p['sharpe'], p['sortino'],
        100 * p['dd'], p['expo']))

print()
print('=' * 108)
print('THE CAPITULATION EDGE IN EQUITY vs WHAT IT COST IN OPTIONS')
print('=' * 108)
caps = [i for i in IDX if SIG[i]['cap']]
if caps:
    fwd3 = np.array([(cl[min(i + 3, n - 1)] / cl[i] - 1) * 100 for i in caps])
    print('  capitulation events: {}   mean 3-session move {:+.3f}%   win {:.1f}%'.format(
        len(caps), fwd3.mean(), 100 * (fwd3 > 0).mean()))
    print()
    print('  {:<34} {:>14} {:>14}'.format('expression', 'gross/trade', 'friction'))
    print('  {:<34} {:>13.2f}% {:>13.2f}%'.format(
        'SPY equity (1bp round trip)', fwd3.mean(), COST))
    print('  {:<34} {:>13.2f}% {:>13.2f}%'.format(
        'SPY bull put spread (measured)', fwd3.mean() * 0.35, 56.0 / 769.35 * 100))
    print()
    print('  net in equity   {:+.3f}%/trade'.format(fwd3.mean() - COST))
    print('  net in options  {:+.3f}%/trade'.format(
        fwd3.mean() * 0.35 - 56.0 / 769.35 * 100))
    print()
    print('  Same signal. The wrapper was the entire difference.')

print()
print('=' * 108)
print('ERA STABILITY — full stack vs buy and hold')
print('=' * 108)
full = run(use_overnight=True, use_trend=True, use_calm=True, cap_boost=2.0)
bh = run(use_overnight=False, use_trend=False, use_calm=False, cap_boost=0)
print('{:<14} {:>7} {:>12} {:>12} {:>11} {:>11}'.format(
    'era', 'n', 'stack CAGR', 'b&h CAGR', 'stack Shrp', 'b&h Shrp'))
wins = 0
tot = 0
for lab, a_, b_ in [('1994-1999', '1994', '2000'), ('2000-2002', '2000', '2003'),
                    ('2003-2007', '2003', '2008'), ('2008-2009', '2008', '2010'),
                    ('2010-2015', '2010', '2016'), ('2016-2019', '2016', '2020'),
                    ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                    ('2024-2026', '2024', '2027')]:
    m = [k for k, i in enumerate(IDX) if a_ <= dts[i][:4] < b_]
    if len(m) < 100:
        continue
    f = np.array([full[k] for k in m])
    b = np.array([bh[k] for k in m])
    yrs = len(m) / 252.0
    cf = np.prod(1 + f / 100) ** (1 / yrs) - 1
    cb = np.prod(1 + b / 100) ** (1 / yrs) - 1
    sf = (cf - 0.02) / (f.std(ddof=1) * math.sqrt(252) / 100) if f.std() > 0 else 0
    sb = (cb - 0.02) / (b.std(ddof=1) * math.sqrt(252) / 100) if b.std() > 0 else 0
    tot += 1
    wins += 1 if sf > sb else 0
    print('{:<14} {:>7} {:>11.2f}% {:>11.2f}% {:>11.2f} {:>11.2f}'.format(
        lab, len(m), 100 * cf, 100 * cb, sf, sb))
print('\n  stack beat buy-and-hold on Sharpe in {}/{} eras'.format(wins, tot))

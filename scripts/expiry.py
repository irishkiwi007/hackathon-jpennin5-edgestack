"""Hold to expiry: does removing the exit trade flip the strategy positive?

The structural problem is that gross P&L and option spreads both scale with spot, so a better
signal never outruns the spread. Holding to expiry attacks the cost side instead: a short put
that finishes out-of-the-money needs NO closing trade, so those trades pay friction once
instead of twice.

Payoff at expiry is deterministic from the underlying, so this needs no option price history -
only the credit/width ratio, which is measured from live chains (24.6% at mid, ATM/-5%).

Cost model, deliberately pessimistic:
  entry  : always pay one-way friction
  exit   : pay it AGAIN only when the short strike finishes in-the-money and we must close
  assignment is treated as a close, not as free equity exposure
"""
import csv, io, json, math, sys
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

FR = json.load(open('friction_screen.json'))
D2 = json.load(open('sp500_bars.json'))
CREDIT_TO_WIDTH = 0.246     # measured at mid on live chains, ATM/-5%, ~1-2wk
WIDTH_PCT = 0.05


def forward_price(sym, date, sessions):
    """Underlying close `sessions` trading days after `date`, or None."""
    rows = D2.get(sym) or []
    for i, b in enumerate(rows):
        if b['t'] == date:
            j = i + sessions
            if j < len(rows):
                return float(rows[j]['c'])
            return None
    return None


print()
print('=' * 104)
print('HOLD TO EXPIRY vs CLOSE AT 3 SESSIONS — calm regime only')
print('  bull put spread, short ATM, long 5% below, credit = 24.6% of width (live-chain mid)')
print('=' * 104)
print('{:<12} {:>6} {:>7} {:>9} {:>9} {:>10} {:>11} {:>10} {:>10}'.format(
    'budget', 'names', 'n', 'OTM at exp', 'win%', 'gross $', 'fric $/ct', 'NET $', 'sig/5d'))

for budget in (10, 20, 35, 60, 100, 10 ** 9):
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    ev = [r for r in EV if r['sym'] in names and r['vol']]
    if len(ev) < 40:
        continue
    pnl, frictions, otm_flags = [], [], []
    for r in ev:
        S0 = r['spot']
        ST = forward_price(r['sym'], r['date'], 10)      # ~2 calendar weeks
        if ST is None or S0 <= 0:
            continue
        width = S0 * WIDTH_PCT
        credit = width * CREDIT_TO_WIDTH
        short_k, long_k = S0, S0 - width
        if ST >= short_k:
            payoff = credit                                     # expires worthless
            otm = True
        else:
            loss = min(short_k - ST, width)
            payoff = credit - loss
            otm = False
        fr = FR[r['sym']]['friction'] / 100.0                   # per share
        cost = fr if otm else 2 * fr                            # exit only when ITM
        pnl.append((payoff - cost) * 100.0)
        frictions.append(cost * 100.0)
        otm_flags.append(otm)
    if len(pnl) < 40:
        continue
    a = np.array(pnl)
    per5 = len(a) / 19.1 / 252 * 5
    gross = float(np.mean([p + f for p, f in zip(a, frictions)]))
    lab = 'any' if budget > 1e8 else '<= ${}'.format(budget)
    print('{:<12} {:>6} {:>7} {:>8.0f}% {:>8.1f}% {:>10.0f} {:>11.0f} {:>10.0f} {:>10.2f}'.format(
        lab, len(names), len(a), 100 * np.mean(otm_flags), 100 * (a > 0).mean(),
        gross, float(np.mean(frictions)), a.mean(), per5))

print()
print('=' * 104)
print('SANITY — the same structure held only 3 sessions, closed both legs')
print('=' * 104)
print('{:<12} {:>6} {:>7} {:>9} {:>10} {:>11} {:>10}'.format(
    'budget', 'names', 'n', 'win%', 'gross $', 'fric $/ct', 'NET $'))
for budget in (20, 60, 10 ** 9):
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    ev = [r for r in EV if r['sym'] in names and r['vol']]
    pnl, fr_l = [], []
    for r in ev:
        S0 = r['spot']
        ST = forward_price(r['sym'], r['date'], 3)
        if ST is None or S0 <= 0:
            continue
        width = S0 * WIDTH_PCT
        credit = width * CREDIT_TO_WIDTH
        # mark-to-market approximation: the spread's value tracks ~35% of the move over 3 days
        gain = min(max((ST - S0) * 0.35, -width), credit)
        fr = FR[r['sym']]['friction'] / 100.0
        pnl.append((gain - 2 * fr) * 100.0)
        fr_l.append(2 * fr * 100.0)
    if len(pnl) < 40:
        continue
    a = np.array(pnl)
    lab = 'any' if budget > 1e8 else '<= ${}'.format(budget)
    print('{:<12} {:>6} {:>7} {:>8.1f}% {:>10.0f} {:>11.0f} {:>10.0f}'.format(
        lab, len(names), len(a), 100 * (a > 0).mean(),
        float(np.mean([p + f for p, f in zip(a, fr_l)])), float(np.mean(fr_l)), a.mean()))

print()
print('=' * 104)
print('EXPIRY HORIZON SWEEP (<= $60 budget) — how long should we hold?')
print('=' * 104)
names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= 60}
ev = [r for r in EV if r['sym'] in names and r['vol']]
print('{:<14} {:>7} {:>10} {:>9} {:>11} {:>10}'.format(
    'sessions', 'n', 'OTM at exp', 'win%', 'gross $', 'NET $'))
for sessions in (5, 8, 10, 15, 21):
    pnl, fr_l, otm_l = [], [], []
    for r in ev:
        S0 = r['spot']
        ST = forward_price(r['sym'], r['date'], sessions)
        if ST is None or S0 <= 0:
            continue
        width = S0 * WIDTH_PCT
        credit = width * CREDIT_TO_WIDTH
        if ST >= S0:
            payoff, otm = credit, True
        else:
            payoff, otm = credit - min(S0 - ST, width), False
        fr = FR[r['sym']]['friction'] / 100.0
        cost = fr if otm else 2 * fr
        pnl.append((payoff - cost) * 100.0)
        fr_l.append(cost * 100.0)
        otm_l.append(otm)
    if len(pnl) < 40:
        continue
    a = np.array(pnl)
    print('{:<14} {:>7} {:>9.0f}% {:>8.1f}% {:>11.0f} {:>10.0f}'.format(
        sessions, len(a), 100 * np.mean(otm_l), 100 * (a > 0).mean(),
        float(np.mean([p + f for p, f in zip(a, fr_l)])), a.mean()))

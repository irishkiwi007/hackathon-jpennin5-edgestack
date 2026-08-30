"""Is the rich-IV / calm-bond premium strategy safe enough to actually run?

It measures +$27/contract, t=3.19, 60% win, 54 trades/year. But it is SHORT VOLATILITY, and
short-volatility books look excellent right up until they do not. Three things decide it:

  1. TAIL. Worst observed is -$1,490 against a +$27 mean. What does the drawdown path look like
     when trades are taken sequentially rather than averaged?
  2. CRISIS. 2003-2009 measured -$6. What happened specifically in 2008, and did the calm-bond
     filter actually keep us out?
  3. SIZING. A 5%-wide SPY spread risks ~$3,600/contract. Against a 2% risk budget on $100k that
     is zero contracts, so the width has to come down - which changes the economics.
"""
import csv, io, json, math, sys, datetime, urllib.request, urllib.parse, http.cookiejar
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
_src = open('vrp_new.py', encoding='utf-8').read().split("print()\nprint('=' * 100)\nprint('1. SORTED")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

RICH = float(np.percentile([r['ivrv'] for r in ALL], 80))
SEL = sorted([r for r in ALL if r['ivrv'] >= RICH and r['calm'] is True],
             key=lambda r: r['date'])
print('\nselected trades (rich IV/RV >= {:.2f} AND calm bonds): {}'.format(RICH, len(SEL)))

a = np.array([r['net'] for r in SEL])
print()
print('=' * 100)
print('1. SEQUENTIAL DRAWDOWN — trades taken in order, 1 contract, no compounding')
print('=' * 100)
eq = np.cumsum(a)
peak = np.maximum.accumulate(eq)
dd = eq - peak
print('  total {:+,.0f} over {} trades ({:.0f}/yr)'.format(eq[-1], len(a), len(a) / 30.0))
print('  max drawdown {:+,.0f}   ({:.1f}x the mean trade)'.format(dd.min(), abs(dd.min() / a.mean())))
i = int(np.argmin(dd))
print('  deepest point at trade {} on {}'.format(i, SEL[i]['date']))
j = int(np.argmax(peak[:i + 1]))
print('  drawdown ran {} -> {}, {} trades'.format(SEL[j]['date'], SEL[i]['date'], i - j))
rec = None
for k in range(i, len(eq)):
    if eq[k] >= peak[i]:
        rec = k
        break
print('  recovered by {}'.format(SEL[rec]['date'] if rec else 'NOT RECOVERED in sample'))
print()
print('  worst single trades:')
for r in sorted(SEL, key=lambda r: r['net'])[:6]:
    print('    {}  {:<5} IV {:.3f}  IV/RV {:.2f}  net {:+.0f}'.format(
        r['date'], r['sym'], r['iv'], r['ivrv'], r['net']))

print()
print('=' * 100)
print('2. CRISIS — did the calm-bond filter keep us out of 2008?')
print('=' * 100)
for lab, a_, b_ in (('2008 GFC', '2008-01', '2009-07'), ('2020 covid', '2020-02', '2020-05'),
                    ('2022 rate shock', '2022-01', '2022-11')):
    taken = [r for r in SEL if a_ <= r['date'][:7] <= b_]
    avail = [r for r in ALL if a_ <= r['date'][:7] <= b_]
    rich_only = [r for r in avail if r['ivrv'] >= RICH]
    if not avail:
        continue
    x = np.array([r['net'] for r in taken]) if taken else np.array([0.0])
    print('  {:<16} sessions {:>4}   rich-IV {:>4}   TAKEN {:>4}   net {:+,.0f}  worst {:+.0f}'
          .format(lab, len(avail), len(rich_only), len(taken),
                  x.sum() if taken else 0, x.min() if taken else 0))
    blocked = len(rich_only) - len(taken)
    print('  {:<16} filter blocked {} of {} rich-IV opportunities ({:.0f}%)'.format(
        '', blocked, len(rich_only), 100 * blocked / max(len(rich_only), 1)))

print()
print('=' * 100)
print('3. SIZING — a 5% wide SPY spread does not fit a 2% risk budget')
print('=' * 100)
EQUITY, RISK_PCT = 100_000.0, 0.02
print('  {:<10} {:>12} {:>12} {:>12} {:>10} {:>12}'.format(
    'width', 'risk/contract', 'contracts', 'credit/ct', 'net/ct', 'net/trade'))
for wpct in (0.05, 0.03, 0.02, 0.015, 0.01):
    width = 769.35 * wpct
    credit = float(np.mean([r['credit'] for r in SEL])) * (wpct / 0.05)
    risk = width * 100 - credit
    n_ct = int((EQUITY * RISK_PCT) // risk) if risk > 0 else 0
    net_ct = a.mean() * (wpct / 0.05)
    print('  {:<10} {:>12,.0f} {:>12} {:>12,.0f} {:>10.0f} {:>12,.0f}'.format(
        '{:.1%}'.format(wpct), risk, n_ct, credit, net_ct, net_ct * n_ct))
print()
print('  Narrowing scales credit, risk and P&L together, so net-per-trade is roughly flat -')
print('  the width choice is about GRANULARITY, not edge.')

print()
print('=' * 100)
print('4. ANNUALISED, at a 2%-risk position size')
print('=' * 100)
for wpct in (0.02, 0.015, 0.01):
    width = 769.35 * wpct
    credit = float(np.mean([r['credit'] for r in SEL])) * (wpct / 0.05)
    risk = width * 100 - credit
    n_ct = int((EQUITY * RISK_PCT) // risk) if risk > 0 else 0
    net_ct = a.mean() * (wpct / 0.05)
    per_yr = (len(a) / 30.0) * net_ct * n_ct
    worst = a.min() * (wpct / 0.05) * n_ct
    print('  width {:<6} {:>3} contracts  ->  {:+,.0f}/yr on ${:,.0f} = {:+.2f}%/yr   '
          'worst single trade {:+,.0f}'.format(
              '{:.1%}'.format(wpct), n_ct, per_yr, EQUITY, 100 * per_yr / EQUITY, worst))

print()
print('=' * 100)
print('5. CURRENT READING — is it firing now?')
print('=' * 100)
last = sorted(ALL, key=lambda r: r['date'])[-1]
print('  most recent modelled session: {}  {}'.format(last['date'], last['sym']))
print('  IV {:.3f}   trailing RV {:.3f}   IV/RV {:.2f}   threshold {:.2f}'.format(
    last['iv'], last['rv'], last['ivrv'], RICH))
print('  bonds: {}'.format('CALM' if last['calm'] else 'STRESSED'))
fires = last['ivrv'] >= RICH and last['calm'] is True
print('  >>> {} <<<'.format('FIRES' if fires else 'no trade'))
recent = sorted([r for r in ALL if r['sym'] == 'SPY'], key=lambda r: r['date'])[-10:]
print()
print('  {:<12} {:>8} {:>8} {:>8} {:>10} {:>8}'.format(
    'date', 'VIX', 'RV20', 'IV/RV', 'bonds', 'fires'))
for r in recent:
    print('  {:<12} {:>8.2f} {:>8.3f} {:>8.2f} {:>10} {:>8}'.format(
        r['date'], r['iv'] * 100, r['rv'], r['ivrv'],
        'calm' if r['calm'] else 'stressed',
        'YES' if (r['ivrv'] >= RICH and r['calm']) else '-'))

"""The one overlay that survived out-of-sample: TLT volatility regime.

Confirmed on 4,359 single-name events (t=6.58) after being only suggestive on 115 ETF events
(t=1.64). Now the questions that decide whether it is usable:
  1. era stability - does it hold in every period, or is it another 2024-2026 artifact?
  2. does it STACK with the volume tiers, or are they measuring the same thing?
  3. what does it do on the tradeable low-friction universe, and to signal frequency?
"""
import csv, io, json, math, sys
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(line for line in _src.splitlines()
                 if not line.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 10 or len(b) < 10:
        return float('nan'), float('nan')
    d = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, (d / se if se > 0 else float('nan'))


print()
print('=' * 100)
print('1. ERA STABILITY of the calm-bond overlay (single names)')
print('=' * 100)
print('{:<14} {:>7} {:>9} {:>7} {:>7}   {:>8} {:>9} {:>7}   {:>9}'.format(
    'era', 'n calm', 'raw%', 't', 'win%', 'n stress', 'raw%', 't', 't(diff)'))
npos = ntot = 0
for lab, a_, b_ in [('2016-2017', '2016', '2018'), ('2018-2019', '2018', '2020'),
                    ('2020-2021', '2020', '2022'), ('2022-2023', '2022', '2024'),
                    ('2024-2026', '2024', '2027')]:
    g = [r for r in EV if a_ <= r['date'][:4] < b_]
    c = stat([r for r in g if r['vol']])
    s = stat([r for r in g if not r['vol']])
    if not c or not s:
        print('{:<14} {:>7}  (thin)'.format(lab, len(g)))
        continue
    d, td = welch([r['f3'] for r in g if r['vol']], [r['f3'] for r in g if not r['vol']])
    ntot += 1
    npos += 1 if d > 0 else 0
    print('{:<14} {:>7} {:>9.3f} {:>7.2f} {:>6.1f}%   {:>8} {:>9.3f} {:>7.2f}   {:>9.2f}'.format(
        lab, c['n'], c['raw'], c['t'], c['win'], s['n'], s['raw'], s['t'], td))
print('\n  calm beat stressed in {}/{} eras'.format(npos, ntot))

print()
print('=' * 100)
print('2. DOES IT STACK WITH THE VOLUME TIERS? (single names)')
print('=' * 100)
print('{:<14}'.format('volume cell') + '{:>26}{:>26}'.format('CALM bonds', 'STRESSED bonds'))
print('{:<14}'.format('') + '{:>26}{:>26}'.format('n    raw%    t   win%', 'n    raw%    t   win%'))
for vlab, vlo, vhi in [('1.4-1.8', 1.4, 1.8), ('1.8-2.5', 1.8, 2.5),
                       ('2.5-4.0', 2.5, 4.0), ('>4.0', 4.0, 1e9)]:
    line = '{:<14}'.format(vlab)
    for calm in (True, False):
        g = [r for r in EV if vlo <= r['volx'] < vhi and r['vol'] == calm]
        s_ = stat(g)
        line += '{:>26}'.format('{:>5} {:+7.2f} {:>5.1f} {:>5.1f}%'.format(
            s_['n'], s_['raw'], s_['t'], s_['win']) if s_ else '-')
    print(line)

print()
print('=' * 100)
print('3. ON THE TRADEABLE LOW-FRICTION UNIVERSE')
print('=' * 100)
FR = json.load(open('friction_screen.json'))
for budget in (20, 35, 60):
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    g = [r for r in EV if r['sym'] in names]
    if len(g) < 60:
        continue
    c = stat([r for r in g if r['vol']])
    s = stat([r for r in g if not r['vol']])
    if not c or not s:
        continue
    d, td = welch([r['f3'] for r in g if r['vol']], [r['f3'] for r in g if not r['vol']])
    per5 = c['n'] / 19.1 / 252 * 5
    print('  friction <= ${:<3} ({:>3} names)'.format(budget, len(names)))
    print('     CALM     n={:<5} {:+.3f}%  t={:.2f}  win {:.1f}%   -> {:.2f} signals/5 sessions'
          .format(c['n'], c['raw'], c['t'], c['win'], per5))
    print('     STRESSED n={:<5} {:+.3f}%  t={:.2f}  win {:.1f}%   t(diff)={:.2f}'
          .format(s['n'], s['raw'], s['t'], s['win'], td))

print()
print('=' * 100)
print('4. FREQUENCY COST and CURRENT REGIME')
print('=' * 100)
tot = len(EV)
calm = sum(1 for r in EV if r['vol'])
print('  capitulation events in a calm-bond regime: {}/{} = {:.0f}%'.format(
    calm, tot, 100 * calm / tot))
days = len(REG)
cd = sum(1 for d in REG if REG[d]['vol'])
print('  calendar days in a calm-bond regime:       {}/{} = {:.0f}%'.format(
    cd, days, 100 * cd / days))
recent = sorted(REG)[-1]
last20 = sorted(REG)[-20:]
print('  CURRENT regime as of {}: {}'.format(
    recent, 'CALM' if REG[recent]['vol'] else 'STRESSED'))
print('  last 20 sessions: {} calm'.format(sum(1 for d in last20 if REG[d]['vol'])))

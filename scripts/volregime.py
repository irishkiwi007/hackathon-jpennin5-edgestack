"""STAGE 1 — the mechanism behind the hypothesis, on 33 years of SPY (no option prices needed).

"Harvest theta in low vol, buy straddles in high vol" reduces to a claim about vol dynamics:

  short premium wins when FORWARD realised vol comes in BELOW what the option was priced at
  long premium wins when FORWARD realised vol comes in ABOVE it

Options are priced off something close to recent realised vol. So the testable core is:

  conditional on trailing vol, does forward vol come in below or above trailing?

If low-vol states see forward vol RISE (mean reversion up), selling premium in calm markets is
structurally penalised - the opposite of the hypothesis. If low-vol states persist, it is supported.
"""
import csv, math, io, sys, datetime, statistics

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
R = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical\SPY.csv'
rows = list(csv.DictReader(open(R, encoding='utf-8')))
d = [datetime.date.fromisoformat(r['date']) for r in rows]
c = [float(r['adj_close']) for r in rows]
N = len(c)
lr = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
print(f'SPY {N} sessions  {d[0]} -> {d[-1]}')
ANN = math.sqrt(252)


def rv(a, b):
    s = lr[a:b]
    if len(s) < 5:
        return None
    m = sum(s) / len(s)
    return math.sqrt(sum((x - m) ** 2 for x in s) / (len(s) - 1)) * ANN


LOOK, FWD = 20, 21          # 20d trailing, 21d forward (~1 month, standard option horizon)
obs = []
for i in range(LOOK + 1, N - FWD - 1):
    t = rv(i - LOOK, i)
    f = rv(i, i + FWD)
    if t and f:
        obs.append((d[i], t, f))
print(f'observations: {len(obs)}')

obs_sorted = sorted(obs, key=lambda x: x[1])
DEC = 10
size = len(obs_sorted) // DEC
print('\n' + '=' * 96)
print('FORWARD vs TRAILING VOL, BY TRAILING-VOL DECILE  (33 years)')
print('=' * 96)
print(f'{"decile":>7} {"trailing RV band":>22} {"mean trailing":>14} {"mean forward":>13} '
      f'{"fwd/trail":>10} {"P(fwd<trail)":>13}')
bands = []
for k in range(DEC):
    grp = obs_sorted[k * size:(k + 1) * size] if k < DEC - 1 else obs_sorted[k * size:]
    t = [x[1] for x in grp]
    f = [x[2] for x in grp]
    mt, mf = sum(t) / len(t), sum(f) / len(f)
    ratio = mf / mt
    pbelow = sum(1 for x in grp if x[2] < x[1]) / len(grp)
    bands.append((k + 1, min(t), max(t), mt, mf, ratio, pbelow))
    print(f'{k+1:>7} {min(t)*100:>9.1f}-{max(t)*100:<11.1f}% {mt*100:>13.1f}% {mf*100:>12.1f}% '
          f'{ratio:>10.3f} {pbelow*100:>12.1f}%')

print("""
fwd/trail < 1  -> vol tends to FALL from here; premium sold at prices reflecting trailing vol
                  is likely to expire cheap. Favours SHORT premium.
fwd/trail > 1  -> vol tends to RISE from here. Favours LONG premium.
P(fwd<trail)   -> how often, not just on average. Short premium needs this HIGH.""")

lo_b, hi_b = bands[0], bands[-1]
print(f'\nLOWEST decile  (trailing {lo_b[3]*100:.1f}%): fwd/trail {lo_b[5]:.3f}, '
      f'P(fwd<trail) {lo_b[6]*100:.1f}%')
print(f'HIGHEST decile (trailing {hi_b[3]*100:.1f}%): fwd/trail {hi_b[5]:.3f}, '
      f'P(fwd<trail) {hi_b[6]*100:.1f}%')

if lo_b[5] > 1.0 and hi_b[5] < 1.0:
    print("""
VERDICT: vol MEAN-REVERTS in both directions. From calm states it rises; from stressed states
it falls. That is the OPPOSITE of the hypothesis on both legs - it favours BUYING premium when
vol is low and SELLING it when vol is high.""")
elif lo_b[5] < 1.0 and hi_b[5] > 1.0:
    print('\nVERDICT: vol PERSISTS in both directions - supports the hypothesis as stated.')
else:
    print('\nVERDICT: mixed - see the decile table.')

print('\n' + '=' * 96)
print('STABILITY: same test, per era')
print('=' * 96)
ERAS = [('1993-2002', datetime.date(1993, 1, 1), datetime.date(2002, 12, 31)),
        ('2003-2007', datetime.date(2003, 1, 1), datetime.date(2007, 12, 31)),
        ('2008-2012', datetime.date(2008, 1, 1), datetime.date(2012, 12, 31)),
        ('2013-2019', datetime.date(2013, 1, 1), datetime.date(2019, 12, 31)),
        ('2020-2022', datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
        ('2023-2026', datetime.date(2023, 1, 1), datetime.date(2026, 12, 31))]
print(f'{"era":<12} {"n":>6} {"lowest tercile fwd/trail":>26} {"highest tercile fwd/trail":>27}')
for nm, a, b in ERAS:
    g = [x for x in obs if a <= x[0] <= b]
    if len(g) < 200:
        continue
    g = sorted(g, key=lambda x: x[1])
    t3 = len(g) // 3
    lo = g[:t3]
    hi = g[-t3:]
    rl = (sum(x[2] for x in lo) / len(lo)) / (sum(x[1] for x in lo) / len(lo))
    rh = (sum(x[2] for x in hi) / len(hi)) / (sum(x[1] for x in hi) / len(hi))
    print(f'{nm:<12} {len(g):>6} {rl:>26.3f} {rh:>27.3f}')

print("""
If the low column is consistently > 1 and the high column consistently < 1 across every era,
vol mean reversion is a structural fact and the hypothesis is inverted.""")

# What a straddle actually needs: realised move vs the move implied by trailing vol
print('\n' + '=' * 96)
print('STRADDLE ECONOMICS PROXY — realised |move| vs move implied by trailing vol')
print('=' * 96)
print('A short straddle priced off trailing vol keeps money when |actual move| < implied move.')
print(f'{"decile":>7} {"trailing RV":>12} {"implied 21d move":>18} {"actual |move|":>15} '
       f'{"ratio":>8} {"short wins":>11}')
for k in range(DEC):
    grp = obs_sorted[k * size:(k + 1) * size] if k < DEC - 1 else obs_sorted[k * size:]
    imp, act, wins = [], [], 0
    for dt, t, f in grp:
        i = next((j for j in range(len(d)) if d[j] == dt), None)
        if i is None or i + FWD >= N:
            continue
        im = t * math.sqrt(FWD / 252)
        am = abs(math.log(c[i + FWD] / c[i]))
        imp.append(im)
        act.append(am)
        # 0.8 factor: ATM straddle premium is ~0.8 x the 1-sigma move
        if am < 0.8 * im:
            wins += 1
    if not imp:
        continue
    mi, ma = sum(imp) / len(imp), sum(act) / len(act)
    print(f'{k+1:>7} {sum(x[1] for x in grp)/len(grp)*100:>11.1f}% {mi*100:>17.2f}% '
          f'{ma*100:>14.2f}% {ma/mi:>8.3f} {wins/len(imp)*100:>10.1f}%')
print("""
'short wins' = share of windows where the actual move stayed inside the straddle premium.
Above ~50% favours selling; below favours buying. Compare the top and bottom deciles.""")

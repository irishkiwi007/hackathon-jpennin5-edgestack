"""Trend vs reversion, tested SEPARATELY for up moves and down moves.

The previous analysis used corr(past, forward) inside mixed-sign buckets. That is the wrong tool:
with SPY drifting up ~10%/yr, forward returns are positive almost everywhere, so a negative
correlation can simply mean "down moves bounce harder than up moves continue" - both positive.

Correct framing, against the unconditional baseline:

  after an UP move:   forward > baseline  -> CONTINUATION (up-trend persists)
                      forward < baseline  -> REVERSION (up-move fades)
  after a DOWN move:  forward < baseline  -> CONTINUATION (down-trend persists)
                      forward > baseline  -> REVERSION (sell-off bounces)
"""
import csv, math, io, sys, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'


def load(sym):
    try:
        rows = list(csv.DictReader(open(f'{BASE}\\{sym}.csv', encoding='utf-8')))
    except Exception:
        return None
    return ([datetime.date.fromisoformat(r['date']) for r in rows],
            [float(r['adj_close']) for r in rows])


d, C = load('SPY')
N = len(C)
lr = [math.log(C[i] / C[i - 1]) for i in range(1, N)]
ANN = math.sqrt(252)
L, M = 21, 21


def rv(i, w=20):
    if i < w + 1:
        return None
    s = lr[i - w:i]
    m = sum(s) / len(s)
    return math.sqrt(sum((x - m) ** 2 for x in s) / (w - 1)) * ANN


def er(i, L):
    net = abs(C[i] - C[i - L])
    path = sum(abs(C[j] - C[j - 1]) for j in range(i - L + 1, i + 1))
    return net / path if path > 0 else None


rows = []
for i in range(260, N - M, 5):        # step 5 to cut overlap
    e, v, vp = er(i, L), rv(i), rv(i - L)
    if e is None or v is None or vp is None:
        continue
    p = math.log(C[i] / C[i - L])
    f = math.log(C[i + M] / C[i])
    ma200 = sum(C[i - 200:i]) / 200
    rows.append(dict(past=p, fwd=f, er=e, rv=v, dvol=v / vp,
                     z=p / (v / ANN * math.sqrt(L)), ma=C[i] / ma200 - 1))

base = sum(r['fwd'] for r in rows) / len(rows)
sd_all = math.sqrt(sum((r['fwd'] - base) ** 2 for r in rows) / (len(rows) - 1))
print(f'SPY {d[0]} -> {d[-1]}   sample {len(rows)} (step 5, L={L} M={M})')
print(f'UNCONDITIONAL BASELINE forward {M}d return = {base*100:+.3f}%   sd {sd_all*100:.2f}%\n')


def cell(g, direction):
    n = len(g)
    if n < 15:
        return None
    m = sum(x['fwd'] for x in g) / n
    sd = math.sqrt(sum((x['fwd'] - m) ** 2 for x in g) / (n - 1))
    exc = m - base
    t = exc / (sd / math.sqrt(n)) if sd else 0
    same = sum(1 for x in g if (x['fwd'] > 0) == (x['past'] > 0)) / n
    if direction == 'up':
        rd = 'CONTINUES' if exc > 0 else 'REVERTS'
    else:
        rd = 'CONTINUES' if exc < 0 else 'REVERTS'
    if abs(t) < 1.7:
        rd = 'no signal'
    return dict(n=n, mean=m, exc=exc, t=t, same=same, rd=rd)


def table(title, keyfn, labels):
    print('=' * 104)
    print(title)
    print('=' * 104)
    print(f'{"bucket":<28} {"dir":>5} {"n":>5} {"mean fwd":>10} {"vs base":>9} {"t":>7} '
          f'{"same-sign":>10} {"verdict":>11}')
    for lab in labels:
        for direction, sel in (('UP', lambda x: x['past'] > 0),
                               ('DOWN', lambda x: x['past'] <= 0)):
            g = [x for x in rows if keyfn(x) == lab and sel(x)]
            c = cell(g, 'up' if direction == 'UP' else 'down')
            if not c:
                print(f'{lab:<28} {direction:>5} {len(g):>5}   (too few)')
                continue
            print(f'{lab:<28} {direction:>5} {c["n"]:>5} {c["mean"]*100:>9.2f}% '
                  f'{c["exc"]*100:>+8.2f}% {c["t"]:>7.2f} {c["same"]*100:>9.1f}% '
                  f'{c["rd"]:>11}')
        print()


# --- overall up vs down ---
print('=' * 104)
print('0. BASELINE SPLIT — all up moves vs all down moves')
print('=' * 104)
print(f'{"":<28} {"dir":>5} {"n":>5} {"mean fwd":>10} {"vs base":>9} {"t":>7} '
      f'{"same-sign":>10} {"verdict":>11}')
for direction, sel, dd in (('UP', lambda x: x['past'] > 0, 'up'),
                           ('DOWN', lambda x: x['past'] <= 0, 'down')):
    g = [x for x in rows if sel(x)]
    c = cell(g, dd)
    print(f'{"all moves":<28} {direction:>5} {c["n"]:>5} {c["mean"]*100:>9.2f}% '
          f'{c["exc"]*100:>+8.2f}% {c["t"]:>7.2f} {c["same"]*100:>9.1f}% {c["rd"]:>11}')
print()

# --- by efficiency ratio quartile ---
ers = sorted(x['er'] for x in rows)
q = [ers[len(ers) * k // 4] for k in (1, 2, 3)]


def erlab(x):
    return ('ER q1 choppy' if x['er'] < q[0] else 'ER q2' if x['er'] < q[1]
            else 'ER q3' if x['er'] < q[2] else 'ER q4 clean')


table('1. BY PATH CLEANLINESS (Kaufman efficiency ratio)', erlab,
      ['ER q1 choppy', 'ER q2', 'ER q3', 'ER q4 clean'])

# --- by magnitude ---
zs = sorted(abs(x['z']) for x in rows)
zq = [zs[len(zs) * k // 3] for k in (1, 2)]


def zlab(x):
    a = abs(x['z'])
    return 'small move' if a < zq[0] else 'medium move' if a < zq[1] else 'LARGE move'


table('2. BY MAGNITUDE (|z-score| of the move)', zlab,
      ['small move', 'medium move', 'LARGE move'])

# --- by vol regime ---
vs = sorted(x['rv'] for x in rows)
vq = [vs[len(vs) * k // 3] for k in (1, 2)]


def vlab(x):
    return 'low vol' if x['rv'] < vq[0] else 'mid vol' if x['rv'] < vq[1] else 'HIGH vol'


table('3. BY VOLATILITY REGIME', vlab, ['low vol', 'mid vol', 'HIGH vol'])

# --- by vol direction ---
def dlab(x):
    return 'vol contracting' if x['dvol'] < 0.95 else (
        'vol flat' if x['dvol'] < 1.15 else 'vol EXPANDING')


table('4. BY VOLATILITY DIRECTION DURING THE MOVE', dlab,
      ['vol contracting', 'vol flat', 'vol EXPANDING'])

# --- 200d MA context ---
def mlab(x):
    return 'below 200d MA' if x['ma'] < 0 else 'above 200d MA'


table('5. BY TREND CONTEXT (vs 200-day MA)', mlab, ['below 200d MA', 'above 200d MA'])

print('=' * 104)
print('6. THE STRONGEST CELLS, ranked by |t|')
print('=' * 104)
allcells = []
for name, fn, labs in (('cleanliness', erlab, ['ER q1 choppy', 'ER q2', 'ER q3', 'ER q4 clean']),
                       ('magnitude', zlab, ['small move', 'medium move', 'LARGE move']),
                       ('vol regime', vlab, ['low vol', 'mid vol', 'HIGH vol']),
                       ('vol direction', dlab, ['vol contracting', 'vol flat', 'vol EXPANDING']),
                       ('trend context', mlab, ['below 200d MA', 'above 200d MA'])):
    for lab in labs:
        for direction, sel, dd in (('UP', lambda x: x['past'] > 0, 'up'),
                                   ('DOWN', lambda x: x['past'] <= 0, 'down')):
            g = [x for x in rows if fn(x) == lab and sel(x)]
            c = cell(g, dd)
            if c:
                allcells.append((abs(c['t']), name, lab, direction, c))
allcells.sort(reverse=True, key=lambda x: x[0])
print(f'{"feature":<15} {"bucket":<20} {"dir":>5} {"n":>5} {"vs base":>9} {"t":>7} {"verdict":>11}')
for _, name, lab, direction, c in allcells[:10]:
    print(f'{name:<15} {lab:<20} {direction:>5} {c["n"]:>5} {c["exc"]*100:>+8.2f}% '
          f'{c["t"]:>7.2f} {c["rd"]:>11}')

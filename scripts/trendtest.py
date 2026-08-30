"""Distinguishing a trend that continues from one that mean-reverts.

Method: for each day, measure a past move over lookback L and the forward move over horizon M.
The CONTINUATION COEFFICIENT is corr(past, forward). Positive = trends persist. Negative = reverts.
Then condition that coefficient on observable features to find which states flip the sign.

Non-overlapping sampling is used for the headline numbers so significance is not inflated.
SPY 1993-2026, split-adjusted.
"""
import csv, math, io, sys, datetime, statistics

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'


def load(sym):
    rows = list(csv.DictReader(open(f'{BASE}\\{sym}.csv', encoding='utf-8')))
    d = [datetime.date.fromisoformat(r['date']) for r in rows]
    c = [float(r['adj_close']) for r in rows]
    o = [float(r['open']) for r in rows]
    h = [float(r['high']) for r in rows]
    lo = [float(r['low']) for r in rows]
    return d, o, h, lo, c


d, O, H, L_, C = load('SPY')
N = len(C)
lr = [math.log(C[i] / C[i - 1]) for i in range(1, N)]
ANN = math.sqrt(252)
print(f'SPY {N} sessions {d[0]} -> {d[-1]}')


def rv(i, w=20):
    if i < w + 1:
        return None
    s = lr[i - w:i]
    m = sum(s) / len(s)
    return math.sqrt(sum((x - m) ** 2 for x in s) / (w - 1)) * ANN


def eff_ratio(i, L):
    """Kaufman: |net move| / sum |daily moves|. 1 = straight line, 0 = pure churn."""
    if i - L < 1:
        return None
    net = abs(C[i] - C[i - L])
    path = sum(abs(C[j] - C[j - 1]) for j in range(i - L + 1, i + 1))
    return net / path if path > 0 else None


def corr(a, b):
    n = len(a)
    if n < 20:
        return None, 0, n
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return None, 0, n
    r = num / (da * db)
    t = r * math.sqrt((n - 2) / max(1 - r * r, 1e-12))
    return r, t, n


print('\n' + '=' * 96)
print('1. THE HORIZON EFFECT — continuation coefficient corr(past L, forward M)')
print('   non-overlapping samples')
print('=' * 96)
HOR = [5, 10, 21, 63, 126, 252]
print(f'{"lookback L":>11} | ' + ' '.join(f'{"M="+str(m):>12}' for m in HOR))
for L in HOR:
    cells = []
    for M in HOR:
        step = L + M              # non-overlapping
        past, fwd = [], []
        i = L
        while i + M < N:
            past.append(math.log(C[i] / C[i - L]))
            fwd.append(math.log(C[i + M] / C[i]))
            i += step
        r, t, n = corr(past, fwd)
        cells.append(f'{r:+.3f}{"*" if r is not None and abs(t)>2 else " "}({n:>3})'
                     if r is not None else f'{"-":>12}')
    print(f'{L:>11} | ' + ' '.join(f'{c:>12}' for c in cells))
print('  * = |t| > 2.   negative = mean reverting, positive = trending')

print("""
The literature's "momentum sandwich": reversal at days, momentum at 1-12 months, reversal beyond.
Read the diagonal and the top-left vs bottom-right corners.""")

# ---- conditional analysis ----
L, M = 21, 21          # 1 month past -> 1 month forward
rows = []
for i in range(260, N - M):
    p = math.log(C[i] / C[i - L])
    f = math.log(C[i + M] / C[i])
    v = rv(i)
    v_prev = rv(i - L)
    er = eff_ratio(i, L)
    if v is None or v_prev is None or er is None:
        continue
    ma200 = sum(C[i - 200:i]) / 200
    gapsum = sum(abs(math.log(O[j] / C[j - 1])) for j in range(i - L + 1, i + 1))
    pathsum = sum(abs(lr[j - 1]) for j in range(i - L + 1, i + 1))
    rows.append(dict(i=i, date=d[i], past=p, fwd=f, rv=v, dvol=v / v_prev, er=er,
                     z=p / (v / ANN * math.sqrt(L)) if v else 0,
                     ma=C[i] / ma200 - 1,
                     gap=gapsum / pathsum if pathsum else 0))
print(f'\nconditional sample: {len(rows)} (overlapping; effective n ~ {len(rows)//M})')


def bucket(rows, key, label, nb=4, subsample=M):
    """Continuation coefficient within quantile buckets of `key`, subsampled to reduce overlap."""
    sub = rows[::max(1, subsample // 4)]
    sub = sorted(sub, key=lambda r: r[key])
    size = len(sub) // nb
    print(f'\n{label}')
    print(f'{"bucket":>8} {"range":>22} {"n":>5} {"corr(past,fwd)":>16} {"t":>7} {"reading":>16}')
    for k in range(nb):
        g = sub[k * size:(k + 1) * size] if k < nb - 1 else sub[k * size:]
        r, t, n = corr([x['past'] for x in g], [x['fwd'] for x in g])
        if r is None:
            continue
        rd = 'TRENDS' if r > 0.08 and abs(t) > 2 else (
            'MEAN REVERTS' if r < -0.08 and abs(t) > 2 else 'no signal')
        print(f'{k+1:>8} {g[0][key]:>10.3f}-{g[-1][key]:<10.3f} {n:>5} {r:>+16.3f} '
              f'{t:>7.2f} {rd:>16}')


print('\n' + '=' * 96)
print('2. WHAT FLIPS THE SIGN?  (L=21d past -> M=21d forward)')
print('=' * 96)
bucket(rows, 'er', 'A. KAUFMAN EFFICIENCY RATIO — how straight the path was')
bucket(rows, 'rv', 'B. REALISED VOL at the end of the move')
bucket(rows, 'dvol', 'C. VOL DIRECTION — did vol expand or contract during the move? (>1 = expanded)')
bucket(rows, 'z', 'D. Z-SCORE of the move — how overextended')
bucket(rows, 'gap', 'E. GAP SHARE — how much of the path came overnight')
bucket(rows, 'ma', 'F. DISTANCE FROM 200d MA — trend context')

print('\n' + '=' * 96)
print('3. THE INTERACTION THE LITERATURE PREDICTS (Daniel-Moskowitz momentum crashes)')
print('=' * 96)
print('  momentum should fail in PANIC states: high vol AND a prior decline')
sub = rows[::5]
med_v = sorted(x['rv'] for x in sub)[len(sub) // 2]
print(f'{"state":<34} {"n":>6} {"corr":>8} {"t":>7} {"reading":>16}')
for vlab, vsel in (('low vol', lambda x: x['rv'] <= med_v),
                   ('high vol', lambda x: x['rv'] > med_v)):
    for plab, psel in (('after UP move', lambda x: x['past'] > 0),
                       ('after DOWN move', lambda x: x['past'] <= 0)):
        g = [x for x in sub if vsel(x) and psel(x)]
        r, t, n = corr([x['past'] for x in g], [x['fwd'] for x in g])
        if r is None:
            continue
        rd = 'TRENDS' if r > 0.08 and abs(t) > 2 else (
            'MEAN REVERTS' if r < -0.08 and abs(t) > 2 else 'no signal')
        print(f'{vlab + ", " + plab:<34} {n:>6} {r:>+8.3f} {t:>7.2f} {rd:>16}')

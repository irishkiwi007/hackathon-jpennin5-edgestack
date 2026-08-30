"""Robustness of the headline finding: does a CLEAN trend (high Kaufman efficiency ratio)
predict reversal? That contradicts standard practitioner use of the indicator, so it needs
checking across horizons, assets and eras before it can be believed.

Also drops the gap-share panel from trendtest.py: it mixed RAW open with ADJUSTED close, which is
invalid across SPY's 1997/2000/2005 splits.
"""
import csv, math, io, sys, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'
SYMS = ['SPY', 'QQQ', 'TLT', 'XLP', 'XLV', 'SOXX', 'HYG', 'IEF']


def load(sym):
    try:
        rows = list(csv.DictReader(open(f'{BASE}\\{sym}.csv', encoding='utf-8')))
    except Exception:
        return None
    d = [datetime.date.fromisoformat(r['date']) for r in rows]
    c = [float(r['adj_close']) for r in rows]
    return d, c


def corr(a, b):
    n = len(a)
    if n < 25:
        return None, 0, n
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return None, 0, n
    r = num / (da * db)
    return r, r * math.sqrt((n - 2) / max(1 - r * r, 1e-12)), n


def er(C, i, L):
    net = abs(C[i] - C[i - L])
    path = sum(abs(C[j] - C[j - 1]) for j in range(i - L + 1, i + 1))
    return net / path if path > 0 else None


def study(C, L, M, step):
    out = []
    i = max(L, 30)
    while i + M < len(C):
        e = er(C, i, L)
        if e is not None:
            out.append((e, math.log(C[i] / C[i - L]), math.log(C[i + M] / C[i])))
        i += step
    return out


print('=' * 100)
print('1. ER x HORIZON on SPY — is the effect specific to L=21/M=21?')
print('=' * 100)
d, C = load('SPY')
print(f'{"L":>4} {"M":>4} | ' + ' '.join(f'{"ER q"+str(q):>14}' for q in (1, 2, 3, 4)))
for L in (10, 21, 63):
    for M in (5, 10, 21, 63):
        s = study(C, L, M, max(3, (L + M) // 8))
        s.sort(key=lambda x: x[0])
        q = len(s) // 4
        cells = []
        for k in range(4):
            g = s[k * q:(k + 1) * q] if k < 3 else s[k * q:]
            r, t, n = corr([x[1] for x in g], [x[2] for x in g])
            cells.append(f'{r:+.3f}{"*" if r is not None and abs(t)>2 else " "}({n:>3})'
                         if r is not None else f'{"-":>14}')
        print(f'{L:>4} {M:>4} | ' + ' '.join(f'{c:>14}' for c in cells))
print('  ER q1 = choppiest path, q4 = straightest.  * = |t|>2.  negative = reverts')

print('\n' + '=' * 100)
print('2. ER TOP-QUARTILE EFFECT ACROSS ASSETS (L=21, M=21)')
print('=' * 100)
print(f'{"sym":>6} {"n":>6} {"span":>22} {"ER q1 corr":>12} {"ER q4 corr":>12} {"q4 t":>7} '
      f'{"q4 reading":>16}')
for s in SYMS:
    r_ = load(s)
    if not r_:
        continue
    dd, cc = r_
    st = study(cc, 21, 21, 5)
    if len(st) < 200:
        continue
    st.sort(key=lambda x: x[0])
    q = len(st) // 4
    r1, _, _ = corr([x[1] for x in st[:q]], [x[2] for x in st[:q]])
    r4, t4, n4 = corr([x[1] for x in st[3 * q:]], [x[2] for x in st[3 * q:]])
    rd = 'MEAN REVERTS' if r4 < -0.08 and abs(t4) > 2 else (
        'TRENDS' if r4 > 0.08 and abs(t4) > 2 else 'no signal')
    print(f'{s:>6} {len(st):>6} {str(dd[0])+" "+str(dd[-1]):>22} '
          f'{r1:>+12.3f} {r4:>+12.3f} {t4:>7.2f} {rd:>16}')

print('\n' + '=' * 100)
print('3. ER TOP-QUARTILE EFFECT ON SPY BY ERA (out-of-sample-ish stability)')
print('=' * 100)
ERAS = [('1993-2002', 1993, 2002), ('2003-2009', 2003, 2009),
        ('2010-2016', 2010, 2016), ('2017-2026', 2017, 2026)]
print(f'{"era":<12} {"n":>6} {"ER q4 corr":>12} {"t":>7} {"reading":>16}')
d, C = load('SPY')
for nm, y0, y1 in ERAS:
    idx = [i for i, x in enumerate(d) if y0 <= x.year <= y1]
    if len(idx) < 400:
        continue
    a, b = idx[0], idx[-1]
    sub = C[max(0, a - 60):b + 1]
    st = study(sub, 21, 21, 5)
    if len(st) < 100:
        continue
    st.sort(key=lambda x: x[0])
    q = len(st) // 4
    r4, t4, n4 = corr([x[1] for x in st[3 * q:]], [x[2] for x in st[3 * q:]])
    rd = 'MEAN REVERTS' if r4 < -0.08 and abs(t4) > 2 else (
        'TRENDS' if r4 > 0.08 and abs(t4) > 2 else 'no signal')
    print(f'{nm:<12} {n4:>6} {r4:>+12.3f} {t4:>7.2f} {rd:>16}')

print('\n' + '=' * 100)
print('4. DOES DIRECTION MATTER? ER q4 split by sign of the prior move (SPY)')
print('=' * 100)
st = study(C, 21, 21, 5)
st.sort(key=lambda x: x[0])
q = len(st) // 4
top = st[3 * q:]
for lbl, sel in (('clean UP move', lambda x: x[1] > 0), ('clean DOWN move', lambda x: x[1] <= 0)):
    g = [x for x in top if sel(x)]
    r, t, n = corr([x[1] for x in g], [x[2] for x in g])
    fwd = [x[2] for x in g]
    mf = sum(fwd) / len(fwd) * 100
    print(f'  {lbl:<18} n={n:>4}  corr {r:+.3f}  t {t:>6.2f}  '
          f'mean forward 21d return {mf:+.2f}%')
print("""
If a clean move reverts, a clean UP move should be followed by weak/negative forward returns and a
clean DOWN move by positive ones. Check the mean forward return column, not just the correlation.""")

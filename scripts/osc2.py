"""Follow-up:
  (a) fix the swing-duration analysis (the zigzag returned <12 pivots and printed nothing)
  (b) THE DECISIVE TEST: is the spectral/ACF structure a genuine oscillation, or just the
      well-known lag-1 reversal? Strip the AR(1) component and re-test what remains.

A negative lag-1 autocorrelation ALONE produces elevated power at 2-4 day periods. That is not an
oscillator - it is a high-frequency bias. Distinguishing the two is the whole question.
"""
import csv, math, io, sys, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'
rows = list(csv.DictReader(open(f'{BASE}\\SPY.csv', encoding='utf-8')))
d = [datetime.date.fromisoformat(x['date']) for x in rows]
C = np.array([float(x['adj_close']) for x in rows])
r = np.diff(np.log(C))
N = len(r)
rng = np.random.default_rng(7)
print(f'SPY {len(C)} sessions {d[0]} -> {d[-1]}')


def acf(x, maxlag):
    x = x - x.mean()
    den = (x * x).sum()
    return np.array([1.0 if k == 0 else (x[:-k] * x[k:]).sum() / den for k in range(maxlag + 1)])


# ---------------------------------------------------------- (a) swings, fixed
print('\n' + '=' * 96)
print('A. SWING DURATIONS (zigzag reversal detector, fixed)')
print('=' * 96)


def zigzag(price, thresh):
    """Return indices of confirmed pivots. Direction is set on the FIRST qualifying move."""
    piv = []
    ext_i, ext_p, direction = 0, price[0], 0
    for i in range(1, len(price)):
        p = price[i]
        if direction == 0:
            if p >= ext_p * (1 + thresh):
                direction, ext_i, ext_p = 1, i, p
            elif p <= ext_p * (1 - thresh):
                direction, ext_i, ext_p = -1, i, p
            elif p > ext_p:
                ext_i, ext_p = i, p
            elif p < ext_p:
                ext_i, ext_p = i, p
        elif direction == 1:
            if p > ext_p:
                ext_i, ext_p = i, p
            elif p <= ext_p * (1 - thresh):
                piv.append(ext_i)
                direction, ext_i, ext_p = -1, i, p
        else:
            if p < ext_p:
                ext_i, ext_p = i, p
            elif p >= ext_p * (1 + thresh):
                piv.append(ext_i)
                direction, ext_i, ext_p = 1, i, p
    return piv


NS = 150
print(f'{"thresh":>7} {"pivots":>7} {"mean":>7} {"median":>7} {"sd":>7} {"CV":>6} '
      f'{"surrogate CV":>13} {"exp?":>6} {"verdict":>18}')
for th in (0.02, 0.03, 0.05, 0.08):
    piv = zigzag(C, th)
    if len(piv) < 12:
        print(f'{th*100:>6.0f}%  only {len(piv)} pivots')
        continue
    dur = np.diff(np.array(piv))
    cv = dur.std(ddof=1) / dur.mean()
    scv = []
    for _ in range(NS):
        s = rng.permutation(r)
        sp = np.exp(np.concatenate([[np.log(C[0])], np.cumsum(s)]))
        spv = zigzag(sp, th)
        if len(spv) > 12:
            sd_ = np.diff(np.array(spv))
            scv.append(sd_.std(ddof=1) / sd_.mean())
    m_scv = float(np.mean(scv))
    lo, hi = np.percentile(scv, [2.5, 97.5])
    verd = ('HAS A SCALE' if cv < lo else 'more erratic' if cv > hi else 'like random walk')
    print(f'{th*100:>6.0f}% {len(dur):>7} {dur.mean():>7.1f} {np.median(dur):>7.1f} '
          f'{dur.std(ddof=1):>7.1f} {cv:>6.2f} {m_scv:>13.2f} '
          f'{"~1" if abs(cv-1)<0.2 else "no":>6} {verd:>18}')
print("""
CV near 1.0 = exponential = memoryless = NO preferred swing length.
The surrogate column is a random walk with identical daily returns, so a real oscillator would
show a CV clearly BELOW its surrogate.""")

# ---------------------------------------------------------- (b) AR(1) residual test
print('\n' + '=' * 96)
print('B. IS IT AN OSCILLATOR, OR JUST LAG-1 REVERSAL?')
print('=' * 96)
a = acf(r, 60)
phi = a[1]
print(f'lag-1 autocorrelation phi = {phi:+.4f}   (explains {phi**2*100:.2f}% of return variance)')

# residual after removing AR(1)
res = r[1:] - phi * r[:-1]
ares = acf(res, 60)
sur = [rng.permutation(res) for _ in range(400)]
sa = np.array([acf(s, 60) for s in sur])
lo, hi = np.percentile(sa, [2.5, 97.5], axis=0)
out = [(k, ares[k]) for k in range(1, 61) if ares[k] < lo[k] or ares[k] > hi[k]]
print(f'\nAFTER removing the AR(1) component:')
print(f'  lags outside the 95% surrogate band: {len(out)} of 60  (expect ~3 by chance)')
if out:
    print('  ' + ', '.join(f'{k}:{v:+.4f}' for k, v in out[:14]))

print(f'\n  raw series had 17 of 60 outside. Residual has {len(out)}.')
if len(out) <= 6:
    print('  -> the structure is essentially ALL lag-1. No separate oscillation survives.')
else:
    print('  -> structure remains beyond lag-1; worth investigating further.')


# spectrum of an AR(1) with the same phi, as the benchmark shape
def spec(x):
    x = x - x.mean()
    return (np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2)[1:]


ps_real = spec(r)
ar1 = np.empty(N)
e = rng.standard_normal(N) * r.std()
ar1[0] = e[0]
for i in range(1, N):
    ar1[i] = phi * ar1[i - 1] + e[i]
ps_ar1 = spec(ar1)
fr = np.fft.rfftfreq(N, d=1.0)[1:]
pe = 1.0 / fr
print('\n  spectral shape: real vs a synthetic AR(1) with the same phi')
print(f'  {"period band":>16} {"real power (norm)":>19} {"AR(1) power (norm)":>20}')
for lo_p, hi_p in ((2, 3), (3, 5), (5, 10), (10, 21), (21, 63), (63, 250)):
    m = (pe >= lo_p) & (pe < hi_p)
    print(f'  {f"{lo_p}-{hi_p}d":>16} {ps_real[m].mean()/ps_real.mean():>19.3f} '
          f'{ps_ar1[m].mean()/ps_ar1.mean():>20.3f}')
print("""
  A pure negative-AR(1) process has power rising monotonically toward SHORT periods, with no peak.
  If the real column tracks the AR(1) column, the '3-4 day period' is that bias, not a cycle.""")

# ---------------------------------------------------------- (c) how fast does it change?
print('\n' + '=' * 96)
print('C. HOW QUICKLY DOES THE REVERSAL STRENGTH CHANGE OVER TIME?')
print('=' * 96)
W = 504
phis, dates = [], []
for s in range(0, N - W, 63):
    seg = r[s:s + W]
    phis.append(acf(seg, 1)[1])
    dates.append(d[s + W])
phis = np.array(phis)
print(f'rolling 2-year lag-1 autocorrelation: n={len(phis)} windows')
print(f'  mean {phis.mean():+.4f}   sd {phis.std():.4f}   min {phis.min():+.4f}   '
      f'max {phis.max():+.4f}')
print(f'  share of windows negative: {(phis<0).mean()*100:.0f}%')
ph_acf = acf(phis, 8)
print(f'  autocorrelation of the phi series itself: lag1 {ph_acf[1]:+.3f}, '
      f'lag4 {ph_acf[4]:+.3f}, lag8 {ph_acf[8]:+.3f}')
print('  (high lag-1 = the reversal strength drifts SLOWLY; near zero = it changes fast)')
print(f'\n{"decade":>10} {"mean phi":>10}')
for dec in (1990, 2000, 2010, 2020):
    m = [p for p, dt in zip(phis, dates) if dec <= dt.year < dec + 10]
    if m:
        print(f'{dec:>7}s {np.mean(m):>10.4f}')

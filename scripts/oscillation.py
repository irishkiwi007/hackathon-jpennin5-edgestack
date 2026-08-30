"""Do short-term reversions have a characteristic frequency?

CRITICAL METHOD NOTE: a random walk also produces peaks, troughs and oscillation-looking patterns.
Every statistic here is therefore compared against SURROGATE series built by shuffling the actual
returns - identical marginal distribution, all temporal structure destroyed. Anything the real
series does that the surrogates also do is not a finding.

SPY daily 1993-2026 (8,371 sessions), split-adjusted.
"""
import csv, math, io, sys, datetime, random
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical'


def load(sym):
    rows = list(csv.DictReader(open(f'{BASE}\\{sym}.csv', encoding='utf-8')))
    return ([datetime.date.fromisoformat(r['date']) for r in rows],
            np.array([float(r['adj_close']) for r in rows]))


d, C = load('SPY')
r = np.diff(np.log(C))
N = len(r)
print(f'SPY {len(C)} sessions {d[0]} -> {d[-1]}   returns n={N}')
rng = np.random.default_rng(42)
NSUR = 400


def surrogates(r, n=NSUR):
    return [rng.permutation(r) for _ in range(n)]


SUR = surrogates(r)

# ---------------------------------------------------------------- 1. ACF
print('\n' + '=' * 96)
print('1. AUTOCORRELATION OF RETURNS vs shuffled surrogates')
print('   a genuine oscillation would show alternating significant lags, not a single one')
print('=' * 96)


def acf(x, maxlag):
    x = x - x.mean()
    denom = (x * x).sum()
    return np.array([1.0 if k == 0 else (x[:-k] * x[k:]).sum() / denom for k in range(maxlag + 1)])


ML = 60
a = acf(r, ML)
sa = np.array([acf(s, ML) for s in SUR])
lo, hi = np.percentile(sa, [2.5, 97.5], axis=0)
sig = [(k, a[k]) for k in range(1, ML + 1) if a[k] < lo[k] or a[k] > hi[k]]
print(f'{"lag":>5} {"acf":>9} {"95% surrogate band":>24} {"":>6}')
for k in list(range(1, 21)) + [25, 30, 40, 50, 60]:
    flag = '  <-- outside' if (a[k] < lo[k] or a[k] > hi[k]) else ''
    print(f'{k:>5} {a[k]:>+9.4f}   [{lo[k]:+.4f}, {hi[k]:+.4f}]{flag}')
print(f'\nlags outside the 95% surrogate band: {len(sig)} of {ML} '
      f'(expect ~{0.05*ML:.0f} by chance)')
if sig:
    print('   ' + ', '.join(f'lag {k}: {v:+.4f}' for k, v in sig[:12]))

# ---------------------------------------------------------------- 2. spectrum
print('\n' + '=' * 96)
print('2. POWER SPECTRUM of returns vs surrogates — is any period over-represented?')
print('=' * 96)


def spec(x):
    x = x - x.mean()
    f = np.fft.rfft(x * np.hanning(len(x)))
    return (np.abs(f) ** 2)[1:]


ps = spec(r)
pss = np.array([spec(s) for s in SUR])
hi95 = np.percentile(pss, 95, axis=0)
freqs = np.fft.rfftfreq(N, d=1.0)[1:]
periods = 1.0 / freqs
band = (periods >= 2) & (periods <= 250)
ratio = ps[band] / np.median(pss, axis=0)[band]
pb, rb = periods[band], ratio
exceed = ps[band] > hi95[band]
print(f'periods examined: {band.sum()}   exceeding the 95th surrogate percentile: '
      f'{exceed.sum()} ({exceed.sum()/band.sum()*100:.1f}%, expect 5.0%)')
top = np.argsort(rb)[::-1][:10]
print(f'\n{"period (days)":>14} {"power / surrogate median":>26} {"exceeds 95%?":>14}')
for i in sorted(top, key=lambda j: -rb[j]):
    print(f'{pb[i]:>14.1f} {rb[i]:>26.2f} {"yes" if exceed[i] else "no":>14}')
print("""
If reversions had a true frequency, one period would stand far above the surrogate band and
neighbouring periods would too (a peak, not a spike). Scattered single spikes at ~5% are noise.""")

# ---------------------------------------------------------------- 3. swing durations
print('\n' + '=' * 96)
print('3. PEAK-TO-TROUGH SWING DURATIONS — do swings have a characteristic length?')
print('=' * 96)


def swings(price, thresh):
    """ZigZag: mark a reversal once price retraces `thresh` from the running extreme."""
    out, direction = [], 0
    piv_i, piv_p = 0, price[0]
    for i in range(1, len(price)):
        p = price[i]
        if direction >= 0 and p > piv_p:
            piv_i, piv_p = i, p
        elif direction <= 0 and p < piv_p:
            piv_i, piv_p = i, p
        if direction >= 0 and p < piv_p * (1 - thresh):
            out.append(piv_i)
            direction, piv_i, piv_p = -1, i, p
        elif direction <= 0 and p > piv_p * (1 + thresh):
            out.append(piv_i)
            direction, piv_i, piv_p = 1, i, p
    return out


print(f'{"threshold":>10} {"swings":>8} {"mean len":>9} {"median":>8} {"sd":>8} {"CV":>7} '
      f'{"surrogate CV":>14} {"verdict":>16}')
for th in (0.02, 0.03, 0.05, 0.08):
    piv = swings(C, th)
    if len(piv) < 12:
        continue
    dur = np.diff(piv)
    cv = dur.std(ddof=1) / dur.mean()
    scvs = []
    for s in SUR[:120]:
        sp = np.exp(np.concatenate([[np.log(C[0])], np.cumsum(s)]))
        spv = swings(sp, th)
        if len(spv) > 12:
            sd_ = np.diff(spv)
            scvs.append(sd_.std(ddof=1) / sd_.mean())
    scv = float(np.mean(scvs)) if scvs else float('nan')
    # CV of 1.0 = exponential = memoryless = no characteristic scale
    verdict = ('has a scale' if cv < scv - 0.15 else
               'more erratic' if cv > scv + 0.15 else 'like random walk')
    print(f'{th*100:>9.0f}% {len(dur):>8} {dur.mean():>9.1f} {np.median(dur):>8.1f} '
          f'{dur.std(ddof=1):>8.1f} {cv:>7.2f} {scv:>14.2f} {verdict:>16}')
print("""
CV (sd/mean) near 1.0 means durations are exponentially distributed - memoryless, no preferred
swing length. Materially below 1.0 would mean swings cluster around a characteristic duration.
The surrogate column is the random-walk benchmark for the same threshold.""")

# ---------------------------------------------------------------- 4. stability
print('\n' + '=' * 96)
print('4. DOES ANY DOMINANT PERIOD PERSIST OVER TIME?')
print('=' * 96)
W = 756  # ~3 years
print(f'{"window ending":>14} {"dominant period (d)":>21} {"power/median":>14}')
prev = []
for start in range(0, N - W, 504):
    seg = r[start:start + W]
    p_ = spec(seg)
    fr = np.fft.rfftfreq(W, d=1.0)[1:]
    pe = 1.0 / fr
    m = (pe >= 3) & (pe <= 120)
    med = np.median(p_[m])
    j = np.argmax(p_[m] / med)
    dom = pe[m][j]
    rat = (p_[m] / med)[j]
    prev.append(dom)
    print(f'{str(d[start + W]):>14} {dom:>21.1f} {rat:>14.1f}')
if len(prev) > 2:
    print(f'\ndominant period across windows: min {min(prev):.1f}d  max {max(prev):.1f}d  '
          f'sd {np.std(prev):.1f}d')
    print('A stable oscillator would repeat roughly the same period each window.')

# ---------------------------------------------------------------- 5. timeframes
print('\n' + '=' * 96)
print('5. DOES ANY TIMEFRAME SHOW MORE RELIABLE TIMING?')
print('   lag-1 autocorrelation of returns aggregated to each timeframe, vs surrogate band')
print('=' * 96)
print(f'{"timeframe":>12} {"n":>7} {"lag-1 acf":>11} {"95% surrogate band":>26} {"":>10}')
for agg, lab in ((1, 'daily'), (2, '2-day'), (3, '3-day'), (5, 'weekly'),
                 (10, '2-week'), (21, 'monthly'), (63, 'quarterly')):
    ra = np.array([r[i:i + agg].sum() for i in range(0, N - agg, agg)])
    if len(ra) < 60:
        continue
    a1 = acf(ra, 1)[1]
    sb = []
    for s in SUR[:200]:
        sa_ = np.array([s[i:i + agg].sum() for i in range(0, N - agg, agg)])
        sb.append(acf(sa_, 1)[1])
    l_, h_ = np.percentile(sb, [2.5, 97.5])
    out = 'OUTSIDE' if (a1 < l_ or a1 > h_) else ''
    print(f'{lab:>12} {len(ra):>7} {a1:>+11.4f}   [{l_:+.4f}, {h_:+.4f}] {out:>10}')

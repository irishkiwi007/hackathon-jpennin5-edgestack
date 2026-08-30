"""Correlation as a regime indicator, not a constant.

A static correlation average hides the most important fact in the table: SPY-TLT flipped sign in
2022. When bonds stop hedging equities, the diversification you thought you had is gone - and the
flip itself carries information about what kind of shock the market is pricing.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
SYMS = ['SPY', 'TLT', 'GLD', 'IWM', 'HYG']


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def bars(s):
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', s, '--timeframe', '1Day', '--start', '2016-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    out.sort(key=lambda x: x['t'])
    return {x['t'][:10]: x['c'] for x in out}


SER = {s: bars(s) for s in SYMS}
common = sorted(set.intersection(*[set(v) for v in SER.values()]))
R = {s: [math.log(SER[s][common[i]] / SER[s][common[i - 1]]) for i in range(1, len(common))]
     for s in SYMS}
D = common[1:]
n = len(D)
print(f'{n} daily returns  {D[0]} -> {D[-1]}')


def corr(a, b):
    m = len(a)
    ma, mb = sum(a) / m, sum(b) / m
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(m))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    return num / (da * db) if da and db else 0.0


W = 63  # ~3 months
print('\n' + '=' * 88)
print(f'ROLLING {W}-DAY CORRELATION TO SPY — quarterly snapshots')
print('=' * 88)
print(f'{"date":>12} ' + ' '.join(f'{s:>8}' for s in SYMS[1:]) + f'{"avg |corr|":>12} {"regime":>22}')
rows = []
for i in range(W, n, 63):
    d = D[i]
    cs = {s: corr(R['SPY'][i - W:i], R[s][i - W:i]) for s in SYMS[1:]}
    avg = sum(abs(v) for v in cs.values()) / len(cs)
    tlt = cs['TLT']
    if tlt > 0.15:
        reg = 'RATES-DRIVEN (no hedge)'
    elif tlt < -0.25:
        reg = 'flight-to-quality'
    else:
        reg = 'transitional'
    rows.append((d, cs, avg, reg))
    print(f'{d:>12} ' + ' '.join(f'{cs[s]:>8.2f}' for s in SYMS[1:]) +
          f'{avg:>12.2f} {reg:>22}')

print('\n' + '=' * 88)
print('CURRENT STATE')
print('=' * 88)
i = n
cs = {s: corr(R['SPY'][i - W:i], R[s][i - W:i]) for s in SYMS[1:]}
for s, v in cs.items():
    print(f'  SPY-{s:<4} {v:+.3f}')
tlt = cs['TLT']
print(f'\n  SPY-TLT = {tlt:+.3f}')
if tlt > 0.15:
    print('  -> RATES-DRIVEN regime. Bonds are NOT hedging equities. A TLT leg adds no protection;')
    print('     it is a second bet on the same driver. Diversification is unavailable here.')
elif tlt < -0.25:
    print('  -> FLIGHT-TO-QUALITY regime. Bonds hedge equities. A long-TLT leg genuinely offsets')
    print('     equity drawdowns, so a rates leg is real diversification.')
else:
    print('  -> TRANSITIONAL. The hedge relationship is weak in both directions; do not rely on it.')

# how unstable is it?
series = []
for i in range(W, n):
    series.append(corr(R['SPY'][i - W:i], R['TLT'][i - W:i]))
print(f'\n  SPY-TLT rolling correlation over the sample:')
print(f'    min {min(series):+.2f}   max {max(series):+.2f}   '
      f'range {max(series)-min(series):.2f}')
pos = sum(1 for x in series if x > 0) / len(series) * 100
print(f'    positive {pos:.0f}% of the time, negative {100-pos:.0f}%')
print(f'    -> the "bonds hedge stocks" assumption held only {100-pos:.0f}% of the last decade.')

# dispersion of correlation as a stress signal
print('\n' + '=' * 88)
print('AVERAGE CROSS-ASSET CORRELATION AS A STRESS GAUGE')
print('=' * 88)
avgs = []
for i in range(W, n):
    cs2 = [abs(corr(R['SPY'][i - W:i], R[s][i - W:i])) for s in SYMS[1:]]
    avgs.append(sum(cs2) / len(cs2))
cur = avgs[-1]
srt = sorted(avgs)
pct = sum(1 for x in avgs if x <= cur) / len(avgs) * 100
print(f'  current avg |corr| to SPY = {cur:.3f}  ({pct:.0f}th percentile of the last decade)')
print(f'  decade range: {min(avgs):.3f} - {max(avgs):.3f}')
print("""
  High average |corr| = everything is one bet; diversification has evaporated and position
  size is the only remaining risk control. Low = independent bets are genuinely available.
  Rising correlation is a classic pre-stress signal.""")

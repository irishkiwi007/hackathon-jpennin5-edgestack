"""Does variance arrive uniformly in time? Option pricing largely assumes it does
(calendar-time theta, sqrt(t) scaling). Where reality violates that, risk is mispriced.

Four tests on SPY 2016-2026, each mapped to a tradeable consequence.
"""
import json, math, os, subprocess, sys, io, statistics as st

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:200])
    return json.loads(r.stdout)


bars, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day', '--start', '2016-01-01',
         '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    bars += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break
bars.sort(key=lambda x: x['t'])
o = [x['o'] for x in bars]
c = [x['c'] for x in bars]
t = [x['t'][:10] for x in bars]
N = len(bars)
print(f'SPY daily bars: {N}   {t[0]} -> {t[-1]}')
ANN = math.sqrt(252)


def var(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


# ---------- TEST 1: overnight vs intraday variance ----------
print('\n' + '=' * 88)
print('TEST 1 — is variance uniform across the 24h cycle?')
print('=' * 88)
overnight = [math.log(o[i] / c[i - 1]) for i in range(1, N)]
intraday = [math.log(c[i] / o[i]) for i in range(1, N)]
daily = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
v_on, v_id, v_d = var(overnight), var(intraday), var(daily)
print(f'{"component":<22} {"ann vol":>9} {"variance":>12} {"share of daily var":>20}')
for nm, v in (('overnight (C->O)', v_on), ('intraday  (O->C)', v_id), ('daily     (C->C)', v_d)):
    print(f'{nm:<22} {math.sqrt(v)*ANN*100:>8.2f}% {v:>12.3e} {v/v_d*100:>19.1f}%')
print(f'\ncovariance term: {(v_d - v_on - v_id)/v_d*100:+.1f}% of daily variance')
print(f'clock hours: intraday 6.5h, overnight 17.5h')
print(f'variance PER CLOCK HOUR: intraday {v_id/6.5:.3e}, overnight {v_on/17.5:.3e}'
      f'  -> intraday is {(v_id/6.5)/(v_on/17.5):.1f}x denser')
print("""
Consequence: options decay by CALENDAR time but variance accrues mostly in the 6.5h session.
Holding an option overnight pays ~17.5h of theta to receive a small share of the variance.
Short overnight is structurally favoured; long overnight is structurally penalised.""")

# ---------- TEST 2: variance ratio / sqrt(t) scaling ----------
print('\n' + '=' * 88)
print('TEST 2 — does variance scale linearly with horizon? (sqrt-t assumption)')
print('=' * 88)
v1 = var(daily)
print(f'{"horizon":>8} {"n":>6} {"realised ann vol":>18} {"VR(q)":>8} {"verdict":>28}')
vrs = {}
for q in (1, 2, 3, 4, 5, 10, 21, 42):
    rets = [math.log(c[i + q] / c[i]) for i in range(0, N - q)]
    vq = var(rets)
    vr = vq / (q * v1)
    vrs[q] = vr
    ann = math.sqrt(vq / q) * ANN
    if vr < 0.93:
        verd = 'MEAN REVERTING (over-priced)'
    elif vr > 1.07:
        verd = 'TRENDING (under-priced)'
    else:
        verd = 'consistent with random walk'
    print(f'{q:>8} {len(rets):>6} {ann*100:>17.2f}% {vr:>8.3f} {verd:>28}')
print("""
VR < 1 => multi-day variance is LESS than q x daily variance. The market, scaling by sqrt(t),
          would then OVERPRICE longer-dated options relative to short.
VR > 1 => the opposite.""")

# ---------- TEST 3: day-of-week ----------
print('\n' + '=' * 88)
print('TEST 3 — is variance uniform across weekdays?')
print('=' * 88)
import datetime
dows = {}
for i in range(1, N):
    d = datetime.date.fromisoformat(t[i]).weekday()
    dows.setdefault(d, {'on': [], 'id': [], 'd': []})
    dows[d]['on'].append(overnight[i - 1])
    dows[d]['id'].append(intraday[i - 1])
    dows[d]['d'].append(daily[i - 1])
names = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri'}
print(f'{"day":>5} {"n":>6} {"daily ann vol":>15} {"vs avg":>9} {"overnight vol":>15} '
      f'{"intraday vol":>14} {"mean ret":>10}')
allv = math.sqrt(v_d) * ANN
for d in sorted(dows):
    if d not in names:
        continue
    g = dows[d]
    vv = math.sqrt(var(g['d'])) * ANN
    print(f'{names[d]:>5} {len(g["d"]):>6} {vv*100:>14.2f}% {vv/allv:>9.3f} '
          f'{math.sqrt(var(g["on"]))*ANN*100:>14.2f}% {math.sqrt(var(g["id"]))*ANN*100:>13.2f}% '
          f'{sum(g["d"])/len(g["d"])*100:>9.3f}%')
print("""
Monday's session absorbs the whole weekend's information but is priced as one trading day.""")

# ---------- TEST 4: implied vs realised term structure ----------
print('\n' + '=' * 88)
print('TEST 4 — implied term structure vs realised term structure')
print('=' * 88)
IMPLIED = {1: 0.0788, 2: 0.0886, 3: 0.0946, 4: 0.0984, 5: 0.1062, 22: 0.1182}
rv20 = [None] * N
for i in range(21, N):
    r = daily[i - 20:i]
    rv20[i] = math.sqrt(var(r)) * ANN
rv_now = rv20[-1]
print(f'current RV20 = {rv_now*100:.2f}%   (conditioning band +/-25%)')
print(f'{"horizon":>8} {"implied":>9} {"realised med":>13} {"realised p75":>13} '
      f'{"impl/med":>10} {"verdict":>10}')
for q, iv in sorted(IMPLIED.items()):
    sample = []
    for i in range(21, N - q):
        if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25:
            r = [daily[j] for j in range(i, i + q)]
            if len(r) < 1:
                continue
            realised = math.sqrt(sum(x * x for x in r) / q) * ANN
            sample.append(realised)
    if len(sample) < 30:
        print(f'{q:>8} {iv*100:>8.2f}%   (insufficient sample)')
        continue
    sample.sort()
    med = sample[len(sample) // 2]
    p75 = sample[int(len(sample) * 0.75)]
    ratio = iv / med
    verd = 'SELL' if ratio > 1.15 else ('BUY' if ratio < 0.95 else '-')
    print(f'{q:>8} {iv*100:>8.2f}% {med*100:>12.2f}% {p75*100:>12.2f}% '
          f'{ratio:>10.3f} {verd:>10}')
print("""
Realised here is sqrt(mean squared daily return) over the horizon, annualised - the quantity a
straddle actually pays out on. Median is the typical outcome; p75 shows the right tail that
short premium has to survive.""")

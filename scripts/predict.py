"""THE ACTUAL PROPOSAL: can intraday tops and bottoms be identified IN ADVANCE?

Reversion existing is not the same as tops being predictable. This tests concrete, causal rules -
using only information available at the moment of entry - and measures forward returns against
the round-trip cost of expressing the trade in options (measured earlier: ~4.5bp for a vertical,
~0.7bp for a single ATM option).

SPY 1-minute SIP bars, regular hours, Jun-Aug 2026.
"""
import json, os, subprocess, sys, io, datetime, math
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(a):
    r = subprocess.run([A] + a + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


out, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Min', '--feed', 'sip',
         '--start', '2026-05-01T13:30:00Z', '--end', '2026-08-28T20:00:00Z', '--limit', '10000']
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    if not d:
        break
    out += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break

sess = defaultdict(list)
for b in out:
    t = datetime.datetime.fromisoformat(b['t'].replace('Z', '+00:00'))
    mins = t.hour * 60 + t.minute
    if 13 * 60 + 30 <= mins < 20 * 60:
        sess[b['t'][:10]].append((mins, b['c'], b['h'], b['l'], b['v']))
sess = {k: v for k, v in sess.items() if len(v) > 300}
print(f'sessions: {len(sess)}   bars: {sum(len(v) for v in sess.values())}')

# baseline move sizes, to compare against the cost hurdle
allm = []
for day, rows in sess.items():
    c = np.array([x[1] for x in rows])
    for h in (1, 5, 10, 30):
        if len(c) > h:
            allm.append((h, np.abs(np.diff(np.log(c[::h]))) * 10000))
print('\n' + '=' * 96)
print('MOVE SIZE vs COST HURDLE')
print('=' * 96)
print(f'{"horizon":>9} {"median |move|":>14} {"p75":>8} {"p90":>8} '
      f'{"vs 4.5bp spread cost":>22}')
for h in (1, 5, 10, 30):
    v = np.concatenate([x[1] for x in allm if x[0] == h])
    med = np.median(v)
    print(f'{h:>8}m {med:>13.2f}b {np.percentile(v,75):>7.2f}b '
          f'{np.percentile(v,90):>7.2f}b {med/4.5:>21.2f}x')
print('  a vertical spread needs ~4.5bp of SPY move just to clear its own bid-ask')

print('\n' + '=' * 96)
print('PREDICTABILITY TEST — causal rules, forward return in bp')
print('=' * 96)


def build(rows, look):
    c = np.array([x[1] for x in rows], dtype=float)
    n = len(c)
    lr = np.diff(np.log(c))
    feats = []
    for i in range(look + 5, n - 31):
        w = lr[i - look:i]
        sd = w.std()
        if sd == 0:
            continue
        ma = c[i - look:i].mean()
        z = (c[i] - ma) / (sd * c[i] * math.sqrt(look))
        run_ = np.sign(lr[i - 1]) if lr[i - 1] != 0 else 0
        streak = 0
        for j in range(i - 1, max(i - 8, 0), -1):
            if np.sign(lr[j]) == run_ and run_ != 0:
                streak += 1
            else:
                break
        feats.append(dict(i=i, z=z, streak=int(streak * run_),
                          past5=math.log(c[i] / c[i - 5]) * 10000,
                          fwd5=math.log(c[i + 5] / c[i]) * 10000,
                          fwd10=math.log(c[i + 10] / c[i]) * 10000,
                          fwd30=math.log(c[i + 30] / c[i]) * 10000))
    return feats


F = []
for day, rows in sess.items():
    F += build(rows, 20)
print(f'observations: {len(F)}')
base5 = np.mean([x['fwd5'] for x in F])
base10 = np.mean([x['fwd10'] for x in F])
base30 = np.mean([x['fwd30'] for x in F])
print(f'unconditional forward: 5m {base5:+.3f}bp  10m {base10:+.3f}bp  30m {base30:+.3f}bp\n')


def report(title, groups):
    print(title)
    print(f'{"bucket":<22} {"n":>7} {"fwd5":>9} {"t":>7} {"fwd10":>9} {"t":>7} '
          f'{"fwd30":>9} {"t":>7}')
    for lab, g in groups:
        if len(g) < 200:
            continue
        line = f'{lab:<22} {len(g):>7}'
        for key, base in (('fwd5', base5), ('fwd10', base10), ('fwd30', base30)):
            v = np.array([x[key] for x in g])
            exc = v.mean() - base
            t = exc / (v.std(ddof=1) / math.sqrt(len(v)))
            line += f' {exc:>+9.3f} {t:>7.2f}'
        print(line)
    print()


zs = np.array([x['z'] for x in F])
q = np.percentile(zs, [5, 25, 75, 95])
report('A. Z-SCORE vs 20-bar mean  (excess over unconditional, bp)', [
    ('z < p5 (deep low)', [x for x in F if x['z'] < q[0]]),
    ('p5-p25', [x for x in F if q[0] <= x['z'] < q[1]]),
    ('p25-p75 (middle)', [x for x in F if q[1] <= x['z'] < q[2]]),
    ('p75-p95', [x for x in F if q[2] <= x['z'] < q[3]]),
    ('z > p95 (spike high)', [x for x in F if x['z'] >= q[3]]),
])

report('B. CONSECUTIVE 1-MIN MOVES IN ONE DIRECTION', [
    ('<= -4 down bars', [x for x in F if x['streak'] <= -4]),
    ('-3 down bars', [x for x in F if x['streak'] == -3]),
    ('flat / mixed', [x for x in F if abs(x['streak']) <= 1]),
    ('+3 up bars', [x for x in F if x['streak'] == 3]),
    ('>= +4 up bars', [x for x in F if x['streak'] >= 4]),
])

p5 = np.array([x['past5'] for x in F])
pq = np.percentile(p5, [5, 25, 75, 95])
report('C. PRIOR 5-MINUTE MOVE', [
    ('past5 < p5 (sharp drop)', [x for x in F if x['past5'] < pq[0]]),
    ('p5-p25', [x for x in F if pq[0] <= x['past5'] < pq[1]]),
    ('middle', [x for x in F if pq[1] <= x['past5'] < pq[2]]),
    ('p75-p95', [x for x in F if pq[2] <= x['past5'] < pq[3]]),
    ('past5 > p95 (sharp rally)', [x for x in F if x['past5'] >= pq[3]]),
])

print('=' * 96)
print('VERDICT CHECK: does any bucket beat the 4.5bp vertical-spread hurdle?')
print('=' * 96)
best = []
for lab, sel in (('z<p5', lambda x: x['z'] < q[0]), ('z>p95', lambda x: x['z'] >= q[3]),
                 ('streak<=-4', lambda x: x['streak'] <= -4),
                 ('streak>=+4', lambda x: x['streak'] >= 4),
                 ('past5<p5', lambda x: x['past5'] < pq[0]),
                 ('past5>p95', lambda x: x['past5'] >= pq[3])):
    g = [x for x in F if sel(x)]
    if len(g) < 200:
        continue
    for key, base, lbl in (('fwd5', base5, '5m'), ('fwd10', base10, '10m'),
                           ('fwd30', base30, '30m')):
        v = np.array([x[key] for x in g])
        exc = v.mean() - base
        t = exc / (v.std(ddof=1) / math.sqrt(len(v)))
        best.append((abs(exc), lab, lbl, exc, t, len(g)))
best.sort(reverse=True)
print(f'{"rule":>12} {"hold":>6} {"n":>7} {"excess bp":>11} {"t":>7} {"clears 4.5bp?":>15}')
for _, lab, lbl, exc, t, n in best[:8]:
    print(f'{lab:>12} {lbl:>6} {n:>7} {exc:>+11.3f} {t:>7.2f} '
          f'{"YES" if abs(exc) > 4.5 and abs(t) > 2 else "no":>15}')

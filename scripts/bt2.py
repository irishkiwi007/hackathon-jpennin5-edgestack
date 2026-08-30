"""Follow-ups to the walk-forward backtest:
  1. Statistical significance of the one winner (Sharpe standard error).
  2. Strike sweep - does the edge exist across a NEIGHBOURHOOD of strikes, or only at one
     lucky parameter pair? A single working cell is overfitting.
  3. Sub-period split within the backtest window.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


out, tok = [], None
while True:
    a = ['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day', '--start', '2024-01-01',
         '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    out += d.get('bars') or []
    tok = d.get('next_page_token')
    if not tok:
        break
out.sort(key=lambda x: x['t'])
dts = [datetime.date.fromisoformat(x['t'][:10]) for x in out]
close = [x['c'] for x in out]
idx = {d: i for i, d in enumerate(dts)}
cycles = []
for i, d in enumerate(dts):
    if d.weekday() != 0:
        continue
    fri = d + datetime.timedelta(days=4)
    if fri in idx and idx[fri] - i == 4:
        cycles.append((i, idx[fri]))
print(f'{len(cycles)} Mon->Fri cycles  {dts[cycles[0][0]]} -> {dts[cycles[-1][0]]}')


def occ(exp, cp, k):
    return f'SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}'


# sweep: long strike offset x width, for put debit and call debit
LONGS_P = [0.995, 0.990, 0.985, 0.980, 0.975]
WIDTHS = [0.005, 0.010, 0.015, 0.020]
LONGS_C = [1.005, 1.010, 1.014, 1.020, 1.025]

need = set()
for i, j in cycles:
    S0, exp = close[i], dts[j]
    for L in LONGS_P:
        need.add(occ(exp, 'P', round(S0 * L)))
        for w in WIDTHS:
            need.add(occ(exp, 'P', round(S0 * (L - w))))
    for L in LONGS_C:
        need.add(occ(exp, 'C', round(S0 * L)))
        for w in WIDTHS:
            need.add(occ(exp, 'C', round(S0 * (L + w))))
need = sorted(need)
print(f'contracts: {len(need)}')

PX = {}
B = 40
for b in range(0, len(need), B):
    ch = need[b:b + B]
    exps = sorted({datetime.date(2000 + int(s[3:5]), int(s[5:7]), int(s[7:9])) for s in ch})
    d = run(['data', 'option', 'bars', '--symbols', ','.join(ch), '--timeframe', '1Day',
             '--start', (min(exps) - datetime.timedelta(days=12)).isoformat(),
             '--end', (max(exps) + datetime.timedelta(days=1)).isoformat(), '--limit', '10000'])
    if d and d.get('bars'):
        for s, rows in d['bars'].items():
            for r in rows:
                PX[(s, r['t'][:10])] = r['c']
    if (b // B) % 15 == 0:
        print(f'  {b+len(ch)}/{len(need)}')
print(f'marks {len(PX)}')

SLIP = 0.02


def bt(cp, L, w, subset=None):
    tr = []
    for i, j in cycles:
        if subset and not (subset[0] <= dts[i] <= subset[1]):
            continue
        S0, ST, exp, ed = close[i], close[j], dts[j], dts[i].isoformat()
        if cp == 'P':
            k1, k2 = round(S0 * L), round(S0 * (L - w))
        else:
            k1, k2 = round(S0 * L), round(S0 * (L + w))
        if k1 == k2:
            continue
        p1, p2 = PX.get((occ(exp, cp, k1), ed)), PX.get((occ(exp, cp, k2), ed))
        if p1 is None or p2 is None:
            continue
        cost = (p1 + SLIP) - (p2 - SLIP)
        if cp == 'P':
            val = max(k1 - ST, 0) - max(k2 - ST, 0)
        else:
            val = max(ST - k1, 0) - max(ST - k2, 0)
        tr.append((val - cost) * 100)
    return tr


def stat(tr):
    n = len(tr)
    if n < 20:
        return None
    m = sum(tr) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in tr) / (n - 1))
    sr = m / sd * math.sqrt(52) if sd else 0
    se = math.sqrt((1 + 0.5 * sr * sr) / n) * math.sqrt(52)
    return dict(n=n, tot=sum(tr), mean=m, sr=sr, se=se, t=sr / se if se else 0,
                win=sum(1 for x in tr if x > 0) / n)


print('\n' + '=' * 92)
print(f'STRIKE SWEEP — annualised Sharpe, ${SLIP*100:.0f}/leg slippage')
print('=' * 92)
for cp, LONGS, lbl in (('P', LONGS_P, 'PUT DEBIT (long strike / width below)'),
                       ('C', LONGS_C, 'CALL DEBIT (long strike / width above)')):
    print(f'\n{lbl}')
    print(f'{"long":>8} ' + ' '.join(f'{"w="+format(w*100,".1f")+"%":>10}' for w in WIDTHS))
    for L in LONGS:
        cells = []
        for w in WIDTHS:
            s = stat(bt(cp, L, w))
            cells.append(f'{s["sr"]:>10.2f}' if s else f'{"-":>10}')
        print(f'{(L-1)*100:>+7.1f}% ' + ' '.join(cells))

print('\n' + '=' * 92)
print('THE ONE WINNER — significance and stability')
print('=' * 92)
best = ('P', 0.990, 0.010)
s = stat(bt(*best))
print(f'put debit long {(best[1]-1)*100:+.1f}% width {best[2]*100:.1f}%  '
      f'(slippage ${SLIP*100:.0f}/leg)')
print(f'  n={s["n"]}  total ${s["tot"]:.0f}  mean ${s["mean"]:.1f}/wk  win {s["win"]*100:.1f}%')
print(f'  annualised Sharpe {s["sr"]:.2f}  +/- {s["se"]:.2f} (1 s.e.)   t = {s["t"]:.2f}')
print(f'  -> {"NOT significant" if abs(s["t"])<1.96 else "significant"} at 5% '
      f'(needs |t| > 1.96)')

print('\nsub-periods:')
SUB = [('2024 H1', datetime.date(2024, 1, 1), datetime.date(2024, 6, 30)),
       ('2024 H2', datetime.date(2024, 7, 1), datetime.date(2024, 12, 31)),
       ('2025 H1', datetime.date(2025, 1, 1), datetime.date(2025, 6, 30)),
       ('2025 H2', datetime.date(2025, 7, 1), datetime.date(2025, 12, 31)),
       ('2026 YTD', datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))]
for nm, lo, hi in SUB:
    tr = bt(*best, subset=(lo, hi))
    if len(tr) < 5:
        print(f'  {nm:<10} (too few)')
        continue
    m = sum(tr) / len(tr)
    print(f'  {nm:<10} n={len(tr):>3}  total ${sum(tr):>7.0f}  mean ${m:>7.1f}  '
          f'win {sum(1 for x in tr if x>0)/len(tr)*100:>5.1f}%')

pos = 0
tot = 0
for cp, LONGS in (('P', LONGS_P), ('C', LONGS_C)):
    for L in LONGS:
        for w in WIDTHS:
            st = stat(bt(cp, L, w))
            if st:
                tot += 1
                if st['sr'] > 0:
                    pos += 1
print(f'\ncells with positive Sharpe: {pos} of {tot}')
print('If the edge were real it should appear across a neighbourhood, not in isolated cells.')

import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
H, NAV, EXP = 5, 100000.0, '2026-09-04'


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


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
c = [x['c'] for x in bars]
spot, N = c[-1], len(bars)
daily = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
rv20 = [None] * N
for i in range(21, N):
    r = daily[i - 20:i]
    m = sum(r) / len(r)
    rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
rv_now = rv20[-1]

UNC = [c[i + H] / c[i] - 1 for i in range(0, N - H)]
CON = [c[i + H] / c[i] - 1 for i in range(21, N - H)
       if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25]


def freq(s, th):
    return sum(1 for r in s if r <= th) / len(s) * 100


print(f'SPY {spot}   H={H}d   RV20 now {rv_now*100:.2f}%')
print(f'{"sample":<38} {"n":>6} {"worst":>8} {"<=-4%":>8} {"<=-5%":>8} {"<=-8%":>8}')
for nm, s in (('unconditional 2016-2026', UNC), ("conditioned on today's calm state", CON)):
    print(f'{nm:<38} {len(s):>6} {min(s)*100:>7.2f}% {freq(s,-0.04):>7.2f}% '
          f'{freq(s,-0.05):>7.2f}% {freq(s,-0.08):>7.2f}%')
print("""
The conditioned row does NOT assume calm persists. It measures how often a calm state turned
into a crash within 5 days - exactly what a 5-day hedge insures against. It is the right sample.""")

snaps, tok = {}, None
while True:
    a = ['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
         '--expiration-date', EXP, '--limit', '500',
         '--strike-price-gte', str(int(spot * 0.80)), '--strike-price-lte', str(int(spot * 1.05))]
    if tok:
        a += ['--page-token', tok]
    d = run(a)
    snaps.update(d.get('snapshots') or {})
    tok = d.get('next_page_token')
    if not tok:
        break
P, C = {}, {}
for k, v in snaps.items():
    q = v.get('latestQuote') or {}
    bp, ap = q.get('bp'), q.get('ap')
    if not bp or not ap or ap <= 0:
        continue
    (C if k[-9] == 'C' else P)[int(k[-8:]) / 1000] = {'bid': bp, 'ask': ap}


def evaluate(legs, sample):
    cost = 0.0
    for q, kind, K in legs:
        s = C if kind == 'C' else P
        if K not in s:
            return None
        cost += q * (s[K]['ask'] if q > 0 else s[K]['bid'])
    pay = []
    for r in sample:
        S = spot * (1 + r)
        pay.append(sum(q * (max(S - K, 0) if t == 'C' else max(K - S, 0))
                       for q, t, K in legs) - cost)
    ev = sum(pay) / len(pay)
    n1 = max(1, int(len(sample) * 0.01))
    idx = sorted(range(len(sample)), key=lambda i: sample[i])[:n1]
    return cost, ev, sum(1 for x in pay if x > 0) / len(pay), sum(pay[i] for i in idx) / n1


print('\n' + '=' * 100)
print('PART 1 — does the drift-aligned core even have tail risk?')
print('=' * 100)
if 780 in C and 785 in C:
    cc = C[780]['ask'] - C[785]['bid']
    print(f'core: call debit 780/785, cost ${cc*100:.0f}/lot. Max loss = ${cc*100:.0f}. '
          f'If SPY drops 20%: -${cc*100:.0f}. Nothing more.')
    print('A long debit spread has NO tail exposure. Aggregate book max loss = sum of debits,')
    print('known before the open. There is no black-swan risk here to insure.')

print('\n' + '=' * 100)
print('PART 2 — what does downside insurance cost, on each sample?')
print('=' * 100)
for nm, samp in (('UNCONDITIONAL (includes COVID/2018/2022)', UNC),
                 ("CONDITIONED on today's calm state  <-- correct", CON)):
    print(f'\n--- {nm} ---')
    print(f'{"hedge":<24} {"cost$":>7} {"%NAV":>7} {"EV$":>8} {"EV/cost":>9} '
          f'{"P(pay)":>8} {"worst-1% payoff":>16}')
    for pct in (-0.04, -0.05, -0.06, -0.08, -0.10):
        K = min(P, key=lambda k: abs(k - spot * (1 + pct)))
        for legs, label in (([(1, 'P', K)], f'long put {pct*100:.0f}% ({K:.0f})'),):
            r = evaluate(legs, samp)
            if not r:
                continue
            cost, ev, pw, tp = r
            print(f'{label:<24} {cost*100:>7.0f} {cost*100/NAV*100:>6.3f}% {ev*100:>8.1f} '
                  f'{ev/cost*100:>8.0f}% {pw*100:>7.1f}% {tp*100:>16.0f}')

print("""
EV/cost is the premium burn: -100% means the hedge expects to lose its entire cost.""")

print('\n' + '=' * 100)
print('PART 3 — where on the put curve is anything actually cheap? (conditioned)')
print('=' * 100)
print(f'{"strike":>8} {"% OTM":>8} {"cost$":>8} {"implied P":>11} {"empirical P":>13} '
      f'{"emp/impl":>10} {"verdict":>12}')
for pct in (-0.01, -0.015, -0.02, -0.025, -0.03, -0.04, -0.05, -0.06):
    K = min(P, key=lambda k: abs(k - spot * (1 + pct)))
    ks = sorted(P)
    i = ks.index(K)
    if i == 0:
        continue
    lo = ks[i - 1]
    mid_hi = (P[K]['bid'] + P[K]['ask']) / 2
    mid_lo = (P[lo]['bid'] + P[lo]['ask']) / 2
    if K == lo:
        continue
    q_imp = (mid_hi - mid_lo) / (K - lo)
    q_imp = min(max(q_imp, 1e-6), 1.0)
    emp = sum(1 for r in CON if r <= pct) / len(CON)
    ratio = emp / q_imp
    verdict = 'CHEAP' if ratio > 1.15 else ('expensive' if ratio < 0.85 else 'fair')
    print(f'{K:>8.0f} {pct*100:>7.1f}% {mid_hi*100:>8.0f} {q_imp*100:>10.2f}% '
          f'{emp*100:>12.2f}% {ratio:>10.2f} {verdict:>12}')
print("""
emp/impl > 1 => history (from a calm start) delivers this more often than the market charges.""")

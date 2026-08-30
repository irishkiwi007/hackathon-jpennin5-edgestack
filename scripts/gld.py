"""Does the drift-aligned call-debit alpha exist on GLD (the one genuinely uncorrelated asset
with positive drift)? Same method as scripts/survivors.py, applied to a different underlying.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
H, EXP = 5, '2026-09-04'
SYMS = sys.argv[1:] or ['GLD']


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def analyse(SYM):
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', SYM, '--timeframe', '1Day', '--start', '2016-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    out.sort(key=lambda x: x['t'])
    c = [x['c'] for x in out]
    dates = [datetime.date.fromisoformat(x['t'][:10]) for x in out]
    spot, N = c[-1], len(c)
    daily = [math.log(c[i] / c[i - 1]) for i in range(1, N)]
    rv20 = [None] * N
    for i in range(21, N):
        r = daily[i - 20:i]
        m = sum(r) / len(r)
        rv20[i] = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
    rv_now = rv20[-1]
    REG = {'pre16-19': (datetime.date(2016, 1, 1), datetime.date(2019, 12, 31)),
           'cov20-22': (datetime.date(2020, 1, 1), datetime.date(2022, 12, 31)),
           'rec23-26': (datetime.date(2023, 1, 1), datetime.date(2026, 12, 31)),
           'ALL': (datetime.date(2016, 1, 1), datetime.date(2026, 12, 31))}
    S = {k: [c[i + H] / c[i] - 1 for i in range(21, N - H) if lo <= dates[i] <= hi]
         for k, (lo, hi) in REG.items()}
    S['lowvol'] = [c[i + H] / c[i] - 1 for i in range(21, N - H)
                   if rv20[i] and rv_now * 0.75 <= rv20[i] <= rv_now * 1.25]
    KEYS = [k for k in S if len(S[k]) > 100]
    S = {k: S[k] for k in KEYS}
    NEUT = {k: [r - sum(v) / len(v) for r in v] for k, v in S.items()}

    snaps, tok = {}, None
    while True:
        a = ['data', 'option', 'chain', '--underlying-symbol', SYM, '--feed', 'indicative',
             '--expiration-date', EXP, '--limit', '500',
             '--strike-price-gte', str(round(spot * 0.90, 0)),
             '--strike-price-lte', str(round(spot * 1.10, 0))]
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        if not d:
            break
        snaps.update(d.get('snapshots') or {})
        tok = d.get('next_page_token')
        if not tok:
            break
    raw = {'C': {}, 'P': {}}
    for k, v in snaps.items():
        q = v.get('latestQuote') or {}
        bp, ap = q.get('bp'), q.get('ap')
        dl = (v.get('greeks') or {}).get('delta')
        if not bp or not ap or ap <= bp or dl is None:
            continue
        raw['C' if k[-9] == 'C' else 'P'][int(k[-8:]) / 1000] = {
            'bid': bp, 'ask': ap, 'mid': (bp + ap) / 2, 'delta': dl}
    bad = {'C': set(), 'P': set()}
    for kind in ('C', 'P'):
        ks = sorted(raw[kind])
        for i in range(len(ks) - 1):
            a1, a2 = raw[kind][ks[i]], raw[kind][ks[i + 1]]
            if kind == 'C':
                v = a1['mid'] < a2['mid'] or abs(a1['delta']) < abs(a2['delta']) or a1['ask'] <= a2['bid']
            else:
                v = a1['mid'] > a2['mid'] or abs(a1['delta']) > abs(a2['delta']) or a2['ask'] <= a1['bid']
            if v:
                bad[kind].add(ks[i]); bad[kind].add(ks[i + 1])
    C, P = {}, {}
    for kind, dst in (('C', C), ('P', P)):
        for K, r in raw[kind].items():
            if K in bad[kind] or (r['ask'] - r['bid']) / r['mid'] > 0.35:
                continue
            dst[K] = r
    mu = sum(S['ALL']) / len(S['ALL'])
    print(f'\n{"="*92}\n{SYM}  spot {spot:.2f}  drift {((1+mu)**(252/H)-1)*100:+.1f}%/yr  '
          f'clean chain {len(C)}C/{len(P)}P\n{"="*92}')
    if len(C) < 4:
        print('  chain too thin after cleaning — cannot build structures')
        return

    def cost_of(legs):
        t = 0.0
        for q, kind, K in legs:
            s = C if kind == 'C' else P
            if K not in s:
                return None
            t += q * (s[K]['ask'] if q > 0 else s[K]['bid'])
        return t

    def series(legs, sample):
        cost = cost_of(legs)
        if cost is None:
            return None
        return [sum(q * (max(spot * (1 + r) - K, 0) if t == 'C' else max(K - spot * (1 + r), 0))
                    for q, t, K in legs) - cost for r in sample]

    ck, pk = sorted(C), sorted(P)
    cands = []
    for pct in (0.005, 0.010, 0.015, 0.020, 0.025, 0.03):
        K = min(ck, key=lambda k: abs(k - spot * (1 + pct)))
        for hi in [x for x in ck if x > K][:3]:
            cands.append((f'call debit {K:g}/{hi:g}', [(1, 'C', K), (-1, 'C', hi)]))
    for pct in (-0.005, -0.01, -0.015, -0.02, -0.025, -0.03):
        K = min(pk, key=lambda k: abs(k - spot * (1 + pct)))
        for lo in [x for x in pk if x < K][-3:]:
            cands.append((f'put debit {K:g}/{lo:g}', [(1, 'P', K), (-1, 'P', lo)]))
            cands.append((f'put credit {K:g}/{lo:g}', [(-1, 'P', K), (1, 'P', lo)]))

    rows = []
    for name, legs in cands:
        per, ok = {}, True
        for k in S:
            a1, a2 = series(legs, S[k]), series(legs, NEUT[k])
            if not a1:
                ok = False; break
            risk = -min(a1)
            if risk <= 0.01:
                ok = False; break
            per[k] = dict(ev=sum(a1) / len(a1), alpha=sum(a2) / len(a2), risk=risk,
                          win=sum(1 for x in a1 if x > 0) / len(a1))
        if ok:
            rows.append((name, per, min(per[k]['alpha'] / per[k]['risk'] for k in per)))
    rows.sort(key=lambda r: -r[2])
    surv = [r for r in rows if r[2] > 0]
    print(f'  tested {len(rows)}  |  positive alpha in EVERY regime: {len(surv)}')
    if surv:
        print(f'  {"structure":<24} {"worstA/R":>9} {"EV$":>8} {"alpha$":>8} {"risk$":>7} {"win%":>7}')
        for name, per, w in surv[:8]:
            a = per['ALL']
            print(f'  {name:<24} {w:>9.3f} {a["ev"]*100:>8.1f} {a["alpha"]*100:>8.1f} '
                  f'{a["risk"]*100:>7.0f} {a["win"]*100:>6.1f}%')
    else:
        print('  nothing survives — no regime-stable edge on this underlying')


for s in SYMS:
    analyse(s)

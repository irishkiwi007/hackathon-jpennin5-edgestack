"""Find genuinely uncorrelated assets with tradeable options.

Two things must both be true for an asset to add an independent bet:
  1. LOW correlation to SPY at the 5-day horizon (independence)
  2. The structure must still have positive alpha ON THAT ASSET (edge)

An uncorrelated asset with no edge adds noise, not diversification. Note the drift-aligned
call-debit-spread alpha depends on the asset having positive drift - gold, bonds and commodities
do not share the equity risk premium, so this cannot be assumed to carry over.
"""
import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
H, EXP = 5, '2026-09-04'

CANDS = {
    'equity':    ['SPY', 'QQQ', 'IWM', 'DIA'],
    'gold':      ['GLD', 'GDX', 'SLV'],
    'rates':     ['TLT', 'IEF', 'HYG', 'LQD'],
    'commodity': ['USO', 'UNG', 'DBC', 'DBA'],
    'currency':  ['UUP', 'FXE'],
    'realestate':['IYR', 'VNQ'],
    'intl':      ['EFA', 'EEM', 'FXI'],
    'defensive': ['XLU', 'XLP'],
    'vol':       ['VXX', 'UVXY'],
}


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def bars(sym):
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', sym, '--timeframe', '1Day', '--start', '2016-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000']
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        if not d:
            return None
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    out.sort(key=lambda x: x['t'])
    return {x['t'][:10]: x['c'] for x in out}


print('pulling history...')
SER = {}
for grp, syms in CANDS.items():
    for s in syms:
        b = bars(s)
        if b and len(b) > 500:
            SER[s] = b
print(f'got {len(SER)} series\n')

spy = SER['SPY']
common = sorted(set.intersection(*[set(v) for v in SER.values()]))
print(f'common trading dates: {len(common)}  {common[0]} -> {common[-1]}')


def rets5(sym):
    v = SER[sym]
    return [v[common[i + H]] / v[common[i]] - 1 for i in range(len(common) - H)]


R = {s: rets5(s) for s in SER}
base = R['SPY']


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    return num / (da * db) if da and db else 0.0


print('\n' + '=' * 96)
print('CORRELATION TO SPY (5-day returns, 2016-2026) + DRIFT + OPTION LIQUIDITY')
print('=' * 96)
print(f'{"sym":>6} {"group":>11} {"corr SPY":>9} {"ann drift":>10} {"ann vol":>8} '
      f'{"opt strikes":>12} {"med spr%":>9} {"verdict":>12}')

rows = []
for grp, syms in CANDS.items():
    for s in syms:
        if s not in R:
            continue
        cr = corr(base, R[s])
        mu = sum(R[s]) / len(R[s])
        drift = (1 + mu) ** (252 / H) - 1
        sd = math.sqrt(sum((x - mu) ** 2 for x in R[s]) / (len(R[s]) - 1))
        vol = sd * math.sqrt(252 / H)
        # option availability
        last = SER[s][common[-1]]
        ch = run(['data', 'option', 'chain', '--underlying-symbol', s, '--feed', 'indicative',
                  '--expiration-date', EXP,
                  '--strike-price-gte', str(round(last * 0.94, 0)),
                  '--strike-price-lte', str(round(last * 1.06, 0)), '--limit', '200'])
        nst, spr = 0, float('nan')
        if ch and ch.get('snapshots'):
            sp = []
            for k, v in ch['snapshots'].items():
                q = v.get('latestQuote') or {}
                bp, ap = q.get('bp'), q.get('ap')
                if bp and ap and ap > bp:
                    sp.append((ap - bp) / ((ap + bp) / 2))
            nst = len(ch['snapshots'])
            if sp:
                sp.sort()
                spr = sp[len(sp) // 2]
        tradeable = nst >= 20 and spr == spr and spr < 0.20
        uncorr = abs(cr) < 0.55
        if s == 'SPY':
            verd = 'BASE'
        elif tradeable and uncorr:
            verd = 'CANDIDATE'
        elif not uncorr:
            verd = 'correlated'
        else:
            verd = 'illiquid'
        rows.append((s, grp, cr, drift, vol, nst, spr, verd))
        print(f'{s:>6} {grp:>11} {cr:>9.3f} {drift*100:>9.1f}% {vol*100:>7.1f}% '
              f'{nst:>12} {spr*100 if spr==spr else float("nan"):>8.1f}% {verd:>12}')

print('\n' + '=' * 96)
print('VERDICT')
print('=' * 96)
cands = [r for r in rows if r[7] == 'CANDIDATE']
print(f'uncorrelated (|corr|<0.55) AND liquid options: {len(cands)}')
for s, grp, cr, drift, vol, nst, spr, _ in cands:
    print(f'   {s:>5} [{grp:<10}] corr {cr:+.3f}  drift {drift*100:+6.1f}%/yr  vol {vol*100:.1f}%')

print('\npairwise correlation among candidates + SPY:')
sel = ['SPY'] + [r[0] for r in cands]
print('        ' + ' '.join(f'{s:>7}' for s in sel))
for a in sel:
    print(f'{a:>7} ' + ' '.join(f'{corr(R[a], R[b]):>7.2f}' for b in sel))

print("""
NOTE ON EDGE: the drift-aligned call-debit alpha found on SPY rests on SPY's +15.8%/yr drift and
its specific put skew. Assets with near-zero or negative drift cannot support the same structure -
an uncorrelated asset with no edge adds variance without adding expected return.
The drift column above is the first filter on that.""")

"""Corrected commodity screen.

FIX 1: Alpaca bars default to --adjustment raw. USO did a 1:8 reverse split in Apr 2020; GDX and
       others have splits too. Raw history corrupts drift and vol. Use adjustment=all.
FIX 2: the cross-asset emp/impl comparison in the first pass was contaminated - it rescaled the
       expiry's move by sqrt(t), which we know is wrong (VR<1), and the bias grows with IV. So
       high-vol commodities were penalised mechanically. The clean test is IV vs each asset's OWN
       realised vol.
"""
import json, math, os, subprocess, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
SYMS = ['SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'GDX', 'USO']
ANN = math.sqrt(252)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def bars(sym, adjustment):
    out, tok = [], None
    while True:
        a = ['data', 'bars', '--symbol', sym, '--timeframe', '1Day', '--start', '2016-01-01',
             '--end', '2026-08-29T00:00:00Z', '--limit', '10000', '--adjustment', adjustment]
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
    return out


def rvs(c, w):
    lr = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    o = []
    for i in range(w, len(lr)):
        s = lr[i - w:i]
        m = sum(s) / len(s)
        o.append(math.sqrt(sum((x - m) ** 2 for x in s) / (w - 1)) * ANN)
    return o


print('=== raw vs split-adjusted: does it matter? ===')
print(f'{"sym":>5} {"raw ann drift":>15} {"adj ann drift":>15} {"raw vol":>9} {"adj vol":>9}')
DATA = {}
for s in SYMS:
    br, ba = bars(s, 'raw'), bars(s, 'all')
    if not br or not ba:
        print(f'{s:>5}  (fetch failed)')
        continue
    out = []
    for lbl, b in (('raw', br), ('adj', ba)):
        c = [x['c'] for x in b]
        yrs = (datetime.date.fromisoformat(b[-1]['t'][:10])
               - datetime.date.fromisoformat(b[0]['t'][:10])).days / 365.25
        dr = (c[-1] / c[0]) ** (1 / yrs) - 1
        v = rvs(c, 20)
        out.append((dr, sum(v) / len(v)))
    DATA[s] = ba
    print(f'{s:>5} {out[0][0]*100:>14.1f}% {out[1][0]*100:>14.1f}% '
          f'{out[0][1]*100:>8.1f}% {out[1][1]*100:>8.1f}%')

print('\n' + '=' * 104)
print('IV vs OWN REALISED VOL  — the clean cross-asset comparison (split-adjusted)')
print('=' * 104)
print(f'{"sym":>5} {"ATM IV":>8} {"RV20 now":>9} {"RV median":>10} {"RV pctile":>10} '
       f'{"IV/RV20":>8} {"IV/RVmed":>9} {"verdict":>16}')
EXPS = ['2026-09-18', '2026-09-30', '2026-10-16']
rows = []
for s, b in DATA.items():
    c = [x['c'] for x in b]
    spot = c[-1]
    v = rvs(c, 20)
    now = v[-1]
    sv = sorted(v)
    med = sv[len(sv) // 2]
    pct = sum(1 for x in v if x <= now) / len(v) * 100
    atm = None
    for e in EXPS:
        ch = run(['data', 'option', 'chain', '--underlying-symbol', s, '--feed', 'indicative',
                  '--expiration-date', e, '--limit', '400',
                  '--strike-price-gte', str(round(spot * 0.90, 0)),
                  '--strike-price-lte', str(round(spot * 1.10, 0))])
        if not ch or not ch.get('snapshots'):
            continue
        ivs = [v2.get('impliedVolatility') for k, v2 in ch['snapshots'].items()
               if v2.get('impliedVolatility') and (v2.get('greeks') or {}).get('delta')
               and 0.40 < abs((v2.get('greeks') or {}).get('delta')) < 0.60]
        if ivs:
            atm = sum(ivs) / len(ivs)
            break
    if not atm:
        print(f'{s:>5}  (no ATM IV)')
        continue
    r1, r2 = atm / now, atm / med
    verd = 'SELL premium' if r2 > 1.15 else ('BUY premium' if r2 < 0.95 else 'no edge')
    rows.append((s, atm, now, med, pct, r1, r2, verd))
    print(f'{s:>5} {atm*100:>7.1f}% {now*100:>8.1f}% {med*100:>9.1f}% {pct:>9.0f} '
          f'{r1:>8.2f} {r2:>9.2f} {verd:>16}')

print("""
IV/RVmed compares today's implied against the asset's OWN long-run realised vol - unit-free and
comparable across assets, unlike the earlier tail-frequency screen which sqrt-t rescaled and
mechanically penalised high-vol names.""")

print('\n' + '=' * 104)
print('DOES THE VOL-REGIME EFFECT EXIST IN COMMODITIES? (33y-style test, per asset)')
print('=' * 104)
H = 21
print(f'{"sym":>5} {"n":>6} {"low-tercile fwd/trail":>23} {"high-tercile fwd/trail":>24} '
       f'{"mean rev?":>11}')
for s, b in DATA.items():
    c = [x['c'] for x in b]
    v = rvs(c, 20)
    obs = []
    for i in range(len(v) - H):
        f = v[i + H] if i + H < len(v) else None
        if f:
            obs.append((v[i], f))
    if len(obs) < 300:
        continue
    obs.sort(key=lambda x: x[0])
    t3 = len(obs) // 3
    lo = obs[:t3]
    hi = obs[-t3:]
    rl = (sum(x[1] for x in lo) / len(lo)) / (sum(x[0] for x in lo) / len(lo))
    rh = (sum(x[1] for x in hi) / len(hi)) / (sum(x[0] for x in hi) / len(hi))
    mr = 'YES' if rl > 1.05 and rh < 0.95 else 'partial' if rl > 1.0 or rh < 1.0 else 'no'
    print(f'{s:>5} {len(obs):>6} {rl:>23.3f} {rh:>24.3f} {mr:>11}')
print("""
Vol mean reversion was established for SPY across 33 years. If it holds in commodities too, the
same regime logic applies there - on a surface with the OPPOSITE skew.""")

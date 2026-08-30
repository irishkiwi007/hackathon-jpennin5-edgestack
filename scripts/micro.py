"""Intraday micro-oscillations: real signal or bid-ask bounce?

THE DECISIVE TEST. Roll (1984): bid-ask bounce induces negative serial correlation in TRADE
prices even when the true price is a pure random walk. Trades alternate between hitting the bid
and lifting the offer, so the printed series zig-zags by the spread with no information in it.

You cannot trade that oscillation - you would be paying the very spread that creates it.

MIDQUOTE returns are immune to bounce. So:
   trade-price reversion >> midquote reversion  ->  artifact, untradeable
   both show reversion                          ->  possibly real
"""
import json, math, os, subprocess, sys, io, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
SYM = 'SPY'
DAYS = ['2026-08-25', '2026-08-26', '2026-08-27']
WIN = ('14:30:00Z', '16:30:00Z')      # 09:30-11:30 ET


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def pull(kind, day, maxpages=60):
    """kind: 'trades' or 'quotes'."""
    out, tok = [], None
    for _ in range(maxpages):
        a = ['data', kind, '--symbol', SYM, '--feed', 'sip',
             '--start', f'{day}T{WIN[0]}', '--end', f'{day}T{WIN[1]}', '--limit', '10000']
        if tok:
            a += ['--page-token', tok]
        d = run(a)
        if not d:
            break
        out += d.get(kind) or []
        tok = d.get('next_page_token')
        if not tok:
            break
    return out


def ts(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def sample(times, prices, dt):
    """Last observation carried forward onto a uniform dt-second grid."""
    if not times:
        return np.array([])
    t0, t1 = times[0], times[-1]
    grid = np.arange(t0, t1, dt)
    idx = np.searchsorted(np.array(times), grid, side='right') - 1
    idx = np.clip(idx, 0, len(prices) - 1)
    return np.array(prices)[idx]


def ac1(x):
    r = np.diff(np.log(x))
    r = r[np.isfinite(r)]
    if len(r) < 50 or r.std() == 0:
        return None, 0
    r = r - r.mean()
    a = (r[:-1] * r[1:]).sum() / (r * r).sum()
    return a, len(r)


ALL = {}
for day in DAYS:
    tr = pull('trades', day)
    qu = pull('quotes', day)
    if not tr or not qu:
        print(f'{day}: trades={len(tr)} quotes={len(qu)}  (skipping)')
        continue
    tt = [ts(x['t']) for x in tr]
    tp = [x['p'] for x in tr]
    qt = [ts(x['t']) for x in qu]
    mid = [(x['bp'] + x['ap']) / 2 for x in qu if x['bp'] and x['ap']]
    qt = [ts(x['t']) for x in qu if x['bp'] and x['ap']]
    spr = [(x['ap'] - x['bp']) for x in qu if x['bp'] and x['ap'] and x['ap'] > x['bp']]
    sprbp = [(x['ap'] - x['bp']) / ((x['ap'] + x['bp']) / 2) * 10000
             for x in qu if x['bp'] and x['ap'] and x['ap'] > x['bp']]
    ALL[day] = dict(tt=tt, tp=tp, qt=qt, mid=mid, spr=spr, sprbp=sprbp)
    print(f'{day}: {len(tr):>7} trades, {len(qu):>7} quotes, '
          f'median spread {np.median(spr):.4f} ({np.median(sprbp):.2f} bp)')

if not ALL:
    print('no data'); sys.exit()

print('\n' + '=' * 96)
print('1. TRADE-PRICE vs MIDQUOTE AUTOCORRELATION — the bounce test')
print('=' * 96)
print(f'{"sample":>9} | ' + ' '.join(f'{d[5:]:>22}' for d in ALL))
print(f'{"interval":>9} | ' + ' '.join(f'{"trade":>10}{"mid":>12}' for d in ALL))
GRID = [1, 2, 5, 10, 30, 60, 300, 900]
summary = {}
for dt in GRID:
    cells = []
    tvals, mvals = [], []
    for day, D in ALL.items():
        pt = sample(D['tt'], D['tp'], dt)
        pm = sample(D['qt'], D['mid'], dt)
        at, nt = ac1(pt)
        am, nm = ac1(pm)
        cells.append(f'{at:>+10.4f}' if at is not None else f'{"-":>10}')
        cells.append(f'{am:>+12.4f}' if am is not None else f'{"-":>12}')
        if at is not None:
            tvals.append(at)
        if am is not None:
            mvals.append(am)
    summary[dt] = (np.mean(tvals) if tvals else None, np.mean(mvals) if mvals else None)
    lbl = f'{dt}s' if dt < 60 else f'{dt//60}m'
    print(f'{lbl:>9} | ' + ' '.join(cells))

print('\n' + '=' * 96)
print('2. THE VERDICT TABLE — averaged across days')
print('=' * 96)
print(f'{"interval":>9} {"trade AC1":>12} {"midquote AC1":>14} {"bounce share":>14} {"reading":>28}')
for dt in GRID:
    t_, m_ = summary[dt]
    if t_ is None or m_ is None:
        continue
    share = (t_ - m_) / t_ * 100 if t_ < 0 else float('nan')
    if m_ < -0.02:
        rd = 'real reversion in mid'
    elif m_ > 0.02:
        rd = 'midquote TRENDS'
    else:
        rd = 'mid ~ random walk'
    lbl = f'{dt}s' if dt < 60 else f'{dt//60}m'
    print(f'{lbl:>9} {t_:>+12.4f} {m_:>+14.4f} {share:>13.0f}% {rd:>28}')
print("""
'bounce share' = how much of the trade-price reversion disappears when using midquotes.
Near 100% means the oscillation is entirely bid-ask bounce and cannot be captured.""")

print('\n' + '=' * 96)
print('3. ROLL (1984) IMPLIED SPREAD from trade-price autocovariance')
print('=' * 96)
print(f'{"day":>12} {"Roll spread":>13} {"actual median":>15} {"ratio":>8}')
for day, D in ALL.items():
    p = sample(D['tt'], D['tp'], 1)
    r = np.diff(np.log(p))
    cov = np.cov(r[:-1], r[1:])[0, 1]
    roll = 2 * math.sqrt(-cov) * np.mean(p) if cov < 0 else float('nan')
    act = np.median(D['spr'])
    print(f'{day:>12} {roll:>13.4f} {act:>15.4f} {roll/act:>8.2f}')
print("""
If the Roll estimate recovers roughly the actual spread, the trade-price serial correlation IS
the spread - by construction there is nothing else in it.""")

print('\n' + '=' * 96)
print('4. OSCILLATION AMPLITUDE vs THE COST OF CAPTURING IT')
print('=' * 96)
for day, D in ALL.items():
    m = sample(D['qt'], D['mid'], 60)
    if len(m) < 30:
        continue
    rr = np.abs(np.diff(np.log(m))) * 10000
    sp = np.median(D['sprbp'])
    print(f'{day}: median 1-min midquote move {np.median(rr):.2f} bp, '
          f'p75 {np.percentile(rr,75):.2f} bp, p95 {np.percentile(rr,95):.2f} bp')
    print(f'            SPY round-trip spread cost {sp*2:.2f} bp '
          f'-> a move must exceed that before any option cost')

"""ARTICLE VOLUME ANOMALY -> does it change the trend/reversion balance?

Design per the correct framing:
  * a single article is not sentiment and carries no context
  * what CAN be measured without context is a RELATIVE spike in coverage:
        news_z = (today's article count - rolling mean) / rolling sd   for that ticker
  * direction cannot be predicted from a count, but the CONTINUATION-vs-REVERSION balance can:
        does a prior move persist or reverse after coverage spikes?

Tested with the up/down split against a matched baseline, not with mixed-sign correlation.
"""
import os
import json, math, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
SYMS = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'MSFT', 'AMZN', 'META', 'SPY']
START, END = '2024-08-01', '2026-08-28'
LOOK = 20


def q(u, t=4):
    for _ in range(t):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.2)
    return None


def daily_counts(sym):
    cnt = defaultdict(int)
    tok = None
    for _ in range(700):
        u = (f'https://data.alpaca.markets/v1beta1/news?symbols={sym}'
             f'&start={START}T00:00:00Z&end={END}T23:59:00Z&limit=50')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        for a in d.get('news', []):
            cnt[a['created_at'][:10]] += 1
        tok = d.get('next_page_token')
        if not tok:
            break
    return cnt


def daily_bars(sym):
    out, tok = [], None
    while True:
        u = (f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Day&feed=sip'
             f'&start={START}&end={END}&limit=10000&adjustment=all')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    return out


ROWS = []
for s in SYMS:
    cnt = daily_counts(s)
    bb = daily_bars(s)
    if not bb or not cnt:
        print(f'{s}: no data')
        continue
    dts = [b['t'][:10] for b in bb]
    px = np.array([b['c'] for b in bb])
    n = len(px)
    counts = np.array([cnt.get(d, 0) for d in dts], dtype=float)
    print(f'{s}: {n} sessions, {int(counts.sum())} articles, '
          f'mean {counts.mean():.1f}/day, max {counts.max():.0f}')
    for i in range(LOOK + 6, n - 11):
        w = counts[i - LOOK:i]
        mu, sd = w.mean(), w.std(ddof=1)
        if sd < 0.5 or mu < 0.5:
            continue
        nz = (counts[i] - mu) / sd
        past5 = math.log(px[i] / px[i - 5])
        f1 = math.log(px[i + 1] / px[i])
        f5 = math.log(px[i + 5] / px[i])
        f10 = math.log(px[i + 10] / px[i])
        ret = np.diff(np.log(px[i - 20:i + 1]))
        rv = ret.std(ddof=1) * math.sqrt(252)
        ROWS.append(dict(sym=s, i=i, nz=nz, ratio=counts[i] / mu, past5=past5,
                         f1=f1, f5=f5, f10=f10, rv=rv,
                         fv5=abs(math.log(px[i + 5] / px[i]))))

print(f'\nobservations: {len(ROWS)}')
if len(ROWS) < 500:
    print('insufficient'); sys.exit()

# per-symbol standardisation so a high-coverage name does not dominate
bysym = defaultdict(list)
for r in ROWS:
    bysym[r['sym']].append(r)

print('\n' + '=' * 100)
print('1. DOES A COVERAGE SPIKE PREDICT A BIGGER MOVE? (direction-agnostic)')
print('=' * 100)
print(f'{"news_z bucket":<20} {"n":>6} {"mean |fwd 5d|":>15} {"vs all":>9} {"t":>7} '
      f'{"mean RV20":>11}')
allfv = np.mean([r['fv5'] for r in ROWS])
BUCK = [('nz < 0 (quiet)', lambda r: r['nz'] < 0),
        ('0 - 1', lambda r: 0 <= r['nz'] < 1),
        ('1 - 2', lambda r: 1 <= r['nz'] < 2),
        ('2 - 3', lambda r: 2 <= r['nz'] < 3),
        ('nz > 3 (big spike)', lambda r: r['nz'] >= 3)]
for lab, sel in BUCK:
    g = [r for r in ROWS if sel(r)]
    if len(g) < 40:
        continue
    v = np.array([r['fv5'] for r in g])
    exc = v.mean() - allfv
    t = exc / (v.std(ddof=1) / math.sqrt(len(v)))
    print(f'{lab:<20} {len(g):>6} {v.mean()*100:>14.2f}% {exc*100:>+8.2f}% {t:>7.2f} '
          f'{np.mean([r["rv"] for r in g])*100:>10.1f}%')

print('\n' + '=' * 100)
print('2. THE ACTUAL QUESTION — does a coverage spike shift TREND vs REVERSION?')
print('   split by direction of the prior 5-day move, vs matched baseline')
print('=' * 100)


def cont_test(rows, fwdkey):
    """Return (up excess, up t, down excess, down t) vs that bucket's own baseline."""
    base = np.mean([r[fwdkey] for r in rows])
    up = [r for r in rows if r['past5'] > 0]
    dn = [r for r in rows if r['past5'] <= 0]
    out = []
    for g in (up, dn):
        if len(g) < 40:
            out += [float('nan'), 0, len(g)]
            continue
        v = np.array([r[fwdkey] for r in g])
        exc = v.mean() - base
        t = exc / (v.std(ddof=1) / math.sqrt(len(v)))
        out += [exc, t, len(g)]
    return out


for fwdkey, lbl in (('f1', 'forward 1d'), ('f5', 'forward 5d'), ('f10', 'forward 10d')):
    print(f'\n--- {lbl} ---')
    print(f'{"news_z bucket":<20} {"n up":>6} {"up excess":>11} {"t":>7} '
          f'{"n dn":>6} {"dn excess":>11} {"t":>7} {"reading":>22}')
    for lab, sel in BUCK:
        g = [r for r in ROWS if sel(r)]
        if len(g) < 80:
            continue
        ue, ut, un, de, dt, dn_ = cont_test(g, fwdkey)
        if math.isnan(ue) or math.isnan(de):
            continue
        # up continues if excess>0 ; down continues if excess<0
        upc = 'cont' if ue > 0 else 'rev'
        dnc = 'cont' if de < 0 else 'rev'
        strong = (abs(ut) > 1.9) or (abs(dt) > 1.9)
        rd = f'up {upc} / down {dnc}' + ('  *' if strong else '')
        print(f'{lab:<20} {un:>6} {ue*100:>+10.3f}% {ut:>7.2f} {dn_:>6} {de*100:>+10.3f}% '
              f'{dt:>7.2f} {rd:>22}')

print('\n' + '=' * 100)
print('3. ROBUSTNESS — same test per symbol, big-spike bucket only (nz > 2), forward 5d')
print('=' * 100)
print(f'{"sym":>6} {"n up":>6} {"up excess":>11} {"t":>7} {"n dn":>6} {"dn excess":>11} {"t":>7}')
for s, rs in bysym.items():
    g = [r for r in rs if r['nz'] >= 2]
    if len(g) < 60:
        print(f'{s:>6}  (only {len(g)} spike days)')
        continue
    ue, ut, un, de, dt, dn_ = cont_test(g, 'f5')
    if math.isnan(ue) or math.isnan(de):
        print(f'{s:>6}  (thin split)')
        continue
    print(f'{s:>6} {un:>6} {ue*100:>+10.3f}% {ut:>7.2f} {dn_:>6} {de*100:>+10.3f}% {dt:>7.2f}')
print("""
A real effect should hold the same SIGN across symbols. Opposite signs = noise, the pattern seen
repeatedly in this project.""")

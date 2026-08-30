"""Does news arrival predict anything TRADEABLE?

The decisive question is not "does news move stocks" - it obviously does. It is whether the move
is still ahead of you when the headline prints. Benzinga headlines often LAG the tape.

So: measure the move BEFORE the timestamp and AFTER it. If the move is pre-print, the signal is
already in the price and the strategy is chasing.

Also measures forward VOLATILITY, which is what a long-option position actually needs, against a
time-of-day-matched baseline (news clusters at the open and close when vol is naturally high).
"""
import os
import json, math, os, sys, io, datetime, urllib.request, time
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
K = os.environ['ALPACA_API_KEY']
S = os.environ['ALPACA_SECRET_KEY']
HDR = {'APCA-API-KEY-ID': K, 'APCA-API-SECRET-KEY': S}
SYMS = ['NVDA', 'TSLA', 'AAPL', 'AMD', 'SPY']
START, END = '2026-05-01', '2026-08-28'


def q(url, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=HDR), timeout=60))
        except Exception:
            time.sleep(1.5)
    return None


def news(sym):
    out, tok = [], None
    for _ in range(60):
        u = (f'https://data.alpaca.markets/v1beta1/news?symbols={sym}'
             f'&start={START}T00:00:00Z&end={END}T23:59:00Z&limit=50')
        if tok:
            u += f'&page_token={tok}'
        d = q(u)
        if not d:
            break
        out += d.get('news', [])
        tok = d.get('next_page_token')
        if not tok:
            break
    return out


def bars(sym):
    out, tok = [], None
    while True:
        u = (f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&feed=sip'
             f'&start={START}T13:00:00Z&end={END}T20:30:00Z&limit=10000&adjustment=all')
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


print(f'window {START} -> {END}\n')
DATA = {}
for s in SYMS:
    nw = news(s)
    bb = bars(s)
    if not bb:
        print(f'{s}: no bars')
        continue
    ts = np.array([datetime.datetime.fromisoformat(b['t'].replace('Z', '+00:00')).timestamp()
                   for b in bb])
    px = np.array([b['c'] for b in bb])
    DATA[s] = (nw, ts, px)
    print(f'{s}: {len(nw):>5} articles, {len(bb):>7} minute bars')


def px_at(ts, px, t):
    i = np.searchsorted(ts, t) - 1
    return px[i] if 0 <= i < len(px) else None


print('\n' + '=' * 100)
print('1. IS THE MOVE BEFORE OR AFTER THE HEADLINE?  (absolute move, bp)')
print('=' * 100)
print(f'{"sym":>6} {"n":>6} | ' + ' '.join(f'{lab:>11}' for lab in
      ('-30m..-5m', '-5m..0', '0..+5m', '+5m..+30m', '+30m..+60m')))
WINS = [(-1800, -300), (-300, 0), (0, 300), (300, 1800), (1800, 3600)]
agg = {}
for s, (nw, ts, px) in DATA.items():
    rows = []
    for a in nw:
        t = datetime.datetime.fromisoformat(a['created_at'].replace('Z', '+00:00')).timestamp()
        vals = []
        ok = True
        for w0, w1 in WINS:
            p0, p1 = px_at(ts, px, t + w0), px_at(ts, px, t + w1)
            if p0 is None or p1 is None or p0 <= 0:
                ok = False
                break
            vals.append(abs(math.log(p1 / p0)) * 10000)
        if ok:
            rows.append(vals)
    if len(rows) < 30:
        print(f'{s:>6} {len(rows):>6}  (too few)')
        continue
    m = np.array(rows)
    agg[s] = m
    print(f'{s:>6} {len(rows):>6} | ' + ' '.join(f'{m[:, k].mean():>11.2f}' for k in range(5)))
print("""
If the '-5m..0' column is as large as '0..+5m', the move is already happening before the print -
the headline is reporting, not predicting.""")

print('\n' + '=' * 100)
print('2. NEWS vs TIME-OF-DAY-MATCHED BASELINE — forward volatility')
print('=' * 100)
print(f'{"sym":>6} {"n":>6} {"post-news 30m":>15} {"matched baseline":>18} {"ratio":>8} '
      f'{"t":>7}')
for s, (nw, ts, px) in DATA.items():
    if s not in agg:
        continue
    # build baseline: same minute-of-day, random days
    bym = defaultdict(list)
    for i in range(len(ts) - 30):
        dt = datetime.datetime.fromtimestamp(ts[i], datetime.timezone.utc)
        if px[i] > 0 and px[i + 30] > 0:
            bym[dt.hour * 60 + dt.minute].append(abs(math.log(px[i + 30] / px[i])) * 10000)
    post, base = [], []
    for a in nw:
        t = datetime.datetime.fromisoformat(a['created_at'].replace('Z', '+00:00')).timestamp()
        p0, p1 = px_at(ts, px, t), px_at(ts, px, t + 1800)
        if p0 is None or p1 is None or p0 <= 0:
            continue
        dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        mn = dt.hour * 60 + dt.minute
        if mn not in bym or len(bym[mn]) < 10:
            continue
        post.append(abs(math.log(p1 / p0)) * 10000)
        base.append(float(np.mean(bym[mn])))
    if len(post) < 30:
        continue
    post, base = np.array(post), np.array(base)
    diff = post - base
    t_ = diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff)))
    print(f'{s:>6} {len(post):>6} {post.mean():>14.2f}b {base.mean():>17.2f}b '
          f'{post.mean()/base.mean():>8.2f} {t_:>7.2f}')
print("""
ratio > 1 means the 30 minutes after a headline are more volatile than the same clock time on an
ordinary day. That is what a long-option position needs.""")

print('\n' + '=' * 100)
print('3. DIRECTIONAL: does the PRE-print move predict the POST-print move?')
print('=' * 100)
print(f'{"sym":>6} {"n":>6} {"corr(pre5, post5)":>19} {"corr(pre5, post30)":>20} {"reading":>16}')
for s, (nw, ts, px) in DATA.items():
    pre, p5, p30 = [], [], []
    for a in nw:
        t = datetime.datetime.fromisoformat(a['created_at'].replace('Z', '+00:00')).timestamp()
        a0, a1, a2, a3 = (px_at(ts, px, t - 300), px_at(ts, px, t),
                          px_at(ts, px, t + 300), px_at(ts, px, t + 1800))
        if None in (a0, a1, a2, a3) or min(a0, a1, a2, a3) <= 0:
            continue
        pre.append(math.log(a1 / a0) * 10000)
        p5.append(math.log(a2 / a1) * 10000)
        p30.append(math.log(a3 / a1) * 10000)
    if len(pre) < 40:
        continue
    pre, p5, p30 = np.array(pre), np.array(p5), np.array(p30)
    c5 = np.corrcoef(pre, p5)[0, 1]
    c30 = np.corrcoef(pre, p30)[0, 1]
    rd = 'momentum' if c5 > 0.06 else 'fade' if c5 < -0.06 else 'no signal'
    print(f'{s:>6} {len(pre):>6} {c5:>+19.3f} {c30:>+20.3f} {rd:>16}')
print("""
Positive = the pre-print drift continues after the print (drift-and-continue).
Negative = it reverses (the print marks exhaustion).""")

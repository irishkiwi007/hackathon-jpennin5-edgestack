"""The long-premium structures land on exactly zero: the +1.6% move is eaten by paying 1.8x
realized volatility plus theta. But the setup is long delta AND short vega - IV is elevated at
entry (0.597 vs 0.447 calm) and normalises as the panic fades.

A BULL PUT SPREAD (short put, long lower put) is long delta and short vega, so it monetises both
legs of the thesis instead of fighting one. Alpaca-legal: the short put is covered by the long.

Tested against the same control days, and against a bear call spread as a sanity check - if the
put spread wins simply because premium selling always wins, the call spread would win too.
"""
import os
import json, os, sys, io, math, time, urllib.request, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
HOLD = 3


def q(u, tries=3):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.6)
    return None


def occ(sym, exp, cp, k):
    return '{}{:%y%m%d}{}{:08d}'.format(sym, exp, cp, int(round(k * 1000)))


def inc_for(spot):
    return 1.0 if spot < 50 else (2.5 if spot < 200 else 5.0)


def next_friday(d, mindays=8):
    d0 = datetime.date.fromisoformat(d)
    x = d0 + datetime.timedelta(days=mindays)
    while x.weekday() != 4:
        x += datetime.timedelta(days=1)
    return x


BARS = {}
for f in ('wide_bars.json', 'single_bars.json'):
    if os.path.exists(f):
        BARS.update(json.load(open(f)))

EV, CTRL = [], []
for s, b in BARS.items():
    if len(b) < 900:
        continue
    c = np.array([x['c'] for x in b])
    v = np.array([x['v'] for x in b], float)
    dt = [x['t'] for x in b]
    n = len(c)
    r = np.zeros(n)
    r[1:] = np.log(c[1:] / np.maximum(c[:-1], 1e-9))
    for i in range(25, n - HOLD - 1):
        if dt[i] < '2024-02-15':
            continue
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        rec = dict(sym=s, date=dt[i], spot=float(c[i]), stretch=st, volx=vx,
                   exit_date=dt[i + HOLD], S_T=float(c[i + HOLD]))
        if st < -2.5 and vx > 1.4:
            EV.append(rec)
        elif abs(st) < 0.5 and 0.8 < vx < 1.2:
            CTRL.append(rec)
EV.sort(key=lambda e: e['date'])
np.random.default_rng(7).shuffle(CTRL)
CTRL = CTRL[:400]
print('signal events {}   control {}'.format(len(EV), len(CTRL)))


def evaluate(events, label, limit=400):
    """Bull put spread: short ATM put, long put 5% lower. Bear call spread as the control test."""
    res = []
    done = 0
    for e in events[:limit]:
        done += 1
        if done % 60 == 0:
            print('   {} {}/{} usable {}'.format(label, done, min(limit, len(events)), len(res)))
        exp = next_friday(e['date'])
        inc = inc_for(e['spot'])
        k_s = round(e['spot'] / inc) * inc                 # short strike, ATM
        k_l = round(e['spot'] * 0.95 / inc) * inc          # long strike, 5% lower
        k_cs = round(e['spot'] * 1.05 / inc) * inc         # bear call spread short leg
        if k_l >= k_s:
            k_l = k_s - inc
        if k_cs <= k_s:
            k_cs = k_s + inc
        syms = [occ(e['sym'], exp, 'P', k_s), occ(e['sym'], exp, 'P', k_l),
                occ(e['sym'], exp, 'C', k_s), occ(e['sym'], exp, 'C', k_cs)]
        end = (datetime.date.fromisoformat(e['exit_date'])
               + datetime.timedelta(days=1)).isoformat()
        d = q('https://data.alpaca.markets/v1beta1/options/bars?symbols={}&timeframe=1Day'
              '&start={}&end={}&limit=200'.format(','.join(syms), e['date'], end))
        if not d or not d.get('bars'):
            continue
        px = {sy: {x['t'][:10]: float(x['c']) for x in rows} for sy, rows in d['bars'].items()}
        ps, pl_, cs, cl = syms
        d0, d1 = e['date'], e['exit_date']
        row = dict(sym=e['sym'], date=d0, stretch=e['stretch'], volx=e['volx'])
        # bull put spread: credit = short - long ; P&L = credit_in - credit_out
        if all(k in px and d0 in px[k] and d1 in px[k] for k in (ps, pl_)):
            c_in = px[ps][d0] - px[pl_][d0]
            c_out = px[ps][d1] - px[pl_][d1]
            width = (k_s - k_l) * 100.0
            if c_in > 0.05 and width > 0:
                row['bps_pl'] = (c_in - c_out) * 100.0
                row['bps_credit'] = c_in * 100.0
                row['bps_risk'] = width - c_in * 100.0
        # bear call spread (should LOSE if the bounce is real)
        if all(k in px and d0 in px[k] and d1 in px[k] for k in (cs, cl)):
            c_in = px[cs][d0] - px[cl][d0]
            c_out = px[cs][d1] - px[cl][d1]
            if c_in > 0.05:
                row['bcs_pl'] = (c_in - c_out) * 100.0
                row['bcs_credit'] = c_in * 100.0
        res.append(row)
    return res


print('\nfetching...')
SIG = evaluate(EV, 'signal')
CON = evaluate(CTRL, 'control', limit=250)
json.dump({'sig': SIG, 'con': CON}, open('putspread_out.json', 'w'))


def summ(rows, k):
    g = [r for r in rows if k in r]
    if len(g) < 20:
        return None
    pl = np.array([r[k] for r in g])
    return dict(n=len(g), pl=pl.mean(),
                t=pl.mean() / (pl.std(ddof=1) / math.sqrt(len(pl))),
                win=(pl > 0).mean() * 100, total=pl.sum(), worst=pl.min(),
                sd=pl.std(ddof=1))


print()
print('=' * 100)
print('BULL PUT SPREAD on the capitulation signal  ({}-day hold, ATM / -5%)'.format(HOLD))
print('=' * 100)
print('{:<34} {:>6} {:>10} {:>7} {:>8} {:>11} {:>9}'.format(
    'structure', 'n', 'mean $', 't', 'win%', 'total $', 'worst $'))
for lab, rows, k in (('SIGNAL  bull put spread', SIG, 'bps_pl'),
                     ('CONTROL bull put spread', CON, 'bps_pl'),
                     ('SIGNAL  bear CALL spread (check)', SIG, 'bcs_pl'),
                     ('CONTROL bear call spread', CON, 'bcs_pl')):
    s_ = summ(rows, k)
    if s_:
        print('{:<34} {:>6} {:>10.1f} {:>7.2f} {:>7.1f}% {:>11.0f} {:>9.0f}'.format(
            lab, s_['n'], s_['pl'], s_['t'], s_['win'], s_['total'], s_['worst']))

a, b = summ(SIG, 'bps_pl'), summ(CON, 'bps_pl')
if a and b:
    td = (a['pl'] - b['pl']) / math.sqrt(a['sd'] ** 2 / a['n'] + b['sd'] ** 2 / b['n'])
    print('\n  signal minus control: {:+.1f} $/contract   t={:+.2f}'.format(a['pl'] - b['pl'], td))
    print('  mean credit {:.0f}, mean risk {:.0f}'.format(
        np.mean([r['bps_credit'] for r in SIG if 'bps_credit' in r]),
        np.mean([r['bps_risk'] for r in SIG if 'bps_risk' in r])))

print()
print('=' * 100)
print('BY VOLUME TIER — bull put spread, signal days')
print('=' * 100)
print('{:<22} {:>6} {:>10} {:>7} {:>8} {:>11}'.format('tier', 'n', 'mean $', 't', 'win%', 'total $'))
for lab, lo, hi in [('vol 1.4-1.8', 1.4, 1.8), ('vol 1.8-2.5', 1.8, 2.5), ('vol >2.5', 2.5, 1e9)]:
    g = [r for r in SIG if lo <= r['volx'] < hi]
    s_ = summ(g, 'bps_pl')
    if s_:
        print('{:<22} {:>6} {:>10.1f} {:>7.2f} {:>7.1f}% {:>11.0f}'.format(
            lab, s_['n'], s_['pl'], s_['t'], s_['win'], s_['total']))
    else:
        print('{:<22} {:>6}   (thin)'.format(lab, len(g)))

"""Does a RISK REGIME overlay sharpen the capitulation-reversal edge?

Hypothesis, and it is the same mechanism as the volume ceiling we already found:

    A panic bounces when the selling is EMOTIONAL. It does not bounce when real risk is being
    repriced. Extreme volume (>2.5x) marks "real news arrived" and the edge weakens there.
    Deteriorating CREDIT should mark the same thing at the macro level - and should predict the
    eras where the effect failed (2020-21 COVID, 2022-23 rate shock).

Overlays, taken from TrustyRustyEngine's spxlrealyields strategy (already parameter-tested there):

    credit_state : HYG/IEF ratio vs its 50-day mean, 1.5% hysteresis   (junk vs quality)
    vol_state    : TLT 21d stdev vs its 90d mean, 1.5% hysteresis      (macro calm)
    real yield   : DGS5 - T5YIE, 50d mean, slope over 10 days          (policy direction)
    gold         : gold-miner composite vs SPY                          (fear rotation)
    defensives   : (XLP+XLV)/2 vs SPY                                   (sector rotation)

Each is tested alone and in combination against the capitulation signal.
"""
import csv, io, math, sys, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
HOLD = 3
TOL = 0.015
CREDIT_LB, TLT_STD_LB, VOL_LB, MACRO_LB, SLOPE_LB = 50, 21, 90, 50, 10


def load(sym, col='adj_close'):
    try:
        rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    except OSError:
        return {}
    out = {}
    for r in rows:
        try:
            v = float(r.get(col) or r.get('value') or r.get('close') or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[r['date']] = v
    return out


def load_full(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    return {r['date']: (float(r['adj_close']), float(r['volume'])) for r in rows
            if float(r['adj_close']) > 0}


HYG, IEF, TLT = load('HYG'), load('IEF'), load('TLT')
DGS5, T5YIE = load('DGS5', 'value'), load('T5YIE', 'value')
WPM, FNV, RGLD = load('WPM'), load('FNV'), load('RGLD')
XLPd, XLVd, SPYd = load('XLP'), load('XLV'), load('SPY')
print('series loaded: HYG {} IEF {} TLT {} DGS5 {} T5YIE {} gold {} '
      .format(len(HYG), len(IEF), len(TLT), len(DGS5), len(T5YIE), len(WPM)))

dates = sorted(set(HYG) & set(IEF) & set(TLT) & set(SPYd))
print('common dates (HYG-limited): {} -> {}  n={}'.format(dates[0], dates[-1], len(dates)))


def sma(x):
    return sum(x) / len(x) if x else 0.0


def sstd(x):
    n = len(x)
    if n < 2:
        return 0.0
    m = sma(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))


# ---- build regime series exactly as the engine does, with hysteresis --------------------
REG = {}
cr_hist, tlt_hist, tlt_std_hist = [], [], []
d5_hist, t5_hist, d5s_hist, t5s_hist = [], [], [], []
credit_state = vol_state = False
for d in dates:
    cr_hist.append(HYG[d] / IEF[d]); cr_hist[:] = cr_hist[-CREDIT_LB:]
    tlt_hist.append(TLT[d]); tlt_hist[:] = tlt_hist[-TLT_STD_LB:]
    if len(tlt_hist) == TLT_STD_LB:
        tlt_std_hist.append(sstd(tlt_hist)); tlt_std_hist[:] = tlt_std_hist[-VOL_LB:]
    if d in DGS5 and d in T5YIE:
        d5_hist.append(DGS5[d]); d5_hist[:] = d5_hist[-MACRO_LB:]
        t5_hist.append(T5YIE[d]); t5_hist[:] = t5_hist[-MACRO_LB:]
        if len(d5_hist) == MACRO_LB:
            d5s_hist.append(sma(d5_hist)); d5s_hist[:] = d5s_hist[-(SLOPE_LB + 1):]
            t5s_hist.append(sma(t5_hist)); t5s_hist[:] = t5s_hist[-(SLOPE_LB + 1):]
    if len(cr_hist) < CREDIT_LB or len(tlt_std_hist) < VOL_LB:
        continue
    c_now, c_avg = cr_hist[-1], sma(cr_hist)
    v_now, v_avg = tlt_std_hist[-1], sma(tlt_std_hist)
    credit_state = (c_now > c_avg * (1 + TOL)) if not credit_state \
        else (c_now >= c_avg * (1 - TOL))
    vol_state = (v_now < v_avg * (1 - TOL)) if not vol_state \
        else (v_now <= v_avg * (1 + TOL))
    ry_slope = None
    if len(d5s_hist) == SLOPE_LB + 1:
        ry_now = d5s_hist[-1] - t5s_hist[-1]
        ry_then = d5s_hist[0] - t5s_hist[0]
        ry_slope = ry_now - ry_then
    gold = [x[d] for x in (WPM, FNV, RGLD) if d in x]
    REG[d] = dict(credit=credit_state, vol=vol_state,
                  risk_on=credit_state and vol_state,
                  credit_ratio=c_now / c_avg - 1.0,
                  ry_slope=ry_slope,
                  gold=float(np.mean(gold)) if gold else None,
                  defensive=((XLPd.get(d, 0) + XLVd.get(d, 0)) / 2) or None,
                  spy=SPYd.get(d))
print('regime days: {}'.format(len(REG)))

# gold-vs-market and defensive-vs-market trends (60-day relative)
rd = sorted(REG)
for i, d in enumerate(rd):
    if i < 60:
        continue
    p = rd[i - 60]
    g0, g1 = REG[p]['gold'], REG[d]['gold']
    s0, s1 = REG[p]['spy'], REG[d]['spy']
    df0, df1 = REG[p]['defensive'], REG[d]['defensive']
    if g0 and g1 and s0 and s1:
        REG[d]['gold_rel'] = math.log(g1 / g0) - math.log(s1 / s0)
    if df0 and df1 and s0 and s1:
        REG[d]['def_rel'] = math.log(df1 / df0) - math.log(s1 / s0)

# ---- capitulation events on the ETF universe --------------------------------------------
ETFS = ['SPY', 'QQQ', 'SOXX', 'XLP', 'XLV', 'FDN']
EV, BASEM = [], {}
for s in ETFS:
    full = load_full(s)
    ds = sorted(full)
    c = np.array([full[d][0] for d in ds])
    v = np.array([full[d][1] for d in ds])
    n = len(c)
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    fwd = [math.log(c[i + HOLD] / c[i]) * 100 for i in range(25, n - HOLD)]
    BASEM[s] = float(np.mean(fwd))
    for i in range(25, n - HOLD):
        d = ds[i]
        if d not in REG:
            continue
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0:
            continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if st < -2.5 and vx >= 1.4:
            EV.append(dict(sym=s, date=d, stretch=st, volx=vx,
                           f3=math.log(c[i + HOLD] / c[i]) * 100, **REG[d]))
print('capitulation events inside the regime window: {}'.format(len(EV)))


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 10:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


def stat(g):
    if len(g) < 10:
        return None
    raw = np.array([r['f3'] for r in g])
    e = np.array([r['f3'] - BASEM[r['sym']] for r in g])
    return dict(n=len(g), raw=raw.mean(), t=nw_t(e, HOLD), win=(raw > 0).mean() * 100)


ALL = stat(EV)
print()
print('=' * 96)
print('BASELINE (no overlay), {} onward: n={} raw {:+.3f}% t={:.2f} win {:.1f}%'.format(
    dates[0][:4], ALL['n'], ALL['raw'], ALL['t'], ALL['win']))
print('=' * 96)

OVERLAYS = [
    ('credit healthy (HYG/IEF above mean)', lambda r: r['credit'], lambda r: not r['credit']),
    ('macro calm (TLT vol low)', lambda r: r['vol'], lambda r: not r['vol']),
    ('risk_on (credit AND calm)', lambda r: r['risk_on'], lambda r: not r['risk_on']),
    ('real yield falling', lambda r: r.get('ry_slope') is not None and r['ry_slope'] < 0,
     lambda r: r.get('ry_slope') is not None and r['ry_slope'] >= 0),
    ('gold LAGGING market (60d)', lambda r: r.get('gold_rel') is not None and r['gold_rel'] < 0,
     lambda r: r.get('gold_rel') is not None and r['gold_rel'] >= 0),
    ('defensives LAGGING market (60d)', lambda r: r.get('def_rel') is not None and r['def_rel'] < 0,
     lambda r: r.get('def_rel') is not None and r['def_rel'] >= 0),
]
print()
def welch(a, b):
    """Two-sample t on the DIFFERENCE. Reporting each side's own t-stat says nothing about
    whether the overlay actually separates them."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 8 or len(b) < 8:
        return float('nan'), float('nan')
    d = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, (d / se if se > 0 else float('nan'))


print('{:<36} {:>5} {:>8} {:>6}  {:>5} {:>8} {:>6}  {:>9} {:>7}'.format(
    'overlay', 'n ON', 'raw%', 'win%', 'nOFF', 'raw%', 'win%', 'ON-OFF', 't(diff)'))
print('-' * 104)
results = []
for lab, on_f, off_f in OVERLAYS:
    gon = [r for r in EV if on_f(r)]
    goff = [r for r in EV if off_f(r)]
    a, b = stat(gon), stat(goff)
    if not a or not b:
        print('{:<36} (thin)'.format(lab)); continue
    d, td = welch([r['f3'] for r in gon], [r['f3'] for r in goff])
    results.append((lab, d, td, a, b))
    print('{:<36} {:>5} {:>8.3f} {:>5.1f}%  {:>5} {:>8.3f} {:>5.1f}%  {:>+9.3f} {:>7.2f}'.format(
        lab, a['n'], a['raw'], a['win'], b['n'], b['raw'], b['win'], d, td))
print()
print('  {} overlays tested -> at 5% we expect {:.1f} false positives by chance alone.'.format(
    len(results), 0.05 * len(results)))
sig = [r for r in results if abs(r[2]) > 2.0]
print('  |t(diff)| > 2.0: {}'.format(', '.join(r[0] for r in sig) if sig else 'NONE'))

print()
print('=' * 96)
print('COMBINED — the two mechanistically coherent overlays')
print('=' * 96)
def both_on(r):
    return (r.get('gold_rel') is not None and r['gold_rel'] < 0) and r['vol']
def either_off(r):
    return not ((r.get('gold_rel') is not None and r['gold_rel'] < 0) and r['vol'])
gon = [r for r in EV if both_on(r)]
goff = [r for r in EV if r.get('gold_rel') is not None and either_off(r)]
a, b = stat(gon), stat(goff)
if a and b:
    d, td = welch([r['f3'] for r in gon], [r['f3'] for r in goff])
    print('  calm AND gold lagging : n={:<4} raw {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
        a['n'], a['raw'], a['t'], a['win']))
    print('  otherwise             : n={:<4} raw {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
        b['n'], b['raw'], b['t'], b['win']))
    print('  difference {:+.3f}%  t(diff)={:.2f}'.format(d, td))
    print('  events per year in the ON state: {:.1f}'.format(a['n'] / 19.1))

print()
print('=' * 96)
print('CREDIT RATIO AS A CONTINUOUS VARIABLE (HYG/IEF vs its 50d mean)')
print('=' * 96)
print('{:<28} {:>6} {:>10} {:>8} {:>8}'.format('credit ratio vs mean', 'n', 'raw%', 't', 'win%'))
qs = np.percentile([r['credit_ratio'] for r in EV], [25, 50, 75])
for lab, lo, hi in [('deteriorating (bottom 25%)', -9, qs[0]), ('25-50%', qs[0], qs[1]),
                    ('50-75%', qs[1], qs[2]), ('healthy (top 25%)', qs[2], 9)]:
    s_ = stat([r for r in EV if lo <= r['credit_ratio'] < hi])
    if s_:
        print('{:<28} {:>6} {:>10.3f} {:>8.2f} {:>7.1f}%'.format(
            lab, s_['n'], s_['raw'], s_['t'], s_['win']))

print()
print('=' * 96)
print('DOES THE OVERLAY EXPLAIN THE ERA FAILURES?')
print('=' * 96)
print('{:<14} {:>6} {:>9} {:>7}   {:>6} {:>9} {:>7}   {:>10}'.format(
    'era', 'n on', 'raw%', 't', 'n off', 'raw%', 't', '%risk_on'))
for lab, a, b in [('2008-2009', '2008', '2010'), ('2010-2015', '2010', '2016'),
                  ('2016-2019', '2016', '2020'), ('2020-2021', '2020', '2022'),
                  ('2022-2023', '2022', '2024'), ('2024-2026', '2024', '2027')]:
    g = [r for r in EV if a <= r['date'][:4] < b]
    if len(g) < 8:
        print('{:<14} {:>6}  (thin)'.format(lab, len(g))); continue
    on = stat([r for r in g if r['credit']])
    off = stat([r for r in g if not r['credit']])
    pct = 100.0 * sum(1 for r in g if r['credit']) / len(g)
    print('{:<14} {:>6} {:>9} {:>7}   {:>6} {:>9} {:>7}   {:>9.0f}%'.format(
        lab,
        on['n'] if on else 0, '{:+.3f}'.format(on['raw']) if on else '-',
        '{:.2f}'.format(on['t']) if on else '-',
        off['n'] if off else 0, '{:+.3f}'.format(off['raw']) if off else '-',
        '{:.2f}'.format(off['t']) if off else '-', pct))

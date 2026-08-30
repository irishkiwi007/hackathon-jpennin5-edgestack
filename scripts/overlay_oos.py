"""Out-of-sample test of the regime overlays.

On 115 ETF events the only significant separations were NEGATIVE: healthy credit (t=-2.80) and
risk_on (t=-2.26) both make the capitulation edge WORSE. The combination "calm AND gold lagging"
looked spectacular (+3.02%, t=6.61, 80.8% win) but n=26, neither component separates alone, and
the pairing was chosen after seeing the results. That is a specification search and it needs an
independent sample before it can be believed.

The 479-name universe is that sample. Same regime series, completely different events.
If the credit effect is real it should appear there too; if the calm+gold combination is noise,
it should evaporate.
"""
import csv, io, json, math, sys
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
HOLD = 3
TOL = 0.015
CREDIT_LB, TLT_STD_LB, VOL_LB = 50, 21, 90
BONDS = {'TLT','IEF','SHY','AGG','BND','TIP','LQD','HYG','JNK','MUB','VTEB','BSV','BIV','BLV',
         'VCIT','VCSH','IGSB','SHV','BIL','SGOV','TLH','EDV','VGIT','VGSH','VGLT','SCHO','SCHR',
         'MBB','EMB','PFF','SRLN','BKLN','FLOT','USFR','TFLO','STIP','VTIP','SPTL','SPTS','SPIB'}
LEVERAGED = {'TQQQ','SQQQ','SOXL','SOXS','SPXL','SPXS','SPXU','UPRO','SDS','SSO','QLD','QID',
             'TNA','TZA','LABU','LABD','YINN','YANG','FAS','FAZ','ERX','ERY','NUGT','DUST',
             'JNUG','JDST','BOIL','KOLD','UCO','SCO','GUSH','DRIP','UVXY','VXX','SVXY','VIXY',
             'TSLL','NVDL','CONL','MSTU','MSTX','BITX','ETHU','USD','TMF','TMV','TYD','TYO'}


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


HYG, IEF, TLT = load('HYG'), load('IEF'), load('TLT')
WPM, FNV, RGLD = load('WPM'), load('FNV'), load('RGLD')
SPYd = load('SPY')
dates = sorted(set(HYG) & set(IEF) & set(TLT) & set(SPYd))


def sma(x): return sum(x) / len(x) if x else 0.0
def sstd(x):
    n = len(x)
    if n < 2: return 0.0
    m = sma(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))


REG = {}
cr, th, tsh = [], [], []
cs = vs = False
for d in dates:
    cr.append(HYG[d] / IEF[d]); cr[:] = cr[-CREDIT_LB:]
    th.append(TLT[d]); th[:] = th[-TLT_STD_LB:]
    if len(th) == TLT_STD_LB:
        tsh.append(sstd(th)); tsh[:] = tsh[-VOL_LB:]
    if len(cr) < CREDIT_LB or len(tsh) < VOL_LB:
        continue
    c_now, c_avg = cr[-1], sma(cr)
    v_now, v_avg = tsh[-1], sma(tsh)
    cs = (c_now > c_avg * (1 + TOL)) if not cs else (c_now >= c_avg * (1 - TOL))
    vs = (v_now < v_avg * (1 - TOL)) if not vs else (v_now <= v_avg * (1 + TOL))
    g = [x[d] for x in (WPM, FNV, RGLD) if d in x]
    REG[d] = dict(credit=cs, vol=vs, risk_on=cs and vs,
                  gold=float(np.mean(g)) if g else None, spy=SPYd.get(d))
rd = sorted(REG)
for i, d in enumerate(rd):
    if i < 60: continue
    p = rd[i - 60]
    g0, g1, s0, s1 = REG[p]['gold'], REG[d]['gold'], REG[p]['spy'], REG[d]['spy']
    if g0 and g1 and s0 and s1:
        REG[d]['gold_rel'] = math.log(g1 / g0) - math.log(s1 / s0)
print('regime days: {}  {} -> {}'.format(len(REG), rd[0], rd[-1]))

D = json.load(open('sp500_bars.json'))
NAMES = [s for s in D if len(D.get(s, [])) > 900 and s not in BONDS and s not in LEVERAGED]
print('single-name universe: {}'.format(len(NAMES)))

EV, BASEM = [], {}
for s in NAMES:
    b = D[s]
    c = np.array([x['c'] for x in b], float)
    v = np.array([x['v'] for x in b], float)
    ds = [x['t'] for x in b]
    n = len(c)
    if (c <= 0).any(): continue
    r = np.zeros(n); r[1:] = np.log(c[1:] / c[:-1])
    fwd = [math.log(c[i + HOLD] / c[i]) * 100 for i in range(25, n - HOLD)]
    if not fwd: continue
    BASEM[s] = float(np.mean(fwd))
    for i in range(25, n - HOLD):
        d = ds[i]
        if d not in REG: continue
        rv = r[i - 19:i + 1].std(ddof=1)
        if not np.isfinite(rv) or rv <= 0: continue
        st = math.log(c[i] / c[i - 5]) / (rv * math.sqrt(5))
        vx = v[i] / max(np.mean(v[i - 19:i + 1]), 1.0)
        if st < -2.5 and vx >= 1.4:
            EV.append(dict(sym=s, date=d, stretch=st, volx=vx, spot=float(c[i]),
                           f3=math.log(c[i + HOLD] / c[i]) * 100, **REG[d]))
print('single-name capitulation events: {}'.format(len(EV)))


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 10: return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


def stat(g):
    if len(g) < 15: return None
    raw = np.array([r['f3'] for r in g])
    e = np.array([r['f3'] - BASEM[r['sym']] for r in g])
    return dict(n=len(g), raw=raw.mean(), t=nw_t(e, HOLD), win=(raw > 0).mean() * 100)


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 10 or len(b) < 10: return float('nan'), float('nan')
    d = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, (d / se if se > 0 else float('nan'))


ALL = stat(EV)
print()
print('=' * 100)
print('OUT-OF-SAMPLE: same overlays, {} single-name events (ETF sample was 115)'.format(len(EV)))
print('  ETF baseline was +1.625%.  Single-name baseline: {:+.3f}% t={:.2f} win {:.1f}%'.format(
    ALL['raw'], ALL['t'], ALL['win']))
print('=' * 100)
TESTS = [
    ('credit healthy', lambda r: r['credit'], -1.590, -2.80),
    ('risk_on (credit AND calm)', lambda r: r['risk_on'], -1.379, -2.26),
    ('macro calm', lambda r: r['vol'], +1.116, 1.64),
    ('gold lagging', lambda r: r.get('gold_rel') is not None and r['gold_rel'] < 0, +0.703, 1.11),
    ('calm AND gold lagging',
     lambda r: r['vol'] and r.get('gold_rel') is not None and r['gold_rel'] < 0, +1.816, 2.56),
]
print('{:<28} {:>6} {:>8} {:>6}  {:>6} {:>8} {:>6}  {:>9} {:>7}  {:>12}'.format(
    'overlay', 'n ON', 'raw%', 'win%', 'nOFF', 'raw%', 'win%', 'ON-OFF', 't(diff)', 'ETF said'))
print('-' * 112)
for lab, f, etf_d, etf_t in TESTS:
    gon = [r for r in EV if f(r)]
    goff = [r for r in EV if not f(r)]
    a, b = stat(gon), stat(goff)
    if not a or not b:
        print('{:<28} (thin)'.format(lab)); continue
    d, td = welch([r['f3'] for r in gon], [r['f3'] for r in goff])
    agree = 'CONFIRMS' if (d > 0) == (etf_d > 0) else 'CONTRADICTS'
    print('{:<28} {:>6} {:>8.3f} {:>5.1f}%  {:>6} {:>8.3f} {:>5.1f}%  {:>+9.3f} {:>7.2f}  '
          '{:>+6.2f} {}'.format(lab, a['n'], a['raw'], a['win'], b['n'], b['raw'], b['win'],
                                d, td, etf_d, agree))

print()
print('=' * 100)
print('BEST FILTER — trade only when credit is NOT healthy (the surviving ETF result)')
print('=' * 100)
for lab, sel in (('single names', EV),):
    gon = [r for r in sel if not r['credit']]
    a = stat(gon); b = stat(sel)
    if a and b:
        print('  unfiltered : n={:<5} raw {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
            b['n'], b['raw'], b['t'], b['win']))
        print('  credit weak: n={:<5} raw {:+.3f}%  t={:.2f}  win {:.1f}%'.format(
            a['n'], a['raw'], a['t'], a['win']))
        print('  retained {:.0f}% of events, mean move {:+.1f}% relative'.format(
            100.0 * a['n'] / b['n'], 100.0 * (a['raw'] / b['raw'] - 1) if b['raw'] else 0))

print()
print('=' * 100)
print('ERA STABILITY of the credit filter, single names')
print('=' * 100)
print('{:<14} {:>7} {:>9} {:>7} {:>7}   {:>7} {:>9} {:>7}'.format(
    'era', 'n weak', 'raw%', 't', 'win%', 'n healthy', 'raw%', 't'))
for lab, a_, b_ in [('2016-2017','2016','2018'),('2018-2019','2018','2020'),
                    ('2020-2021','2020','2022'),('2022-2023','2022','2024'),
                    ('2024-2026','2024','2027')]:
    g = [r for r in EV if a_ <= r['date'][:4] < b_]
    w = stat([r for r in g if not r['credit']])
    h = stat([r for r in g if r['credit']])
    print('{:<14} {:>7} {:>9} {:>7} {:>7}   {:>7} {:>9} {:>7}'.format(
        lab,
        w['n'] if w else 0, '{:+.3f}'.format(w['raw']) if w else '-',
        '{:.2f}'.format(w['t']) if w else '-', '{:.1f}%'.format(w['win']) if w else '-',
        h['n'] if h else 0, '{:+.3f}'.format(h['raw']) if h else '-',
        '{:.2f}'.format(h['t']) if h else '-'))

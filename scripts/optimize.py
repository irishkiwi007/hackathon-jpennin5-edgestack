"""Structure optimisation: raise RETURN ON RISK, since sizing alone cannot.

The binding number is 0.75% return on risk per trade ($27 net on $3,597 at risk). Deploying more
capital scales return and risk together and changes nothing. These are the levers that actually
move return-on-risk:

  1. IRON CONDOR vs put spread. Selling both sides collects roughly double the credit while max
     loss is still only one side - so return on risk can nearly double for the same capital.
  2. SHORT STRIKE MONEYNESS. Further OTM raises the win rate and lowers the credit; only the
     ratio matters.
  3. WIDTH. Narrower cuts risk and credit together, but changes the credit/width ratio.
  4. DTE. Shorter means faster theta per day at risk.
  5. TAKE-PROFIT. Closing at a fraction of max profit frees capital sooner, so more trades per
     year on the same capital, and cuts tail exposure.

Volatility skew is taken from live measurement, not assumed: 4% OTM puts price at 1.33x ATM IV,
4% OTM calls at 0.85x. Ignoring that would overstate the call credit by ~18%.

Regime is the validated one throughout: bonds CALM and IV/RV not cheap.
"""
import csv, io, json, math, sys, datetime, urllib.request, urllib.parse, http.cookiejar
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(u, ref=None):
    r = urllib.request.Request(u)
    r.add_header('User-Agent', UA)
    if ref:
        r.add_header('Referer', ref)
    return op.open(r, timeout=60).read().decode('utf-8', 'replace')


try:
    get('https://fc.yahoo.com')
except Exception:
    pass
cr = get('https://query1.finance.yahoo.com/v1/test/getcrumb',
         ref='https://finance.yahoo.com/').strip()
end = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
start = end - 34 * 365 * 86400


def yseries(tk):
    u = ('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(tk)
         + '?period1={}&period2={}&interval=1d&crumb={}'.format(
             start, end, urllib.parse.quote(cr)))
    c = json.loads(get(u, ref='https://finance.yahoo.com/'))
    res = c['chart']['result'][0]
    ts, q = res['timestamp'], res['indicators']['quote'][0]
    out = {}
    for i, t in enumerate(ts):
        v = q['close'][i]
        if v:
            out[datetime.datetime.fromtimestamp(
                t, datetime.timezone.utc).date().isoformat()] = float(v)
    return out


VIX = yseries('^VIX')
BASE = ('C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/'
        'data/historical')
RATE = 0.045
LEG_FR = 4.0                     # SPY one-way per leg, measured
SPOT_NOW = 769.35

# measured skew: IV multiplier vs ATM, by moneyness (negative = below spot)
SKEW_X = [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06]
SKEW_Y = [1.63, 1.35, 1.15, 1.00, 0.85, 0.90, 1.12]


def skew_mult(m):
    return float(np.interp(m, SKEW_X, SKEW_Y))


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsp(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return K * math.exp(-r * T) * ncdf(-(d1 - s * math.sqrt(T))) - S * ncdf(-d1)


def bsc(S, K, T, r, s):
    if s <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d1 - s * math.sqrt(T))


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 12:
        return float('nan')
    m = x.mean(); e = x - m; s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    return m / math.sqrt(s / n) if s > 0 else float('nan')


def load(sym):
    rows = list(csv.DictReader(open(BASE + '/' + sym + '.csv', encoding='utf-8')))
    return ([r['date'] for r in rows],
            np.array([float(r['adj_close']) for r in rows]))


td, tc = load('TLT')
stds = {}
for i in range(21, len(tc)):
    stds[td[i]] = float(np.std(tc[i - 21:i], ddof=1))
CALM = {}
hist, state = [], False
for d in [x for x in td if x in stds]:
    hist.append(stds[d]); hist[:] = hist[-90:]
    if len(hist) < 90:
        continue
    now, avg = hist[-1], sum(hist) / len(hist)
    state = (now < avg * 0.985) if not state else (now <= avg * 1.015)
    CALM[d] = state

dts, cl = load('SPY')
n = len(cl)
rr = np.zeros(n); rr[1:] = np.log(cl[1:] / cl[:-1])
scale = SPOT_NOW / cl[-1]

# base event list: regime-qualified sessions
EV = []
for i in range(30, n - 32):
    d = dts[i]
    if d not in VIX or d not in CALM or not CALM[d]:
        continue
    rv = rr[i - 19:i + 1].std(ddof=1) * math.sqrt(252)
    if rv <= 0:
        continue
    ivrv = (VIX[d] / 100.0) / rv
    if ivrv < 1.04:                       # "not cheap" - the validated condition
        continue
    EV.append(dict(i=i, date=d, iv=VIX[d] / 100.0, rv=rv, ivrv=ivrv))
print('regime-qualified SPY sessions: {}'.format(len(EV)))
YEARS = 33.3


def price(S, K, T, iv_atm, cp):
    m = K / S - 1.0
    return (bsp if cp == 'P' else bsc)(S, K, T, RATE, iv_atm * skew_mult(m))


def run(structure, put_off, call_off, width_pct, dte, hold, take_profit=None):
    """Return list of per-contract P&L and per-contract max risk."""
    out = []
    for e in EV:
        i = e['i']
        if i + hold >= n:
            continue
        d, dE = dts[i], dts[i + hold]
        if dE not in VIX:
            continue
        S0, S1 = cl[i] * scale, cl[i + hold] * scale
        iv0, iv1 = e['iv'], VIX[dE] / 100.0
        T0, T1 = dte / 365.0, max((dte - hold) / 365.0, 1e-4)
        w = S0 * width_pct
        legs = 2
        Kps, Kpl = S0 * (1 + put_off), S0 * (1 + put_off) - w
        c0 = price(S0, Kps, T0, iv0, 'P') - price(S0, Kpl, T0, iv0, 'P')
        c1 = price(S1, Kps, T1, iv1, 'P') - price(S1, Kpl, T1, iv1, 'P')
        if structure == 'condor':
            Kcs, Kcl = S0 * (1 + call_off), S0 * (1 + call_off) + w
            c0 += price(S0, Kcs, T0, iv0, 'C') - price(S0, Kcl, T0, iv0, 'C')
            c1 += price(S1, Kcs, T1, iv1, 'C') - price(S1, Kcl, T1, iv1, 'C')
            legs = 4
        if c0 <= 0:
            continue
        # take-profit: close early if the credit has decayed to (1-tp) of entry
        pnl = c0 - c1
        if take_profit is not None and pnl >= take_profit * c0:
            pnl = take_profit * c0
        fr = 2 * legs * LEG_FR
        risk = w * 100 - c0 * 100
        if risk <= 0:
            continue
        out.append(((pnl * 100) - fr, risk))
    return out


def summarise(rows, hold, label):
    if len(rows) < 60:
        return None
    a = np.array([r[0] for r in rows])
    risk = float(np.mean([r[1] for r in rows]))
    per_yr = len(a) / YEARS
    ror = a.mean() / risk if risk > 0 else 0
    # capital-aware annual return: each trade ties up `risk` for `hold` sessions
    turns = 252.0 / hold
    ann = ror * min(per_yr, turns)
    return dict(label=label, n=len(a), net=a.mean(), risk=risk, ror=ror,
                t=nw_t(a, hold), win=100 * (a > 0).mean(), per_yr=per_yr, ann=ann)


print()
print('=' * 112)
print('1. STRUCTURE — put spread vs iron condor (2% width, 14 DTE, 5-session hold)')
print('=' * 112)
print('{:<34} {:>6} {:>9} {:>9} {:>9} {:>7} {:>7} {:>9}'.format(
    'structure', 'n', 'net $', 'risk $', 'ret/risk', 't', 'win%', 'ann %'))
for lab, st, po, co in (('put spread ATM', 'put', 0.0, None),
                        ('put spread 2% OTM', 'put', -0.02, None),
                        ('condor  2% OTM / 2% OTM', 'condor', -0.02, 0.02),
                        ('condor  3% OTM / 3% OTM', 'condor', -0.03, 0.03),
                        ('condor  2% put / 3% call', 'condor', -0.02, 0.03)):
    r = summarise(run(st, po, co, 0.02, 14, 5), 5, lab)
    if r:
        print('{:<34} {:>6} {:>9.0f} {:>9.0f} {:>8.2f}% {:>7.2f} {:>6.1f}% {:>8.1f}%'.format(
            r['label'], r['n'], r['net'], r['risk'], 100 * r['ror'], r['t'], r['win'],
            100 * r['ann']))

print()
print('=' * 112)
print('2. DTE x HOLD — theta per day at risk (condor 2%/3%, 2% width)')
print('=' * 112)
print('{:<10}'.format('DTE') + ''.join('{:>22}'.format('hold {}d'.format(h))
                                       for h in (2, 5, 10)))
print('{:<10}'.format('') + ''.join('{:>22}'.format('ret/risk  t   ann%')
                                    for _ in range(3)))
for dte in (7, 14, 21, 30):
    line = '{:<10}'.format(dte)
    for hold in (2, 5, 10):
        if hold >= dte:
            line += '{:>22}'.format('-')
            continue
        r = summarise(run('condor', -0.02, 0.03, 0.02, dte, hold), hold, 'x')
        line += '{:>22}'.format('{:+6.2f}% {:5.2f} {:5.1f}%'.format(
            100 * r['ror'], r['t'], 100 * r['ann']) if r else '-')
    print(line)

print()
print('=' * 112)
print('3. WIDTH and MONEYNESS (condor, 14 DTE, 5-session hold)')
print('=' * 112)
print('{:<12}'.format('width') + ''.join('{:>20}'.format('{:.0%} OTM'.format(abs(o)))
                                         for o in (-0.01, -0.02, -0.03, -0.04)))
for w in (0.01, 0.02, 0.03, 0.05):
    line = '{:<12}'.format('{:.0%}'.format(w))
    for off in (-0.01, -0.02, -0.03, -0.04):
        r = summarise(run('condor', off, -off, w, 14, 5), 5, 'x')
        line += '{:>20}'.format('{:+6.2f}% {:5.1f}%'.format(
            100 * r['ror'], 100 * r['ann']) if r else '-')
    print(line)

print()
print('=' * 112)
print('4. TAKE-PROFIT — does closing early raise capital efficiency?')
print('=' * 112)
print('{:<20} {:>6} {:>9} {:>10} {:>7} {:>7} {:>9}'.format(
    'rule', 'n', 'net $', 'ret/risk', 't', 'win%', 'ann %'))
for lab, tp in (('hold full 5 sessions', None), ('close at 25% of credit', 0.25),
                ('close at 50% of credit', 0.50), ('close at 75% of credit', 0.75)):
    r = summarise(run('condor', -0.02, 0.03, 0.02, 14, 5, take_profit=tp), 5, lab)
    if r:
        print('{:<20} {:>6} {:>9.0f} {:>9.2f}% {:>7.2f} {:>6.1f}% {:>8.1f}%'.format(
            r['label'], r['n'], r['net'], 100 * r['ror'], r['t'], r['win'], 100 * r['ann']))

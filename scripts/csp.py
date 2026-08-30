"""Cash-secured put on the capitulation signal — the structure that changes the friction math.

Everything before this failed for one of two reasons:
  1. friction: a bull put spread crosses 4 legs round trip (~$56 on SPY) against a gross edge
     of ~$45
  2. payoff: credit was 24.6% of width, so breakeven needed a ~75% win rate; the signal gives
     62-66%

A cash-secured put fixes both:
  - ONE leg on entry, and ZERO on exit when it expires worthless -> 1 crossing instead of 4
  - no long leg eating the premium, so the whole credit is kept

Permitted: Alpaca level 3 includes level 1 (covered calls + cash-secured puts). Verified on the
account: options_approved_level 3, options_buying_power $100,000.

Premiums are measured from LIVE chains as a percentage of spot at each moneyness, then applied
to the historical event set. Payoff at expiry is deterministic from the underlying, so no
option price history is needed.
"""
import os
import io, json, math, sys, time, datetime, urllib.request
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
PAPER = 'https://paper-api.alpaca.markets'
DATA = 'https://data.alpaca.markets'

_src = open('overlay_oos.py', encoding='utf-8').read().split("ALL = stat(EV)")[0]
_src = "\n".join(l for l in _src.splitlines()
                 if not l.startswith("sys.stdout = io.TextIOWrapper"))
exec(_src)

D2 = json.load(open('sp500_bars.json'))
FR = json.load(open('friction_screen.json'))


def q(u, tries=2):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=45))
        except Exception:
            time.sleep(0.4)
    return None


# ---- measure live single-leg put premium and half-spread, by moneyness -------------------
SAMPLE = ['SPY', 'QQQ', 'IWM', 'DIA', 'NFLX', 'NVDA', 'BAC', 'WMT', 'PLTR', 'F', 'SOFI',
          'XLE', 'XLF', 'GLD', 'SLV', 'T', 'PFE', 'VZ', 'KO', 'NKE']
today = datetime.date.today()
lo = (today + datetime.timedelta(days=8)).isoformat()
hi = (today + datetime.timedelta(days=16)).isoformat()
spot = {}
d = q(DATA + '/v2/stocks/bars/latest?symbols=' + ','.join(SAMPLE) + '&feed=iex')
for s, b in (d or {}).get('bars', {}).items():
    spot[s] = float(b['c'])

BUCKETS = [('ATM', 0.00), ('2% OTM', -0.02), ('5% OTM', -0.05), ('8% OTM', -0.08)]
prem = defaultdict(list)
half = defaultdict(list)
for s in SAMPLE:
    if s not in spot:
        continue
    S = spot[s]
    c = q('{}/v2/options/contracts?underlying_symbols={}&expiration_date_gte={}'
          '&expiration_date_lte={}&type=put&limit=400&status=active'.format(PAPER, s, lo, hi))
    rows = [x for x in ((c or {}).get('option_contracts') or [])
            if x.get('tradable') and 0.85 * S <= float(x['strike_price']) <= 1.03 * S]
    if len(rows) < 3:
        continue
    exps = sorted({x['expiration_date'] for x in rows})
    rows = [x for x in rows if x['expiration_date'] == exps[0]]
    occ = [x['symbol'] for x in rows]
    snaps = {}
    for i in range(0, len(occ), 100):
        sd = q(DATA + '/v1beta1/options/snapshots?symbols=' + ','.join(occ[i:i + 100]))
        for k, v2 in (sd or {}).get('snapshots', {}).items():
            qt = v2.get('latestQuote') or {}
            b_, a_ = float(qt.get('bp', 0) or 0), float(qt.get('ap', 0) or 0)
            if b_ > 0 and a_ >= b_:
                snaps[k] = (b_, a_)
    byk = {}
    for x in rows:
        if x['symbol'] in snaps:
            byk[float(x['strike_price'])] = snaps[x['symbol']]
    if len(byk) < 2:
        continue
    ks = sorted(byk)
    for lab, off in BUCKETS:
        target = S * (1 + off)
        k = min(ks, key=lambda z: abs(z - target))
        if abs(k - target) / S > 0.025:
            continue
        b_, a_ = byk[k]
        mid = 0.5 * (b_ + a_)
        if mid <= 0:
            continue
        prem[lab].append(mid / S)              # premium as a fraction of spot
        half[lab].append(0.5 * (a_ - b_) / S)  # one-way crossing cost as a fraction of spot

print('LIVE single-leg put economics ({} names, ~8-16 DTE)'.format(len(spot)))
print('{:<10} {:>8} {:>14} {:>16} {:>14}'.format(
    'moneyness', 'n', 'premium/spot', 'half-spread/spot', 'prem/friction'))
PREM, HALF = {}, {}
for lab, _ in BUCKETS:
    if len(prem[lab]) < 5:
        continue
    p_ = float(np.median(prem[lab]))
    h_ = float(np.median(half[lab]))
    PREM[lab], HALF[lab] = p_, h_
    print('{:<10} {:>8} {:>13.3%} {:>15.3%} {:>14.1f}'.format(
        lab, len(prem[lab]), p_, h_, p_ / h_ if h_ else 0))

# ---- apply to the historical event set ---------------------------------------------------
def forward_price(sym, date, sessions):
    rows = D2.get(sym) or []
    for i, b in enumerate(rows):
        if b['t'] == date:
            j = i + sessions
            return float(rows[j]['c']) if j < len(rows) else None
    return None


print()
print('=' * 106)
print('CASH-SECURED PUT held to expiry (~10 sessions), CALM regime only')
print('  P&L per contract = premium, minus assignment loss if it finishes ITM,')
print('  minus 1 crossing on entry and 1 more only when assignment forces a close.')
print('=' * 106)
print('{:<12} {:<10} {:>6} {:>8} {:>9} {:>9} {:>10} {:>10} {:>11}'.format(
    'budget', 'strike', 'n', 'OTM%', 'win%', 'prem $', 'loss $', 'NET $', 'ret on cash'))
BUDGETS = [('<= $60', 60), ('<= $100', 100), ('any', 10 ** 9)]
best = None
for blab, budget in BUDGETS:
    names = {s for s, v in FR.items() if v and v.get('friction', 1e9) <= budget}
    ev = [r for r in EV if r['sym'] in names and r['vol']]
    if len(ev) < 60:
        continue
    for mlab, off in BUCKETS:
        if mlab not in PREM:
            continue
        pnl, otm_l, cash_l = [], [], []
        for r in ev:
            S0 = r['spot']
            ST = forward_price(r['sym'], r['date'], 10)
            if ST is None or S0 <= 0:
                continue
            K = S0 * (1 + off)
            premium = PREM[mlab] * S0
            cross = HALF[mlab] * S0
            if ST >= K:
                p = premium - cross
                otm = True
            else:
                p = premium - (K - ST) - 2 * cross
                otm = False
            pnl.append(p * 100.0)
            otm_l.append(otm)
            cash_l.append(K * 100.0)
        if len(pnl) < 40:
            continue
        a = np.array(pnl)
        cash = float(np.mean(cash_l))
        ret = a.mean() / cash if cash else 0
        print('{:<12} {:<10} {:>6} {:>7.0f}% {:>8.1f}% {:>9.0f} {:>10.0f} {:>10.0f} {:>10.3f}%'
              .format(blab, mlab, len(a), 100 * np.mean(otm_l), 100 * (a > 0).mean(),
                      float(np.mean([PREM[mlab] * r['spot'] for r in ev[:len(a)]])) * 100,
                      float(np.mean([min(0, x) for x in a])), a.mean(), ret * 100))
        if a.mean() > 0 and (best is None or ret > best[0]):
            best = (ret, blab, mlab, len(a), a.mean(), cash)

print()
if best:
    ret, blab, mlab, n, mean, cash = best
    per5 = n / 19.1 / 252 * 5
    print('  BEST: {} / {} strike -> {:+.0f} $/contract on ${:,.0f} cash = {:+.3f}% per trade'
          .format(blab, mlab, mean, cash, ret * 100))
    print('  fires {:.2f} times per 5 sessions'.format(per5))
else:
    print('  no cash-secured put configuration is net positive')

print()
print('=' * 106)
print('CONTROL — the same structure on random days (is this the SIGNAL or just selling puts?)')
print('=' * 106)
rng = np.random.default_rng(3)
allrows = []
for s in list(FR):
    if not FR[s] or FR[s].get('friction', 1e9) > 100:
        continue
    rows = D2.get(s) or []
    if len(rows) < 400:
        continue
    for _ in range(6):
        i = int(rng.integers(30, len(rows) - 12))
        allrows.append(dict(sym=s, date=rows[i]['t'], spot=float(rows[i]['c'])))
print('  random control sample: {}'.format(len(allrows)))
for mlab, off in BUCKETS:
    if mlab not in PREM:
        continue
    pnl = []
    for r in allrows:
        S0 = r['spot']
        ST = forward_price(r['sym'], r['date'], 10)
        if ST is None or S0 <= 0:
            continue
        K = S0 * (1 + off)
        premium, cross = PREM[mlab] * S0, HALF[mlab] * S0
        p = (premium - cross) if ST >= K else (premium - (K - ST) - 2 * cross)
        pnl.append(p * 100.0)
    if len(pnl) < 100:
        continue
    a = np.array(pnl)
    t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
    print('  {:<10} n={:<6} NET {:+.0f} $/contract  win {:.1f}%  t={:.2f}'.format(
        mlab, len(a), a.mean(), 100 * (a > 0).mean(), t))

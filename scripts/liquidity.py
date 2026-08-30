"""Corrected liquidity comparison.

Wrong metric: median % bid-ask across a chain. It scales inversely with premium size, so
high-IV single names flatter themselves against low-IV index ETFs. Not comparable across classes.

Right metric: build the SAME structure on every underlying - a delta-matched, expected-move-scaled
put credit spread - and measure round-trip spread cost as a fraction of the credit collected.
That is what actually erodes the trade, and it is unit-free.
"""
import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)
EXP = '2026-09-04'

ETFS = ['SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'TLT']
STOCKS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'AMD']


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def analyse(sym):
    b = run(['data', 'bars', '--symbol', sym, '--timeframe', '1Day',
             '--start', '2026-08-25', '--end', '2026-08-29T00:00:00Z'])
    if not b or not b.get('bars'):
        return None
    spot = b['bars'][-1]['c']
    ch = run(['data', 'option', 'chain', '--underlying-symbol', sym, '--feed', 'indicative',
              '--expiration-date', EXP,
              '--strike-price-gte', str(round(spot * 0.85, 0)),
              '--strike-price-lte', str(round(spot * 1.05, 0)), '--limit', '500'])
    if not ch or not ch.get('snapshots'):
        return None

    puts, atm_iv = {}, []
    for k, v in ch['snapshots'].items():
        if k[-9] != 'P':
            continue
        q = v.get('latestQuote') or {}
        bp, ap = q.get('bp'), q.get('ap')
        d = (v.get('greeks') or {}).get('delta')
        iv = v.get('impliedVolatility')
        if iv and d and 0.35 < abs(d) < 0.65:
            atm_iv.append(iv)
        if bp and ap and ap > bp and d:
            puts[int(k[-8:]) / 1000] = {'bid': bp, 'ask': ap, 'delta': d}
    if not puts or not atm_iv:
        return None
    iv = sum(atm_iv) / len(atm_iv)

    # delta-matched short leg: closest to -0.16 delta
    short_K = min(puts, key=lambda K: abs(abs(puts[K]['delta']) - 0.16))
    # width scaled to one expected move so structures are economically comparable
    em = spot * iv * math.sqrt(5 / 252)
    target_long = short_K - em
    longs = [K for K in puts if K < short_K]
    if not longs:
        return None
    long_K = min(longs, key=lambda K: abs(K - target_long))
    if long_K == short_K:
        return None

    s, l = puts[short_K], puts[long_K]
    credit_mid = (s['bid'] + s['ask']) / 2 - (l['bid'] + l['ask']) / 2
    credit_fill = s['bid'] - l['ask']              # conservative entry
    exit_fill = s['ask'] - l['bid']                # conservative exit
    roundtrip = exit_fill - credit_fill            # total spread cost, both legs, both ways
    width = short_K - long_K
    if credit_mid <= 0 or width <= 0:
        return None
    return dict(sym=sym, spot=spot, iv=iv, short_K=short_K, long_K=long_K, width=width,
                credit_mid=credit_mid, roundtrip=roundtrip,
                cost_frac=roundtrip / credit_mid,
                credit_pct_width=credit_mid / width,
                delta=abs(s['delta']))


for label, group in (('INDEX / COMMODITY ETFs', ETFS), ('SINGLE STOCKS', STOCKS)):
    print('=' * 94)
    print(label + '   —   16-delta put credit spread, width = 1 expected move, ' + EXP)
    print('=' * 94)
    print(f'{"sym":>6} {"spot":>8} {"ATM IV":>7} {"short":>7} {"long":>7} {"width":>6} '
          f'{"credit":>7} {"c/width":>8} {"rt cost":>8} {"cost/credit":>12} {"gate":>7}')
    rows = []
    for sym in group:
        r = analyse(sym)
        if not r:
            print(f'{sym:>6}   (no comparable structure)')
            continue
        gate = 'PASS' if r['cost_frac'] < 0.25 else 'REJECT'
        rows.append(r)
        print(f'{r["sym"]:>6} {r["spot"]:>8.2f} {r["iv"]*100:>6.1f}% {r["short_K"]:>7.0f} '
              f'{r["long_K"]:>7.0f} {r["width"]:>6.0f} {r["credit_mid"]:>7.2f} '
              f'{r["credit_pct_width"]*100:>7.1f}% {r["roundtrip"]:>8.2f} '
              f'{r["cost_frac"]*100:>11.1f}% {gate:>7}')
    if rows:
        rows.sort(key=lambda r: r['cost_frac'])
        print(f'\n  best within class: ' +
              ', '.join(f'{r["sym"]} ({r["cost_frac"]*100:.0f}%)' for r in rows[:4]))
    print()

print('cost/credit = round-trip bid-ask cost as a share of the credit collected.')
print('The rulebook gate is 25%. Above that, spread cost eats the edge.')
print('NOTE: Friday-close quotes. Spreads widen into the close - rerun during Monday RTH.')

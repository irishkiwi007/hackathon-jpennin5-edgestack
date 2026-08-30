"""Two questions:
1. What does a documented option strategy actually produce over a 4-day window?
2. How many underlyings are tradeable on the free indicative feed (i.e. can we diversify)?
"""
import json, math, os, subprocess, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


# ---------- 1. reality check ----------
print('=' * 72)
print('WHAT A DOCUMENTED EDGE ACTUALLY PRODUCES OVER 4 TRADING DAYS')
print('=' * 72)
H = 4 / 252
print(f'{"strategy":<34} {"ann ret":>8} {"ann vol":>8} {"Sharpe":>7} | '
      f'{"4d mean":>8} {"4d sd":>8} {"P(+)":>6}')


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


for name, ret, vol in [
    ('CBOE PUT (PutWrite) 1986-2015', 0.101, 0.101),
    ('CBOE BXMD 30-delta buywrite', 0.1066, 0.1180),
    ('S&P 500 total return', 0.098, 0.153),
    ('0DTE short straddle (claimed hi)', 0.140, 0.100),
]:
    sharpe = ret / vol
    m = ret * H
    sd = vol * math.sqrt(H)
    print(f'{name:<34} {ret*100:>7.1f}% {vol*100:>7.1f}% {sharpe:>7.2f} | '
          f'{m*100:>7.2f}% {sd*100:>7.2f}% {norm_cdf(m/sd)*100:>5.1f}%')

print("""
On $100,000, the best of these has an expected 4-day P&L of about +$160
against a standard deviation of roughly $1,270.

To place in a P&L contest you need a result several standard deviations out.
That is not edge. That is leverage plus luck.
""")

print('Effect of splitting the same total risk across N independent bets:')
print(f'{"N bets":>7} {"sd of total":>13} {"P(finish +)":>12}')
base_sd = 0.0127
for n in (1, 2, 4, 8, 16, 32):
    sd = base_sd / math.sqrt(n)
    print(f'{n:>7} {sd*100:>12.2f}% {norm_cdf((0.0016)/sd)*100:>11.1f}%')
print('  (mean unchanged; only the spread narrows. More bets = more reliably')
print('   positive, and less likely to be spectacular. Those are in conflict.)')

# ---------- 2. tradeable universe ----------
print()
print('=' * 72)
print('TRADEABLE UNIVERSE ON THE FREE INDICATIVE FEED')
print('=' * 72)

CANDIDATES = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'GLD', 'TLT', 'EEM',
              'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'AMD']
EXP = '2026-09-04'

print(f'{"sym":>6} {"spot":>8} {"contracts":>10} {"ATM IV":>8} {"med spr%":>9} '
      f'{"med OI":>8} {"verdict":>10}')
rows = []
for sym in CANDIDATES:
    b = run(['data', 'bars', '--symbol', sym, '--timeframe', '1Day',
             '--start', '2026-08-25', '--end', '2026-08-29T00:00:00Z'])
    if not b or not b.get('bars'):
        print(f'{sym:>6}  no bars')
        continue
    spot = b['bars'][-1]['c']
    ch = run(['data', 'option', 'chain', '--underlying-symbol', sym, '--feed', 'indicative',
              '--expiration-date', EXP,
              '--strike-price-gte', str(round(spot * 0.97, 0)),
              '--strike-price-lte', str(round(spot * 1.03, 0)), '--limit', '200'])
    if not ch or not ch.get('snapshots'):
        print(f'{sym:>6} {spot:>8.2f}  no chain for {EXP}')
        continue
    snaps = ch['snapshots']
    spreads, ivs = [], []
    for k, v in snaps.items():
        q = v.get('latestQuote') or {}
        bp, ap = q.get('bp'), q.get('ap')
        iv = v.get('impliedVolatility')
        d = (v.get('greeks') or {}).get('delta')
        if bp and ap and ap > 0 and (bp + ap) > 0:
            spreads.append((ap - bp) / ((ap + bp) / 2))
        if iv and d and 0.35 < abs(d) < 0.65:
            ivs.append(iv)
    if not spreads:
        print(f'{sym:>6} {spot:>8.2f}  no two-sided quotes')
        continue
    spreads.sort()
    med_spr = spreads[len(spreads) // 2]
    atm_iv = sum(ivs) / len(ivs) if ivs else float('nan')

    oi = run(['option', 'contracts', '--underlying-symbols', sym, '--expiration-date', EXP,
              '--strike-price-gte', str(round(spot * 0.97, 0)),
              '--strike-price-lte', str(round(spot * 1.03, 0)), '--limit', '200'])
    ois = sorted(int(c.get('open_interest') or 0)
                 for c in (oi or {}).get('option_contracts', []))
    med_oi = ois[len(ois) // 2] if ois else 0

    ok = med_spr < 0.05 and med_oi >= 100
    verdict = 'TRADEABLE' if ok else ('marginal' if med_spr < 0.12 else 'reject')
    rows.append((sym, ok))
    print(f'{sym:>6} {spot:>8.2f} {len(snaps):>10} {atm_iv*100:>7.1f}% '
          f'{med_spr*100:>8.2f}% {med_oi:>8} {verdict:>10}')

good = [s for s, ok in rows if ok]
print(f'\ntradeable at <5% spread and OI>=100: {len(good)} -> {good}')

import json, math, subprocess, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
A = r'C:\Users\Lenovo\go\bin\alpaca.exe'
env = dict(os.environ)


def run(args):
    r = subprocess.run([A] + args + ['--quiet'], capture_output=True, text=True, env=env)
    return json.loads(r.stdout)


bars = run(['data', 'bars', '--symbol', 'SPY', '--timeframe', '1Day',
            '--start', '2026-05-01', '--end', '2026-08-29T00:00:00Z'])['bars']
print(f'daily bars: {len(bars)}  last close {bars[-1]["c"]} @ {bars[-1]["t"][:10]}')


def rv(bars, n):
    b = bars[-(n + 1):]
    o = [x['o'] for x in b]
    h = [x['h'] for x in b]
    lo = [x['l'] for x in b]
    c = [x['c'] for x in b]
    N = len(b) - 1

    # close-to-close
    r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    m = sum(r) / len(r)
    cc = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)

    # Parkinson
    pk = math.sqrt(sum(math.log(h[i] / lo[i]) ** 2 for i in range(1, len(b)))
                   / (4 * N * math.log(2))) * math.sqrt(252)

    # Rogers-Satchell
    rs_terms = [math.log(h[i] / c[i]) * math.log(h[i] / o[i])
                + math.log(lo[i] / c[i]) * math.log(lo[i] / o[i]) for i in range(1, len(b))]
    rs = math.sqrt(sum(rs_terms) / N) * math.sqrt(252)

    # Yang-Zhang
    ov = [math.log(o[i] / c[i - 1]) for i in range(1, len(b))]
    mo = sum(ov) / len(ov)
    v_ov = sum((x - mo) ** 2 for x in ov) / (N - 1)
    oc = [math.log(c[i] / o[i]) for i in range(1, len(b))]
    moc = sum(oc) / len(oc)
    v_oc = sum((x - moc) ** 2 for x in oc) / (N - 1)
    k = 0.34 / (1.34 + (N + 1) / (N - 1))
    yz = math.sqrt(v_ov + k * v_oc + (1 - k) * (sum(rs_terms) / N)) * math.sqrt(252)
    return cc, pk, rs, yz


print()
print(f'{"win":>5} {"close-close":>12} {"Parkinson":>11} {"Rog-Satch":>11} {"Yang-Zhang":>11}')
store = {}
for n in (10, 20, 30):
    cc, pk, rs, yz = rv(bars, n)
    store[n] = (cc, pk, rs, yz)
    print(f'{n:>5} {cc*100:>11.2f}% {pk*100:>10.2f}% {rs*100:>10.2f}% {yz*100:>10.2f}%')

rv_sell = max(store[10] + store[20])
rv_buy = min(store[10] + store[20])
print(f'\nRV for a SELLER (max of 10/20d estimators): {rv_sell*100:.2f}%')
print(f'RV for a BUYER  (min of 10/20d estimators): {rv_buy*100:.2f}%')

# ATM IV per expiry
spot = bars[-1]['c']
print(f'\nspot {spot}\n')
print(f'{"expiry":>12} {"ATM IV":>8} {"VRP ratio (vs sell-RV)":>24} {"verdict":>12}')
for exp in ('2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-30'):
    try:
        ch = run(['data', 'option', 'chain', '--underlying-symbol', 'SPY', '--feed', 'indicative',
                  '--expiration-date', exp,
                  '--strike-price-gte', str(int(spot - 3)), '--strike-price-lte', str(int(spot + 3)),
                  '--limit', '40'])
    except Exception:
        continue
    ivs = []
    for k, v in (ch.get('snapshots') or {}).items():
        iv = v.get('impliedVolatility')
        d = (v.get('greeks') or {}).get('delta')
        if iv and d and 0.35 < abs(d) < 0.65:
            ivs.append(iv)
    if not ivs:
        print(f'{exp:>12} {"n/a":>8}')
        continue
    iv = sum(ivs) / len(ivs)
    ratio = iv / rv_sell
    verdict = 'SELL' if ratio > 1.15 else ('BUY' if ratio < 0.95 else 'NO TRADE')
    print(f'{exp:>12} {iv*100:>7.2f}% {ratio:>23.3f}  {verdict:>12}')

print('\n\n=== SENSITIVITY: the verdict depends entirely on which RV estimator you pick ===')
labels = {0:'close-close', 1:'Parkinson', 2:'Rogers-Satchell', 3:'Yang-Zhang'}
ivs_by_exp = {'2026-08-31':0.0788,'2026-09-01':0.0886,'2026-09-02':0.0946,
              '2026-09-03':0.0984,'2026-09-04':0.1062,'2026-09-30':0.1182}
print(f'{"RV estimator":>22} {"RV":>7} | ' + ' '.join(f'{e[5:]:>7}' for e in ivs_by_exp))
for win in (10,20):
    for i in range(4):
        r = store[win][i]
        row = []
        for e,iv in ivs_by_exp.items():
            ratio = iv/r
            tag = 'S' if ratio>1.15 else ('B' if ratio<0.95 else '-')
            row.append(f'{ratio:>5.2f}{tag}')
        print(f'{labels[i]+" "+str(win)+"d":>22} {r*100:>6.2f}% | ' + ' '.join(row))
print('\n  S = sell premium (>1.15)   B = buy premium (<0.95)   - = no trade')

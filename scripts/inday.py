"""INTRADAY overshoot-and-reverse. Same mechanism, timescale that can fire several times a day.

The trap: intraday volume and volatility are U-shaped (heavy at the open and close, dead midday).
A flat trailing average flags EVERY open as capitulation. Both are normalised against the same
time-of-day across the sample, so 'heavy volume' means heavy FOR 10:15am.
"""
import os
import json, os, sys, io, math, time, urllib.request, datetime
from collections import defaultdict
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HDR = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}
ETFS = ['SPY', 'QQQ', 'SOXX', 'XLV', 'HYG', 'XLP', 'FDN', 'IWM']
START, END = '2024-06-01', '2026-08-27'
CACHE = 'inday_bars.json'


def q(u, tries=4):
    for _ in range(tries):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=90))
        except Exception as e:
            time.sleep(1.2)
    return None


bars = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for s in ETFS:
    if s in bars:
        continue
    out, tok = [], None
    while True:
        u = ('https://data.alpaca.markets/v2/stocks/{}/bars?timeframe=5Min&feed=sip'
             '&start={}&end={}&limit=10000&adjustment=all').format(s, START, END)
        if tok:
            u += '&page_token=' + tok
        d = q(u)
        if not d:
            break
        out += d.get('bars') or []
        tok = d.get('next_page_token')
        if not tok:
            break
    bars[s] = [{'t': b['t'], 'o': b['o'], 'h': b['h'], 'l': b['l'], 'c': b['c'], 'v': b['v']}
               for b in out]
    json.dump(bars, open(CACHE, 'w'))
    print('pulled {:<6} {} bars'.format(s, len(bars[s])))

print('\nbars: ' + '  '.join('{}={}'.format(s, len(bars.get(s, []))) for s in ETFS))
json.dump(bars, open(CACHE, 'w'))

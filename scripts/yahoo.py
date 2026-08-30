"""Can Yahoo Finance replace the free-tier SIP feed for same-day data?

The engine's fetcher.rs uses Yahoo (crumb + cookie, no API key). If Yahoo serves today's
completed daily bar with CONSOLIDATED volume, the agent can compute the signal from today's
close and enter at today's close - recovering the full +1.365% instead of the +1.205% that
next-open entry gives, and rescuing the SMALL tier (+0.721% vs -0.223%).

The test that matters is not "does it return data" but "does its volume match SIP". IEX volume
is ~3% of consolidated and would wreck the volume ratio; Yahoo must not have the same problem.
"""
import os
import json
import sys
import io
import urllib.request
import urllib.error
import http.cookiejar
import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [('User-Agent', UA)]


def get(url, referer=None):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    if referer:
        req.add_header('Referer', referer)
    with opener.open(req, timeout=45) as r:
        return r.read().decode('utf-8', errors='replace')


def crumb():
    try:
        get('https://fc.yahoo.com')
    except Exception:
        pass                      # seeds the consent cookie; a non-200 is fine
    return get('https://query1.finance.yahoo.com/v1/test/getcrumb',
               referer='https://finance.yahoo.com/').strip()


def chart(sym, cr, days=30):
    end = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    start = end - days * 86400
    url = ('https://query1.finance.yahoo.com/v8/finance/chart/{}'
           '?period1={}&period2={}&interval=1d&events=div%2Csplit&crumb={}'
           .format(sym, start, end, urllib.parse.quote(cr)))
    return json.loads(get(url, referer='https://finance.yahoo.com/'))


import urllib.parse  # noqa: E402

print('fetching Yahoo crumb...')
try:
    cr = crumb()
    print('  crumb: {}'.format(cr[:12] + '...' if cr else '(empty)'))
except Exception as exc:
    print('  FAILED: {}'.format(exc))
    raise SystemExit(1)

SYMS = ['SPY', 'QQQ', 'SOXX', 'XLV', 'HYG']
ALP = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
       'APCA-API-SECRET-KEY': os.environ['ALPACA_SECRET_KEY']}


def sip_bars(sym):
    u = ('https://data.alpaca.markets/v2/stocks/{}/bars?timeframe=1Day&feed=sip'
         '&start={}&limit=40&adjustment=all'.format(
             sym, (datetime.date.today() - datetime.timedelta(days=40)).isoformat()))
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=ALP), timeout=45))
    return d.get('bars') or []


print()
print('=' * 96)
print('YAHOO vs ALPACA SIP — same session, same numbers?')
print('=' * 96)
print('{:<7} {:<12} {:>11} {:>11} {:>9} {:>15} {:>15} {:>8}'.format(
    'sym', 'last date', 'Y close', 'SIP close', 'px diff', 'Y volume', 'SIP volume', 'vol %'))
ok_all = True
for s in SYMS:
    try:
        c = chart(s, cr)
        res = c['chart']['result'][0]
        ts = res['timestamp']
        q = res['indicators']['quote'][0]
        ydates = [datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat()
                  for t in ts]
        yclose = q['close']
        yvol = q['volume']
        sip = sip_bars(s)
        sipmap = {b['t'][:10]: b for b in sip}
        # compare on the most recent date Yahoo has that SIP also has
        common = [d for d in ydates if d in sipmap]
        if not common:
            print('{:<7} no overlapping session'.format(s))
            ok_all = False
            continue
        d = common[-1]
        i = ydates.index(d)
        yc, yv = yclose[i], yvol[i]
        sc, sv = sipmap[d]['c'], sipmap[d]['v']
        pxd = abs(yc - sc) / sc * 100 if sc else 0
        volpct = (yv / sv * 100) if sv else 0
        flag = '' if (pxd < 0.5 and 90 < volpct < 110) else '  <-- MISMATCH'
        if flag:
            ok_all = False
        print('{:<7} {:<12} {:>11.2f} {:>11.2f} {:>8.2f}% {:>15,} {:>15,} {:>7.1f}%{}'.format(
            s, d, yc, sc, pxd, int(yv), int(sv), volpct, flag))
    except Exception as exc:
        print('{:<7} ERROR {}'.format(s, str(exc)[:60]))
        ok_all = False

print()
print('=' * 96)
print('DOES YAHOO HAVE TODAY / THE LATEST SESSION THAT SIP WITHHOLDS?')
print('=' * 96)
try:
    c = chart('SPY', cr)
    res = c['chart']['result'][0]
    ydates = [datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat()
              for t in res['timestamp']]
    sip = sip_bars('SPY')
    sipdates = [b['t'][:10] for b in sip]
    print('  Yahoo latest session : {}'.format(ydates[-1]))
    print('  SIP   latest session : {}'.format(sipdates[-1] if sipdates else 'none'))
    extra = [d for d in ydates if d not in sipdates]
    print('  sessions Yahoo has that SIP does not: {}'.format(extra or 'none'))
except Exception as exc:
    print('  ERROR {}'.format(exc))

print()
print('VERDICT: {}'.format(
    'Yahoo matches SIP on price and consolidated volume - usable as the signal feed'
    if ok_all else 'Yahoo does NOT match SIP closely enough - see mismatches above'))

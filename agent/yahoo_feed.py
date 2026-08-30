"""Yahoo Finance price feed - the path to SAME-DAY entry.

Why this exists. Alpaca's free tier refuses any SIP range reaching today ("subscription does not
permit querying recent SIP data"), and the IEX feed it does allow carries only ~3% of
consolidated volume (SPY: 1.16M vs 36.8M), which would destroy the volume ratio the whole
strategy rests on. So on Alpaca alone the agent must trade the PRIOR session's signal at the
next open, which measures +1.205% instead of +1.365% and turns the SMALL tier negative.

Yahoo (the feed TrustyRustyEngine's fetcher.rs already uses) has neither problem. Verified
against Alpaca SIP on 2026-08-28:

    symbol   price diff   Yahoo volume / SIP volume
    SPY          0.00%              99.7%
    QQQ          0.00%              99.3%
    SOXX         0.00%              99.9%
    XLV          0.00%              99.3%
    HYG          0.00%             100.0%

True consolidated volume, no delay, no API key. `meta.regularMarketPrice` and
`meta.regularMarketVolume` update live during the session, so today's provisional bar can be
built at 15:45 and the signal traded at the close.

The one estimate: volume-so-far must be scaled to a full-day figure. Measured over 4,432
symbol-sessions of 5-minute bars, the median session has 89.4% of its volume done by 15:45
(p10 0.825, p90 0.934). `stretch` needs no such correction - it is a price ratio and the live
price is exact.
"""
from __future__ import annotations

import datetime
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{}"

# fraction of a session's volume completed by minute-of-day (ET), from 4,432 symbol-sessions
VOLUME_COMPLETION = {
    900: 0.772,   # 15:00
    915: 0.805,   # 15:15
    930: 0.843,   # 15:30
    945: 0.894,   # 15:45
    960: 1.000,   # 16:00
}

# Estimation error in the scaled volume (p10-p90 spans about +/-8%) can straddle a tier
# boundary. The tier below FULL loses money on this strategy, so the same-day path demands a
# margin: 1.9x instead of 1.8x. Costs a few marginal trades, prevents the losing tier leaking in.
SAME_DAY_FULL_FLOOR = 1.90


class FeedError(RuntimeError):
    pass


class YahooFeed:
    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        self._crumb: str | None = None

    def _get(self, url: str, referer: str | None = None) -> str:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        if referer:
            req.add_header("Referer", referer)
        with self._opener.open(req, timeout=45) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def crumb(self) -> str:
        if self._crumb:
            return self._crumb
        try:
            self._get("https://fc.yahoo.com")       # seeds the consent cookie
        except Exception:                            # noqa: BLE001 - non-200 is expected
            pass
        c = self._get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                      referer="https://finance.yahoo.com/").strip()
        if not c:
            raise FeedError("Yahoo returned an empty crumb")
        self._crumb = c
        return c

    def daily(self, symbol: str, days: int = 90) -> tuple[list[dict], dict]:
        """(bars, meta). Bars are completed sessions; meta carries the live values."""
        end = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        url = (CHART.format(urllib.parse.quote(symbol)) +
               "?period1={}&period2={}&interval=1d&crumb={}".format(
                   end - days * 86400, end, urllib.parse.quote(self.crumb())))
        try:
            payload = json.loads(self._get(url, referer="https://finance.yahoo.com/"))
        except (urllib.error.URLError, ValueError) as exc:
            raise FeedError(f"{symbol}: {exc}") from exc
        chart = (payload.get("chart") or {})
        if chart.get("error"):
            raise FeedError(f"{symbol}: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise FeedError(f"{symbol}: empty result")
        res = results[0]
        stamps = res.get("timestamp") or []
        quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes, volumes = quote.get("close") or [], quote.get("volume") or []
        bars = []
        for i, ts in enumerate(stamps):
            c = closes[i] if i < len(closes) else None
            v = volumes[i] if i < len(volumes) else None
            if c is None or v is None:
                continue
            d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date()
            bars.append({"date": d.isoformat(), "close": float(c), "volume": float(v)})
        return bars, res.get("meta") or {}


def completion_fraction(now_et: datetime.datetime) -> float:
    """Interpolated fraction of the session's volume expected to be done by now."""
    minute = now_et.hour * 60 + now_et.minute
    keys = sorted(VOLUME_COMPLETION)
    if minute <= keys[0]:
        return VOLUME_COMPLETION[keys[0]]
    if minute >= keys[-1]:
        return 1.0
    for lo, hi in zip(keys, keys[1:]):
        if lo <= minute <= hi:
            span = hi - lo
            w = (minute - lo) / span if span else 0.0
            return VOLUME_COMPLETION[lo] + w * (VOLUME_COMPLETION[hi] - VOLUME_COMPLETION[lo])
    return 1.0


def provisional_bar(meta: dict, now_et: datetime.datetime) -> dict | None:
    """Build today's in-progress bar from live meta, with volume scaled to a full-day estimate.

    Returns None when meta has no usable live values, which is the signal to fall back to the
    prior-session path rather than guess.
    """
    price = meta.get("regularMarketPrice")
    volume = meta.get("regularMarketVolume")
    ts = meta.get("regularMarketTime")
    if price is None or volume is None or not ts:
        return None
    frac = completion_fraction(now_et)
    if frac <= 0:
        return None
    est_volume = float(volume) / frac
    return {
        "date": now_et.date().isoformat(),
        "close": float(price),
        "volume": est_volume,
        "raw_volume": float(volume),
        "completion_fraction": round(frac, 3),
        "provisional": True,
    }

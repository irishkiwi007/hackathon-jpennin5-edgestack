"""Thin Alpaca client. Paper only, and it refuses to run against the live host.

Only the endpoints the strategy actually needs. Keys come from the environment - never
hard-coded, never logged.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DATA_HOST = "https://data.alpaca.markets"
PAPER_HOST = "https://paper-api.alpaca.markets"


class BrokerError(RuntimeError):
    pass


class Alpaca:
    """Brokerage layer. Routes through the Alpaca MCP Server when it is up (the hackathon's
    required integration), with direct REST as a reliability fallback — and records which
    path served every routed call so the journal can show the MCP pathway working."""

    def __init__(self, key: str | None = None, secret: str | None = None,
                 paper: bool = True) -> None:
        self.route_log: list[str] = []
        self._mcp = None
        try:
            import mcp_gateway
            if mcp_gateway.available():
                self._mcp = mcp_gateway.get_client()
                self.route_log.append("mcp: connected " + mcp_gateway.MCP_URL)
        except Exception as exc:                       # noqa: BLE001
            self.route_log.append(f"mcp: unavailable ({exc}); using REST")
        self.key = key or os.environ.get("ALPACA_API_KEY", "")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY", "")
        if not self.key or not self.secret:
            raise BrokerError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in environment")
        if not paper:
            raise BrokerError("this agent is paper-only by construction")
        self.trade_host = PAPER_HOST

    # ---- plumbing ------------------------------------------------------------------------
    def _req(self, url: str, method: str = "GET", body: dict | None = None,
             tries: int = 3) -> Any:
        headers = {"APCA-API-KEY-ID": self.key,
                   "APCA-API-SECRET-KEY": self.secret,
                   "Content-Type": "application/json"}
        data = json.dumps(body).encode() if body is not None else None
        last = None
        for attempt in range(tries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                last = f"HTTP {exc.code}: {detail}"
                if exc.code in (400, 401, 403, 404, 422):
                    raise BrokerError(f"{method} {url.split('?')[0]} -> {last}") from exc
            except Exception as exc:                       # noqa: BLE001
                last = str(exc)
            time.sleep(0.8 * (attempt + 1))
        raise BrokerError(f"{method} {url.split('?')[0]} failed after {tries}: {last}")

    # ---- MCP routing ---------------------------------------------------------------------
    @staticmethod
    def _unwrap(out):
        """MCP tool results wrap payloads as {"_alpaca_mcp_security":..., "data": {...}}."""
        if isinstance(out, dict) and "data" in out:
            return out["data"]
        return out

    def _mcp_submit(self, payload: dict) -> dict:
        if payload.get("order_class") == "mleg":
            args = {"qty": str(payload["qty"]), "type": payload.get("type", "limit"),
                    "time_in_force": payload.get("time_in_force", "day"),
                    "order_class": "mleg", "legs": payload["legs"]}
            if payload.get("limit_price") is not None:
                args["limit_price"] = str(payload["limit_price"])   # server wants strings
            return self._unwrap(self._mcp.call("place_option_order", args))
        args = {"symbol": payload["symbol"], "side": payload["side"],
                "type": payload.get("type", "market"),
                "time_in_force": payload.get("time_in_force", "day")}
        if payload.get("qty") is not None:
            args["qty"] = str(payload["qty"])
        if payload.get("notional") is not None:
            args["notional"] = str(payload["notional"])             # server wants strings
        if payload.get("limit_price") is not None:
            args["limit_price"] = str(payload["limit_price"])
        return self._unwrap(self._mcp.call("place_stock_order", args))

    # ---- account -------------------------------------------------------------------------
    def account(self) -> dict:
        if self._mcp is not None:
            try:
                out = self._unwrap(self._mcp.call("get_account_info"))
                if isinstance(out, dict) and out.get("account_number"):
                    self.route_log.append("account: via MCP")
                    return out
            except Exception as exc:                   # noqa: BLE001
                self.route_log.append(f"account: MCP failed ({exc}); REST fallback")
        else:
            self.route_log.append("account: via REST (no MCP)")
        return self._req(f"{self.trade_host}/v2/account")

    def positions(self) -> list[dict]:
        return self._req(f"{self.trade_host}/v2/positions") or []

    def clock(self) -> dict:
        return self._req(f"{self.trade_host}/v2/clock")

    def orders(self, status: str = "open") -> list[dict]:
        return self._req(f"{self.trade_host}/v2/orders?status={status}&limit=100") or []

    # ---- market data ---------------------------------------------------------------------
    def daily_bars(self, symbols: list[str], start: str, end: str | None = None,
                   feed: str = "sip") -> dict[str, list[dict]]:
        """Omit `end` deliberately. Free-tier SIP rejects any range reaching today
        (403 "subscription does not permit querying recent SIP data"), but with no `end` it
        happily returns everything through the last completed session. IEX would be allowed
        for today, but IEX volume is only ~3% of consolidated (SPY: 1.16M vs 36.8M), which
        would wreck the volume ratio the strategy depends on."""
        out: dict[str, list[dict]] = {s: [] for s in symbols}
        for i in range(0, len(symbols), 20):
            chunk = symbols[i:i + 20]
            token = None
            while True:
                q = {"symbols": ",".join(chunk), "timeframe": "1Day", "feed": feed,
                     "start": start, "limit": "10000", "adjustment": "all"}
                if end:
                    q["end"] = end
                if token:
                    q["page_token"] = token
                d = self._req(f"{DATA_HOST}/v2/stocks/bars?{urllib.parse.urlencode(q)}")
                for sym, rows in (d.get("bars") or {}).items():
                    out.setdefault(sym, []).extend(rows)
                token = d.get("next_page_token")
                if not token:
                    break
        return out

    def option_contracts(self, underlying: str, exp_gte: str, exp_lte: str,
                         kind: str = "put", limit: int = 500) -> list[dict]:
        q = {"underlying_symbols": underlying, "expiration_date_gte": exp_gte,
             "expiration_date_lte": exp_lte, "type": kind, "limit": str(limit),
             "status": "active"}
        d = self._req(f"{self.trade_host}/v2/options/contracts?{urllib.parse.urlencode(q)}")
        return d.get("option_contracts") or []

    def option_snapshots(self, occ_symbols: list[str]) -> dict[str, dict]:
        """Live bid/ask per contract. This is the clean pricing path - unlike historical
        option bars, snapshots carry an actual two-sided quote."""
        out: dict[str, dict] = {}
        for i in range(0, len(occ_symbols), 100):
            chunk = occ_symbols[i:i + 100]
            q = {"symbols": ",".join(chunk)}
            d = self._req(f"{DATA_HOST}/v1beta1/options/snapshots?"
                          f"{urllib.parse.urlencode(q)}")
            for sym, snap in (d.get("snapshots") or {}).items():
                quote = snap.get("latestQuote") or {}
                out[sym] = {"bid": float(quote.get("bp", 0) or 0),
                            "ask": float(quote.get("ap", 0) or 0),
                            "bid_size": quote.get("bs"), "ask_size": quote.get("as"),
                            "quote_time": quote.get("t")}
        return out

    # ---- trading -------------------------------------------------------------------------
    def submit_order(self, payload: dict) -> dict:
        if self._mcp is not None:
            try:
                out = self._mcp_submit(payload)
                if isinstance(out, dict) and out.get("id"):
                    self.route_log.append(
                        f"order {payload.get('symbol', 'mleg')}: via MCP")
                    return out
                raise BrokerError(f"MCP order returned no id: {str(out)[:200]}")
            except Exception as exc:                   # noqa: BLE001
                self.route_log.append(
                    f"order {payload.get('symbol', 'mleg')}: MCP failed ({exc}); REST fallback")
        return self._req(f"{self.trade_host}/v2/orders", method="POST", body=payload)

    def cancel_order(self, order_id: str) -> dict:
        return self._req(f"{self.trade_host}/v2/orders/{order_id}", method="DELETE")


def load_env(path: str = ".env") -> None:
    """Minimal .env loader so keys stay out of the source and out of the shell history."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

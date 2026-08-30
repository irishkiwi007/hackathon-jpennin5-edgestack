"""Equity core + sleeve — the validated edge stack, live.

Components (evidence in EDGE-PORTFOLIO.md and ENGINE-TRIAL.md):

  CORE   Long SPY OVERNIGHT ONLY: buy at the close (market-on-close), sell at the open.
         Overnight Sharpe 0.89 vs intraday 0.05 (7/8 ETFs, 8/9 eras).
         Gated by BOTH:
           - 12-month SPY trend up (fwd +1.011%/21d t=5.77 vs +0.113% t=0.17)
           - credit canary: HYG > its own 100d SMA (borrowed from the user's `canaries`
             strategy; passed both disjoint engine windows: Sharpe 0.80->0.98 train,
             0.65->1.02 valid, drawdown ~halved)
  SLEEVE Capitulation basket, 0.3x-of-equity batch, max 0.6x total, 3-session hold,
         across the 7 research ETFs. Entries and exits at the close (market-on-close),
         matching the validated close-entry convention (+1.42%/event, 67.6% win, t=4.27).

The options flow (bull put spreads via risk_gates) runs alongside and is NOT gated here —
equity positions are tracked separately and never count against the options risk budget.

Order mechanics: market-on-close ("cls") needs integer qty and must reach Alpaca before
~15:50 ET — the 15:45 entry pass fits. If a cls order is rejected (late, or unsupported
symbol), we fall back to an immediate market order, which fills within a minute of the
close anyway. Core exit is a plain market order at 09:31.
"""
from __future__ import annotations

import datetime
import json
import math
import os
from typing import Any

from broker import Alpaca, BrokerError

SLEEVE_UNIVERSE = ["SPY", "QQQ", "SOXX", "XLV", "XLP", "HYG", "FDN"]
CORE_SYMBOL = "SPY"
CORE_WEIGHT = 0.70          # engine-validated defaults (ENGINE-TRIAL.md)
SLEEVE_BATCH = 0.30
MAX_TOTAL_SLEEVE = 0.60
HOLD_SESSIONS = 3
TREND_LOOKBACK = 252
CREDIT_SMA = 100

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "journal", "equity_state.json")


# ---------------------------------------------------------------- state
def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"core": None, "sleeve": []}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"core": None, "sleeve": []}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


# ---------------------------------------------------------------- gate
def compute_gate(spy_closes: list, hyg_closes: list) -> tuple:
    """(open: bool, reason: str). Closes must END at the signal day (provisional included
    when in-session) — the same convention every backtest used."""
    if len(spy_closes) < TREND_LOOKBACK + 1:
        return False, f"insufficient SPY history ({len(spy_closes)}/{TREND_LOOKBACK + 1})"
    if len(hyg_closes) < CREDIT_SMA:
        return False, f"insufficient HYG history ({len(hyg_closes)}/{CREDIT_SMA})"
    trend = spy_closes[-1] / spy_closes[-1 - TREND_LOOKBACK] - 1.0 > 0.0
    sma = sum(hyg_closes[-CREDIT_SMA:]) / CREDIT_SMA
    credit = hyg_closes[-1] > sma
    reason = (f"trend {'UP' if trend else 'DOWN'} "
              f"(12m {100 * (spy_closes[-1] / spy_closes[-1 - TREND_LOOKBACK] - 1):+.1f}%) | "
              f"credit {'OK' if credit else 'DETERIORATING'} "
              f"(HYG {hyg_closes[-1]:.2f} vs SMA100 {sma:.2f})")
    return trend and credit, reason


# ---------------------------------------------------------------- orders
def _moc_or_market(api: Alpaca, symbol: str, qty: int, side: str) -> dict:
    """Market-on-close, falling back to an immediate market order if cls is rejected."""
    base = {"symbol": symbol, "qty": str(int(qty)), "side": side, "type": "market"}
    try:
        return api.submit_order({**base, "time_in_force": "cls"})
    except BrokerError:
        return api.submit_order({**base, "time_in_force": "day"})


def _sessions_between(a: str, b: datetime.date) -> int:
    cur = datetime.date.fromisoformat(a)
    n = 0
    while cur < b:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


# ---------------------------------------------------------------- passes
def equity_entry(api: Alpaca, equity: float, gate_open: bool, gate_reason: str,
                 sleeve_signals: list, prices: dict, today: datetime.date,
                 dry_run: bool) -> list:
    """15:45 pass: sleeve exits due today, new sleeve entries, core overnight entry.
    `sleeve_signals` = [(symbol, note)] already filtered to SLEEVE_UNIVERSE.
    `prices` = {symbol: last price} for qty computation."""
    actions: list = []
    state = load_state()

    # 1. sleeve exits: positions completing their 3rd session exit at TODAY's close
    keep = []
    for p in state["sleeve"]:
        held = _sessions_between(p["entry_date"], today)
        if held >= HOLD_SESSIONS:
            if dry_run:
                actions.append({"action": "would_close_sleeve",
                                "detail": f"{p['symbol']} x{p['qty']} after {held} sessions"})
            else:
                try:
                    res = _moc_or_market(api, p["symbol"], p["qty"], "sell")
                    actions.append({"action": "sleeve_exit",
                                    "detail": f"{p['symbol']} x{p['qty']} MOC "
                                              f"order {res.get('id', '?')[:8]}"})
                    continue
                except BrokerError as exc:
                    actions.append({"action": "sleeve_exit_failed",
                                    "detail": f"{p['symbol']}: {exc}"})
        keep.append(p)
    state["sleeve"] = keep

    # 2. new sleeve entries at today's close, equal split of the batch budget
    if sleeve_signals:
        current = sum(p["dollars"] for p in state["sleeve"])
        budget = max(0.0, min(SLEEVE_BATCH * equity, MAX_TOTAL_SLEEVE * equity - current))
        if budget > 0:
            per = budget / len(sleeve_signals)
            for sym, note in sleeve_signals:
                px = prices.get(sym, 0.0)
                qty = int(per / px) if px > 0 else 0
                if qty < 1:
                    actions.append({"action": "sleeve_skip",
                                    "detail": f"{sym}: budget ${per:,.0f} < 1 share"})
                    continue
                if dry_run:
                    actions.append({"action": "would_enter_sleeve",
                                    "detail": f"{sym} x{qty} (~${qty * px:,.0f}) — {note}"})
                    continue
                try:
                    res = _moc_or_market(api, sym, qty, "buy")
                    state["sleeve"].append({"symbol": sym, "qty": qty,
                                            "dollars": qty * px,
                                            "entry_date": today.isoformat()})
                    actions.append({"action": "sleeve_enter",
                                    "detail": f"{sym} x{qty} MOC — {note} "
                                              f"order {res.get('id', '?')[:8]}"})
                except BrokerError as exc:
                    actions.append({"action": "sleeve_enter_failed",
                                    "detail": f"{sym}: {exc}"})
        else:
            actions.append({"action": "sleeve_full",
                            "detail": f"sleeve at cap (${current:,.0f})"})

    # 3. core: overnight entry when the gate is open
    if gate_open and state["core"] is None:
        px = prices.get(CORE_SYMBOL, 0.0)
        qty = int(CORE_WEIGHT * equity / px) if px > 0 else 0
        if qty >= 1:
            if dry_run:
                actions.append({"action": "would_enter_core",
                                "detail": f"SPY x{qty} MOC overnight — {gate_reason}"})
            else:
                try:
                    res = _moc_or_market(api, CORE_SYMBOL, qty, "buy")
                    state["core"] = {"qty": qty, "entry_date": today.isoformat()}
                    actions.append({"action": "core_enter",
                                    "detail": f"SPY x{qty} MOC overnight — {gate_reason} "
                                              f"order {res.get('id', '?')[:8]}"})
                except BrokerError as exc:
                    actions.append({"action": "core_enter_failed", "detail": str(exc)})
    elif not gate_open:
        actions.append({"action": "core_gated", "detail": gate_reason})
        # a stranded core position (exit failed earlier) must not ride a closed gate
        if state["core"] is not None and not dry_run:
            try:
                _moc_or_market(api, CORE_SYMBOL, state["core"]["qty"], "sell")
                actions.append({"action": "core_force_exit",
                                "detail": "gate closed with core still held"})
                state["core"] = None
            except BrokerError as exc:
                actions.append({"action": "core_force_exit_failed", "detail": str(exc)})

    if not dry_run:
        save_state(state)
    return actions


def equity_exit(api: Alpaca, dry_run: bool) -> list:
    """09:31 pass: the core held overnight is sold at the open. Sleeve rides."""
    actions: list = []
    state = load_state()
    if state["core"] is not None:
        qty = state["core"]["qty"]
        if dry_run:
            actions.append({"action": "would_exit_core", "detail": f"SPY x{qty} at open"})
        else:
            try:
                res = api.submit_order({"symbol": CORE_SYMBOL, "qty": str(int(qty)),
                                        "side": "sell", "type": "market",
                                        "time_in_force": "day"})
                state["core"] = None
                save_state(state)
                actions.append({"action": "core_exit",
                                "detail": f"SPY x{qty} market open "
                                          f"order {res.get('id', '?')[:8]}"})
            except BrokerError as exc:
                actions.append({"action": "core_exit_failed", "detail": str(exc)})
    return actions

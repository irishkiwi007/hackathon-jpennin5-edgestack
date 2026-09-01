"""Turn a Signal into a concrete, priced, Alpaca-legal bull put spread.

Structure choice, and its evidence, from HERD-REVERSAL.md:

  The signal is LONG DELTA (the bounce) and occurs when implied volatility is ELEVATED
  (ATM call IV 0.652 on signal days vs 0.433 on calm days) and about to normalise. A bull put
  spread is long delta and SHORT vega, so it monetises both halves. The long-premium structures
  tested - outright call and call debit spread - are long vega and fight the second half; both
  measured almost exactly zero.

  Honest limit: the option-level edge is NOT statistically established. Alpaca serves no
  historical option quotes (404), only trades, so backtest entry/exit prices are asynchronous -
  put-call parity is violated in the data, which proves contamination. What IS established is
  the underlying move (+1.646%, t=5.42 over 33 years; +1.360% vs -0.187% control out-of-sample)
  and the bull put spread's relative result (+$221.7/contract vs control, t=3.03).
  Live pricing is clean: real-time snapshots return real bid/ask.

Width: the study used ATM/-5%. On a $100k account at 2% risk, a 5%-wide spread on SPY risks
$3,846/contract and cannot be traded at all. So width ADAPTS DOWN from the 5% target toward a
2% floor until one contract fits the tier-weighted cap. Narrowing only reduces risk; it never
widens beyond what was tested.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from risk_gates import Proposal, MAX_RISK_PER_TRADE_PCT
from signal_engine import Signal

TARGET_WIDTH_PCT = 0.05
MIN_WIDTH_PCT = 0.02
MIN_DTE = 8
MAX_DTE = 21


@dataclass(frozen=True)
class Contract:
    occ: str
    strike: float
    expiration: datetime.date
    kind: str            # "put" / "call"
    bid: float
    ask: float
    open_interest: int | None = None

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)


def pick_expiration(today: datetime.date,
                    available: Iterable[datetime.date]) -> datetime.date | None:
    """Nearest expiry inside the tested window. The study entered at >=8 DTE so that a 3-day
    hold never runs into expiry gamma."""
    ok = sorted(d for d in available if MIN_DTE <= (d - today).days <= MAX_DTE)
    return ok[0] if ok else None


def _nearest(strikes: Sequence[float], target: float) -> float | None:
    if not strikes:
        return None
    return min(strikes, key=lambda k: abs(k - target))


def build(signal: Signal,
          puts: Sequence[Contract],
          equity: float,
          today: datetime.date,
          conservative_fill: bool = False) -> tuple[Proposal | None, str]:
    """Return (proposal, explanation). proposal is None when no legal spread fits.

    PRICING. The limit is placed at MID, not at the worst fill. Measured on live chains, paying
    the full spread on both legs costs about $70/contract on a broad ETF list - against a gross
    edge of $37.8/contract, that alone is fatal. Quoting at mid and letting the order work is the
    difference between negative and positive expectancy.

    `friction` (half-spread on each leg) is computed and carried on the proposal so a gate can
    refuse trades where crossing would eat the credit, and so the journal shows the real cost.
    Set conservative_fill=True to price at the worst fill instead - useful for stress-testing,
    not for live quoting.
    """
    if not puts:
        return None, "no put contracts available"

    expiry = puts[0].expiration
    dte = (expiry - today).days
    by_strike = {c.strike: c for c in puts if c.bid > 0 and c.ask > 0 and c.ask >= c.bid}
    if len(by_strike) < 2:
        return None, "fewer than two quotable put strikes"
    strikes = sorted(by_strike)

    spot = signal.spot
    short_strike = _nearest(strikes, spot)
    if short_strike is None:
        return None, "no ATM strike"

    cap = equity * MAX_RISK_PER_TRADE_PCT * signal.size_weight
    attempts: list[str] = []

    # widest first (matches the study), narrowing only if risk does not fit
    width_pcts = []
    w = TARGET_WIDTH_PCT
    while w >= MIN_WIDTH_PCT - 1e-9:
        width_pcts.append(round(w, 4))
        w -= 0.005

    for wpct in width_pcts:
        target_long = spot * (1.0 - wpct)
        candidates = [k for k in strikes if k < short_strike]
        if not candidates:
            continue
        long_strike = _nearest(candidates, target_long)
        if long_strike is None or long_strike >= short_strike:
            continue

        short_c, long_c = by_strike[short_strike], by_strike[long_strike]
        # half-spread on each leg = what crossing once would cost
        friction = 0.5 * ((short_c.ask - short_c.bid) + (long_c.ask - long_c.bid))
        worst = short_c.bid - long_c.ask
        if conservative_fill:
            credit = worst
        else:
            credit = short_c.mid - long_c.mid
        width = short_strike - long_strike
        if credit <= 0:
            attempts.append(f"{wpct:.1%}: credit {credit:.2f} <= 0")
            continue

        risk_per_contract = (width - credit) * 100.0
        if risk_per_contract <= 0:
            attempts.append(f"{wpct:.1%}: non-positive risk")
            continue
        contracts = int(cap // risk_per_contract)
        if contracts < 1:
            attempts.append(
                f"{wpct:.1%}: ${risk_per_contract:,.0f}/contract > cap ${cap:,.0f}")
            continue

        note = (f"width {width:.2f} ({width / spot:.1%} of spot), "
                f"mid credit {credit:.2f} ({credit / width:.0%} of width), "
                f"friction ${friction * 100:.0f}/contract one-way "
                f"(worst fill would be {worst:.2f}), "
                f"{contracts} contract(s), risk ${risk_per_contract * contracts:,.0f} "
                f"vs tier-{signal.tier} cap ${cap:,.0f}, {dte} DTE")
        if wpct < TARGET_WIDTH_PCT:
            note += f" [narrowed from {TARGET_WIDTH_PCT:.0%} target to fit risk budget]"

        return Proposal(
            symbol=signal.symbol,
            structure="bull_put_spread",
            short_leg=short_c.occ,
            long_leg=long_c.occ,
            short_strike=short_strike,
            long_strike=long_strike,
            expiration=expiry,
            contracts=contracts,
            limit_credit=round(credit, 2),
            tier=signal.tier,
            size_weight=signal.size_weight,
            stretch=signal.stretch,
            volx=signal.volx,
            friction=round(friction, 4),
            tradeable=signal.tradeable,
        ), note

    return None, ("no width from {:.0%} down to {:.0%} fits the risk budget: {}"
                  .format(TARGET_WIDTH_PCT, MIN_WIDTH_PCT, "; ".join(attempts) or "none tried"))


def to_mleg_order(p: Proposal, tif: str = "day") -> dict:
    """Alpaca multi-leg order payload.

    Constraints honoured: <=4 legs; every short covered inside the same order (the long put is
    the cover); ratio_qty GCD is 1; limit order (MLeg supports limit only); single expiration.
    A credit spread is submitted as a NET CREDIT limit, so side is 'sell' on the package.
    """
    return {
        "order_class": "mleg",
        "qty": str(p.contracts),
        "type": "limit",
        "limit_price": f"{p.limit_credit:.2f}",
        "time_in_force": tif,
        "legs": [
            {"symbol": p.short_leg, "ratio_qty": "1", "side": "sell",
             "position_intent": "sell_to_open"},
            {"symbol": p.long_leg, "ratio_qty": "1", "side": "buy",
             "position_intent": "buy_to_open"},
        ],
    }


def to_closing_order(p: Proposal, limit_debit: float, tif: str = "day") -> dict:
    """Close the spread: buy back the short, sell the long, as a net debit."""
    return {
        "order_class": "mleg",
        "qty": str(p.contracts),
        "type": "limit",
        "limit_price": f"{limit_debit:.2f}",
        "time_in_force": tif,
        "legs": [
            {"symbol": p.short_leg, "ratio_qty": "1", "side": "buy",
             "position_intent": "buy_to_close"},
            {"symbol": p.long_leg, "ratio_qty": "1", "side": "sell",
             "position_intent": "sell_to_close"},
        ],
    }

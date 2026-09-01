"""Deterministic risk gates. The LLM proposes; this disposes.

Every gate is a pure function of (proposal, account state, market data) -> pass/fail + reason.
No model output can bypass one, and no gate consults a model. Each returns a human-readable
reason so the decision journal can show exactly why a trade did or did not happen.

Gate order matters: cheap structural checks first, market-data checks last, so a rejected
proposal costs as few API calls as possible.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable

# ---- risk budget -------------------------------------------------------------------------
MAX_CONCURRENT_POSITIONS = 4
MAX_RISK_PER_TRADE_PCT = 0.02        # 2% of equity at risk on a full-size trade
MAX_TOTAL_RISK_PCT = 0.06            # 6% of equity at risk across all open positions
MIN_CREDIT_TO_WIDTH = 0.12           # a credit spread paying <12% of its width is not worth it
MAX_FRICTION_TO_EDGE = 0.40          # round-trip crossing cost vs the structure's gross edge
MAX_BID_ASK_PCT = 0.25               # per-leg spread as a fraction of the leg mid
MIN_DTE = 8                          # research entered at >=8 days; 3-day hold must not near expiry
MAX_DTE = 21
MIN_OPEN_INTEREST = 100
MIN_EQUITY = 5_000.0

# Macro blackouts: do not open into a scheduled print. Times are ET.
MACRO_BLACKOUTS = {
    datetime.date(2026, 9, 1): "JOLTS 10:00 ET",
    datetime.date(2026, 9, 4): "Non-farm payrolls 08:30 ET",
}


@dataclass
class GateResult:
    name: str
    passed: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Proposal:
    """A concrete, fully specified trade. No free text, no ambiguity."""
    symbol: str
    structure: str                 # "bull_put_spread"
    short_leg: str                 # OCC symbol
    long_leg: str                  # OCC symbol
    short_strike: float
    long_strike: float
    expiration: datetime.date
    contracts: int
    limit_credit: float            # per-share credit, so x100 per contract
    tier: str
    size_weight: float
    stretch: float
    volx: float
    friction: float = 0.0          # half-spread per leg, summed; cost of crossing once
    # Carried from the signal so a retired tier is refused at the gate rather
    # than silently sized to zero. Defaults True: exit-management proposals are
    # rebuilt from the journal for trades that were already opened.
    tradeable: bool = True

    @property
    def round_trip_friction(self) -> float:
        return self.friction * 200.0 * self.contracts

    @property
    def width(self) -> float:
        return abs(self.short_strike - self.long_strike)

    @property
    def max_loss(self) -> float:
        return (self.width - self.limit_credit) * 100.0 * self.contracts

    @property
    def max_gain(self) -> float:
        return self.limit_credit * 100.0 * self.contracts


@dataclass
class AccountState:
    equity: float
    buying_power: float
    open_positions: list[dict]      # each: {"symbol","underlying","max_loss"}
    today: datetime.date
    regime_calm: bool = True        # macro overlay; see regime.py
    regime_reason: str = "regime not evaluated"


# ---- individual gates --------------------------------------------------------------------

def gate_equity(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    ok = acct.equity >= MIN_EQUITY
    return GateResult("equity_floor", ok,
                      f"equity ${acct.equity:,.0f} "
                      f"{'>=' if ok else '<'} floor ${MIN_EQUITY:,.0f}")


def gate_position_count(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    n = len(acct.open_positions)
    ok = n < MAX_CONCURRENT_POSITIONS
    return GateResult("position_count", ok,
                      f"{n} open, cap {MAX_CONCURRENT_POSITIONS}")


def gate_duplicate_underlying(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    dupes = [q for q in acct.open_positions if q.get("underlying") == p.symbol]
    ok = not dupes
    return GateResult("duplicate_underlying", ok,
                      f"no open position in {p.symbol}" if ok
                      else f"already holding {p.symbol}; signals cluster, do not double up")


def gate_structure(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    """Alpaca MLeg rules: <=4 legs, every short covered inside the same order."""
    problems = []
    if p.structure != "bull_put_spread":
        problems.append(f"unsupported structure {p.structure!r}")
    if p.short_strike <= p.long_strike:
        problems.append("bull put spread requires short strike above long strike")
    if p.contracts < 1:
        problems.append("contracts must be >= 1")
    if p.limit_credit <= 0:
        problems.append("credit must be positive")
    ok = not problems
    return GateResult("structure_valid", ok,
                      "legs valid and short leg is covered" if ok else "; ".join(problems))


def gate_tier_tradeable(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    """Two different tiers are refused here, for two different measured reasons.

    SMALL (1.4-1.8x) measures +0.721% entering at the signal-day close but -0.223%
    entering at the next open, which is the only entry free-tier data allows.
    MEDIUM (>=2.5x) was retired 2026-09-01: its per-event t of 3.5-4.0 assumed
    independent events, but its 27 signal days cluster in 2015/2018/2020 and the
    clustered statistic is t~0.90-1.12.

    Both are detected and refused here rather than dropped silently, so the journal
    shows the reasoning instead of an unexplained absence."""
    ok = p.tradeable and p.size_weight > 0.0
    if ok:
        why = f"tier {p.tier} tradeable on next-open entry"
    elif not p.tradeable:
        why = (f"tier {p.tier} retired by clustered-t audit "
               f"(t~1.0 once the panic days are clustered, not 3.5); refused")
    else:
        why = (f"tier {p.tier} inverts on delayed entry "
               f"(-0.223% vs +0.721% at the close); refused")
    return GateResult("tier_tradeable", ok, why)


def gate_expiry(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    dte = (p.expiration - acct.today).days
    ok = MIN_DTE <= dte <= MAX_DTE
    return GateResult("expiry_window", ok,
                      f"{dte} DTE, need {MIN_DTE}-{MAX_DTE} "
                      f"(3-day hold must not approach expiry)",
                      {"dte": dte})


def gate_macro_blackout(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    event = MACRO_BLACKOUTS.get(acct.today)
    ok = event is None
    return GateResult("macro_blackout", ok,
                      "no scheduled macro print today" if ok
                      else f"blackout: {event}")


def gate_credit_quality(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    if p.width <= 0:
        return GateResult("credit_quality", False, "zero width")
    ratio = p.limit_credit / p.width
    ok = ratio >= MIN_CREDIT_TO_WIDTH
    return GateResult("credit_quality", ok,
                      f"credit {ratio:.1%} of width, need >={MIN_CREDIT_TO_WIDTH:.0%}",
                      {"credit_to_width": round(ratio, 4)})


def gate_macro_regime(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    """Capitulation only reverts when the selling is emotional, not when macro risk is being
    repriced. Measured on 4,359 out-of-sample single-name events:

        calm bonds      +1.553%   win 63.3%
        stressed bonds  +0.066%   win 55.7%     t(diff) = 6.58

    In a stressed regime the edge is not merely smaller - it is absent, and the lowest volume
    tier is significantly negative. So this is a hard refusal, not a size reduction.
    """
    return GateResult("macro_regime", acct.regime_calm, acct.regime_reason)


def gate_friction(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    """Refuse trades the bid/ask would eat.

    Measured on live chains: friction is concentrated, not uniform. IWM costs $2/contract to
    cross and SOXX costs $105 - a 50x range on the same structure. The broad-ETF average of
    $70/contract round trip exceeds the $37.8/contract gross edge outright, so this gate, not
    the universe list, is what actually keeps the strategy solvent.
    """
    gross = 37.8 * p.contracts          # measured mean for this structure, per contract
    rt = p.round_trip_friction
    if gross <= 0:
        return GateResult("friction", False, "no gross edge estimate")
    ratio = rt / gross
    ok = ratio <= MAX_FRICTION_TO_EDGE
    return GateResult("friction", ok,
                      f"round-trip crossing ${rt:,.0f} vs gross edge ${gross:,.0f} "
                      f"= {ratio:.0%}, cap {MAX_FRICTION_TO_EDGE:.0%}",
                      {"round_trip": rt, "ratio": round(ratio, 3)})


def gate_trade_risk(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    cap = acct.equity * MAX_RISK_PER_TRADE_PCT * p.size_weight
    ok = p.max_loss <= cap
    return GateResult("per_trade_risk", ok,
                      f"max loss ${p.max_loss:,.0f} vs tier-{p.tier} cap ${cap:,.0f} "
                      f"({MAX_RISK_PER_TRADE_PCT:.0%} x weight {p.size_weight})",
                      {"max_loss": p.max_loss, "cap": cap})


def gate_portfolio_risk(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    existing = sum(float(q.get("max_loss", 0.0)) for q in acct.open_positions)
    total = existing + p.max_loss
    cap = acct.equity * MAX_TOTAL_RISK_PCT
    ok = total <= cap
    return GateResult("portfolio_risk", ok,
                      f"total risk ${total:,.0f} vs cap ${cap:,.0f} "
                      f"({MAX_TOTAL_RISK_PCT:.0%} of equity)",
                      {"total_risk": total, "cap": cap})


def gate_buying_power(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    ok = p.max_loss <= acct.buying_power
    return GateResult("buying_power", ok,
                      f"requires ${p.max_loss:,.0f}, available ${acct.buying_power:,.0f}")


def gate_liquidity(p: Proposal, acct: AccountState, mkt: dict) -> GateResult:
    """Both legs must be quotable and tight. mkt: {occ: {"bid","ask","open_interest"}}"""
    problems = []
    for leg in (p.short_leg, p.long_leg):
        qd = mkt.get(leg)
        if not qd:
            problems.append(f"{leg}: no quote")
            continue
        bid, ask = float(qd.get("bid", 0)), float(qd.get("ask", 0))
        if bid <= 0 or ask <= 0 or ask < bid:
            problems.append(f"{leg}: invalid quote {bid}/{ask}")
            continue
        mid = 0.5 * (bid + ask)
        spread_pct = (ask - bid) / mid if mid > 0 else 1.0
        if spread_pct > MAX_BID_ASK_PCT:
            problems.append(f"{leg}: spread {spread_pct:.0%} > {MAX_BID_ASK_PCT:.0%}")
        oi = qd.get("open_interest")
        if oi is not None and int(oi) < MIN_OPEN_INTEREST:
            problems.append(f"{leg}: open interest {oi} < {MIN_OPEN_INTEREST}")
    ok = not problems
    return GateResult("liquidity", ok,
                      "both legs quotable and tight" if ok else "; ".join(problems))


GATES: tuple[Callable[[Proposal, AccountState, dict], GateResult], ...] = (
    gate_equity,
    gate_structure,
    gate_tier_tradeable,
    gate_position_count,
    gate_duplicate_underlying,
    gate_expiry,
    gate_macro_blackout,
    gate_macro_regime,
    gate_credit_quality,
    gate_friction,
    gate_trade_risk,
    gate_portfolio_risk,
    gate_buying_power,
    gate_liquidity,
)


def evaluate_all(p: Proposal, acct: AccountState, mkt: dict) -> tuple[bool, list[GateResult]]:
    """Run every gate. Returns (approved, results). All gates run even after a failure so the
    journal shows the complete picture rather than stopping at the first objection."""
    results = [g(p, acct, mkt) for g in GATES]
    return all(r.passed for r in results), results


def size_for_tier(equity: float, size_weight: float, width: float,
                  credit: float) -> int:
    """Largest whole contract count whose max loss fits the tier-weighted per-trade cap."""
    risk_per_contract = (width - credit) * 100.0
    if risk_per_contract <= 0:
        return 0
    cap = equity * MAX_RISK_PER_TRADE_PCT * size_weight
    return max(0, int(cap // risk_per_contract))

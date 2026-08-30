"""Capitulation-reversal signal engine.

Pure and deterministic: given daily bars, it returns signals. No LLM, no network, no side
effects, so it can be unit-tested against the historical record that produced it.

The rule, from HERD-REVERSAL.md (7 ETFs, 1993-2026, n=135, t=5.42, win 68.1%, robust to
dropping any single era):

    stretch = log(C[t] / C[t-5]) / (rv20 * sqrt(5))      rv20 = sd of last 20 daily log returns
    volx    = V[t] / mean(V[t-19 .. t])

    FIRE LONG when stretch < -2.5 and volx >= 1.4, sized by the volume cell.

Volume cells are DISJOINT. Measured separately over 33 years, entering at the signal-day close:

    1.4 - 1.8x  -> +0.721%  win 64.4%  t=2.67   SMALL
    1.8 - 2.5x  -> +1.897%  win 70.1%  t=4.32   FULL     <- the peak
    > 2.5x      -> +1.312%  win 65.5%  t=3.96   MEDIUM

The fall-off above 2.5x is the mechanism's own boundary condition: extreme volume means real
information actually arrived, so there is less to revert. Do not "improve" the rule by removing
that ceiling - it is load-bearing.

Those are the numbers this engine's tier boundaries reproduce exactly (test_signal_engine.py).
The TIERS table below carries the NEXT-OPEN numbers instead, because that is the entry the free
data tier actually permits - and SMALL does not survive that delay. See the note on TIERS.

Hold 3 sessions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Sequence

LOOKBACK_RETURN = 5      # sessions in the stretch numerator
VOL_WINDOW = 20          # sessions for realized volatility and average volume
HOLD_SESSIONS = 3        # from the next open: 3 sessions best on mean, 2 best on t
MIN_BARS = VOL_WINDOW + LOOKBACK_RETURN + 1

STRETCH_TRIGGER = -2.5

# (label, vol_lo, vol_hi, size_weight, win_rate, mean_pct, t_stat, tradeable)
#
# TWO TABLES, because the achievable ENTRY depends on which data feed is working.
#
# SAME_DAY - Yahoo serves today's live price and consolidated volume, so the signal is computed
# at ~15:45 and traded at today's close. These are the study's close-entry numbers.
# The volume floors are nudged up from the measured boundaries because today's volume is an
# ESTIMATE (volume-so-far / 0.894), carrying roughly +/-8% error; the nudge keeps the flat
# 1.0-1.4x cell (+0.184%, t=0.21) from leaking into a tradeable tier.
#
# NEXT_OPEN - Yahoo unavailable, so Alpaca's free SIP gives only the prior completed session and
# entry slips to the next open. Measured cost over 33 years (scripts/delay.py):
#
#     entry                 mean     win      t
#     signal-day close    +1.365%   67.0%   6.21
#     NEXT OPEN           +1.205%   68.0%   4.14
#     next close          +0.606%   61.9%   2.24
#
# The delay is nearly free in aggregate but NOT uniform: SMALL inverts from +0.721% to -0.223%,
# while FULL and MEDIUM improve. So SMALL is refused on this path - detected and journalled,
# not silently dropped.
TIER_TABLES = {
    "same_day": (
        ("SMALL",  1.5, 1.8, 0.35, 0.644, 0.721, 2.67, True),
        ("FULL",   1.8, 2.5, 1.00, 0.701, 1.897, 4.32, True),
        ("MEDIUM", 2.5, float("inf"), 0.60, 0.655, 1.312, 3.96, True),
    ),
    "next_open": (
        ("SMALL",  1.4, 1.8, 0.00, 0.000, -0.223, 0.00, False),
        ("FULL",   1.8, 2.5, 1.00, 0.687,  2.019, 4.14, True),
        ("MEDIUM", 2.5, float("inf"), 0.60, 0.672, 1.578, 3.50, True),
    ),
}
DEFAULT_MODE = "next_open"          # the safe path; same_day is opt-in when the feed proves out
TIERS = TIER_TABLES[DEFAULT_MODE]   # back-compat for the verification test

# Bonds showed no mechanism (+0.012%, t=0.11, win 45.7%) - excluded by name, not by accident.
EXCLUDED = frozenset({"TLT", "IEF", "SHY", "AGG", "BND", "TIP", "LQD"})


@dataclass(frozen=True)
class Bar:
    date: str
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    date: str
    stretch: float
    volx: float
    tier: str
    size_weight: float
    spot: float
    hold_sessions: int
    hist_win_rate: float
    hist_mean_pct: float
    hist_t: float
    tradeable: bool
    mode: str

    def as_dict(self) -> dict:
        return asdict(self)


def _log_returns(closes: Sequence[float]) -> list[float]:
    out = []
    for prev, cur in zip(closes, closes[1:]):
        if prev <= 0 or cur <= 0:
            raise ValueError("non-positive close encountered")
        out.append(math.log(cur / prev))
    return out


def _stdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))


def compute_metrics(bars: Sequence[Bar]) -> tuple[float, float] | None:
    """(stretch, volx) as of the LAST bar, or None if there is not enough clean history."""
    if len(bars) < MIN_BARS:
        return None
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    if any(c <= 0 for c in closes[-MIN_BARS:]):
        return None

    rets = _log_returns(closes[-(VOL_WINDOW + 1):])
    rv = _stdev(rets)
    if rv <= 0:
        return None

    window = closes[-(LOOKBACK_RETURN + 1):]
    stretch = math.log(window[-1] / window[0]) / (rv * math.sqrt(LOOKBACK_RETURN))

    recent_vol = volumes[-VOL_WINDOW:]
    avg_vol = sum(recent_vol) / len(recent_vol)
    if avg_vol <= 0:
        return None
    volx = volumes[-1] / avg_vol
    return stretch, volx


def classify(stretch: float, volx: float, mode: str = DEFAULT_MODE):
    """Return the matching tier tuple, or None for no trade."""
    if stretch >= STRETCH_TRIGGER:
        return None
    for tier in TIER_TABLES[mode]:
        _, lo, hi, _, _, _, _, _ = tier
        if lo <= volx < hi:
            return tier
    return None       # volx < 1.4: measured t=0.21 and 47-49% win. No flush, no trade.


def evaluate(symbol: str, bars: Sequence[Bar],
             mode: str = DEFAULT_MODE) -> Signal | None:
    """Evaluate one symbol as of its last bar. None means no trade."""
    if symbol.upper() in EXCLUDED:
        return None
    metrics = compute_metrics(bars)
    if metrics is None:
        return None
    stretch, volx = metrics
    tier = classify(stretch, volx, mode)
    if tier is None:
        return None
    label, _, _, weight, win, mean_pct, t_stat, tradeable = tier
    return Signal(
        symbol=symbol.upper(),
        date=bars[-1].date,
        stretch=round(stretch, 4),
        volx=round(volx, 4),
        tier=label,
        size_weight=weight,
        spot=bars[-1].close,
        hold_sessions=HOLD_SESSIONS,
        hist_win_rate=win,
        hist_mean_pct=mean_pct,
        hist_t=t_stat,
        tradeable=tradeable,
        mode=mode,
    )


def scan(universe: dict[str, Sequence[Bar]],
         mode: str = DEFAULT_MODE) -> list[Signal]:
    """Evaluate a whole universe; strongest (most stretched) first."""
    out = []
    for symbol, bars in universe.items():
        try:
            sig = evaluate(symbol, bars, mode)
        except (ValueError, ZeroDivisionError):
            continue
        if sig is not None:
            out.append(sig)
    out.sort(key=lambda s: s.stretch)
    return out


def near_misses(universe: dict[str, Sequence[Bar]], limit: int = 10,
                mode: str = DEFAULT_MODE) -> list[dict]:
    """What is closest to firing. Feeds the decision journal on no-trade days, which is most
    days - a journal that only records trades cannot show that the gates were doing anything."""
    rows = []
    for symbol, bars in universe.items():
        if symbol.upper() in EXCLUDED:
            continue
        try:
            metrics = compute_metrics(bars)
        except (ValueError, ZeroDivisionError):
            continue
        if metrics is None:
            continue
        stretch, volx = metrics
        blockers = []
        if stretch >= STRETCH_TRIGGER:
            blockers.append(f"stretch {stretch:+.2f} > {STRETCH_TRIGGER}")
        floor = TIER_TABLES[mode][0][1]
        if volx < floor:
            blockers.append(f"volume {volx:.2f}x < {floor}x (no capitulation)")
        rows.append({
            "symbol": symbol.upper(),
            "stretch": stretch,
            "volx": volx,
            "would_fire": not blockers,
            "blocked_by": blockers,
        })
    rows.sort(key=lambda r: r["stretch"])
    return rows[:limit]

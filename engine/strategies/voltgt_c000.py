"""
STRATEGY: voltgt_c000 - volatility-targeted SPY exposure (from scratch).

Thesis: equity volatility is persistent and is negatively related to
subsequent risk-adjusted returns, so a book that holds LESS of the index
when trailing realized vol is high and more when it is low should keep most
of the index's upside while cutting the left tail. That is what Sortino
rewards and what the 2pp drawdown constraint asks for.

One symbol, one rule, no cross-asset gates: if this loses to buy-and-hold it
is a clean finding, not a tangle of confounded rules.

Cadence: the target is recomputed every rebalance_every sessions and acted
on only when it differs from the live weight by more than deadband, so
turnover stays low enough to survive 2x/5x cost stress.

Null twin: with null_seed != 0 the vol input is discarded and the weight is
drawn from a seeded LCG over the same range on the same cadence - same trade
frequency, zero market information.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


@dataclass
class VoltgtC000Config(StrategyConfig):
    vol_lb: int = 20
    target_vol: float = 0.13
    max_w: float = 0.98
    min_w: float = 0.20
    rebalance_every: int = 5
    deadband: float = 0.05
    null_seed: int = 0
    consecutive_bad_bars_threshold: int = 3


class VoltgtC000Strategy(TrustyStrategy):
    def __init__(self, config: VoltgtC000Config) -> None:
        super().__init__(config)
        self._closes: List[float] = []
        self._bars = 0
        self._weight = 0.0

    def name(self) -> str:
        return "voltgt_c000"

    def universe(self) -> List[str]:
        return ["SPY"]

    def max_lookback_period(self) -> int:
        return int(self._config.vol_lb) + 5

    def _realized_vol(self) -> float:
        """Annualized stdev of the last vol_lb daily returns, or -1 if short."""
        lb = int(self._config.vol_lb)
        px = self._closes[-(lb + 1):]
        if len(px) < lb + 1:
            return -1.0
        rets: List[float] = []
        i = 1
        while i < len(px):
            prev = px[i - 1]
            if prev > 0.0:
                rets.append(px[i] / prev - 1.0)
            i += 1
        if len(rets) < 2:
            return -1.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) * (r - mean) for r in rets) / (len(rets) - 1)
        return math.sqrt(max(var, 0.0)) * math.sqrt(252.0)

    def _null_weight(self) -> float:
        """Seeded LCG draw in [min_w, max_w]: no market information at all."""
        state = (int(self._config.null_seed) * 1103515245 + 12345 + self._bars * 2654435761) % 2147483648
        state = (state * 1103515245 + 12345) % 2147483648
        u = state / 2147483648.0
        lo = float(self._config.min_w)
        hi = float(self._config.max_w)
        return lo + u * (hi - lo)

    def calculate_target_weights(
        self, data: Dict[str, BarSnapshot]
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        self._bars += 1

        snap = data.get("SPY")
        if snap is not None:
            close = float(snap.close)
            if close > 0.0:
                self._closes.append(close)
        if len(self._closes) > 400:
            self._closes = self._closes[-400:]

        every = int(self._config.rebalance_every)
        if every < 1:
            every = 1
        due = ((self._bars - 1) % every) == 0

        vol = -1.0
        if due:
            if int(self._config.null_seed) != 0:
                target = self._null_weight()
            else:
                vol = self._realized_vol()
                if vol < 0.0:
                    target = float(self._config.max_w)
                else:
                    raw = float(self._config.target_vol) / max(vol, 0.01)
                    target = min(max(raw, float(self._config.min_w)), float(self._config.max_w))
            if abs(target - self._weight) > float(self._config.deadband):
                self._weight = target

        w = self._weight
        return {"SPY": w}, {
            "bars": float(self._bars),
            "weight": w,
            "realized_vol": vol,
            "regime": "vol_target",
        }

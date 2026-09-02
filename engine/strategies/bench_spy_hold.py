"""
STRATEGY: bench_spy_hold — the benchmark a from-scratch strategy must beat.

Buy-and-hold SPY at 99% of NAV from the first bar after warmup. No signals,
no rules, no parameters that change behaviour. It exists so that an agent-
authored strategy has something honest to be measured against: an adoption
means "beats holding the index on Sortino in both windows, with drawdown no
worse than 2pp and the sign surviving 2x/5x costs", not "made money once".

Operator-owned and pinned; the agent cannot edit it, only lose to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


@dataclass
class BenchSpyHoldConfig(StrategyConfig):
    weight: float = 0.99
    consecutive_bad_bars_threshold: int = 3


class BenchSpyHoldStrategy(TrustyStrategy):
    def __init__(self, config: BenchSpyHoldConfig) -> None:
        super().__init__(config)
        self._bars = 0

    def name(self) -> str:
        return "bench_spy_hold"

    def universe(self) -> List[str]:
        return ["SPY"]

    def max_lookback_period(self) -> int:
        return 1

    def calculate_target_weights(
        self, data: Dict[str, BarSnapshot]
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        self._bars += 1
        w = float(self._config.weight)
        return {"SPY": w}, {"bars": float(self._bars), "regime": "hold"}

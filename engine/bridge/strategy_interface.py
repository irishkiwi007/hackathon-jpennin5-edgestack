"""
trusty_strategy — Isomorphic strategy interface.

This module defines the pure strategy contract that is shared between:
  • The Rust live/paper execution engine (Strategy trait in trusty-strategy)
  • The Python QuantConnect backtest environment (RustBridgeAlgorithm)

A strategy is a stateful mathematical function that maps a synchronized
daily bar snapshot onto a set of target portfolio weights.  It has no
knowledge of orders, fills, or broker connectivity — those concerns belong
to the execution layer.

Usage (standalone backtest or live Proxmox engine):
    from bridge.strategy_interface import TrustyStrategy, StrategyConfig, BarSnapshot

Usage (QuantConnect):
    from bridge.rust_bridge_algorithm import RustBridgeAlgorithm
    (RustBridgeAlgorithm imports TrustyStrategy automatically)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, NamedTuple, Optional, Tuple


# ---------------------------------------------------------------------------
# BarSnapshot  (mirrors Rust BarSnapshot in crates/strategy/src/lib.rs)
# ---------------------------------------------------------------------------

class BarSnapshot(NamedTuple):
    """
    A single OHLCV bar from a synchronized daily session.

    Passed as the values in the ``data`` dict to
    ``TrustyStrategy.calculate_target_weights()``.

    Attributes
    ----------
    open, high, low, close : float
        Standard OHLC prices.
    volume : float
        Total session volume (set to 0.0 for rate/yield feeds).
    """
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0
    time:   Optional[datetime] = None


# ---------------------------------------------------------------------------
# StrategyConfig  (mirrors consecutive_bad_bars_threshold in config crate)
# ---------------------------------------------------------------------------

@dataclass
class StrategyConfig:
    """
    Strongly-typed configuration injected into a strategy at construction.

    All strategy parameters must live here — the strategy must not read
    global state, environment variables, or external broker state.

    Base Fields
    -----------
    consecutive_bad_bars_threshold : int
        Number of consecutive invalid/stale bars required to trip the
        circuit breaker and force the portfolio to cash.  Recommended: 2–3.

    Subclass Usage
    --------------
    Extend this dataclass for each strategy:

        @dataclass
        class PlatinumConfig(StrategyConfig):
            credit_window: int = 50
            vol_window: int = 90
            notional_budget: float = 10_000_000.0
    """
    consecutive_bad_bars_threshold: int = 3


# ---------------------------------------------------------------------------
# TrustyStrategy  (mirrors Strategy trait in crates/strategy/src/lib.rs)
# ---------------------------------------------------------------------------

class TrustyStrategy(ABC):
    """
    Abstract base class for all isomorphic strategies.

    Subclasses must implement all ``@abstractmethod`` methods.  The optional
    ``teardown()`` hook defaults to a no-op and may be left unimplemented.

    Contract
    --------
    - **No I/O** of any kind inside ``calculate_target_weights()``.
    - **No blocking calls** — the function must return synchronously.
    - **No broker state** — do not query positions, cash, or orders from the
      broker.  Maintain your own shadow copy if needed.
    - The function must be a **pure function of its inputs and internal state**.
      Given the same sequence of bars, it must produce identical weights on
      every run (Rust engine and QuantConnect must agree byte-for-byte on logs).

    Thread Safety
    -------------
    Instances are single-threaded.  The execution engine calls methods
    sequentially; no synchronisation is required inside the strategy.
    """

    def __init__(self, config: StrategyConfig) -> None:
        self._config = config

    @property
    def config(self) -> StrategyConfig:
        """Read-only access to the injected config."""
        return self._config

    # -----------------------------------------------------------------------
    # Required interface
    # -----------------------------------------------------------------------

    @abstractmethod
    def name(self) -> str:
        """
        Human-readable strategy identifier.

        Must match the Rust strategy's ``Strategy::name()`` implementation
        exactly so that structured log lines can be correlated across systems.

        Example: ``"Platinum_Live_Production"``
        """

    @abstractmethod
    def universe(self) -> list[str]:
        """
        List of raw ticker symbols required by this strategy.

        The execution engine uses this list to:
          - Validate that all feeds are present before calling the strategy.
          - Detect bad bars (any symbol absent or with an invalid price).

        Example: ``["SPXL", "HYG", "IEF", "TLT", "XLP", "XLV", "WPM",
                     "FNV", "RGLD", "DGS5", "T5YIE"]``

        Mirrors: ``Strategy::required_symbols()`` in Rust.
        """

    @abstractmethod
    def max_lookback_period(self) -> int:
        """
        Number of historical bars required for all indicators to warm up.

        The execution engine enforces a warmup lockout until this many valid
        bars have been ingested.  Set to the period of the longest indicator
        in the strategy (e.g. 90 for a 90-day SMA).

        Mirrors: ``Strategy::max_lookback_period()`` in Rust.
        """

    @abstractmethod
    def calculate_target_weights(
        self,
        data: Dict[str, BarSnapshot],
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        Core strategy logic.  Maps a synchronized daily snapshot to weights.

        Parameters
        ----------
        data : dict[str, BarSnapshot]
            A complete, validated bar snapshot for every symbol in
            ``universe()``.  The engine guarantees:
              - All symbols are present.
              - All close prices are positive and finite.

        Returns
        -------
        weights : dict[str, float]
            Desired fractional portfolio allocation per symbol.
            Values must be in [0.0, 1.0].  Symbols absent from the dict
            are treated as 0.0 (flat).  The engine does NOT enforce that
            weights sum to ≤ 1.0, but the strategy should respect this.

        signals : dict[str, float | str]
            Diagnostic key/value pairs emitted verbatim in the
            ``[STRATEGY_STATE]`` log line.  Use floats for numeric
            indicators and strings for regime labels.

        Mirrors: ``Strategy::calculate_target_weights()`` in Rust.

        Example Return
        --------------
        weights = {"SPXL": 0.99, "XLP": 0.0, "XLV": 0.0}
        signals = {"credit_ratio_sma": 1.042, "vol_regime": "low",
                   "regime": "risk_on"}
        return weights, signals
        """

    # -----------------------------------------------------------------------
    # Optional lifecycle hook
    # -----------------------------------------------------------------------

    def rate_symbols(self) -> list[str]:
        """
        Subset of ``universe()`` whose data comes from FRED (rate/yield series)
        rather than Yahoo Finance.

        The engine calls this to decide which CSV fetcher to use for each
        symbol.  Override this method when your strategy uses FRED series
        such as DGS5, T5YIE, FEDFUNDS, SOFR, etc.

        Example: ``return ["DGS5", "T5YIE"]``

        Default: empty list (all symbols fetched from Yahoo Finance).
        """
        return []

    def teardown(self) -> None:
        """
        Called once when the engine shuts down or the strategy is terminated.

        Use to flush file handles, save final state, or emit a terminal log.
        The default implementation is a no-op; override only when needed.

        Mirrors: ``Strategy::on_stop()`` in Rust.
        """

    def rate_symbols(self) -> list[str]:
        """
        Optional list of symbols that are FRED rate / yield series.

        Symbols returned here are fetched from the FRED API rather than
        Yahoo Finance.  The default is an empty list (all symbols treated
        as equity tickers).  Override in strategies that use macro feeds
        such as DGS5, T5YIE, DGS3MO.
        """
        return []

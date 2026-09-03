'''
STRATEGY: regimebasket - a two-state weekly regime allocator, authored from
the lab's own cross-family findings rather than from any operator strategy.

THESIS
------
Three results in the record are larger and more window-stable than anything
else measured here:
  1. canaries H-C08: replacing the DEFENSIVE BASKET with cash in risk-off
     costs -0.460 train / -0.510 valid Sortino. Being out of equities is only
     half the trade; what you hold instead is the other half.
  2. canaries H-C07: a WEEKLY decision cadence beats daily (daily scores
     -0.052/-0.426 and degrades to -0.61 under cost stress). Regime state is
     slow; sampling it every day buys whipsaw.
  3. The HYG credit canary and the long trend gate are adjudicated essential
     across unrelated families (edgestack H-CAL-001/DRV-CAL-001, canaries
     H-C01, SPXLrealyields H-S001).

All three were measured INSIDE 3x-leveraged, ten-rule strategies, where they
are confounded with everything else in the stack. This file is those three
findings and nothing else, at 1x:

  RISK-ON   SPY above its price 200 sessions ago AND HYG above its own
            100-day SMA -> 0.98 NAV in the stronger of SPY / QQQ over the
            trailing 126 sessions
  RISK-OFF  either gate shut -> 0.98 NAV split equally across IEF / XLP / GLD

Decisions are taken every 5th session; between decisions the book is held.
Every input is trailing, so the strategy is causal by construction. Six
numbers, none of them swept: 200 and 100 are the conventional windows already
adjudicated in this lab, 126 is a half-year, 5 is a week, 0.98 is the budget
cap, and the defensive basket is equal-weighted rather than optimised.

WHY IT SHOULD BEAT SPY BUY-AND-HOLD
-----------------------------------
The benchmark takes the full 2008 and 2022 drawdowns. This takes neither, and
- the part that matters - it does not sit in cash while it waits: IEF, XLP and
GLD all carried positively through both of those episodes. Sortino punishes
downside deviation only, so removing the two worst equity years while staying
invested should raise it materially even after the whipsaw cost of the gates.

NULL TWIN
---------
null_seed != 0 replaces BOTH decisions (the regime, and the SPY/QQQ pick) with
a deterministic integer-hash walk over the decision index that carries zero
market information, toggling at a rate chosen to match the real rule's switch
frequency. Cadence, sizing and instruments are unchanged, so the null measures
exactly how often this SHAPE of strategy beats the benchmark by luck.
'''

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


RISK_ON_SYMBOLS: List[str] = ['SPY', 'QQQ']
DEFENSIVE_SYMBOLS: List[str] = ['IEF', 'XLP', 'GLD']
CREDIT_SYMBOL: str = 'HYG'
TREND_SYMBOL: str = 'SPY'
ALL_SYMBOLS: List[str] = ['SPY', 'QQQ', 'HYG', 'IEF', 'XLP', 'GLD']


@dataclass
class RegimeBasketConfig(StrategyConfig):
    # --- cadence ---
    rebalance_every:   int   = 5      # H-C07: weekly, never daily

    # --- regime gates ---
    trend_lookback:    int   = 200    # SPY vs its own price 200 sessions ago
    credit_sma:        int   = 100    # HYG vs its own 100-day SMA
    use_trend_gate:    int   = 1
    use_credit_gate:   int   = 1

    # --- risk-on leg ---
    rs_lookback:       int   = 126    # SPY vs QQQ relative strength, half a year
    use_rs_pick:       int   = 1      # 0 = always SPY
    equity_weight:     float = 0.98

    # --- risk-off leg (the rule this family exists to test) ---
    use_defensive_basket: int = 1     # 0 = risk-off goes to cash instead
    defensive_weight:  float = 0.98

    # --- null twin ---
    null_seed:         int   = 0      # 0 = live decisions; !=0 = seeded noise
    null_switch_per_mille: int = 40   # ~ the live rule's regime switch rate


def _noise(seed: int, k: int) -> int:
    '''Deterministic, salt-free integer hash. Same seed and k -> same value in
    every process and every run; carries no market information whatsoever.'''
    x = (seed * 1103515245 + k * 12345 + 2654435761) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 2246822519) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 3266489917) & 0xFFFFFFFF
    x ^= x >> 16
    return x


class RegimeBasketC000Strategy(TrustyStrategy):
    '''Weekly two-state allocator: gated equity, or a defensive basket.'''

    def __init__(self, config: RegimeBasketConfig) -> None:
        super().__init__(config)
        self._cfg: RegimeBasketConfig = config
        depth = max(config.trend_lookback, config.credit_sma, config.rs_lookback) + 2
        self._close: Dict[str, deque] = {s: deque(maxlen=depth) for s in ALL_SYMBOLS}
        self._bars_seen = 0
        self._decisions = 0
        self._held: Dict[str, float] = {}
        self._has_book = False
        self._risk_on = True          # null-twin state, seeded identically each run
        self._pick_qqq = False        # null-twin state

    # ---------------------------------------------------------------- meta
    def name(self) -> str:
        return 'regimebasket_c000'

    def universe(self) -> List[str]:
        return list(ALL_SYMBOLS)

    def max_lookback_period(self) -> int:
        # Small on purpose: the runner skips this many bars without feeding
        # them in, and we self-gate below, so a large value would warm up twice.
        return 5

    @property
    def _warmup_bars(self) -> int:
        cfg = self._cfg
        return max(cfg.trend_lookback, cfg.credit_sma, cfg.rs_lookback) + 1

    # ---------------------------------------------------------- indicators
    @staticmethod
    def _sma(seq: deque, n: int) -> float:
        if len(seq) < n or n <= 0:
            return 0.0
        return sum(list(seq)[-n:]) / n

    def _trend_up(self) -> bool:
        c = self._close[TREND_SYMBOL]
        lb = self._cfg.trend_lookback
        if len(c) < lb + 1 or c[-1 - lb] <= 0:
            return False
        return c[-1] / c[-1 - lb] - 1.0 > 0.0

    def _credit_ok(self) -> bool:
        c = self._close[CREDIT_SYMBOL]
        sma = self._sma(c, self._cfg.credit_sma)
        return len(c) > 0 and sma > 0.0 and c[-1] > sma

    def _trailing_return(self, sym: str, lb: int) -> float:
        c = self._close[sym]
        if len(c) < lb + 1 or c[-1 - lb] <= 0:
            return 0.0
        return c[-1] / c[-1 - lb] - 1.0

    def _stronger_leg(self) -> str:
        cfg = self._cfg
        if not cfg.use_rs_pick:
            return 'SPY'
        spy = self._trailing_return('SPY', cfg.rs_lookback)
        qqq = self._trailing_return('QQQ', cfg.rs_lookback)
        return 'QQQ' if qqq > spy else 'SPY'

    # ----------------------------------------------------------- decision
    def _decide(self) -> Tuple[bool, str, Dict[str, Any]]:
        cfg = self._cfg
        notes: Dict[str, Any] = {}
        if cfg.null_seed:
            if _noise(cfg.null_seed, self._decisions) % 1000 < cfg.null_switch_per_mille:
                self._risk_on = not self._risk_on
            if _noise(cfg.null_seed + 7919, self._decisions) % 1000 < cfg.null_switch_per_mille:
                self._pick_qqq = not self._pick_qqq
            notes['mode'] = 'null'
            return self._risk_on, ('QQQ' if self._pick_qqq else 'SPY'), notes

        trend = self._trend_up()
        credit = self._credit_ok()
        risk_on = ((trend or not cfg.use_trend_gate)
                   and (credit or not cfg.use_credit_gate))
        notes['mode'] = 'live'
        notes['trend_up'] = trend
        notes['credit_ok'] = credit
        return risk_on, self._stronger_leg(), notes

    def _book_for(self, risk_on: bool, leg: str) -> Dict[str, float]:
        cfg = self._cfg
        if risk_on:
            return {leg: cfg.equity_weight}
        if not cfg.use_defensive_basket:
            return {}
        per = cfg.defensive_weight / len(DEFENSIVE_SYMBOLS)
        return {s: per for s in DEFENSIVE_SYMBOLS}

    # ---------------------------------------------------------------- main
    def calculate_target_weights(
        self,
        data: Dict[str, BarSnapshot],
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        cfg = self._cfg
        self._bars_seen += 1

        for s in ALL_SYMBOLS:
            if s in data:
                self._close[s].append(float(data[s].close))

        weights: Dict[str, float] = {s: 0.0 for s in ALL_SYMBOLS}
        signals: Dict[str, Any] = {'bars_seen': self._bars_seen}

        if self._bars_seen <= self._warmup_bars:
            signals['state'] = 'warming_up'
            return weights, signals

        elapsed = self._bars_seen - self._warmup_bars - 1
        if (not self._has_book) or (elapsed % max(1, cfg.rebalance_every) == 0):
            risk_on, leg, notes = self._decide()
            self._decisions += 1
            self._held = self._book_for(risk_on, leg)
            self._has_book = True
            signals.update(notes)
            signals['risk_on'] = risk_on
            signals['leg'] = leg
            signals['rebalanced'] = True
        else:
            signals['rebalanced'] = False

        for sym, w in self._held.items():
            weights[sym] = weights.get(sym, 0.0) + w

        signals['decisions'] = self._decisions
        signals['gross'] = round(sum(weights.values()), 3)
        return weights, signals

    def teardown(self) -> None:
        pass

'''
STRATEGY: regimeduo - a two-state weekly regime allocator, authored from
scratch under ADR-016. Benchmark: bench_spy_hold.py.

THESIS
------
The lab record says regime detection is where the durable edge lives. On the
canaries family the defensive BASKET (rather than going to cash) is the
largest effect ever measured here (-0.460/-0.510 on removal), the growth
confirm is essential (-0.144/-0.214), and the FDN risk canary is the
strategy's drawdown controller while being invisible to Sortino. Every one
of those verdicts, though, was measured inside a strategy that also carries
3x leverage, trailing stops, a sniper leg and volume tiering, so none of them
is a statement about regime allocation as such.

regimeduo states it alone, at 1x, with nothing else in the file:

  RISK-ON   SPY above its own close 200 sessions ago
            AND HYG above its own 100-day SMA (the credit canary)
            -> 0.98 NAV in whichever of SPY / QQQ has the stronger
               trailing 126-session return.

  RISK-OFF  -> 0.98 NAV split equally across IEF, XLP and TLT.
               The defensive BASKET, never cash. That is the canaries
               lesson restated as a standalone, falsifiable hypothesis.

Decisions are taken every 5th session and the book is held in between, so
turnover sits near the weekly cadence H-C07 adjudicated essential and the
engine's 10bps/side cannot dominate the result.

CAUSALITY. Every input is trailing: the trend compares today's close to a
close 200 bars back, the credit gate to an SMA of past closes, the pick to a
126-bar trailing return. Appending future bars cannot change a past decision.

SYMBOLS. Only names whose stored history runs to 2026-08-31 are used. The
first draft of this family held GLD and died in birth_check on an HTTP 403
raised inside the engine's own fetcher - the July-2026 symbols (XLE, GLD,
SLV) provoke a live refresh that the upstream now refuses. That was
infrastructure, not strategy logic, and it is avoided here rather than
worked around.

NULL TWIN. At null_seed != 0 the regime state and the asset pick are replaced
by a seeded deterministic mixer running on the same 5-session cadence with a
matched switch rate, so the null trades about as often as the real rule and
the family can be null-calibrated.
'''

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


@dataclass
class RegimeDuoConfig(StrategyConfig):
    # --- regime gates ---
    trend_lookback:       int   = 200   # SPY vs its own close N sessions back
    credit_sma:           int   = 100   # HYG vs its own SMA (the credit canary)
    use_trend_gate:       int   = 1     # 0 = drop the trend requirement
    use_credit_gate:      int   = 1     # 0 = drop the credit canary

    # --- risk-on leg ---
    rel_lookback:         int   = 126   # trailing window for the SPY/QQQ pick
    use_rel_pick:         int   = 1     # 0 = always SPY when risk-on

    # --- risk-off leg ---
    use_defensive_basket: int   = 1     # 0 = go to cash instead of the basket

    # --- cadence and sizing ---
    decide_every:         int   = 5     # sessions between decisions
    total_cap:            float = 0.98  # long-only budget ceiling

    # --- mining null ---
    null_seed:            int   = 0     # 0 = real rules; != 0 = seeded noise
    null_switch_mod:      int   = 12    # ~1 state flip per 12 decisions


RISK_ON: List[str] = ['SPY', 'QQQ']
DEFENSIVE: List[str] = ['IEF', 'XLP', 'TLT']
UNIVERSE: List[str] = ['SPY', 'QQQ', 'HYG', 'IEF', 'XLP', 'TLT']


class RegimeDuoStrategy(TrustyStrategy):
    '''Two states, one decision a week, no leverage and no stops.'''

    def __init__(self, config: RegimeDuoConfig) -> None:
        super().__init__(config)
        self._cfg: RegimeDuoConfig = config
        self._bars_seen = 0
        self._decisions = 0
        depth = max(config.trend_lookback,
                    config.credit_sma,
                    config.rel_lookback) + 3
        self._close: Dict[str, deque] = {s: deque(maxlen=depth) for s in UNIVERSE}
        self._book: Dict[str, float] = {s: 0.0 for s in UNIVERSE}
        self._null_state = 1
        self._null_pick = 0

    # ---------------------------------------------------------------- meta
    def name(self) -> str:
        return 'regimeduo'

    def universe(self) -> List[str]:
        return list(UNIVERSE)

    def max_lookback_period(self) -> int:
        # Small on purpose: the runner skips this many bars without feeding
        # them in, and we self-gate below, so a large value would warm up
        # twice (the double-warmup quirk in ENGINE-TRIAL.md).
        return 5

    @property
    def _warmup_bars(self) -> int:
        c = self._cfg
        return max(c.trend_lookback, c.credit_sma, c.rel_lookback) + 2

    # ---------------------------------------------------------- indicators
    @staticmethod
    def _sma(seq: deque, n: int) -> float:
        if len(seq) < n:
            return 0.0
        return sum(list(seq)[-n:]) / n

    def _trend_up(self) -> bool:
        c = self._close['SPY']
        lb = self._cfg.trend_lookback
        if len(c) < lb + 1:
            return False
        return c[-1] > c[-1 - lb]

    def _credit_ok(self) -> bool:
        h = self._close['HYG']
        s = self._sma(h, self._cfg.credit_sma)
        return len(h) > 0 and s > 0.0 and h[-1] > s

    def _stronger(self) -> str:
        cfg = self._cfg
        if not cfg.use_rel_pick:
            return 'SPY'
        best = 'SPY'
        best_r = None
        for s in RISK_ON:
            c = self._close[s]
            if len(c) < cfg.rel_lookback + 1:
                continue
            ref = c[-1 - cfg.rel_lookback]
            if ref <= 0:
                continue
            r = c[-1] / ref - 1.0
            if best_r is None or r > best_r:
                best = s
                best_r = r
        return best

    # --------------------------------------------------------- mining null
    def _mix(self, k: int) -> int:
        '''Deterministic integer mixer: carries zero market information.'''
        x = (self._cfg.null_seed * 2654435761 + k * 40503 + 2166136261) & 0xFFFFFFFF
        x = (x ^ (x >> 13)) & 0xFFFFFFFF
        x = (x * 1274126177) & 0xFFFFFFFF
        x = (x ^ (x >> 16)) & 0xFFFFFFFF
        return x

    # ---------------------------------------------------------- the decision
    def _decide(self) -> Tuple[Dict[str, float], Dict[str, Any]]:
        cfg = self._cfg
        w: Dict[str, float] = {s: 0.0 for s in UNIVERSE}
        sig: Dict[str, Any] = {}

        if cfg.null_seed:
            h = self._mix(self._decisions)
            if h % max(2, cfg.null_switch_mod) == 0:
                self._null_state = 1 - self._null_state
                self._null_pick = (h >> 8) % len(RISK_ON)
            risk_on = bool(self._null_state)
            pick = RISK_ON[self._null_pick]
            sig['mode'] = 'null'
        else:
            trend = self._trend_up()
            credit = self._credit_ok()
            risk_on = ((trend or not cfg.use_trend_gate)
                       and (credit or not cfg.use_credit_gate))
            pick = self._stronger()
            sig['mode'] = 'live'
            sig['trend_up'] = trend
            sig['credit_ok'] = credit

        if risk_on:
            w[pick] = cfg.total_cap
        elif cfg.use_defensive_basket:
            per = cfg.total_cap / len(DEFENSIVE)
            for s in DEFENSIVE:
                w[s] = per

        sig['risk_on'] = risk_on
        sig['held'] = pick if risk_on else ('basket' if cfg.use_defensive_basket else 'cash')
        return w, sig

    # ---------------------------------------------------------------- main
    def calculate_target_weights(
        self,
        data: Dict[str, BarSnapshot],
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        cfg = self._cfg
        self._bars_seen += 1

        for s in UNIVERSE:
            if s in data:
                self._close[s].append(float(data[s].close))

        signals: Dict[str, Any] = {'bars_seen': self._bars_seen}

        if self._bars_seen <= self._warmup_bars:
            signals['state'] = 'warming_up'
            return {s: 0.0 for s in UNIVERSE}, signals

        step = max(1, cfg.decide_every)
        if (self._bars_seen - self._warmup_bars - 1) % step == 0:
            self._decisions += 1
            book, sig = self._decide()
            self._book = book
            signals.update(sig)
            signals['decided'] = True
        else:
            signals['decided'] = False

        signals['decisions'] = self._decisions
        return dict(self._book), signals

    def teardown(self) -> None:
        pass

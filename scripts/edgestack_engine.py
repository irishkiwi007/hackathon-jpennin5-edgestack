"""
STRATEGY: edgestack (v2 — cross-pollination trial)
Port of the validated edge-stack research (alpaca-mcp-lab / EDGE-PORTFOLIO.md) to the
TrustyRustyEngine daily bar-by-bar contract, extended with the transferable rules from the
repo's other strategies (spxlrealyields, canaries) as sweepable flags.

ALL NEW FLAGS DEFAULT OFF: with defaults, behavior is identical to the validated v1
(train Sharpe 0.80 / validation 0.65) — verified by regression run.

Borrowed-rule flags (source in brackets):
  riskoff_mode       0 cash | 1 defensives XLP/XLV | 2 defensives+gold WPM/RGLD  [both]
  gate_mode          0 trend | 1 trend&HYG>SMA100 | 2 trend&FDN>SMA200
                     3 trend&!divergence | 4 trend&credit&risk&!div [canaries]
                     5 risk_on(HYG/IEF & TLT-vol) | 6 trend&risk_on [spxlrealyields]
  gate_cadence       evaluate the gate every N bars (5 = canaries' weekly scan)
  use_trailing_stop  15% trailing stop from HWM on the core; re-entry needs SPY>SMA50
  sniper_mode        1 = ATR-pullback entries added to the sleeve (SPY>SMA50 and
                     close <= SMA20 - 2.6*ATR14) [canaries "sniper"]

Engine adaptations carried over from v1 (see ENGINE-TRIAL.md): no overnight-only core
(T+1 open fills), sleeve volume floor 1.8x (next-open entry variant), long-only budget
core+sleeve <= 0.98 with sleeve priority, runner-warmup workaround in max_lookback_period().
FNV is deliberately NOT in the gold basket: its data starts 2007-12 and would shrink the
common-date window past HYG's 2007-04.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


@dataclass
class EdgeStackConfig(StrategyConfig):
    # core
    core_mode: int = 1              # 0 = off, 1 = gated SPY, 2 = always-on SPY
    core_weight: float = 0.70
    trend_lookback: int = 252

    # capitulation sleeve
    sleeve_weight: float = 0.30
    max_total_sleeve: float = 0.60
    stretch_trigger: float = -2.5
    vol_floor: float = 1.8
    vol_ceiling: float = 2.5        # load-bearing, do not remove
    hold_sessions: int = 3
    rv_window: int = 20
    stretch_lookback: int = 5

    # TLT calm-bond gate on the sleeve
    use_calm_filter: int = 0
    tlt_std_window: int = 21
    tlt_vol_window: int = 90
    calm_tolerance: float = 0.015

    # ---- borrowed rules (all default OFF / v1-equivalent) ----
    riskoff_mode: int = 0
    gate_mode: int = 1              # 1 = trend AND HYG>SMA100 (canaries' credit canary).
                                    # Adopted after passing BOTH disjoint windows:
                                    # Sharpe 0.80->0.98 train, 0.65->1.02 valid, DD ~halved.
                                    # Set 0 for the pure-trend v1 gate.
    gate_cadence: int = 1
    use_trailing_stop: int = 0
    trail_pct: float = 0.15
    sniper_mode: int = 0
    sniper_entry_mult: float = 2.6
    canary_credit_lb: int = 100     # HYG vs its own SMA
    canary_risk_lb: int = 200       # FDN vs its own SMA
    canary_spy_lb: int = 50         # SPY SMA for sniper gate / stop re-entry
    credit_ratio_lb: int = 50       # HYG/IEF vs SMA (spxlrealyields construction)
    sniper_basis_lb: int = 20
    sniper_atr_lb: int = 14
    div_high_lb: int = 252


SLEEVE_SYMBOLS = ["SPY", "QQQ", "SOXX", "XLV", "XLP", "HYG", "FDN"]
CORE_SYMBOL = "SPY"
GOLD = ["WPM", "RGLD"]
TOTAL_CAP = 0.98


class EdgeStackStrategy(TrustyStrategy):

    def __init__(self, config: EdgeStackConfig) -> None:
        super().__init__(config)
        self._cfg: EdgeStackConfig = config
        self._bars_seen = 0

        n = max(config.rv_window + config.stretch_lookback + 2,
                config.trend_lookback + 2, config.div_high_lb + 2,
                config.canary_risk_lb + 2)
        self._close = {s: deque(maxlen=n) for s in SLEEVE_SYMBOLS}
        self._vol = {s: deque(maxlen=n) for s in SLEEVE_SYMBOLS}
        self._high = {s: deque(maxlen=n) for s in SLEEVE_SYMBOLS}
        self._low = {s: deque(maxlen=n) for s in SLEEVE_SYMBOLS}
        self._ief = deque(maxlen=n)

        # TLT regime (hysteresis is path-dependent)
        self._tlt = deque(maxlen=config.tlt_std_window)
        self._tlt_stds = deque(maxlen=config.tlt_vol_window)
        self._calm = True

        # credit-ratio regime (spxlrealyields construction, hysteresis)
        self._credit_ratio = deque(maxlen=config.credit_ratio_lb)
        self._credit_state = False

        # gate cache (for gate_cadence) + trailing-stop state
        self._gate_open = False
        self._core_hwm = 0.0
        self._core_stopped = False

        self._sleeve: list = []     # [symbol, weight, sessions_left]

    # ------------------------------------------------------------------ meta
    def name(self) -> str:
        return "edgestack"

    def universe(self) -> list:
        return SLEEVE_SYMBOLS + ["TLT", "IEF"] + GOLD

    def max_lookback_period(self) -> int:
        # small on purpose — the runner skips (never feeds) this many bars; the strategy
        # self-gates on _warmup_bars instead (see ENGINE-TRIAL.md, double-warmup quirk)
        return 5

    @property
    def _warmup_bars(self) -> int:
        return max(self._cfg.trend_lookback + 1,
                   self._cfg.tlt_std_window + self._cfg.tlt_vol_window,
                   self._cfg.div_high_lb + 1, self._cfg.canary_risk_lb + 1)

    # ------------------------------------------------------------- indicators
    @staticmethod
    def _sma(seq, n):
        if len(seq) < n:
            return 0.0
        window = list(seq)[-n:]
        return sum(window) / n

    def _update_regimes(self, data: Dict[str, BarSnapshot]) -> None:
        if "TLT" in data:
            self._tlt.append(float(data["TLT"].close))
            if len(self._tlt) == self._cfg.tlt_std_window:
                m = sum(self._tlt) / len(self._tlt)
                var = sum((x - m) ** 2 for x in self._tlt) / (len(self._tlt) - 1)
                self._tlt_stds.append(math.sqrt(var))
            if len(self._tlt_stds) >= self._cfg.tlt_vol_window:
                now = self._tlt_stds[-1]
                avg = sum(self._tlt_stds) / len(self._tlt_stds)
                tol = self._cfg.calm_tolerance
                if not self._calm:
                    self._calm = now < avg * (1.0 - tol)
                else:
                    self._calm = now <= avg * (1.0 + tol)
        if "IEF" in data:
            self._ief.append(float(data["IEF"].close))
            hyg = self._close["HYG"]
            if hyg and self._ief and self._ief[-1] > 0:
                self._credit_ratio.append(hyg[-1] / self._ief[-1])
            if len(self._credit_ratio) >= self._cfg.credit_ratio_lb:
                c_now = self._credit_ratio[-1]
                c_avg = sum(self._credit_ratio) / len(self._credit_ratio)
                tol = self._cfg.calm_tolerance
                if not self._credit_state:
                    self._credit_state = c_now > c_avg * (1.0 + tol)
                else:
                    self._credit_state = c_now >= c_avg * (1.0 - tol)

    def _capitulation(self, sym: str) -> Tuple[bool, float, float]:
        cfg = self._cfg
        closes, vols = self._close[sym], self._vol[sym]
        if len(closes) < cfg.rv_window + cfg.stretch_lookback + 1:
            return False, 0.0, 0.0
        c = list(closes)
        v = list(vols)
        rets = []
        for i in range(len(c) - cfg.rv_window, len(c)):
            if c[i - 1] > 0 and c[i] > 0:
                rets.append(math.log(c[i] / c[i - 1]))
        if len(rets) < cfg.rv_window - 1:
            return False, 0.0, 0.0
        m = sum(rets) / len(rets)
        var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
        rv = math.sqrt(var)
        if rv <= 0:
            return False, 0.0, 0.0
        ref = c[-1 - cfg.stretch_lookback]
        if ref <= 0 or c[-1] <= 0:
            return False, 0.0, 0.0
        stretch = math.log(c[-1] / ref) / (rv * math.sqrt(cfg.stretch_lookback))
        avg_vol = sum(v[-cfg.rv_window:]) / cfg.rv_window
        if avg_vol <= 0:
            return False, 0.0, 0.0
        volx = v[-1] / avg_vol
        return (stretch < cfg.stretch_trigger
                and cfg.vol_floor <= volx < cfg.vol_ceiling), stretch, volx

    def _sniper_fires(self, sym: str) -> bool:
        """canaries' ATR pullback: SPY bullish and close <= SMA20 - mult*ATR14."""
        cfg = self._cfg
        spy = self._close[CORE_SYMBOL]
        if self._sma(spy, cfg.canary_spy_lb) <= 0 or not spy:
            return False
        if spy[-1] <= self._sma(spy, cfg.canary_spy_lb):
            return False
        c, h, l = self._close[sym], self._high[sym], self._low[sym]
        if len(c) < cfg.sniper_basis_lb + 2 or len(h) < cfg.sniper_atr_lb + 2:
            return False
        basis = self._sma(c, cfg.sniper_basis_lb)
        trs = []
        cl = list(c)
        hl = list(h)
        ll = list(l)
        for i in range(len(cl) - cfg.sniper_atr_lb, len(cl)):
            trs.append(max(hl[i] - ll[i], abs(hl[i] - cl[i - 1]),
                           abs(ll[i] - cl[i - 1])))
        atr = sum(trs) / len(trs)
        return c[-1] <= basis - cfg.sniper_entry_mult * atr

    def _trend_up(self) -> bool:
        c = self._close[CORE_SYMBOL]
        lb = self._cfg.trend_lookback
        if len(c) < lb + 1:
            return False
        return c[-1] / c[-1 - lb] - 1.0 > 0.0

    def _evaluate_gate(self) -> bool:
        cfg = self._cfg
        trend = self._trend_up()
        if cfg.gate_mode == 0:
            return trend
        hyg = self._close["HYG"]
        fdn = self._close["FDN"]
        qqq_c, qqq_h = self._close["QQQ"], self._high["QQQ"]
        sox_c, sox_h = self._close["SOXX"], self._high["SOXX"]
        credit_ok = bool(hyg) and hyg[-1] > self._sma(hyg, cfg.canary_credit_lb) > 0
        risk_ok = bool(fdn) and fdn[-1] > self._sma(fdn, cfg.canary_risk_lb) > 0
        div = False
        if len(qqq_h) >= cfg.div_high_lb and len(sox_h) >= cfg.div_high_lb:
            mq = max(list(qqq_h)[-cfg.div_high_lb:])
            ms = max(list(sox_h)[-cfg.div_high_lb:])
            div = (qqq_c[-1] >= mq * 0.99) and (sox_c[-1] < ms * 0.97)
        risk_on = self._credit_state and self._calm
        if cfg.gate_mode == 1:
            return trend and credit_ok
        if cfg.gate_mode == 2:
            return trend and risk_ok
        if cfg.gate_mode == 3:
            return trend and not div
        if cfg.gate_mode == 4:
            return trend and credit_ok and risk_ok and not div
        if cfg.gate_mode == 5:
            return risk_on
        if cfg.gate_mode == 6:
            return trend and risk_on
        return trend

    # ------------------------------------------------------------------ main
    def calculate_target_weights(
        self,
        data: Dict[str, BarSnapshot],
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        cfg = self._cfg
        self._bars_seen += 1

        for s in SLEEVE_SYMBOLS:
            if s in data:
                self._close[s].append(float(data[s].close))
                self._vol[s].append(float(data[s].volume))
                self._high[s].append(float(getattr(data[s], "high", data[s].close)))
                self._low[s].append(float(getattr(data[s], "low", data[s].close)))
        self._update_regimes(data)

        weights: Dict[str, float] = {s: 0.0 for s in self.universe()}
        signals: Dict[str, Any] = {"bars_seen": self._bars_seen}

        if self._bars_seen <= self._warmup_bars:
            signals["state"] = "warming_up"
            return weights, signals

        # age sleeve positions
        for p in self._sleeve:
            p[2] -= 1
        self._sleeve = [p for p in self._sleeve if p[2] > 0]

        # capitulation signals (+ optional sniper union)
        fired = []
        for s in SLEEVE_SYMBOLS:
            ok, stretch, volx = self._capitulation(s)
            if ok:
                fired.append(s)
                signals[f"cap_{s}"] = round(stretch, 2)
        if cfg.sniper_mode:
            for s in SLEEVE_SYMBOLS:
                if s not in fired and self._sniper_fires(s):
                    fired.append(s)
                    signals[f"snp_{s}"] = 1
        if cfg.use_calm_filter and not self._calm:
            fired = []
            signals["sleeve_blocked"] = "stressed_bonds"

        if fired:
            current = sum(p[1] for p in self._sleeve)
            budget = max(0.0, min(cfg.sleeve_weight, cfg.max_total_sleeve - current))
            if budget > 0:
                w = budget / len(fired)
                for s in fired:
                    self._sleeve.append([s, w, cfg.hold_sessions])

        sleeve_total = 0.0
        for sym, w, _left in self._sleeve:
            weights[sym] = weights.get(sym, 0.0) + w
            sleeve_total += w

        # ---- core gate (cached per gate_cadence) ----
        if (self._bars_seen % max(cfg.gate_cadence, 1) == 0
                or self._bars_seen == self._warmup_bars + 1):
            self._gate_open = self._evaluate_gate()

        core_on = (cfg.core_mode == 2) or (cfg.core_mode == 1 and self._gate_open)

        # ---- trailing stop on the core [both strategies use HWM stops] ----
        spy_c = self._close[CORE_SYMBOL][-1] if self._close[CORE_SYMBOL] else 0.0
        if cfg.use_trailing_stop and cfg.core_mode == 1:
            if core_on and not self._core_stopped:
                self._core_hwm = max(self._core_hwm, spy_c)
                if (self._core_hwm > 0
                        and (self._core_hwm - spy_c) / self._core_hwm > cfg.trail_pct):
                    self._core_stopped = True
            if self._core_stopped:
                # re-entry requires SPY back above its 50d SMA (canaries' spy_bullish)
                sma50 = self._sma(self._close[CORE_SYMBOL], cfg.canary_spy_lb)
                if sma50 > 0 and spy_c > sma50:
                    self._core_stopped = False
                    self._core_hwm = spy_c
                else:
                    core_on = False
            if not core_on and not self._core_stopped:
                self._core_hwm = 0.0

        core_w = cfg.core_weight if core_on else 0.0
        core_w = max(0.0, min(core_w, TOTAL_CAP - sleeve_total))
        if core_w > 0:
            weights[CORE_SYMBOL] = weights.get(CORE_SYMBOL, 0.0) + core_w
        elif cfg.riskoff_mode and cfg.core_mode == 1:
            # park the core budget in the risk-off basket instead of cash [both]
            park = max(0.0, min(cfg.core_weight, TOTAL_CAP - sleeve_total))
            if cfg.riskoff_mode == 1:
                for s in ("XLP", "XLV"):
                    weights[s] = weights.get(s, 0.0) + park / 2.0
            elif cfg.riskoff_mode == 2:
                for s in ("XLP", "XLV"):
                    weights[s] = weights.get(s, 0.0) + park * 0.25
                for s in GOLD:
                    weights[s] = weights.get(s, 0.0) + park * 0.25

        total = sum(weights.values())
        if total > TOTAL_CAP:
            scale = TOTAL_CAP / total
            weights = {k: v * scale for k, v in weights.items()}

        signals.update({
            "gate_open": self._gate_open, "calm": self._calm,
            "credit_state": self._credit_state, "core_stopped": self._core_stopped,
            "core_w": round(core_w, 3), "sleeve_n": len(self._sleeve),
        })
        return weights, signals

    def teardown(self) -> None:
        pass

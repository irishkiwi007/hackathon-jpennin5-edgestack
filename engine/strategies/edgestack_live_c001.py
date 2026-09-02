"""
STRATEGY: edgestack_live_c001 — INSTRUMENTED COPY of edgestack_live.py.

A verbatim copy of the live mirror, with five decision points the baseline
hard-codes turned into config flags. EVERY new flag defaults to the live
behaviour, so at default config this file must be metric-identical to
edgestack_live.py (the promoter proves that; nothing here is a rewrite).

  fixed_warmup / warmup_ref   experimental hygiene, not a trading rule. The
      baseline derives its self-gate from trend_lookback, so ANY lookback
      change also moves the first traded bar: 252 -> 126 starts the strategy
      ~6 months earlier, i.e. inside Q4-2008 (train) and Q4-2018 (valid),
      which contaminates the very test it is meant to answer. fixed_warmup=1
      pins the warmup at warmup_ref bars (253 = the live value) so a lookback
      probe measures the rule and not the start date.
  gate_priority   the baseline gives the SLEEVE first claim on the budget
      (core_w = min(core_w, total_cap - sleeve_total)), so every change to
      sleeve frequency silently de-weights the core as well. =1 reverses the
      priority: the core is sized first and the sleeve is scaled into the
      room that is left.
  use_partial_derisk / partial_derisk_w   the core gate is binary - both gates
      pass -> core_weight, otherwise flat. =1 holds core_weight *
      partial_derisk_w when exactly one of the two ENABLED gates is passing.
  no_restack   the baseline can re-enter a symbol it is already holding,
      stacking weight in one name. =1 refuses the duplicate entry.
  sleeve_trail_pct   the sleeve has NO adverse-move exit; positions leave only
      on the 3-session timer. >0 adds a trailing stop from the position's peak
      close. This is the rule the never-admitted edgestack_c001.py carried:
      H-002 / H-002.2 cite that file, it is not in the workspace, and those
      two verdicts are records only - they are not reproducible.

Baseline documentation follows, verbatim.

STRATEGY: edgestack_live — faithful mirror of the agent running in the
Alpaca AI Trading Agents Hackathon (alpaca-mcp-lab, account PA3ZCDDOPR2N).

Built with the manual strategy-builder contract (templates/template_strategy.py):
upload via Dashboard > Strategies, or run headless with run_backtest.py.

WHAT THE LIVE AGENT DOES (agent/equity_core.py + agent/signal_engine.py)
-----------------------------------------------------------------------
  CORE    long SPY, entered at the 15:45 pass, gated by BOTH
            - 12-month trend up            (SPY close / close[-252] > 1)
            - credit canary                (HYG > its own 100-day SMA)
          sized CORE_WEIGHT = 0.70 of NAV.

  SLEEVE  capitulation basket across SPY/QQQ/SOXX/XLV/XLP/HYG/FDN:
            - stretch = log(c/c[-5]) / (rv20 * sqrt(5))  <  -2.5
            - volume cell decides whether the signal is TRADEABLE at all
            - 3-session hold, batch budget 0.30 split EQUALLY across the
              signals that fire that day, total sleeve capped at 0.60.

  VOLUME TIERS (signal_engine.TIER_TABLES) — the live agent runs the
  "next_open" table whenever entry is delayed to the next open, which is
  exactly this engine's fill model (T+1 open). That table is:
        SMALL   1.4 - 1.8x   NOT tradeable  (inverts to -0.223% on delay)
        FULL    1.8 - 2.5x   tradeable      (+2.019%, t=4.14)
        MEDIUM  2.5x and up  tradeable      (+1.578%, t=3.50)
  So the live agent DOES trade above 2.5x volume. This is the one place the
  earlier engine port (strategies/edgestack.py) differs: it applies a hard
  vol_ceiling of 2.5 and never trades the MEDIUM cell. `tier_mode` below
  makes that difference switchable so the two can be compared directly.

WHAT THIS ENGINE CANNOT EXPRESS (unchanged from ENGINE-TRIAL.md)
---------------------------------------------------------------
  1. The overnight-only core. Orders fill at the NEXT bar's open, so
     "hold from today's close to tomorrow's open" is inexpressible. The core
     here is therefore trend+credit-gated FULL-TIME SPY, which forfeits the
     research stack's main trick (shedding the ~zero-Sharpe intraday hours).
     Expect a materially different Sharpe from the 0.85 research figure.
  2. The defined-risk options sleeve (bull put spreads behind 14 gates).
     This contract returns equity target weights only.
  Both gaps are structural, not oversights.

Costs are the engine's own defaults (5bps slippage + 5bps commission per
side) unless overridden — 10x the research assumption, deliberately harsh.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy


# ---------------------------------------------------------------------------
# Configuration — mirrors agent/equity_core.py and agent/signal_engine.py
# ---------------------------------------------------------------------------

@dataclass
class EdgeStackLiveC001Config(StrategyConfig):
    # --- core (agent/equity_core.py) ---
    core_weight:      float = 0.70    # CORE_WEIGHT
    trend_lookback:   int   = 252     # TREND_LOOKBACK
    credit_sma:       int   = 100     # CREDIT_SMA (HYG vs its own SMA)
    use_credit_gate:  int   = 1       # 1 = trend AND credit canary (live), 0 = trend only
    use_trend_gate:   int   = 1       # 0 = drop the 12-month trend requirement
    # 0 = core trades SPY (full-time, the engine's T+1 approximation)
    # 1 = core trades SPYON, a synthetic index whose bar-to-bar return IS the
    #     close->open move, so the OVERNIGHT-ONLY core becomes expressible here.
    core_overnight:   int   = 0

    # --- capitulation sleeve ---
    sleeve_batch:     float = 0.30    # SLEEVE_BATCH, split equally across the day's signals
    max_total_sleeve: float = 0.60    # MAX_TOTAL_SLEEVE
    hold_sessions:    int   = 3       # HOLD_SESSIONS
    stretch_trigger:  float = -2.5    # STRETCH_TRIGGER
    rv_window:        int   = 20
    stretch_lookback: int   = 5

    # --- volume tiers ---
    # 0 = live "next_open" table: trade >= vol_full_lo with NO upper bound
    # 1 = earlier engine port:    trade only vol_full_lo .. vol_med_lo
    tier_mode:        int   = 0
    vol_full_lo:      float = 1.8     # FULL tier floor (SMALL below this is refused)
    vol_med_lo:       float = 2.5     # MEDIUM tier floor

    # 1 = honour the tier size weights (proportional split), 0 = live behaviour.
    use_tier_size:    int   = 0
    med_size:         float = 0.60

    total_cap:        float = 0.98    # long-only budget ceiling

    # --- causal vol-regime core scaler (pre-registered 2026-08-31) ---
    vol_scale_mode:   int   = 0       # 0 = off (live behaviour), 1 = scale core
    vol_lookback:     int   = 21      # realized-vol window
    vol_median_lb:    int   = 504     # trailing median of realized vol (~2y)
    vol_scale_hi:     float = 0.60    # core multiplier when vol > trailing median

    # ---- BORROWED RULES from other hackathon entries (all default OFF) -------
    borrow_mtf_mom:   int   = 0
    mtf_fast:         int   = 5
    mtf_slow:         int   = 20
    mtf_sma_a:        int   = 50
    mtf_sma_b:        int   = 200
    borrow_rsi_veto:  int   = 0
    rsi_lb:           int   = 14
    rsi_max:          float = 70.0
    borrow_dd_brake:  int   = 0
    dd_lookback:      int   = 252
    dd_trigger:       float = 0.10    # SPY this far below its 252d high -> stand down
    borrow_mom63:     int   = 0
    mom63_window:     int   = 63

    # ---- INSTRUMENTATION (candidate only; every default = LIVE behaviour) ---
    fixed_warmup:       int   = 0     # 1 = warmup pinned to warmup_ref bars
    warmup_ref:         int   = 253   # = live max(trend_lookback+1, credit_sma+1)
    gate_priority:      int   = 0     # 1 = core sized first, sleeve gets the room
    use_partial_derisk: int   = 0     # 1 = fractional core when ONE gate fails
    partial_derisk_w:   float = 0.5   # the fraction kept in that case
    no_restack:         int   = 0     # 1 = never add a symbol already held
    sleeve_trail_pct:   float = 0.0   # 0.0 = timer-only exit (live); >0 = trail %


SLEEVE_SYMBOLS: List[str] = ["SPY", "QQQ", "SOXX", "XLV", "XLP", "HYG", "FDN"]
CORE_SYMBOL = "SPY"


class EdgeStackLiveC001Strategy(TrustyStrategy):
    """edgestack_live, unchanged, with its hard-coded rules made switchable."""

    def __init__(self, config: EdgeStackLiveC001Config) -> None:
        super().__init__(config)
        self._cfg: EdgeStackLiveC001Config = config
        self._bars_seen = 0
        depth = max(config.trend_lookback + 2,
                    config.credit_sma + 2,
                    config.rv_window + config.stretch_lookback + 2,
                    config.vol_lookback + 2)
        self._close: Dict[str, deque] = {s: deque(maxlen=depth) for s in SLEEVE_SYMBOLS}
        self._vol: Dict[str, deque] = {s: deque(maxlen=depth) for s in SLEEVE_SYMBOLS}
        # [symbol, weight, sessions_left, peak_close] — the 4th field is inert
        # bookkeeping unless sleeve_trail_pct > 0.
        self._sleeve: List[list] = []
        self._rvol_hist: deque = deque(maxlen=config.vol_median_lb)

    # ---------------------------------------------------------------- meta
    def name(self) -> str:
        return "edgestack_live_c001"

    def universe(self) -> List[str]:
        u = list(SLEEVE_SYMBOLS)
        if self._cfg.core_overnight:
            u.append("SPYON")
        return u

    def max_lookback_period(self) -> int:
        return 5

    @property
    def _warmup_bars(self) -> int:
        cfg = self._cfg
        if cfg.fixed_warmup:
            # HYGIENE FLAG: hold the first traded bar fixed so a lookback probe
            # is not also a start-date change. Inert at the live lookbacks.
            return max(cfg.warmup_ref, 1)
        return max(cfg.trend_lookback + 1, cfg.credit_sma + 1)

    # ---------------------------------------------------------- indicators
    @staticmethod
    def _sma(seq: deque, n: int) -> float:
        if len(seq) < n:
            return 0.0
        return sum(list(seq)[-n:]) / n

    def _trend_up(self) -> bool:
        c = self._close[CORE_SYMBOL]
        lb = self._cfg.trend_lookback
        if len(c) < lb + 1:
            return False
        return c[-1] / c[-1 - lb] - 1.0 > 0.0

    def _vol_multiplier(self) -> Tuple[float, Any]:
        """Causal vol-regime scaler for the CORE. Uses only the trailing median."""
        cfg = self._cfg
        c = self._close[CORE_SYMBOL]
        if not cfg.vol_scale_mode or len(c) < cfg.vol_lookback + 2:
            return 1.0, None
        px = list(c)[-(cfg.vol_lookback + 1):]
        rets = [math.log(px[i] / px[i - 1]) for i in range(1, len(px))
                if px[i - 1] > 0 and px[i] > 0]
        if len(rets) < cfg.vol_lookback - 1:
            return 1.0, None
        m = sum(rets) / len(rets)
        rv = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(252)
        # median is taken over PRIOR observations only, then today's is appended
        prior = sorted(self._rvol_hist)
        self._rvol_hist.append(rv)
        if len(prior) < 252:
            return 1.0, None
        med = prior[len(prior) // 2]
        if rv > med:
            return cfg.vol_scale_hi, f"vol {100*rv:.1f}% > med {100*med:.1f}%"
        return 1.0, f"vol {100*rv:.1f}% <= med {100*med:.1f}%"

    # ---- borrowed rules (each returns True when it BLOCKS the core) ---------
    def _mtf_blocks(self) -> bool:
        """team-v: needs positive 5d & 20d momentum and price above SMA50 & SMA200."""
        cfg = self._cfg
        c = self._close[CORE_SYMBOL]
        if len(c) < cfg.mtf_sma_b + 2:
            return False
        px = list(c)
        ok = (px[-1] > px[-1 - cfg.mtf_fast]
              and px[-1] > px[-1 - cfg.mtf_slow]
              and px[-1] > self._sma(c, cfg.mtf_sma_a)
              and px[-1] > self._sma(c, cfg.mtf_sma_b))
        return not ok

    def _rsi_blocks(self) -> bool:
        """cloudrise: RSI exhaustion veto."""
        cfg = self._cfg
        c = self._close[CORE_SYMBOL]
        if len(c) < cfg.rsi_lb + 2:
            return False
        px = list(c)[-(cfg.rsi_lb + 1):]
        gains = [max(px[i] - px[i - 1], 0.0) for i in range(1, len(px))]
        losses = [max(px[i - 1] - px[i], 0.0) for i in range(1, len(px))]
        ag = sum(gains) / len(gains)
        al = sum(losses) / len(losses)
        if al <= 0:
            return True                      # no losses at all -> maximally extended
        rsi = 100.0 - 100.0 / (1.0 + ag / al)
        return rsi > cfg.rsi_max

    def _dd_blocks(self) -> bool:
        """VibeHedge: stand down when SPY is far below its own trailing high."""
        cfg = self._cfg
        c = self._close[CORE_SYMBOL]
        if len(c) < cfg.dd_lookback + 1:
            return False
        window = list(c)[-cfg.dd_lookback:]
        hi = max(window)
        return hi > 0 and (window[-1] / hi - 1.0) < -abs(cfg.dd_trigger)

    def _credit_ok(self) -> bool:
        hyg = self._close["HYG"]
        sma = self._sma(hyg, self._cfg.credit_sma)
        return bool(hyg) and sma > 0 and hyg[-1] > sma

    def _tradeable_volume(self, volx: float) -> bool:
        """Live next_open tier table: SMALL refused, FULL and MEDIUM tradeable."""
        cfg = self._cfg
        if volx < cfg.vol_full_lo:
            return False                       # SMALL cell: inverts on delayed entry
        if cfg.tier_mode == 1 and volx >= cfg.vol_med_lo:
            return False                       # earlier port's hard 2.5x ceiling
        return True

    def _capitulation(self, sym: str) -> Tuple[bool, float, float]:
        cfg = self._cfg
        closes, vols = self._close[sym], self._vol[sym]
        need = cfg.rv_window + cfg.stretch_lookback + 1
        if len(closes) < need:
            return False, 0.0, 0.0
        c, v = list(closes), list(vols)
        rets = [math.log(c[i] / c[i - 1])
                for i in range(len(c) - cfg.rv_window, len(c))
                if c[i - 1] > 0 and c[i] > 0]
        if len(rets) < cfg.rv_window - 1:
            return False, 0.0, 0.0
        m = sum(rets) / len(rets)
        rv = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
        ref = c[-1 - cfg.stretch_lookback]
        if rv <= 0 or ref <= 0 or c[-1] <= 0:
            return False, 0.0, 0.0
        stretch = math.log(c[-1] / ref) / (rv * math.sqrt(cfg.stretch_lookback))
        avg_vol = sum(v[-cfg.rv_window:]) / cfg.rv_window
        if avg_vol <= 0:
            return False, 0.0, 0.0
        volx = v[-1] / avg_vol
        fires = stretch < cfg.stretch_trigger and self._tradeable_volume(volx)
        return fires, stretch, volx

    # ---------------------------------------------------------------- main
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

        weights: Dict[str, float] = {s: 0.0 for s in self.universe()}
        signals: Dict[str, Any] = {"bars_seen": self._bars_seen}

        if self._bars_seen <= self._warmup_bars:
            signals["state"] = "warming_up"
            return weights, signals

        # 1. age sleeve positions; a 3-session hold exits on its 3rd close
        for p in self._sleeve:
            p[2] -= 1
        self._sleeve = [p for p in self._sleeve if p[2] > 0]

        # 1b. RULE (OFF by default = live): the live sleeve has NO adverse-move
        #     exit at all; positions leave only on the timer above.
        if cfg.sleeve_trail_pct > 0.0:
            kept: List[list] = []
            for p in self._sleeve:
                c = self._close[p[0]]
                if not c:
                    kept.append(p)
                    continue
                px = c[-1]
                if px > p[3]:
                    p[3] = px
                if p[3] > 0 and px / p[3] - 1.0 <= -abs(cfg.sleeve_trail_pct) / 100.0:
                    signals[f"trail_{p[0]}"] = round(px / p[3] - 1.0, 4)
                    continue
                kept.append(p)
            self._sleeve = kept

        # 2. today's capitulation signals
        held = {p[0] for p in self._sleeve}
        fired: List[Tuple[str, float]] = []          # (symbol, tier size multiplier)
        for s in SLEEVE_SYMBOLS:
            ok, stretch, volx = self._capitulation(s)
            # RULE (OFF by default = live): the live sleeve may stack a second
            # helping into a name it already holds.
            if ok and cfg.no_restack and s in held:
                ok = False
            if ok:
                mult = cfg.med_size if volx >= cfg.vol_med_lo else 1.0
                fired.append((s, mult))
                signals[f"cap_{s}"] = f"{stretch:.2f}/{volx:.2f}x"

        # 3. new entries. Live equity_core splits the batch budget EQUALLY across
        #    the day's signals; use_tier_size=1 instead splits it in proportion to
        #    the tier size weights the signal engine already computes.
        if fired:
            current = sum(p[1] for p in self._sleeve)
            budget = max(0.0, min(cfg.sleeve_batch, cfg.max_total_sleeve - current))
            if budget > 0:
                if cfg.use_tier_size:
                    tot = sum(m for _s, m in fired)
                    for s, m in fired:
                        px0 = self._close[s][-1] if self._close[s] else 0.0
                        self._sleeve.append([s, budget * m / tot, cfg.hold_sessions, px0])
                else:
                    per = budget / len(fired)
                    for s, _m in fired:
                        px0 = self._close[s][-1] if self._close[s] else 0.0
                        self._sleeve.append([s, per, cfg.hold_sessions, px0])

        sleeve_total = 0.0
        for sym, w, _left, _pk in self._sleeve:
            weights[sym] = weights.get(sym, 0.0) + w
            sleeve_total += w

        # 4. core gate: 12-month trend AND (optionally) the credit canary
        trend = self._trend_up()
        credit = self._credit_ok()
        trend_ok = trend or not cfg.use_trend_gate
        credit_ok = credit or not cfg.use_credit_gate
        gate_open = trend_ok and credit_ok

        # RULE (OFF by default = live): the live core gate is BINARY — both
        # gates pass or the core is flat. use_partial_derisk keeps a fraction
        # when exactly one of the two ENABLED gates is passing.
        gate_mult = 1.0
        if cfg.use_partial_derisk and not gate_open:
            enabled = int(bool(cfg.use_trend_gate)) + int(bool(cfg.use_credit_gate))
            passing = (int(bool(cfg.use_trend_gate and trend))
                       + int(bool(cfg.use_credit_gate and credit)))
            if enabled == 2 and passing == 1:
                gate_open = True
                gate_mult = max(0.0, min(1.0, cfg.partial_derisk_w))

        blocks = []
        if cfg.borrow_mtf_mom and self._mtf_blocks():
            blocks.append("mtf_momentum")
        if cfg.borrow_rsi_veto and self._rsi_blocks():
            blocks.append("rsi_exhaustion")
        if cfg.borrow_dd_brake and self._dd_blocks():
            blocks.append("drawdown_brake")
        if cfg.borrow_mom63:
            c = self._close[CORE_SYMBOL]
            if len(c) > cfg.mom63_window:
                ref = list(c)[-1 - cfg.mom63_window]
                if not (ref > 0 and c[-1] / ref - 1.0 > 0.0):
                    blocks.append("mom63")
        if blocks:
            gate_open = False
        signals["borrowed_blocks"] = blocks

        vmult, vnote = self._vol_multiplier()
        core_w = (cfg.core_weight * vmult * gate_mult) if gate_open else 0.0

        # RULE (0 = live): WHO GETS THE BUDGET FIRST. The live file squeezes the
        # core into whatever the sleeve leaves, so every sleeve-frequency change
        # is also a core-sizing change. gate_priority=1 sizes the core first and
        # scales the sleeve into the remaining room (an allocation overlay: the
        # stored positions keep their nominal size).
        if cfg.gate_priority:
            core_w = max(0.0, min(core_w, cfg.total_cap))
            room = max(0.0, cfg.total_cap - core_w)
            if sleeve_total > room and sleeve_total > 0:
                shrink = room / sleeve_total
                for k in list(weights.keys()):
                    weights[k] = weights[k] * shrink
                sleeve_total *= shrink
        else:
            core_w = max(0.0, min(core_w, cfg.total_cap - sleeve_total))

        signals["vol_regime"] = vnote
        signals["vol_mult"] = vmult
        core_sym = "SPYON" if cfg.core_overnight else CORE_SYMBOL
        if core_w > 0:
            weights[core_sym] = weights.get(core_sym, 0.0) + core_w

        total = sum(weights.values())
        if total > cfg.total_cap:
            scale = cfg.total_cap / total
            weights = {k: v * scale for k, v in weights.items()}

        signals.update({
            "trend_up": trend, "credit_ok": credit, "gate_open": gate_open,
            "gate_mult": gate_mult,
            "core_w": round(core_w, 3), "sleeve_n": len(self._sleeve),
            "sleeve_w": round(sleeve_total, 3),
        })
        return weights, signals

    def teardown(self) -> None:
        pass

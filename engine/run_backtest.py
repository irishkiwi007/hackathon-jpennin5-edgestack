#!/usr/bin/env python3
"""
run_backtest.py — Generic bar-by-bar backtest runner for TrustyStrategy files.

Usage (called by the Rust API server as a subprocess):
    python3 run_backtest.py <strategy_file> <data_dir> [options_json]

options_json (optional, passed as the 3rd CLI argument):
    {
        "start_date":          "2020-01-01",   // ISO-8601, inclusive
        "end_date":            "2025-12-31",   // ISO-8601, inclusive
        "initial_capital":     100000.0,       // USD
        "slippage_bps":        5,
        "commission_bps":      5,
        "param_overrides":     {"fast_period": 20, "slow_period": 50}
    }

Output (stdout): JSON object with keys:
    fills           : list of {date, symbol, side, qty, price, commission}
    equity_curve    : list of {date, equity}
    metrics         : {cagr, max_drawdown, sharpe_ratio, total_return,
                       win_rate, profit_factor, total_trades,
                       start_date, end_date, duration_days}
    params          : {param_name: current_value, …}
    error           : str — set only on failure

The equity curve uses the EOD portfolio mark-to-market value.
All trades execute at next-bar open (T+1 execution, realistic for daily data).

Architecture
------------
This script is intentionally self-contained.  It loads historical CSVs
directly from data_dir rather than going through the Rust data pipeline,
which keeps the subprocess communication simple (no shared memory, no IPC
beyond stdin/stdout JSON).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
import traceback
from collections import defaultdict
from dataclasses import fields as dc_fields
from datetime import date as Date, timedelta, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def _load_ohlcv(path: Path, start: Optional[Date], end: Optional[Date]) -> Dict[str, Dict]:
    """
    Load a Yahoo Finance OHLCV CSV.
    Returns {date_str: {open, high, low, close, adj_close, volume}}.
    Applies split/dividend adjustment via the adj_close column.
    """
    rows: Dict[str, Dict] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 6:
                continue
            d_str = row[0].strip()
            if not d_str:
                continue
            try:
                d = Date.fromisoformat(d_str)
            except ValueError:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            try:
                raw_close  = float(row[4])
                adj_close  = float(row[5])
                adj_factor = adj_close / raw_close if raw_close > 0 else 1.0
                rows[d_str] = {
                    "open":      float(row[1]) * adj_factor,
                    "high":      float(row[2]) * adj_factor,
                    "low":       float(row[3]) * adj_factor,
                    "close":     adj_close,
                    "adj_close": adj_close,
                    "volume":    float(row[6]) if len(row) > 6 else 0.0,
                }
            except (ValueError, ZeroDivisionError):
                continue
    return rows


def _load_rate(path: Path, start: Optional[Date], end: Optional[Date]) -> Dict[str, Dict]:
    """
    Load a FRED rate/yield CSV (2-column: date, value).
    Returns {date_str: {open, high, low, close, adj_close, volume}}.
    All OHLC fields are set to the single rate value so BarSnapshot works.
    """
    rows: Dict[str, Dict] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            d_str = row[0].strip()
            val_str = row[1].strip()
            if not d_str or val_str in (".", ""):
                continue
            try:
                d = Date.fromisoformat(d_str)
            except ValueError:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            try:
                v = float(val_str)
                rows[d_str] = {
                    "open": v, "high": v, "low": v, "close": v,
                    "adj_close": v, "volume": 0.0,
                }
            except ValueError:
                continue
    return rows


def _rule_text(signals: Optional[Dict], limit: int = 160) -> str:
    """EdgeStack addition (2026-09-03): the strategy's signal dict at decision
    time, compacted to one line - what the trades table shows as the rule."""
    if not isinstance(signals, dict) or not signals:
        return ""
    parts = []
    for k, v in signals.items():
        if isinstance(v, float):
            s = f"{v:+.2%}" if abs(v) < 1.5 and k.lower().startswith(("r", "ret", "chg", "mom", "stretch")) else f"{v:.3g}"
        else:
            s = str(v)
        parts.append(f"{k}={s}")
    out = " | ".join(parts)
    return out if len(out) <= limit else out[:limit - 1] + "…"


# ---------------------------------------------------------------------------
# Portfolio + execution
# ---------------------------------------------------------------------------

class SimplePortfolio:
    """
    Minimal daily-resolution portfolio for strategy simulation.

    - Cash held in dollars; can go negative (margin borrowing).
    - Positions tracked as fractional share counts (3 dp, matching QC Alpaca).
    - Trades execute at next-bar OPEN (T+1), realistic for daily strategies.
    - Only rebalances when target weights change by > WEIGHT_THRESHOLD from the
      last executed set, matching QC's event-driven order placement.
    """
    # Minimum absolute weight change that triggers a rebalance.  Changes below
    # this are treated as "hold current position", preventing continuous drift-
    # based rebalancing that doesn't happen in QC's event-driven model.
    WEIGHT_THRESHOLD = 0.005  # 0.5 percentage points

    def __init__(self, initial_capital: float, slippage_bps: int, commission_bps: int) -> None:
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.slippage_bps = slippage_bps
        self.commission_bps = commission_bps
        self.positions: Dict[str, float] = defaultdict(float)  # symbol → fractional shares
        self.last_prices: Dict[str, float] = {}
        self._pending_weights: Optional[Dict[str, float]] = None
        self._active_weights: Dict[str, float] = {}  # weights from last execution

    def queue_weights(self, weights: Dict[str, float], signals: Optional[Dict] = None) -> None:
        # EdgeStack addition (2026-09-03): remember the strategy's own signal
        # dict at decision time, so every fill can say what triggered it.
        self._pending_rule = _rule_text(signals)
        # Skip if the new weights are effectively identical to the last executed
        # set (i.e., strategy is just "holding" with no meaningful change).
        if self._active_weights:
            all_syms = set(weights) | set(self._active_weights)
            max_chg = max(
                abs(weights.get(s, 0.0) - self._active_weights.get(s, 0.0))
                for s in all_syms
            ) if all_syms else 0.0
            if max_chg < self.WEIGHT_THRESHOLD:
                return
        self._pending_weights = weights

    def execute_pending(
        self,
        date_str: str,
        bars: Dict[str, "BarSnapshot"],
    ) -> List[Dict]:
        """Execute any queued target-weight orders at today's open price."""
        if self._pending_weights is None:
            return []
        fills = []
        target = self._pending_weights
        self._pending_weights = None
        rule = getattr(self, "_pending_rule", "")
        # Record these as the new active weights so subsequent identical calls
        # are skipped by queue_weights.
        self._active_weights = dict(target)

        # Mark-to-market before we start trading today (use current close estimates).
        portfolio_value = self._nav(bars, use_open=True)

        for symbol, target_weight in target.items():
            bar = bars.get(symbol)
            if bar is None:
                continue
            exec_price = bar.open * (1.0 + self.slippage_bps / 10_000.0)
            if exec_price <= 0:
                continue
            # Allow weights > 1.0 (margin / leveraged positions).
            # Negative cash represents margin borrowing; NAV = cash + holdings
            # handles this correctly since cash simply becomes negative.
            target_value = portfolio_value * max(0.0, target_weight)
            target_shares = round(target_value / exec_price, 3)  # fractional (3 dp = QC Alpaca)
            current_shares = self.positions.get(symbol, 0)
            delta = target_shares - current_shares
            if delta == 0:
                continue
            # Skip orders below the minimum notional (QC: min_order_notional = 3.0).
            if abs(delta * exec_price) < 3.0:
                continue

            commission = abs(delta) * exec_price * self.commission_bps / 10_000.0
            cost = delta * exec_price + commission

            self.cash -= cost
            self.positions[symbol] = current_shares + delta

            fills.append({
                "date":       date_str,
                "symbol":     symbol,
                "side":       "buy" if delta > 0 else "sell",
                "qty":        abs(delta),
                "price":      round(exec_price, 4),
                "commission": round(commission, 4),
                "rule":       rule,
            })

        # Liquidate any symbols that dropped out of the target set.
        for symbol in list(self.positions.keys()):
            if symbol not in target and self.positions[symbol] != 0:
                bar = bars.get(symbol)
                exec_price = (bar.open if bar else self.last_prices.get(symbol, 0.0))
                exec_price *= (1.0 - self.slippage_bps / 10_000.0)
                if exec_price <= 0:
                    continue
                shares = self.positions[symbol]
                commission = abs(shares) * exec_price * self.commission_bps / 10_000.0
                self.cash += shares * exec_price - commission
                fills.append({
                    "date": date_str, "symbol": symbol,
                    "side": "sell", "qty": abs(shares),
                    "price": round(exec_price, 4),
                    "commission": round(commission, 4),
                    "rule": rule,
                })
                self.positions[symbol] = 0

        return fills

    def nav(self, bars: Dict[str, "BarSnapshot"]) -> float:
        return self._nav(bars, use_open=False)

    def _nav(self, bars: Dict[str, "BarSnapshot"], use_open: bool) -> float:
        nav = self.cash
        for symbol, shares in self.positions.items():
            if shares == 0:
                continue
            bar = bars.get(symbol)
            if bar is not None:
                price = bar.open if use_open else bar.close
                nav += shares * price
                self.last_prices[symbol] = price
            elif symbol in self.last_prices:
                nav += shares * self.last_prices[symbol]
        return nav


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_metrics(
    equity_curve: List[Dict],
    fills: List[Dict],
    initial_capital: float,
) -> Dict:
    if len(equity_curve) < 2:
        return {}

    equities = [e["equity"] for e in equity_curve]
    dates    = [Date.fromisoformat(e["date"]) for e in equity_curve]

    # Daily returns.
    daily_returns = [
        (equities[i] - equities[i - 1]) / equities[i - 1]
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]

    # Total return.
    total_return = (equities[-1] - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    # CAGR.
    duration_days = max((dates[-1] - dates[0]).days, 1)
    years = duration_days / 365.25
    cagr = ((equities[-1] / initial_capital) ** (1.0 / years) - 1.0) if years > 0 and initial_capital > 0 else 0.0

    # Max drawdown.
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualised, risk-free = 0).
    n = len(daily_returns)
    if n > 1:
        mean_r = sum(daily_returns) / n
        std_r  = math.sqrt(sum((r - mean_r) ** 2 for r in daily_returns) / (n - 1))
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Win/loss from fills (round-trip matching, FIFO).
    pnl_per_trade: List[float] = []
    open_lots: Dict[str, List[Tuple[float, int]]] = defaultdict(list)  # symbol → [(price, qty)]
    for fill in fills:
        sym   = fill["symbol"]
        side  = fill["side"]
        qty   = fill["qty"]
        price = fill["price"]
        comm  = fill["commission"]
        if side == "buy":
            open_lots[sym].append((price, qty))
        else:
            remaining = qty
            while remaining > 0 and open_lots[sym]:
                open_price, open_qty = open_lots[sym][0]
                matched = min(remaining, open_qty)
                pnl = matched * (price - open_price) - comm * (matched / qty)
                pnl_per_trade.append(pnl)
                remaining -= matched
                if open_qty > matched:
                    open_lots[sym][0] = (open_price, open_qty - matched)
                else:
                    open_lots[sym].pop(0)

    wins   = [p for p in pnl_per_trade if p > 0]
    losses = [p for p in pnl_per_trade if p <= 0]
    win_rate = len(wins) / len(pnl_per_trade) if pnl_per_trade else 0.0
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    if profit_factor == float("inf"):
        profit_factor = gross_profit  # avoid JSON issues

    return {
        "cagr":           round(cagr, 6),
        "total_return":   round(total_return, 6),
        "max_drawdown":   round(max_dd, 6),
        "sharpe_ratio":   round(sharpe, 6),
        "win_rate":       round(win_rate, 6),
        "profit_factor":  round(profit_factor, 6),
        "total_trades":   len(pnl_per_trade),
        "avg_win":        round(sum(wins)   / len(wins)   if wins   else 0.0, 4),
        "avg_loss":       round(sum(losses) / len(losses) if losses else 0.0, 4),
        "start_date":     dates[0].isoformat(),
        "end_date":       dates[-1].isoformat(),
        "duration_days":  duration_days,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_backtest(strategy_path: str, data_dir: str, options: Dict) -> Dict:
    """Full pipeline: load strategy → load data → simulate → return results."""

    start_str  = options.get("start_date")
    end_str    = options.get("end_date")
    capital    = float(options.get("initial_capital", 100_000.0))
    slip_bps   = int(options.get("slippage_bps",   5))
    comm_bps   = int(options.get("commission_bps", 5))
    overrides  = options.get("param_overrides", {})

    start_date = Date.fromisoformat(start_str) if start_str else None
    end_date   = Date.fromisoformat(end_str)   if end_str   else None

    # Extend the data load window backward to pre-seed strategy indicators,
    # matching QC's History() construction-time seeding.  600 calendar days
    # (≈420 trading days) covers any strategy's max_lookback_period.
    WARMUP_EXTEND_DAYS = 600
    load_start = (start_date - timedelta(days=WARMUP_EXTEND_DAYS)) if start_date else None
    live_start_str = start_date.isoformat() if start_date else ""

    # ── Load strategy module ─────────────────────────────────────────────────
    p = Path(strategy_path).resolve()
    workspace_root = p.parent
    for _ in range(4):
        if (workspace_root / "bridge" / "strategy_interface.py").exists():
            break
        workspace_root = workspace_root.parent
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

    spec = importlib.util.spec_from_file_location("_bt_strategy_", str(p))
    if spec is None or spec.loader is None:
        return {"error": "Could not load strategy module"}

    mod = importlib.util.module_from_spec(spec)
    sys.modules["_bt_strategy_"] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop("_bt_strategy_", None)
        return {"error": f"Import error: {exc}\n{traceback.format_exc()}"}
    finally:
        sys.modules.pop("_bt_strategy_", None)

    try:
        from bridge.strategy_interface import TrustyStrategy, StrategyConfig, BarSnapshot
    except ImportError as exc:
        return {"error": f"Bridge import failed: {exc}"}

    strategy_classes = [
        c for c in vars(mod).values()
        if isinstance(c, type) and issubclass(c, TrustyStrategy) and c is not TrustyStrategy
    ]
    if not strategy_classes:
        return {"error": "No TrustyStrategy subclass found"}

    strategy_cls = strategy_classes[-1]

    config_classes = [
        c for c in vars(mod).values()
        if isinstance(c, type) and issubclass(c, StrategyConfig) and c is not StrategyConfig
    ]
    config_cls = config_classes[-1] if config_classes else None

    # Build config with overrides applied.
    config_kwargs: Dict[str, Any] = {}
    if config_cls is not None:
        for f in dc_fields(config_cls):
            if f.name in overrides:
                raw = overrides[f.name]
                try:
                    field_type = f.type if isinstance(f.type, type) else type(f.default)
                    config_kwargs[f.name] = field_type(raw)
                except (TypeError, ValueError):
                    config_kwargs[f.name] = raw

    config_instance = config_cls(**config_kwargs) if config_cls else None
    try:
        strategy = strategy_cls(config_instance) if config_instance is not None else strategy_cls()
    except Exception as exc:
        return {"error": f"Strategy instantiation failed: {exc}"}

    symbols  = strategy.universe()
    lookback = strategy.max_lookback_period()

    # ── Load historical data ─────────────────────────────────────────────────
    data_path = Path(data_dir)
    # Detect which symbols are rate series (2-column FRED CSVs).
    # Convention: load as rate if the file has only 2 columns on first data row.
    symbol_data: Dict[str, Dict[str, Dict]] = {}
    for sym in symbols:
        csv_path = data_path / f"{sym}.csv"
        if not csv_path.exists():
            return {"error": f"Missing data file: {csv_path}. Fetch historical data first."}
        # Sniff format.
        with open(csv_path) as f:
            header = next(csv.reader(f), [])
        is_rate = len(header) <= 2
        loader = _load_rate if is_rate else _load_ohlcv
        symbol_data[sym] = loader(csv_path, load_start, end_date)

    # SPY benchmark — loaded from load_start so the first live equity date
    # always has a valid price reference for benchmark anchoring.
    spy_path = data_path / "SPY.csv"
    spy_data: Dict[str, Dict] = {}
    if spy_path.exists():
        spy_data = _load_ohlcv(spy_path, load_start, end_date)

    # ── Build aligned date index ─────────────────────────────────────────────
    # Intersection of all symbols' available dates — only run on days all feeds have data.
    all_date_sets = [set(symbol_data[s].keys()) for s in symbols]
    if not all_date_sets:
        return {"error": "No data loaded for any symbol"}

    common_dates = sorted(all_date_sets[0].intersection(*all_date_sets[1:]))
    if len(common_dates) < lookback + 1:
        return {"error": f"Insufficient data: need {lookback + 1} bars, have {len(common_dates)}"}

    # ── Simulate bar-by-bar ──────────────────────────────────────────────────
    portfolio = SimplePortfolio(capital, slip_bps, comm_bps)
    all_fills: List[Dict] = []
    equity_curve: List[Dict] = []
    bad_bar_streak = 0
    bad_bar_threshold = (
        config_instance.consecutive_bad_bars_threshold
        if config_instance is not None
        else 3
    )

    for bar_idx, date_str in enumerate(common_dates):
        # is_live: bar falls within the requested backtest window.
        # Pre-start bars advance indicator state but produce no fills and are
        # excluded from the equity curve — replicating QC's History() seeding.
        is_live = not live_start_str or date_str >= live_start_str

        # Build BarSnapshot dict for this date.
        bars_today: Dict[str, BarSnapshot] = {}
        bar_ok = True
        for sym in symbols:
            row = symbol_data[sym].get(date_str)
            if row is None or row["close"] <= 0:
                bar_ok = False
                break
            bars_today[sym] = BarSnapshot(
                open=row["open"], high=row["high"], low=row["low"],
                close=row["close"], volume=row["volume"],
                time=datetime.fromisoformat(date_str),
            )

        if not bar_ok:
            if is_live:
                bad_bar_streak += 1
                if bad_bar_streak >= bad_bar_threshold:
                    # Circuit breaker: liquidate to cash.
                    portfolio.queue_weights({})
                equity_curve.append({"date": date_str, "equity": round(portfolio.nav(bars_today), 2)})
            continue

        bad_bar_streak = 0

        # Execute any T+1 orders (live bars only).
        if is_live:
            fills = portfolio.execute_pending(date_str, bars_today)
            all_fills.extend(fills)

        # Call strategy on every bar — including pre-start — so all indicators
        # are fully warmed by the time the first live bar is reached.
        try:
            weights, _signals = strategy.calculate_target_weights(bars_today)
        except Exception as exc:
            weights, _signals = {}, {"error": str(exc)[:200]}

        if is_live:
            portfolio.queue_weights(weights, _signals)
            equity_curve.append({"date": date_str, "equity": round(portfolio.nav(bars_today), 2)})

    # Execute any final pending orders (not needed for metrics — omit).

    # EdgeStack addition (2026-09-02): the last bar's target weights and
    # signals, so the live manager can drive a deployment from the SAME
    # runner that backtests it (one code path, no re-implementation).
    final_weights = dict(weights) if "weights" in locals() else {}
    final_signals = {}
    try:
        final_signals = {k: (v if isinstance(v, (int, float, str)) else str(v))
                         for k, v in (_signals or {}).items()}
    except Exception:
        final_signals = {}
    last_bar_date = common_dates[-1] if common_dates else None

    # ── SPY benchmark equity curve ───────────────────────────────────────────
    benchmark_curve: List[Dict] = []
    if spy_data and equity_curve:
        # Anchor benchmark to the first live trading date (equity_curve[0]),
        # not the extended pre-warmup start.
        first_live_spy = spy_data.get(equity_curve[0]["date"])
        first_price = first_live_spy["close"] if first_live_spy else 1.0
        for e in equity_curve:
            spy_row = spy_data.get(e["date"])
            if spy_row and first_price > 0:
                benchmark_curve.append({
                    "date":   e["date"],
                    "equity": round(capital * spy_row["close"] / first_price, 2),
                })

    # ── Collect current param values ─────────────────────────────────────────
    current_params: Dict[str, Any] = {}
    if config_cls is not None and config_instance is not None:
        for f in dc_fields(config_cls):
            if f.name == "consecutive_bad_bars_threshold":
                continue
            current_params[f.name] = getattr(config_instance, f.name, None)

    metrics = _compute_metrics(equity_curve, all_fills, capital)

    return {
        "fills":           all_fills,
        "equity_curve":    equity_curve,
        "benchmark_curve": benchmark_curve,
        "metrics":         metrics,
        "params":          current_params,
        "final_weights":   final_weights,
        "final_signals":   final_signals,
        "last_bar_date":   last_bar_date,
        "universe":        symbols,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: run_backtest.py <strategy_file> <data_dir> [options_json]"}))
        sys.exit(1)

    options: Dict = {}
    if len(sys.argv) >= 4:
        try:
            options = json.loads(sys.argv[3])
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"Invalid options JSON: {exc}"}))
            sys.exit(1)

    result = run_backtest(sys.argv[1], sys.argv[2], options)
    print(json.dumps(result))

# The agent

Three deterministic components; the LLM proposes, a rule engine disposes. Nothing in the
decision path consults a model.

1. **Equity core** — long SPY overnight only (market-on-close in, market-at-open out), gated
   by the 12-month trend AND the credit canary (HYG > its own 100d SMA — adopted from the
   user's `canaries` strategy after passing both disjoint engine windows; ENGINE-TRIAL.md).
2. **Equity sleeve** — capitulation basket across 7 ETFs (stretch < -2.5, volume band with
   the load-bearing 2.5x ceiling), 0.3x batches, 0.6x cap, 3-session hold, close-to-close.
3. **Options component** — capitulation bull put spreads on the liquid core, behind 14
   deterministic risk gates (macro regime, friction, liquidity, sizing).

Evidence: [EDGE-PORTFOLIO.md](EDGE-PORTFOLIO.md), [ENGINE-TRIAL.md](ENGINE-TRIAL.md),
[HERD-REVERSAL.md](HERD-REVERSAL.md).

## Decision rule

On a daily bar:

    stretch = log(C[t] / C[t-5]) / (rv20 * sqrt(5))     rv20 = sd of last 20 daily log returns
    volx    = V[t] / mean(V[t-19..t])

    FIRE LONG when stretch < -2.5 and volx clears the tier floor. Hold 3 sessions.

Measured over 33 years, 7 ETFs, entering at the signal-day close:

| volume cell | n | mean | win | t |
|---|---|---|---|---|
| <1.0x | 38 | -0.172% | 47.4% | -0.53 |
| 1.0-1.4x | 47 | +0.184% | 48.9% | 0.21 |
| 1.4-1.8x SMALL | 59 | +0.721% | 64.4% | 2.67 |
| **1.8-2.5x FULL** | 77 | **+1.897%** | **70.1%** | **4.32** |
| >2.5x MEDIUM | 58 | +1.312% | 65.5% | 3.96 |

Combined (>1.8x): n=135, +1.646%, win 68.1%, **t=5.42**, robust to dropping any single era
(t stays 4.32-5.40). Surrogate-confirmed: real +0.572% vs shuffled +0.002% [-0.126, +0.148].

**The peak at 1.8-2.5x, then the fall-off above 2.5x, is the mechanism's own boundary
condition.** Extreme volume means real information arrived, so there is less to revert. The
ceiling is load-bearing — removing it degrades the edge.

## Layout

| file | role |
|---|---|
| `agent/signal_engine.py` | pure signal. No network, no model, no side effects |
| `agent/yahoo_feed.py` | live consolidated price+volume; enables same-day entry |
| `agent/spread_builder.py` | Signal -> priced, Alpaca-legal bull put spread |
| `agent/risk_gates.py` | 13 deterministic gates; nothing bypasses them |
| `agent/broker.py` | thin Alpaca client, paper-only by construction |
| `agent/journal.py` | append-only decision journal, JSONL + markdown |
| `agent/equity_core.py` | overnight core + capitulation sleeve, gate, MOC orders, state |
| `agent/run_agent.py` | one session pass (options + equity) |
| `agent/scheduler.py` | keeps it live unattended |

## Verification

    python agent/test_signal_engine.py     # engine reproduces the study exactly
    python agent/test_risk_gates.py        # every gate rejects what it claims to

`test_signal_engine.py` walks 44,787 bars through the same entry point the live agent calls and
requires n, mean and win rate to match the study on every tier. It currently matches to three
decimals (n exact, mean exact, win within 0.05pp).

`test_risk_gates.py` runs 21 cases and requires the RIGHT gate to object in each - a gate that
never fires is not a control.

## Running

    python agent/run_agent.py --dry-run    # decide and journal, submit nothing
    python agent/run_agent.py              # decide, submit, journal
    python agent/scheduler.py              # unattended: exits 09:31 ET, entries 15:45 ET

Keys come from `.env` (gitignored). Paper only — `broker.py` raises if asked for live.

## Known limits

- **Fires rarely.** ~0.15 signals/day across 50 ETFs, and signals CLUSTER (a market-wide selloff
  fires many at once, a calm week fires none). Expect roughly 1-2 in a 5-session window, possibly
  zero. Every attempt to raise the rate destroyed the edge: looser thresholds, intraday bars,
  cross-sectional pairs, single stocks. The constraint is structural.
- **Execution friction is the binding operational constraint.** Crossing the spread costs $2/
  contract on IWM and $105 on SOXX for the identical structure - a 50x range. Paying it on a
  broad ETF list ($70/contract, $140 round trip) exceeds the entire gross edge. The agent quotes
  at MID and `gate_friction` refuses anything whose round-trip crossing exceeds 40% of gross
  edge, using live quotes. Which names you trade matters more than any signal parameter.
- **The option-level edge is not statistically established.** The underlying move is
  (t=5.42 over 33 years; +1.360% vs -0.187% control out-of-sample). The bull put spread is
  chosen on mechanism — long delta, short vega, and implied volatility is elevated at entry
  (ATM call IV 0.652 signal vs 0.433 calm) — plus its relative result (+$221.7/contract vs
  control, t=3.03). Its absolute return measured +$37.8, t=1.26: not significant.
  Alpaca serves no historical option quotes, so backtest prices are asynchronous and the
  contamination is irreducible. Live pricing is clean.

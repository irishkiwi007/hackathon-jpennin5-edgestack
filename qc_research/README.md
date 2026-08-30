# QuantConnect trial — edge stack

`edge_stack.py` is a self-contained QCAlgorithm implementing the validated equity strategy
from [EDGE-PORTFOLIO.md](../EDGE-PORTFOLIO.md):

- **Core**: long SPY overnight only (enter ~15:58 ET, exit ~09:31 ET), gated by the
  12-month trend.
- **Sleeve**: capitulation basket at 0.5x weight — 5-day stretch < -2.5 sigma AND volume
  1.5-2.5x its 20-day mean, 3-session hold, across SPY/QQQ/SOXX/XLV/XLP/HYG/FDN.

## How to run

1. quantconnect.com → Create New Algorithm → Python.
2. Replace the contents of `main.py` with `edge_stack.py`. Run.
3. First pass: the default 2010-2026 window at minute resolution is slow on the free tier —
   shorten to 2018-2026 for a quick sanity run, then do the full window.

## What to compare against

Research backtest (SPY-based, 1994-2026, 1bp round-trip costs):

| configuration | CAGR | vol | Sharpe | max DD |
|---|---|---|---|---|
| buy and hold | 7.98% | 18.81% | 0.32 | -58.9% |
| core only | 8.01% | 7.92% | 0.76 | -24.9% |
| **core + sleeve 0.5x (this algo)** | **9.72%** | **9.07%** | **0.85** | **-26.6%** |

Expect QC to come in somewhat different: its own fill/slippage models, its own dividend
adjustment, and sleeve entries here use a 15:45 volume *estimate* (scaled by the measured
0.894 completion factor) with a 1.5x floor instead of the research's exact-close 1.4x — a
deliberate safety margin that drops a few marginal events. Directionally the three-way
ranking (buy-and-hold < core < core+sleeve) and the drawdown profile are what the trial
should confirm. If QC shows core+sleeve *below* core only, something is wrong — say so.

## Verification already done locally

The signal arithmetic in `_capitulation` was replayed over the 33-year CSV record and
reproduces the research exactly: **136 events, +1.44% mean 3-session move, 67.6% win**
(research: 136, +1.42%, 67.6%). A window-convention bug found during transcription
(completed-sessions-only windows gave 190 weaker events) is fixed and documented in the
code comment.

## Not included in this trial

The earnings iron-condor options sleeve (15.31% return-on-risk, t=4.79). It needs QC option
chains plus an earnings calendar — separate file, separate trial, after the equity stack is
confirmed.

## Result — run 2026-08-30 ("Pensive Tan Kitten", default config, credit canary ON)

Full window 2010-01-04 → 2026-06-01, minute resolution, QC's own fill models and its
Interactive Brokers fee model: **$25,149 in fees ≈ 4.4bp per round trip — ~4x the research's
1bp assumption**. Completed clean: 7,589 orders, no runtime errors. The sleeve fired on all
7 ETFs (~79 non-SPY round trips vs 84 research-engine events in the window — the deliberate
1.5x volume floor dropping a few marginal events, as designed).

Because QC's dashboard Sharpe uses its own variable risk-free model (it prints 0.35 for this
curve), everything below is restated in the research convention, Sharpe = (CAGR − 2%) / vol,
computed from the exported equity curve. Period-matched rows come from rerunning
`scripts/equity_wide.py` restricted to the exact QC window
(`simulate(0.5, False, True)` etc. — same code that produced the 33-year table above).

| configuration (2010-2026 window) | CAGR | vol | Sharpe | max DD |
|---|---|---|---|---|
| buy and hold (research data, no costs) | 14.03% | 17.15% | 0.70 | -33.7% |
| core only (research engine) | 4.88% | 9.10% | 0.32 | -24.9% |
| core + sleeve 0.5x (research engine) | 6.62% | 9.76% | 0.47 | -26.6% |
| **core + sleeve 0.5x + canary (QC, this run)** | **6.97%** | **8.84%** | **0.56** | **-24.2%** |

### What the trial confirms

1. **Engine independence.** Year-by-year correlation between QC and the research engine is
   **+0.87** (mean absolute yearly gap 3.6pp), and QC lands **above** its period-matched
   research twin — 0.56 vs 0.47 — despite ~4x the cost assumption. The overnight
   close→open core, the one piece no other engine could express (TrustyRustyEngine fills at
   next open only), survives its first minute-resolution replay with real fills and fees.
2. **The drawdown profile.** -24.2% vs -33.7% buy-and-hold in-window (-59% full record) —
   inside the -20% to -30% band expected before the run.
3. **The credit canary doesn't hurt the overnight core.** This run (canary ON) beats the
   trend-only research twin on every line, and the yearly gaps carry the canary's
   signature: better in credit-stress years (2015: -2.3% vs -9.2%; 2020: +5.6% vs +0.8%;
   2022: -2.4% vs -9.8%), worse in 2010 when HYG chopped around its 100d SMA. A clean A/B
   still needs a `USE_CREDIT_CANARY = False` run; nothing here suggests harm.
4. QC estimates strategy capacity at **$130M** (binding asset: SPY).

### What the trial does not show

- **The 33-year Sharpe.** Before the run we expected 0.6-0.9, a band calibrated to the
  full-record 0.85. Measured: 0.56. The gap is the *window*, not the engine — the same
  research code restricted to the same window gives 0.47, and the era table published
  before this trial says why: the stack *"wins decisively in every bear market and lags in
  strong bulls,"* and 2010-2026 contains exactly one bear. On this window buy-and-hold
  beats the stack in **both** engines (0.70 vs 0.56/0.47). The pre-registered red flag —
  core+sleeve below core — did **not** trigger.
- **Component attribution inside QC.** One run cannot separate core from sleeve or canary
  from trend. Two optional follow-up backtests would close this: `SLEEVE_WEIGHT = 0`
  (core-only ranking check) and `USE_CREDIT_CANARY = False` (canary A/B).

**Verdict: the stack's first fully independent minute-resolution replay agrees with the
research engine year-by-year and lands above its period-matched twin under real costs.
Engine risk is retired; window sensitivity was already on the record before the trial.**

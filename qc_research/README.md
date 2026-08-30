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

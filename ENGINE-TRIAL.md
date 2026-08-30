# TrustyRustyEngine trial — edgestack port and rule sweep

Strategy file: `TrustyRustyEngine-main/python_strategies/strategies/edgestack.py`
(runs via the engine's own `run_backtest.py`; every config field is sweepable through
`param_overrides`). Sweep drivers: `scripts/sweep_edgestack.py`, `scripts/sweep_phase3.py`.

## Engine adaptations (execution model changes the rules)

1. **No overnight-only core.** The engine fills at next-bar OPEN only (T+1); close fills do
   not exist, so "hold close->open" is inexpressible. Core = trend-gated full-time SPY.
   This forfeits the research stack's main trick (shedding the zero-Sharpe intraday hours),
   so engine Sharpe is expected below the research 0.85.
2. **Sleeve enters at next open** — exactly the delay-study variant, so the default
   vol_floor is 1.8 (the 1.4-1.8x tier inverted on delayed entry in research).
3. Long-only, cash-constrained: core+sleeve budgeted to <= 0.98, sleeve priority.
4. Engine costs kept at its defaults: 5bps slippage + 5bps commission per side
   (10x the research assumption — deliberate, it is the engine's realism).

## Engine quirk found and worked around

**Double warmup**: the runner skips the first `max_lookback_period()` bars *without feeding
them to the strategy*, and a strategy that also self-gates then waits again — on a 2007
start, every config went live ~April 2009, the exact GFC bottom (buy-and-hold showed an
impossible -18% max DD). Fix: report a tiny lookback to the runner and self-gate internally.
`spxlrealyields.py` has the same double-warmup pattern (111+111 bars) — worth checking.

Also noted: the runner re-queues target weights every bar, so integer-share drift produces
~1 small rebalance fill per day (inflates trade counts, small commission drag).

## Sweep protocol

Train 2007-2017 (effective ~2008-04+, includes GFC) -> pick winners -> validate 2017-2026
(effective 2018+). A rule change counts only if it survives validation.

## Results

| config | TRAIN Sharpe | VALID Sharpe | VALID DD |
|---|---|---|---|
| always-on core (no trend gate) | 0.51 (DD 50.7%) | — | — |
| B1 trend core only | 0.71 | 0.61 | 28.0% |
| **B3 research default (core .7 / sleeve .3)** | 0.80 | **0.65** | 21.2% |
| C1 "improved" (stretch -2.0, sleeve .5) | **0.89** | 0.44 | 28.1% |
| C2 C1+hold5 | 0.76 | 0.43 | 27.8% |
| C3 C1+core.98 | 0.82 | 0.49 | 32.7% |
| B3 + calm filter | 0.77 | 0.65 | **20.7%** |

## Conclusions

1. **Every train-window "improvement" failed validation.** C1 gained +0.09 Sharpe in
   training and gave back -0.21 out-of-sample. The untuned research parameters were the
   best sleeve config on validation. The sweep's real product is *negative*: the original
   rules survived an attempt to beat them, which is worth more than a tuned Sharpe.
2. **The trend gate is confirmed in-engine**: always-on core 0.51/-50.7% DD vs gated
   0.71/-19.4% (train).
3. **The sleeve itself survives out-of-sample**: B3 beats core-only on validation
   (0.65 vs 0.61) with much lower DD (21.2% vs 28.0%).
4. **vol_floor 1.8 vs 1.4**: train weakly favours 1.8 (0.80 vs 0.76), validation weakly
   favours 1.4 inside the C1 family (0.51 vs 0.44). Verdict: noise-level either way in this
   engine; keeping 1.8 on the strength of the original delay study, not the sweep.
5. **Calm-bond filter**: Sharpe-neutral, mild drawdown reduction (21.2% -> 20.7% val).
   Optional; default off.
6. Engine Sharpe (0.65 val / 0.80 train) sits below the research stack's 0.85 as expected:
   no overnight-only core, and 10x the transaction costs.

## Recommended engine config

**The defaults as shipped** (core_mode 1, core .70, sleeve .30/.60, stretch -2.5,
volume 1.8-2.5x, hold 3). The sweep earned its keep by failing to improve on them.

## What the engine cannot test

The overnight-only core (needs close fills) and the earnings iron condor (needs options).
Those remain QuantConnect / live-agent territory.

---

# Cross-pollination — rules borrowed from spxlrealyields and canaries

Every distinct rule in the repo's other two strategies was extracted and tested as a flag on
edgestack (v2 of the strategy file; all flags default to v1 behavior — regression run
reproduced 0.80/0.65 exactly). Same discipline as before: a rule counts only if it helps on
BOTH the train window and the disjoint validation window. Drivers:
`scripts/sweep_phase4.py`, `scripts/sweep_phase5.py`.

## Verdicts (Sharpe train -> valid, vs baseline 0.80 -> 0.65)

| rule | source | train | valid | verdict |
|---|---|---|---|---|
| **credit canary: HYG > own SMA100 added to core gate** | canaries | **0.98** | **1.02** | **ADOPTED** |
| trailing stop 15% from HWM | both | 0.81 | 0.73 | pass alone; adds nothing on top of G1 (never triggers) |
| risk_on gate (HYG/IEF ratio & TLT-vol) | spxlrealyields | 0.77 | 1.07, DD 5.7% | risk-profile option — halves CAGR, near-eliminates DD |
| TLT-vol calm construction | spxlrealyields | — | — | already adopted earlier (the sleeve calm filter) |
| risk-off park in defensives (XLP/XLV) | both | 0.67 | 0.77 | fails train |
| risk-off park in defensives+gold (WPM/RGLD) | both | 0.70, DD 33% | 0.96 | fails train — gold miners were lethal in the GFC |
| FDN > SMA200 canary | canaries | 0.71 | 0.77 | fails train |
| QQQ/SOXX divergence canary | canaries | 0.80 | 0.55 | fails valid |
| weekly (5-bar) gate cadence | canaries | 0.85 | 0.63 | fails valid |
| ATR-pullback "sniper" sleeve entries | canaries | 0.77 | 0.69 | fails train |
| real-yield-slope gold gate | spxlrealyields | — | — | not tested here; research measured t=-1.03 |

## The adopted rule

Core gate becomes: **SPY 12-month trend up AND HYG above its own 100-day SMA.**

| window | B3 (trend only) | G1 (trend + credit canary) |
|---|---|---|
| TRAIN 2008-2017 | 0.80, DD 15.0% | **0.98, DD 11.0%** |
| VALID 2018-2026 | 0.65, DD 21.2% | **1.02, DD 11.8%** |
| FULL 2007-2026 | 0.75, DD 21.2%, CAGR 7.14% | **1.04, DD 11.8%, CAGR 7.68%** |

Higher return, ~25% less volatility, drawdown nearly halved — in both disjoint windows.
The trailing stop becomes redundant under it: credit deteriorates and closes the core before
a 15% drawdown can accumulate, which is itself evidence the gate exits for the right reason.

Mechanistic note: this is consistent with the session's recurring boundary — capitulation
reverts only when selling is emotional, not informational (volume ceiling, TLT-vol overlay).
Deteriorating credit marks informational risk at the macro level. Also an instructive
contrast: the HYG/IEF *ratio* construction failed the earlier out-of-sample test as a
*sleeve conditioner*, while HYG-vs-its-own-SMA as a *core exposure gate* passes both windows.
Same instrument, different construction, different role, opposite verdict.

## Caveats

- Single-history evidence; HYG limits everything to 2007+. Each window contains essentially
  one credit crisis (2008 | 2020+2022) — the effective n of crises is small.
- G1 survived the same both-windows bar that killed every phase-3 parameter tuning, which is
  the strongest evidence standard available in this engine, but it is not a t-statistic.

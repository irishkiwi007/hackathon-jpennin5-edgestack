# Vol-regime conditioning

**Hypothesis tested:** harvest theta (short premium) when vol is low; buy straddles when vol is high.

> ## ⚠️ HEADLINE CORRECTION
>
> An earlier version of this file concluded the hypothesis was "inverted on both legs." **That was
> wrong**, and the error is instructive.
>
> Stage 1 below establishes that realised vol mean-reverts hard from both extremes — that part is
> solid, 33 years, six eras, no exceptions. But it then priced a hypothetical straddle **off
> trailing realised vol**, and concluded selling premium in calm markets must lose.
>
> **Options are not priced off trailing realised vol.** Measured on real chains, IV/RV runs
> **0.94 in low-vol regimes and 0.60 in high-vol regimes** — the market already discounts high
> trailing vol because it knows vol mean-reverts. The mean reversion is *in the price*.
>
> Once real prices are used (`scripts/straddle.py`), the result flips to **support** the
> hypothesis: short straddles in the low-vol tercile returned **+$567/trade, 70% win, t = 3.62**.
> See `THETA-REGIME.md` for the validated version and its caveats.
>
> What survives from Stage 1 is the **vol-dynamics** table. What does not survive is its
> straddle-economics proxy, which mispriced the option.

`scripts/volregime.py`.

---

## The mechanism

"Short premium in low vol" only works if forward realised vol comes in *below* what the option was
priced at. Options price off something close to recent realised vol. So the testable core is:
**conditional on trailing vol, does forward vol come in above or below trailing?**

## Forward vs trailing vol by decile — SPY, 8,328 observations, 1993–2026

| Decile | Trailing RV band | Mean trailing | Mean forward | **fwd/trail** | **P(fwd < trail)** |
|---|---|---|---|---|---|
| **1** | 3.2–7.4% | 6.4% | 9.9% | **1.560** | **14.8%** |
| 2 | 7.4–8.9% | 8.2% | 10.9% | 1.323 | 29.1% |
| 3 | 8.9–10.3% | 9.6% | 11.7% | 1.221 | 29.9% |
| 4 | 10.3–11.7% | 10.9% | 11.8% | 1.079 | 49.3% |
| 5 | 11.7–13.4% | 12.5% | 12.7% | 1.019 | 60.9% |
| 6 | 13.4–15.3% | 14.3% | 14.8% | 1.033 | 60.7% |
| 7 | 15.3–17.7% | 16.4% | 16.6% | 1.015 | 56.9% |
| 8 | 17.7–20.8% | 19.2% | 18.8% | 0.977 | 57.9% |
| 9 | 20.8–26.3% | 23.0% | 21.3% | 0.928 | 70.4% |
| **10** | 26.3–94.0% | 37.7% | 30.1% | **0.796** | **79.8%** |

**Vol mean-reverts in both directions.** From the calmest decile, forward vol runs **56% higher**
than trailing and falls below it only **14.8%** of the time. From the most stressed decile, forward
vol runs **20% lower** and falls below trailing **79.8%** of the time.

This is the robust part and it holds in every era. What it does *not* license is a conclusion about
premium selling — that requires knowing what the option costs, and the market prices this effect in.

## It holds in every era

| Era | Lowest tercile fwd/trail | Highest tercile fwd/trail |
|---|---|---|
| 1993–2002 | 1.176 | 0.872 |
| 2003–2007 | 1.263 | 0.868 |
| 2008–2012 | 1.272 | 0.906 |
| 2013–2019 | 1.502 | 0.748 |
| 2020–2022 | 1.579 | 0.818 |
| 2023–2026 | 1.314 | 0.854 |

Low tercile **> 1 in all six**. High tercile **< 1 in all six**. No exceptions in 33 years.

## Straddle economics proxy — SUPERSEDED, kept to show the error

Share of 21-day windows where the actual move stayed inside a straddle priced off trailing vol
(premium ≈ 0.8 × the 1-sigma move):

| Decile | Trailing RV | Implied 21d move | Actual \|move\| | Ratio | **Short straddle wins** |
|---|---|---|---|---|---|
| **1** | 6.4% | 1.84% | 2.25% | 1.222 | **35.5%** |
| 2 | 8.2% | 2.38% | 2.29% | 0.961 | 44.7% |
| 3 | 9.6% | 2.77% | 2.34% | 0.843 | 53.8% |
| 4 | 10.9% | 3.16% | 2.48% | 0.785 | 59.5% |
| 7 | 16.4% | 4.73% | 3.68% | 0.779 | 57.3% |
| 9 | 23.0% | 6.64% | 4.66% | 0.702 | 64.8% |
| **10** | 37.7% | 10.90% | 6.01% | 0.551 | **76.3%** |

A monotone gradient from **35.5% → 76.3%**, suggesting short straddles lose in calm markets.

**This table is wrong**, because it prices the straddle at trailing vol. Real chains show IV/RV of
0.94 in low vol and 0.60 in high vol. Correcting for actual pricing reverses the low-vol cell —
see `THETA-REGIME.md`.

---

## What this says about right now

Current **RV20 = 10.40%** → decile 3–4. Short-straddle win rate in that band is 53.8–59.5%, mildly
favourable to selling *if* the option were priced off trailing vol.

**But it isn't.** Measured front IV is **7.88%** (1 DTE) to **10.62%** (5 DTE) against trailing RV
of **10.40%** — implied is at or *below* trailing. So the straddle is cheaper than this proxy
assumes, which pushes the balance toward buying.

Two independent effects now point the same way:

1. **Mean reversion** — from decile 3–4, forward vol runs 1.08–1.22× trailing, i.e. ~11–12%
2. **Cheap premium** — implied (7.9–10.6%) sits at or below trailing (10.4%)

Expected forward realised (~11–12%) **exceeds** implied (~8–10.6%). That is a case for **long
premium**, and it is the opposite of what most of the surveyed field is running.

## Why this matters more than the earlier work

It is the second finding to survive all 33 years and six regimes — alongside the variance-ratio
violation. Both are structural facts about vol dynamics rather than artifacts of one chain snapshot,
and neither depends on the option-price history that has been the binding constraint everywhere else.

**Caveat:** this is a *directional* result about when to be long or short premium. It is not yet a
tradeable strategy — sizing, structure and the drift interaction still have to be settled, and the
real-price validation is in `scripts/straddle.py`.

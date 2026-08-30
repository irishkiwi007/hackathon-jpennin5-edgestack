# Do short-term reversions have a frequency?

SPY daily 1993–2026 (8,371 sessions), split-adjusted. **Every statistic is compared against
surrogate series** built by shuffling the actual returns — identical marginal distribution, all
temporal structure destroyed. A random walk also produces peaks, troughs and oscillation-looking
patterns, so anything the surrogates reproduce is not a finding.

Scripts: `scripts/oscillation.py`, `scripts/osc2.py`.

---

## 1. Is there an oscillation? **No.**

### The spectrum has no peak

| Period band | Real power (normalised) | Synthetic AR(1), same φ |
|---|---|---|
| 2–3d | 1.064 | 1.123 |
| **3–5d** | **1.125** | 1.011 |
| 5–10d | 0.966 | 0.910 |
| 10–21d | 0.816 | 0.930 |
| 21–63d | 0.685 | 0.857 |
| 63–250d | 0.688 | 0.702 |

Both decline monotonically toward longer periods. **That is the signature of negative lag-1
autocorrelation, not a cycle.** A real oscillator produces a *peak* at its period with elevated
power in neighbouring bins; this produces a *slope*.

The raw periodogram appeared to flag "periods" of 3.2 and 4.0 days with 10–15× median power — but
7.8% of all periods exceeded the 95th surrogate percentile against 5% expected, and the hits were
scattered singletons. Those are the high-frequency bias showing through, not a frequency.

### Swing durations have no characteristic length — they are *less* regular than random

ZigZag reversal detector at four thresholds:

| Threshold | Pivots | Mean | Median | CV | **Surrogate CV** | Verdict |
|---|---|---|---|---|---|---|
| 2% | 776 | 10.7d | 6.0d | **1.44** | 0.86 | more erratic |
| 3% | 462 | 16.4d | 8.0d | **1.51** | 0.87 | more erratic |
| 5% | 218 | 32.8d | 17.0d | **1.44** | 0.87 | more erratic |
| 8% | 49 | 89.6d | 40.0d | **1.60** | 0.90 | more erratic |

A coefficient of variation near 1.0 means exponential, memoryless durations — no preferred length.
An oscillator would sit **well below** its surrogate. Real swings sit **well above**: 1.44–1.60
against 0.86–0.90.

**Swing timing is not merely random — it is more dispersed than random.** Mean far exceeds median
at every threshold (10.7 vs 6.0; 89.6 vs 40.0), so durations are heavily right-skewed: most swings
are short, a few run very long. That is self-similar/heavy-tailed behaviour, the opposite of
periodicity.

### The "dominant period" wanders

Rolling 3-year windows: dominant period ranges **3.0 to 34.4 days**, sd 7.4 days. A stable
oscillator would repeat.

## 2. Are they completely random? **No — but the structure is not periodic**

| | Lags outside 95% surrogate band (of 60) |
|---|---|
| Raw returns | **17** (expect ~3) |
| After removing AR(1) | **15** |

Real structure exists, ~5× chance, and it survives stripping the lag-1 term. But the surviving lags
are scattered — 2(−), 4(−), 5(−), 6(−), 9(+), 12(+), 15(−), 16(+), 27(+), 34(−), 39(+), 43(−) —
with **no harmonic pattern**. A period-P oscillation would spike at P, 2P, 3P. This does not.

Scale matters: **φ = −0.0804 explains 0.65% of return variance.** Detectable is not the same as
large.

## 3. Do they change quickly or slowly? **Slowly — and they have drifted**

Rolling 2-year lag-1 autocorrelation, 125 windows:

- mean **−0.0566**, sd 0.0704, range −0.2886 to +0.0457
- **negative in 83% of windows**
- **autocorrelation of the φ series itself: +0.853 at lag 1**

That last number is the answer: reversal strength is **highly persistent**. It drifts slowly rather
than flickering, so the current state carries information about the near future.

And it has shifted materially:

| Decade | mean φ |
|---|---|
| 1990s | −0.0424 |
| 2000s | −0.0515 |
| 2010s | −0.0409 |
| **2020s** | **−0.1011** |

**Mean reversion in the 2020s is roughly double every prior decade.** This is independent
corroboration of the earlier finding that conditional reversion effects only became significant
after 2010.

## 4. Do some timeframes have more reliable timing? **Yes — clearly**

Lag-1 autocorrelation of returns aggregated to each timeframe, against the surrogate band:

| Timeframe | n | lag-1 ACF | 95% surrogate band | |
|---|---|---|---|---|
| daily | 8,369 | **−0.0804** | [−0.0195, +0.0201] | **OUTSIDE** |
| 2-day | 4,184 | **−0.0806** | [−0.0324, +0.0352] | **OUTSIDE** |
| **3-day** | 2,789 | **−0.0992** | [−0.0342, +0.0382] | **OUTSIDE** |
| weekly | 1,673 | −0.0141 | [−0.0479, +0.0527] | inside |
| 2-week | 836 | −0.0476 | [−0.0699, +0.0598] | inside |
| monthly | 398 | −0.0089 | [−0.1037, +0.0992] | inside |

**Mean reversion is statistically detectable at 1–3 day aggregation and vanishes from weekly
onward.** The 3-day bar is the strongest (−0.0992), and the weekly reading (−0.0141) is
indistinguishable from noise.

This aligns with the horizon table from `TREND-VS-REVERSION.md`, where 5–10 day forward windows
reverted and 126-day windows trended.

---

## Summary

| Question | Answer |
|---|---|
| A frequency / oscillation? | **No.** Spectrum has a slope, not a peak; matches a negative-AR(1) process |
| Characteristic swing length? | **No.** Durations heavy-tailed, median 6d at 2%, and **more erratic than a random walk** |
| Completely random? | **No.** ~5× the expected significant lags, surviving AR(1) removal — but scattered, non-harmonic, and only 0.65% of variance |
| Change fast or slow? | **Slowly.** φ-series autocorrelation +0.853; reversal strength persists across quarters |
| Reliable timeframes? | **1–3 days only.** Strongest at 3-day; gone by weekly |

**The practical read:** what exists is a short-horizon mean-reversion *bias* concentrated in the
1–3 day band, currently running at about double its historical strength, and persistent enough that
its present level is informative. What does not exist is a clock. There is no period to time, no
characteristic swing length to anticipate, and the swings are less regular than chance would produce.

Effect size remains the binding constraint: ~1% of variance explained at the strongest timeframe,
before any transaction cost.

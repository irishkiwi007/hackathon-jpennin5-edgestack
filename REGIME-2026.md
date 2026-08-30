# "We're in 2026" — tested, and it does not rescue the trade

I claimed the long-premium result was actionable *because* we are in the favourable regime rather
than fitting a past one. **That claim does not survive.** `scripts/regime2026.py`, 114 SPY weekly
cycles.

---

## 1. The 2026 gain is two months, not a regime

| Month | ratio | long straddle $ | cumulative $ |
|---|---|---|---|
| 2025-09 | 0.606 | −2,112 | −2,112 |
| 2025-10 | 0.777 | −1,328 | −3,440 |
| 2025-11 | 1.028 | +166 | −3,274 |
| 2025-12 | 0.329 | −4,441 | −7,715 |
| 2026-01 | 0.305 | −2,628 | −10,343 |
| 2026-02 | 0.596 | −1,931 | −12,274 |
| **2026-03** | **1.557** | **+4,671** | −7,603 |
| **2026-04** | **1.716** | **+4,647** | −2,956 |
| 2026-05 | 0.958 | −236 | −3,192 |
| 2026-06 | 1.336 | +1,373 | −1,819 |
| 2026-07 | 0.972 | −204 | −2,023 |
| 2026-08 | 1.054 | +109 | −1,914 |

**March and April are the entire 2026 result.** Every other month is flat or negative, and the
cumulative long straddle since September 2025 is still **−1,914**.

May through August 2026 nets **+1,042 across four months** — essentially nothing.

## 2. The recent windows have no edge

| Window | n | mean ratio | long $/trade | t |
|---|---|---|---|---|
| last 4 cycles | 4 | 1.116 | +177.7 | 0.28 |
| last 8 | 8 | 1.072 | +110.8 | 0.33 |
| last 12 | 12 | 1.065 | +86.8 | 0.36 |
| **last 20** | 20 | 1.275 | **+518.0** | **2.14** |
| all 2026 | 26 | 1.087 | +223.1 | 1.03 |

The **only** significant window is the one long enough to reach back into March–April. Every
genuinely recent window sits at t ≈ 0.3.

## 3. The state does not persist — which was the whole argument

Autocorrelation of the weekly actual/implied ratio:

| Lag | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| corr | +0.199 | +0.110 | +0.339 | +0.147 |

Low and non-monotone. And the direct test:

| Next-week long straddle | n | mean | t |
|---|---|---|---|
| after a **cheap** week | 57 | **−248.8** | −1.93 |
| after a **rich** week | 56 | **−375.5** | −2.55 |

**Both negative.** A cheap week is modestly better than a rich week (+127 difference), so a trace
of persistence exists — but it does not get you to a profitable next week.

The live sequence says the same thing. Last four weekly ratios: **0.31, 2.05, 1.52, 0.59.** That is
not a regime you can lean on; it is noise around 1.0.

---

## What I got wrong

I reported that three independent methods agreed implied was below realised, and framed the long-
premium result as a current-regime read rather than regime-fitting. The first part still holds as a
*level* observation. The inference did not:

- **"2026 favours long premium"** is really **"March and April 2026 did."**
- Being in the year does not help, because **the state does not persist week to week** — which was
  the exact condition I said would make it actionable.
- Cumulatively, long premium is **still down** over the last twelve months.

The honest position: **there is no reliable vol-premium edge in either direction at present.**
Short premium lost significantly in 2026 (t = −2.99); long premium only worked in two event months
and is flat since. The ratio oscillates around 1.0 with weak, unusable persistence.

## Current live reading

- SPY trailing RV20: **10.40%**
- Last four implied moves: 2.21%, 2.26%, **1.59%, 1.60%**
- Trailing RV implies a ~7-session move of **1.73%** against implied of **1.60%**

Implied sits marginally below trailing realised — the same direction as before, but the margin is
small and the four-week ratio history shows it carries no predictive weight.

**The tradeable conclusion is to sit out the vol-premium trade in both directions**, not to take the
long side.

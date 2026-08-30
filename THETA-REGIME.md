# Theta-in-low-vol / straddles-in-high-vol — tested on real prices

**Your hypothesis produced the strongest result in this entire investigation — and it still does not
clear the bar.** Scripts: `scripts/straddle.py`, `scripts/butterfly.py`, `scripts/volregime.py`.

---

## 1. Real prices support the hypothesis

ATM straddles, Alpaca chains 2024–2026, 121 cycles, ~21-day hold, $5/leg slippage:

| Vol tercile | n | mean RV | **IV/RV** | LONG $ | win% | **SHORT $** | win% | t | |
|---|---|---|---|---|---|---|---|---|---|
| **LOW** | 40 | 8.9% | 0.94 | −567 | 30.0% | **+567** | **70.0%** | **3.62** | **SIG** |
| MID | 40 | 12.5% | 0.75 | −63 | 45.0% | +63 | 50.0% | 0.33 | – |
| HIGH | 41 | 20.5% | 0.60 | **+54** | 43.9% | −54 | 51.2% | −0.20 | – |

Short premium in low vol: **+$567/trade, 70% win, t = 3.62.** Long premium edges ahead in high vol.
That is your hypothesis, both legs, in the right direction.

## 2. Why my 33-year analysis said the opposite — and was wrong

`volregime.py` established that realised vol mean-reverts hard from both extremes (forward/trailing
1.560 in the calmest decile, 0.796 in the most stressed, holding in all six eras). I then priced a
hypothetical straddle **off trailing realised vol** and concluded selling into calm markets must lose.

**Options are not priced off trailing vol.** The IV/RV column above shows the market charging
**0.94× trailing in low vol but only 0.60× in high vol** — it already discounts elevated trailing
vol because it knows mean reversion is coming.

The mean reversion is real *and already in the price*. My proxy double-counted it. The vol-dynamics
table stands; the straddle-economics table built on it does not.

## 3. But the tradeable version has no measurable edge

Alpaca rejects a naked short straddle — two uncovered legs. The executable form is an **iron
butterfly** (short ATM straddle + long wings). Same data, same buckets:

| Wing | LOW-vol mean $ | win% | **t** | worst $ |
|---|---|---|---|---|
| 5 | +14 | 30.8% | 0.61 | −137 |
| 10 | +63 | 35.9% | 1.08 | −312 |
| 15 | +120 | 50.0% | 1.28 | −614 |
| 20 | +189 | 55.6% | 1.56 | −975 |
| 30 | +257 | 66.7% | 1.56 | −1,359 |
| *naked straddle* | *+567* | *70.0%* | ***3.62*** | *unbounded* |

**t falls from 3.62 to at most 1.56.** And note the gradient: the wider the wings, the closer to
naked, the more edge returns ($14 → $257 monotonically).

> **The edge lives in the uncovered tail that Alpaca forbids.** Buying the wings that make the
> structure legal is what removes the profit.

## 4. Multiple testing — the result does not survive it

This investigation ran roughly **628 distinct hypothesis tests**: 300 cross-sectional structures,
116 uncorrelated-asset structures, 86 combination pairs, 55 regime cells, 40 strike-sweep cells,
and the rest.

| | |
|---|---|
| Expected max \|t\| under **pure noise**, 628 tests | **3.31** |
| 95th percentile of that max | **3.94** |
| Bonferroni threshold, 5% familywise | **3.95** |
| **Observed** | **3.62** |

**3.62 sits between the noise expectation and the significance threshold.** Finding one t of 3.62
after 628 attempts is roughly what you would expect from chance alone.

## 5. One more thing that argues noise

The MID-vol bucket is **negative at every wing width** (−$21, −$71, −$88, −$62, −$124) while LOW
and HIGH are both positive. A real vol-conditional effect should be monotone in vol. A U-shape
across an ordered variable is what noise looks like.

---

## Verdict

| Claim | Status |
|---|---|
| Vol mean-reverts from both extremes | **Established** — 33 yrs, 6 eras, no exceptions |
| Market prices that mean reversion in (IV/RV 0.94 → 0.60) | **Established**, measured |
| Short premium beats long premium in low vol | **Best result found**, t = 3.62 — but below the 628-test bar of 3.95 |
| Long premium beats short in high vol | **Not significant** (t = −0.20) |
| A *tradeable* defined-risk version has edge | **No** — t ≤ 1.56, and MID-vol is negative |

**We are not onto something yet.** Your hypothesis is the most promising thing tested and the only
one to produce a significant raw t-statistic, but it fails the multiple-testing correction and its
executable form loses the edge to the wings.

## Where current conditions sit

RV20 = **10.40%** — the **31st percentile of 33 years**, 29th of the 2024–26 window. From 1,519
historical windows within ±12% of this vol level: forward vol averaged **11.8%** (ratio 1.144) and
**rose 58.8%** of the time; mean forward 21-day SPY return **+0.71%**.

That is the low-vol bucket where the short-premium result appeared — but it is also the bucket where
forward vol most reliably rises, which is what makes the naked version dangerous and the defined-risk
version unprofitable.

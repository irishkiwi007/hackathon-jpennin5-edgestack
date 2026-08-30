# Elliott Wave Theory — tested, rejected

Tested 2026-08-29 on SPY, 8,371 sessions (1993-01-29 → 2026-05-01).
Scripts: `scripts/elliott.py`, `scripts/elliott2.py`.

Classic EWT is not directly testable — wave counts are relabelled after the fact, and
Prechter's own rebuttal to Batchelor & Ramyar ("you measured filtered trends, not real
Elliott waves") makes the theory unfalsifiable by construction. Three sub-claims ARE
falsifiable. All three fail on our data.

## Claim 1 — retracements cluster at 0.382 / 0.500 / 0.618 — FAILS

Every Fibonacci level sits inside the shuffled-return surrogate 95% band at every
zigzag threshold.

| threshold | n   | 0.382 real/surr | 0.500 real/surr | 0.618 real/surr |
|-----------|-----|-----------------|-----------------|-----------------|
| 2%        | 718 | 3.62 / 2.95     | 2.92 / 2.99     | 3.34 / 2.86     |
| 3%        | 431 | 3.94 / 2.71     | 2.78 / 2.92     | 2.09 / 2.84     |
| 5%        | 201 | 3.98 / 2.57     | 3.48 / 3.07     | 3.48 / 3.03     |

Ranked against 28 equally-wide candidate bands, the Fibonacci levels place
4th/9th/5th (2%), 6th/10th/14th (3%), 1st/8th/6th (5%). Densest band at 2% was **0.46**.
Retracement depth is ~uniform. Replicates Batchelor & Ramyar (2005) on our own data.

## Claim 2 — impulse/correction alternation — ARTIFACT OF OUR OWN TOOL

Raw result looked strong: corr(prior swing size, retracement depth) = **-0.525, t = -16.5**;
large prior swings retraced 0.62x, small ones 1.57x.

It is entirely mechanical. The zigzag requires every swing to exceed `thresh`, so the
ratio next/prior is bounded below by thresh/prior_size — small prior swing forces a high
minimum ratio, large prior swing permits a tiny one.

| threshold | real   | surrogate | 95% band         | verdict  |
|-----------|--------|-----------|------------------|----------|
| 2%        | -0.525 | -0.526    | [-0.559, -0.492] | ARTIFACT |
| 3%        | -0.539 | -0.527    | [-0.565, -0.481] | ARTIFACT |
| 5%        | -0.598 | -0.522    | [-0.574, -0.445] | (1 of 7 marginal) |

Still an artifact after requiring both legs to clear 2x and 3x the threshold.

**Lesson: any zigzag-derived ratio must be surrogate-tested. The threshold manufactures
correlation between adjacent swing sizes.**

## Claim 3 — self-similar swing SIZE — FAILS

| threshold | n swings | mean size | real CV | surrogate CV |
|-----------|----------|-----------|---------|--------------|
| 1%        | 1561     | 3.54%     | 0.74    | 0.78         |
| 2%        | 776      | 5.70%     | 0.68    | 0.71         |
| 3%        | 462      | 7.72%     | 0.64    | 0.68         |
| 5%        | 218      | 11.72%    | 0.61    | 0.70         |
| 8%        | 49       | 22.36%    | 0.81    | 0.79         |

Indistinguishable from a random walk at every scale.

**Contrast with the earlier finding:** swing *duration* IS non-random (CV 1.44–1.60 vs
surrogate 0.86–0.90, `scripts/osc2.py`). Timing carries structure; magnitude does not.

## On the "41.5% → 57.4% win rate" claim

Source: <https://stratbase.ai/en/blog/elliott-wave-backtesting> — a vendor blog, no
methodology disclosure, not peer-reviewed. It is titled Elliott Wave backtesting, but the
strategy tested contains **no EWT content**: ZigZag(5%) + a Fibonacci band of 38.2%–78.6%
+ MACD histogram and RSI crosses. No wave counts, no impulse/corrective labels, no
wave-degree nesting.

The "Fibonacci filter" spans 40 percentage points. Given Claim 1 (retracements ~uniform),
that band simply requires *a pullback occurred and did not fully reverse*. It is a
trend-continuation filter; the mechanism is momentum (Moskowitz-Ooi-Pedersen), not Fibonacci.

**Why it does not transfer to us:** it needs trend continuation, and our most robust
structural finding is VR(q) < 1 at every horizon in all six eras 1993–2026 — SPY
mean-reverts at every scale. Untested on single names.

## Verdict

No tradeable signal. Do not re-open without a new falsifiable sub-claim.

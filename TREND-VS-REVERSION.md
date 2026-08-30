# Telling a real trend from one about to revert

SPY 1993–2026 plus seven other assets, split-adjusted. Method: the **continuation coefficient**
`corr(past return over L, forward return over M)`. Positive = trends persist. Negative = reverts.
Then condition it on observable features to find what flips the sign.

Scripts: `scripts/trendtest.py`, `scripts/trendrobust.py`.

---

## 1. Horizon sets the sign before anything else

Continuation coefficient, non-overlapping samples, SPY:

| Lookback L | M=5 | M=10 | M=21 | M=63 | M=126 |
|---|---|---|---|---|---|
| 5 | −0.063 | −0.047 | +0.021 | +0.011 | +0.109 |
| 10 | **−0.141\*** | **−0.110\*** | **−0.163\*** | +0.058 | +0.233 |
| 21 | **−0.163\*** | **−0.168\*** | +0.033 | −0.058 | −0.106 |
| 63 | **−0.316\*** | **−0.197\*** | +0.074 | +0.096 | −0.056 |
| 126 | **−0.359\*** | −0.028 | +0.159 | +0.108 | **+0.422\*** |

\* = |t| > 2

**Short forward horizons (5–10 days) revert, and the effect strengthens the longer the lookback**
— from −0.063 to −0.359, a clean monotone gradient. The only significant *positive* cell is
126→126 (**+0.422**), the six-month momentum the literature documents. That is the "momentum
sandwich": reversal at days, momentum at months.

**Practical consequence: at the horizons an options position actually lives, SPY is a
mean-reverting instrument.** Trend-following needs months.

## 2. What flips the sign (L=21 → M=21)

| Feature | Bucket | corr | t | Reading |
|---|---|---|---|---|
| **Kaufman efficiency ratio** | 0.34–0.81 (straightest) | **−0.224** | **−4.63** | **mean reverts** |
| | 0.00–0.11 (choppiest) | −0.009 | −0.18 | no signal |
| **Realised vol** | top quartile | −0.109 | −2.21 | mean reverts |
| **Vol direction** | expanded (>1.29×) | −0.123 | −2.49 | mean reverts |
| | contracted (<0.76×) | +0.067 | +1.36 | no signal |
| **Z-score of move** | most negative | −0.163 | −3.30 | mean reverts |
| | most positive | +0.027 | +0.55 | no signal |
| **vs 200d MA** | below | −0.134 | −2.70 | mean reverts |
| | above | −0.063 | −1.27 | no signal |

### The counterintuitive one

**The cleaner and straighter the move, the more likely it reverses** — the strongest single result
in the study (t = −4.63). This is the *opposite* of how the Kaufman efficiency ratio is normally
used, where a high reading is taken as licence to follow the trend. On SPY at monthly horizons, a
high reading is a warning.

### Daniel–Moskowitz panic state, reproduced

| State | n | corr | t | Reading |
|---|---|---|---|---|
| low vol, after UP move | 654 | +0.015 | 0.37 | no signal |
| low vol, after DOWN move | 156 | −0.157 | −1.98 | borderline |
| high vol, after UP move | 398 | −0.014 | −0.27 | no signal |
| **high vol, after DOWN move** | 410 | **−0.165** | **−3.37** | **mean reverts** |

Momentum fails precisely in the panic state the literature predicts — high volatility following a
decline. That is the single cleanest conditional signal here.

---

## 3. Robustness — where it holds and where it does not

### It is asset-dependent, but not randomly so

ER top quartile, L=21 → M=21:

| Asset | corr | t | Reading |
|---|---|---|---|
| XLV (healthcare) | −0.356 | −7.03 | mean reverts |
| HYG (credit) | −0.338 | −5.52 | mean reverts |
| XLP (staples) | −0.275 | −5.28 | mean reverts |
| SPY | −0.226 | −4.72 | mean reverts |
| SOXX | −0.057 | −1.00 | no signal |
| IEF | +0.075 | 1.30 | no signal |
| TLT | +0.020 | 0.34 | no signal |
| **QQQ** | **+0.148** | **+2.75** | **TRENDS** |

Four revert, one **trends**, three show nothing. The split is economically coherent — defensive and
income assets (staples, healthcare, credit) revert hardest; the growth index trends. **It is not a
universal law, and QQQ runs the other way.**

### It is era-dependent — the real weakness

SPY, ER top quartile, by era:

| Era | n | corr | t | Reading |
|---|---|---|---|---|
| 1993–2002 | 124 | −0.159 | −1.78 | no signal |
| 2003–2009 | 91 | +0.040 | 0.38 | no signal |
| 2010–2016 | 91 | −0.247 | −2.40 | mean reverts |
| 2017–2026 | 120 | −0.260 | −2.92 | mean reverts |

**Significant only after 2010.** Absent — and briefly positive — in 1993–2009. This looks like a
post-2010 phenomenon rather than a structural constant, and that materially weakens it.

### The effect is asymmetric — this reframes it

ER top quartile on SPY, split by direction:

| | n | corr | t | **mean forward 21d return** |
|---|---|---|---|---|
| clean **UP** move | 340 | +0.008 | 0.14 | **+0.93%** |
| clean **DOWN** move | 76 | −0.379 | −3.52 | **+2.35%** |

It is not symmetric reversion. **A clean sell-off is a buy signal** (+2.35% forward, ~2.5× normal
drift). A clean rally is simply followed by normal drift (+0.93%). The whole "clean trends revert"
result is carried by the downside — on **n = 76**.

---

## 4. The answer

**Signs a move will revert** (strongest first):
1. Clean, efficient path **downward** — high Kaufman ER with a negative move
2. High volatility following a decline (the panic state)
3. Volatility **expanding** during the move
4. Price below the 200-day MA
5. Short forward horizon (5–21 days)

**Signs a move will continue:**
1. Long horizon — six-month lookback into six-month forward is the only significant positive
2. Volatility **contracting** during the move (weak, not significant)
3. The asset is a growth index — QQQ trends where SPY reverts

**What I would not claim:** that any of this is a tradeable edge. The era table says the headline
effect was absent for the first 17 years of the sample, the asset table says QQQ does the opposite,
and the direction split says the result rests on 76 observations. It is a solid *description* of
conditional autocorrelation, not a validated signal.

## Correction

The `trendtest.py` gap-share panel is **invalid** — it divided raw `open` by adjusted `close`,
which is meaningless across SPY's 1997/2000/2005 splits. Ignore that panel; the others use
adjusted closes only and are unaffected.

---

# 5. CORRECTION — tested up and down separately, almost nothing survives

Everything above used `corr(past, forward)` inside mixed-sign buckets. **That is the wrong tool.**
SPY drifts up, so forward returns are positive nearly everywhere. A negative correlation can mean
"down moves bounce harder than up moves continue" — with **both** positive. That is not reversion
in any tradeable sense.

Correct framing, against the unconditional baseline (`scripts/updown.py`):

```
after an UP move:    forward > baseline -> CONTINUATION     forward < baseline -> REVERSION
after a DOWN move:   forward < baseline -> CONTINUATION     forward > baseline -> REVERSION
```

**Unconditional baseline forward 21d return = +0.870%** (sd 4.64%, n=1,618).

## The headline split

| | n | mean fwd | vs base | t | same-sign | Verdict |
|---|---|---|---|---|---|---|
| all **UP** moves | 1052 | +0.78% | −0.09% | −0.77 | 66.6% | **no signal** |
| all **DOWN** moves | 566 | +1.04% | +0.17% | +0.68 | 35.9% | **no signal** |

Neither direction shows continuation or reversion. And the same-sign column is pure drift: forward
returns are positive ~66% of the time unconditionally, so UP scoring 66.6% and DOWN scoring 35.9%
(≈ 1 − 0.66) carries **no directional information at all**.

## The four-way splits

| Feature | Bucket | Dir | n | vs base | t | Verdict |
|---|---|---|---|---|---|---|
| cleanliness | ER q3 | UP | 270 | −0.61% | **−2.38** | reverts |
| trend context | above 200d MA | DOWN | 309 | +0.48% | 1.95 | borderline |
| cleanliness | ER q4 clean | DOWN | 75 | +1.39% | 1.84 | borderline |
| vol direction | vol flat | DOWN | 96 | +0.87% | 1.55 | no signal |
| vol regime | low vol | UP | 472 | −0.17% | −1.34 | no signal |
| magnitude | LARGE move | DOWN | 116 | +0.77% | 1.29 | no signal |
| *(20 further cells)* | | | | | all \|t\| < 1.3 | no signal |

**Exactly one cell of ~26 clears |t| > 2** — and at 26 tests you expect ~1.3 by chance. It is also
**non-monotone**: ER q3 UP reverts (−0.61%) while ER q4 UP, the *cleaner* bucket, shows +0.10% and
nothing. A real cleanliness effect would strengthen from q3 to q4.

## What this retracts

The previous section's headline — *"a clean sell-off is a buy signal, +2.35% forward"* — does not
survive. Measured against the +0.87% baseline rather than against zero, the excess is **+1.39% with
t = 1.84 on n = 75**: below significance.

And the strongest number in the whole study, the ER top-quartile correlation of **−0.224, t = −4.63**,
decomposes into clean-UP +0.97% and clean-DOWN +2.26% — **both above zero, neither significantly
different from baseline.** The correlation was measuring the *gap between* the two cells, which the
drift creates on its own.

## Revised answer to "how do you tell the difference?"

On SPY at a 21-day horizon, conditioned on path cleanliness, magnitude, volatility level, volatility
direction, or position versus the 200-day MA, **you largely cannot.** Neither up moves nor down moves
depart reliably from the unconditional drift.

What still stands from the earlier work:
- **Horizon** genuinely sets the sign — short forward windows revert, ~6-month windows trend. That
  was measured on non-overlapping samples and does not depend on the mixed-sign correlation.
- **QQQ trends where SPY reverts**, and the defensive/growth split behind it.

What does not stand: any of the conditional up/down signals. The apparent effects were the drift
showing through a statistic that could not separate it.

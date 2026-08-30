# Coverage-volume anomaly — the first robust finding

**Construction:** `news_z = (today's article count − 20-day rolling mean) / rolling sd`, per ticker.
A relative coverage spike, not the presence of an article. 10 symbols, 2024-08 → 2026-08,
**66,793 articles**, 4,740 symbol-days.

Scripts: `scripts/newsvol2.py`, `scripts/newsdeep.py`, `scripts/newsdeep2.py`.

---

## The result: coverage spikes predict move SIZE, not direction

### Monotone, and it survives the volatility confound

The naive version is confounded — spike days already had higher trailing vol (38.6% vs 35.9%), so
part of the bigger forward move is just "vol was already high." Normalising the forward move by
what trailing vol predicts:

| news_z | n | trail RV | raw \|fwd5\| | **normalised** | vs all | **t** |
|---|---|---|---|---|---|---|
| < 0 (quiet) | 2805 | 35.9% | 3.74% | **0.805** | −0.067 | **−4.98** |
| 0 – 1 | 1236 | 33.9% | 3.99% | 0.908 | +0.036 | 1.56 |
| 1 – 2 | 415 | 33.4% | 4.38% | 0.997 | +0.125 | 2.57 |
| 2 – 3 | 197 | 34.0% | 4.83% | 1.089 | +0.216 | 3.08 |
| **> 3** | 187 | 38.6% | 5.31% | **1.137** | **+0.265** | **3.20** |

**Monotone across all five buckets: 0.805 → 0.908 → 0.997 → 1.089 → 1.137.** The effect is not the
vol confound — it survives normalisation.

### It decays smoothly, exactly as a real effect should

Forward move relative to unconditional, by horizon:

| news_z | \|f1\| | \|f2\| | \|f3\| | \|f5\| | \|f10\| | \|f20\| |
|---|---|---|---|---|---|---|
| quiet <0 | 0.933 | 0.944 | 0.924 | 0.955 | 0.969 | 0.982 |
| mild 0–1.5 | 0.969 | 0.990 | 1.036 | 1.024 | 1.034 | 1.021 |
| spike >1.5 | 1.419 | 1.311 | 1.282 | 1.165 | 1.062 | 1.034 |
| **big >3** | **1.935** | 1.704 | 1.570 | 1.382 | 1.193 | 1.121 |

A big coverage spike **nearly doubles the next day's move** (1.935×) and decays smoothly back to
baseline over ~20 sessions. Monotone in both dimensions.

### It holds in 10 of 10 symbols — the test everything else failed

Vol-normalised 1-day move, spike (nz ≥ 1.0) vs rest:

| Symbol | n spike | spike | rest | **ratio** | t |
|---|---|---|---|---|---|
| **NFLX** | 81 | 1.385 | 0.692 | **2.002** | **3.86** |
| **TSLA** | 85 | 1.080 | 0.752 | 1.436 | **2.83** |
| **MSFT** | 84 | 1.167 | 0.751 | 1.554 | **2.66** |
| **AMZN** | 85 | 1.181 | 0.755 | 1.565 | **2.62** |
| **AMD** | 78 | 1.237 | 0.734 | 1.685 | **2.58** |
| **META** | 79 | 1.221 | 0.749 | 1.630 | **2.45** |
| AAPL | 75 | 0.984 | 0.784 | 1.255 | 1.65 |
| GOOGL | 78 | 0.940 | 0.799 | 1.177 | 0.98 |
| SPY | 72 | 0.883 | 0.803 | 1.099 | 0.77 |
| NVDA | 78 | 0.841 | 0.800 | 1.051 | 0.48 |

**Positive in 10 of 10. Six individually significant at |t| > 2.4.**

Note the pattern in the weak names: **SPY and NVDA have the heaviest baseline coverage** (18,505 and
10,506 articles). For a name always in the news, a "spike" means less. The effect is strongest where
baseline coverage is thinner — which is a mechanism, not a coincidence.

---

## The directional half does not work

Per-symbol continuation score (nz ≥ 1.0, forward 3d):

| Symbol | score | Symbol | score |
|---|---|---|---|
| AMZN | +2.064 | NVDA | −0.608 |
| NFLX | +1.873 | GOOGL | −0.234 |
| AMD | +1.585 | AAPL | −0.126 |
| META | +0.070 | MSFT | −1.017 |
| | | SPY | −1.101 |
| | | TSLA | −1.965 |

**Continuation in 4 of 10.** A coin flip, no consistent sign, no t-statistic above 2.55.

The finer bucket table also fails: buckets from +0.5 to +3.5 are mostly *negative* with no gradient,
and only the extreme +3.5 bucket turns positive (+1.47 to +1.94 across every horizon). One bucket of
eight, with the bucket immediately below it at −1.30. **A real threshold effect strengthens
gradually; this jumps.**

## And the pooled statistics were inflated

Mean pairwise daily-return correlation across the 10 names: **0.411**. Effective independent names
≈ **2.13 of 10**. **Pooled t-statistics are inflated by ~2.17×.**

That guts the "fade zone" result. The pooled fade-zone reversion (t = −2.11 to −2.32) adjusts to
t ≈ 1.0 — not significant. It was the general mean-reversion tendency amplified by treating eight
correlated tech names as independent observations.

---

## What this means for the proposed strategy

> *"Target the small reversions on names with sufficient article delta, then go with the trend when
> data says to."*

**Neither half survives.** The fade side is pooling inflation; the follow side is 4-of-10 noise.

**But the direction-neutral trade does.** The data supports **long volatility on a coverage spike** —
buy the move, not the direction. That is also exactly what your own reasoning predicted: *"it would
still be very difficult to predict direction without understanding the context."* The data agrees,
and the context-free signal turns out to carry information about magnitude alone.

### Economics look workable

Cost to clear the bid-ask on a 5-day directional view (measured live):

| Symbol | single option | debit spread |
|---|---|---|
| NVDA | 3.5 bp | 23.5 bp |
| NFLX | 7.8 bp | 28.9 bp |
| AMZN | 12.2 bp | 39.6 bp |
| AMD | 13.0 bp | 161 bp |
| TSLA | 19.3 bp | 78.7 bp |

**Single options are 3–20 bp; debit spreads are 6–160 bp.** A straddle costs roughly two single
options. Against a next-day move ~1.9× normal on a big spike, the spread cost is not the binding
constraint — which is a very different situation from the intraday micro-oscillation work, where
the edge was *below* the cost.

Best candidates pair a strong effect with a cheap chain: **NFLX** (2.00× ratio, 7.8 bp),
**AMZN** (1.57×, 12.2 bp), **AMD** (1.69×, 13.0 bp).

---

## The open question that decides tradeability

**Is the spike already priced into implied volatility?**

The normalisation above controls for *trailing realised* vol. Options are priced off *forward
implied* vol. If IV already rises on coverage-spike days to reflect the larger expected move, there
is no edge — you would be paying for exactly what you expect to receive.

This is testable but requires reconstructing historical IV, since Alpaca provides no historical
option quotes — only trade bars. The route is Black-Scholes inversion on ATM option trade prices for
each spike day back to January 2024.

**Until that is done, this is a validated forecasting result, not a validated trading edge.**
Everything in this project that skipped that step has failed on contact with real prices.

---

# ANSWERED: the spike is already priced

`scripts/ivtest.py`. Method changed from Black-Scholes inversion to a **model-free** test — the ATM
straddle price *is* the market's expected move:

```
implied move = (ATM call + ATM put) / spot        actual move = |log(spot_expiry / spot_entry)|
ratio = actual / implied
```

No rate assumption, no vol surface, no inversion. **271,544 option price marks** across 22,380
contracts covering 2,216 usable symbol-days (734 spike, 1,482 control).

## The market raises its price in lockstep with the signal

| Bucket | n | **implied move** | actual move | ratio | t vs 1 |
|---|---|---|---|---|---|
| control nz<1 | 1482 | **4.63%** | 4.75% | 1.010 | 0.44 |
| spike 1–2 | 392 | **5.19%** | 5.48% | 1.037 | 0.83 |
| spike 2–3 | 174 | **5.40%** | 5.68% | 1.048 | 0.77 |
| spike >3 | 168 | **5.97%** | 5.76% | 0.995 | −0.08 |

**Read the implied-move column: 4.63 → 5.19 → 5.40 → 5.97.** The straddle price rises monotonically
with `news_z`, tracking the actual move almost exactly. The options market has the same information
and prices it in advance.

## The decisive comparison

```
spike   ratio 1.030  (n=734)
control ratio 1.010  (n=1482)
difference +0.021    t = 0.54      -> NOT significant
```

**Per-symbol: 4 of 10.** And the two individually significant results point in **opposite
directions** — MSFT +0.316 (t=2.86) versus NVDA −0.209 (t=−2.19). The familiar noise signature.

## What this means

**The forecasting result was correct. The trading conclusion is that there is no edge.**

`news_z` genuinely predicts larger moves — monotone across five buckets, positive in 10 of 10
symbols, surviving the trailing-vol control. All of that stands. It is simply **already in the
option price**. You would pay 5.97% of spot for a move that averages 5.76%.

That is an efficient-market outcome, not a measurement error, and it is the exact test every other
hypothesis in this project skipped before failing on contact with real prices.

## One incidental confirmation

SPY's ratio is **0.638–0.740** — far below 1 — while single names cluster near 1.0. SPY straddles are
systematically expensive relative to what SPY actually delivers. That is the index variance risk
premium, showing up independently here, and it is consistent with the literature and with the
earlier finding that equity-index options are dearer than single-name options.

## Status

| Claim | Verdict |
|---|---|
| Coverage spikes predict larger moves | **Established** — monotone, 10/10 symbols, vol-controlled |
| The effect decays over ~20 sessions | **Established** — smooth, monotone in both dimensions |
| Direction is predictable from coverage alone | **Rejected** — 4/10 symbols, no gradient |
| "Fade the mild, follow the big" | **Rejected** — pooled t-stats inflated 2.17× by correlation |
| **A tradeable volatility edge exists** | **Rejected — the spike is fully priced** |

---

# How long do the IV gains last? — and one useful by-product

## The IV lift is small and lasts about a week

Spike-group implied vol relative to control, same contract benchmarked 5 sessions pre-event
(`scripts/ivdecay.py`, 740 events, 158k price marks):

| Offset | spike / control |
|---|---|
| t+0 | 1.023 |
| t+1 | 1.030 |
| t+2 | 1.028 |
| t+3 | 1.019 |
| t+5 | 1.029 |
| **t+10** | **0.949** |

**A coverage spike lifts IV ~2–3%, flat through t+5, gone by t+10.**

> **Correction to my own method.** I first compared this 4-week IV lift against the *1-day* realised
> elevation (1.935) and read it as "IV cheap." That comparison is invalid — realised elevation decays
> to baseline within ~20 sessions, so a four-week option averaging over that decay has a fair lift of
> a few percent, not 93%. Two different quantities.

## Matched-horizon lag test — no tradeable edge at any lag

Enter *k* days after the spike, buy the ~7-session straddle, hold to expiry, compare actual to
implied over the identical window (`scripts/ivlag.py`, 20,254 contracts, 252k marks):

| Lag | spike n | spike ratio | ctrl n | ctrl ratio | diff | t |
|---|---|---|---|---|---|---|
| 0 | 324 | 1.006 | 336 | 0.928 | +0.078 | 1.24 |
| 1 | 325 | 1.044 | 332 | 0.939 | +0.105 | 1.65 |
| 2 | 328 | 0.990 | 330 | 0.936 | +0.054 | 0.89 |
| 3 | 327 | 0.963 | 334 | 0.920 | +0.043 | 0.70 |
| 5 | 328 | 1.034 | 335 | 0.925 | +0.109 | 1.78 |

Every lag is positive (+0.043 to +0.109) but **none reaches significance** — t peaks at 1.78. And
the five lags are not independent draws: they overlap on the same events, so consistent sign across
them is close to a single observation, not five.

**IV does not collapse faster than realised after a coverage spike. There is no lagged entry that
works.**

## The useful by-product — a screen, not a trade

Look at the absolute levels rather than the difference:

| Group | ratio (all lags) | t vs 1.0 |
|---|---|---|
| **control** (ordinary days) | **0.920 – 0.939** | −1.34 to −1.84 |
| **spike** (nz ≥ 2) | **0.963 – 1.044** | −0.84 to +0.99 |

On ordinary days the actual move runs **~93% of implied** — options are modestly rich, the variance
risk premium showing through consistently at every lag. **On coverage-spike days that disappears**:
the ratio sits at ~1.00, priced fairly.

> **If you sell premium, avoid names with elevated news coverage.** The edge you normally harvest
> vanishes precisely when the news is flowing — the market prices those days correctly, and you are
> left holding the risk without the compensation.

That is a genuine, actionable filter. It is not a trade on its own, and the difference is not
individually significant (t = 0.70–1.78), so treat it as a prior rather than a proven effect.

## Closing the news thread

| Claim | Verdict |
|---|---|
| Coverage spikes predict larger moves | **Established** — monotone, 10/10 symbols, vol-controlled |
| Effect decays over ~20 sessions | **Established** |
| IV lift from a spike | **~2–3%, lasting ~5 days** |
| Direction predictable from coverage | **Rejected** — 4/10 symbols |
| Tradeable edge on the spike day | **Rejected** — fully priced, t = 0.54 |
| Tradeable edge at a lag | **Rejected** — no lag reaches t = 1.9 |
| **Premium-selling filter** | **Weak support** — VRP present on quiet days, absent on spike days |

The coverage-volume signal is a validated volatility *forecaster* that the options market already
prices. Its only practical use found here is as a **negative screen** for premium selling.

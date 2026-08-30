# Live readings — 2026-08-29 (pre-open, from Fri 2026-08-28 close)

Measured on the competition account against Alpaca's free tier. Reproduce with `scripts/vrp.py`.

Spot SPY **769.35**. Market closed; next open **Mon 2026-08-31 09:30 ET**.

---

## Account (meets every hackathon requirement)

| Field | Value |
|---|---|
| **Account ID (submit this)** | `b9697c2b-40fd-4698-8ecc-90afb944b6b8` |
| Account number | `PA3ZCDDOPR2N` |
| Created | 2026-08-29 — **fresh, dedicated** ✓ |
| Equity | **$100,000** ✓ |
| `options_trading_level` | **3** ✓ (multi-leg enabled by default) |
| Shorting enabled | true |
| Regt buying power | $200,000 (4x multiplier) |

---

## Data access — what actually works

| Call | Result |
|---|---|
| SPY 1-min bars from **2016-01-04** | ✓ works — the 9-year probability model is viable |
| Stock bars, **SIP feed, `--end` ≥15 min in the past** | ✓ **full consolidated tape** (n≈600k trades/day) |
| Stock bars, SIP, `--end` = now | ✗ `subscription does not permit querying recent SIP data` |
| Stock bars, `--feed iex` | ✓ works, but thin (n≈20k trades/day) |
| Option chain, `--feed indicative` | ✓ works |
| Option chain, `--feed opra` (CLI default) | ✗ `OPRA agreement is not signed` |
| **IV + Greeks on indicative feed** | ✓ **populated near the money** (zero on deep-ITM/illiquid only) |

Two corrections to earlier assumptions:

1. **Historical data is not IEX-limited.** Free tier gets full SIP history as long as the request
   window ends more than 15 minutes ago. Only *real-time* is IEX-only. Backtesting is in much
   better shape than assumed.
2. **The OPRA block is an unsigned agreement, not only a plan limit.** Worth checking the dashboard
   for a market-data agreement to sign before paying $99 for Algo Trader Plus.

---

## Realised volatility — 83 daily bars to 2026-08-28

| Window | Close-to-close | Parkinson | Rogers-Satchell | Yang-Zhang |
|---|---|---|---|---|
| 10d | 7.83% | 5.63% | 6.19% | 8.01% |
| 20d | 10.40% | 7.10% | 6.32% | 8.16% |
| 30d | 11.87% | 8.49% | 8.26% | 10.56% |

**Range-based estimators read ~30–40% below close-to-close.** Parkinson and Rogers-Satchell see only
the intraday high-low; close-to-close includes the overnight. The gap between them *is* the gap risk.

> **Interpretation: SPY has been gapping overnight and trading quietly intraday.**
> Intraday realised vol ≈ 5.6–7.1%. Total realised vol ≈ 10.4%.

That is a directly actionable market fact, and it cuts against holding anything overnight.

---

## Implied volatility and the VRP gate

| Expiry | ATM IV | vs seller-RV (10.40%) | Verdict |
|---|---|---|---|
| 2026-08-31 | 7.88% | 0.757 | **BUY** |
| 2026-09-01 | 8.86% | 0.852 | **BUY** |
| 2026-09-02 | 9.46% | 0.909 | **BUY** |
| 2026-09-03 | 9.84% | 0.946 | **BUY** |
| 2026-09-04 | 10.62% | 1.021 | no trade |
| 2026-09-30 | 11.82% | 1.137 | no trade |

Term structure `TS = 7.88 / 11.82 = **0.667**` — steep contango. Front vol is deeply depressed.

---

## ⚠️ The finding that matters most: the gate is not robust

Same bars, same chain, different estimator:

| RV estimator | RV | 08-31 | 09-01 | 09-02 | 09-03 | 09-04 | 09-30 |
|---|---|---|---|---|---|---|---|
| close-to-close 10d | 7.83% | 1.01 – | 1.13 – | 1.21 **S** | 1.26 **S** | 1.36 **S** | 1.51 **S** |
| Parkinson 10d | 5.63% | 1.40 **S** | 1.57 **S** | 1.68 **S** | 1.75 **S** | 1.89 **S** | 2.10 **S** |
| Rogers-Satchell 10d | 6.19% | 1.27 **S** | 1.43 **S** | 1.53 **S** | 1.59 **S** | 1.72 **S** | 1.91 **S** |
| Yang-Zhang 10d | 8.01% | 0.98 – | 1.11 – | 1.18 **S** | 1.23 **S** | 1.33 **S** | 1.47 **S** |
| close-to-close 20d | 10.40% | 0.76 **B** | 0.85 **B** | 0.91 **B** | 0.95 **B** | 1.02 – | 1.14 – |
| Parkinson 20d | 7.10% | 1.11 – | 1.25 **S** | 1.33 **S** | 1.39 **S** | 1.50 **S** | 1.67 **S** |
| Rogers-Satchell 20d | 6.32% | 1.25 **S** | 1.40 **S** | 1.50 **S** | 1.56 **S** | 1.68 **S** | 1.87 **S** |
| Yang-Zhang 20d | 8.16% | 0.97 – | 1.09 – | 1.16 **S** | 1.21 **S** | 1.30 **S** | 1.45 **S** |

**S** = sell premium · **B** = buy premium · **–** = no trade

**Seven of eight estimator choices say SELL somewhere in the window. One says BUY. The rulebook's
own rule (`max` of estimators) picks the one that says BUY.**

The estimators span **5.63% → 11.87%**, a 2.1x range on identical data. The decision is not being
made by the market; it is being made by a modelling choice that nothing in the data constrains.

### What follows

1. **Pre-registration is no longer optional, it is the whole submission.** Commit the estimator,
   the windows and the thresholds *before* running the historical study.
2. **Disclose that this table was inspected first.** A pre-registration written after seeing the
   current regime is not a pre-registration. The honest framing: *"we inspected the live regime on
   2026-08-29, then froze these parameters, then ran the historical study."* Say it plainly — it is
   still far stronger than silent tuning, and the field will notice the difference.
3. **The right resolution is empirical, not aesthetic.** Which estimator best predicts the *next*
   session's realised move? That is a measurable question on 2,400 sessions of SPY bars, and the
   answer picks the estimator for you. Run it before Monday.

---

## Provisional read for Monday

Not a recommendation — a hypothesis to test against the calibration:

- Intraday realised (5.6–7.1%) is running **below** front implied (7.9%), while total realised
  (10.4%) is running **above** it. The difference is entirely overnight gaps.
- That combination favours **selling intraday premium and closing before the bell**, rather than
  either holding to expiry or buying premium outright.
- It also argues against every structure that carries overnight, which is most of what the field
  is running.
- Steep contango (`TS = 0.667`) means long calendars are poorly compensated — you would be selling
  the cheapest point on the curve.

The `0DTE opened ≥10:30, force-flat 15:45` structure now looks better supported than the rulebook's
original blanket "never 0DTE". Both are hypotheses; the calibration decides.


---

# Implied vs empirical distribution — the mispricing hunt

`scripts/mispricing.py`. Extracts risk-neutral tail probabilities from the **2026-09-04** chain by
finite-differencing option mids across strikes, and compares them to the empirical distribution of
**4-trading-day SPY returns** over 2,679 sessions (2016-01-04 → 2026-08-28).

**Drift is removed from the empirical sample.** The risk-neutral measure is driftless by
construction; comparing it to a drifting empirical distribution measures the equity risk premium,
not a mispricing. Mean 4-day drift removed: +0.233%.

Conditioning: 978 of 2,654 windows had trailing 20d RV within ±25% of today's 10.40%.

| Move | Strike | Implied | Emp (all) | Emp (low-vol) | Ratio all | **Ratio low-vol** |
|---|---|---|---|---|---|---|
| −4.0% | 739 | 4.00% | 3.43% | 0.82% | 0.86 | **0.20** |
| −3.0% | 746 | 4.00% | 6.07% | 2.97% | 1.52 | **0.74** |
| −2.0% | 754 | 8.00% | 12.06% | 8.28% | 1.51 | **1.04** |
| −1.5% | 758 | 10.00% | 16.62% | 11.86% | 1.66 | **1.19** |
| −1.0% | 762 | 18.50% | 23.29% | 20.25% | 1.26 | **1.09** |
| +1.0% | 777 | 21.50% | 26.38% | 22.49% | 1.23 | **1.05** |
| +1.5% | 781 | 10.50% | 16.84% | 11.25% | 1.60 | **1.07** |
| +2.0% | 785 | 5.00% | 11.27% | 6.13% | 2.25 | **1.23** |

Ratio > 1 = history says it happens more often than the market charges for.

## What it says

1. **The deep downside is expensive, not cheap.** At −4% the market charges **5x** what low-vol
   history justifies. This is Bondarenko's model-free "overpriced puts puzzle" reproduced live on
   our own chain. The market is not complacent about crashes — it charges heavily for them,
   permanently.
2. **Near the money, pricing is roughly fair** against low-vol history (ratios 1.04–1.23). The
   mild cheapness at −1.5% and +2% is inside the noise.
3. **The unconditional column is the trap.** Every unconditional ratio exceeds 1 because 2016–2026
   contains 2018, 2020 and 2022. Comparing a calm market's pricing to crash-inclusive history
   manufactures a mispricing that is really just regime mismatch.
4. **The one real distortion is the shape of the put curve**, not its level: far puts are expensive
   *relative to near puts* (0.20 at −4% vs 1.19 at −1.5%). That is a relative-value trade — be net
   short the far region inside a defined-risk spread — not a reason to buy tails.

## What this does NOT yet establish

- **A favourable P/Q ratio is not positive EV.** It has to clear `p_be = 1 − C/W`. The −4% ratio
  of 0.20 looks spectacular, but the credit there is tiny and the breakeven win rate correspondingly
  brutal. **Next computation: EV using actual credits, not ratios.**
- **The −4% cell rests on ~8 observations** out of 978, and those 978 are overlapping 4-day windows,
  so effective independent n ≈ 245. Wide confidence interval. Exactly the case `EDGE-AND-SIZING.md`
  says to shrink hard.
- **The implied probabilities are coarse.** They come out quantised (4.00%, 8.00%, 10.00%) because
  the finite difference runs on cent-quantised mids over 1-point strikes. A production version fits
  a smooth IV curve across strikes and differentiates that.

## Also now confirmed available

`option contracts` returns **`open_interest`** (one day stale, OCC overnight publication). Combined
with per-strike `gamma` from the chain snapshot, **dealer gamma exposure (GEX) is computable**.
Positive GEX = dealers long gamma = they sell strength and buy weakness = vol suppressed and
range-bound. Negative = amplification. The zero-gamma flip is a genuine short-horizon volatility
regime signal, and nothing in the surveyed field appears to compute it.

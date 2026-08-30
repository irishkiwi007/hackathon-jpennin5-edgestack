# Where variance is not uniform in time, and what that pays

Thesis under test: option pricing embeds an assumption that returns arrive evenly through time
(calendar-day theta, √t variance scaling, a distribution close to lognormal). Where reality
violates that, risk is mispriced. Find the violation that has paid across a decade and multiple
market structures.

All figures SPY, 2,679 sessions, 2016-01-04 → 2026-08-28. Scripts: `scripts/nonuniform.py`,
`scripts/clean.py`.

---

# Part 1 — Four tests of "is variance uniform in time?"

## Test 1: across the 24h cycle — NO

| Component | Ann. vol | Share of daily variance |
|---|---|---|
| Overnight (close→open) | 11.51% | **42.8%** |
| Intraday (open→close) | 13.29% | **57.0%** |
| Covariance | — | +0.2% |

Per clock hour, intraday variance is **3.6×** denser (6.5h carries 57%; 17.5h carries 43%).

> **Correction to an earlier claim.** I previously inferred from Parkinson reading below
> close-to-close that "gaps dominate, SPY trades quietly intraday." That was wrong — Parkinson
> ignores gaps *and* carries a discretisation bias, so the gap was over-attributed. Measured
> directly, intraday is the larger share. I also quoted a literature figure of 80/20; the direct
> measurement on this sample is **57/43**.

**Consequence:** options decay on calendar time but variance accrues in the session. Holding
overnight pays ~73% of a day's theta to receive ~43% of its variance. Short overnight is
structurally favoured; long overnight is penalised. Market makers partially defend this by marking
IV down into the close — how completely is unmeasured here.

## Test 2: across horizons — NO, and this is the strongest violation

Variance ratio `VR(q) = Var(q-day) / (q × Var(1-day))`:

| Horizon | Realised ann. vol | VR(q) |
|---|---|---|
| 1 | 17.60% | 1.000 |
| 2 | 16.56% | 0.885 |
| 5 | 16.41% | **0.869** |
| 10 | 16.12% | 0.839 |
| 21 | 15.95% | 0.821 |
| 42 | 14.77% | **0.704** |

**VR < 1 at every horizon, declining monotonically.** SPY returns mean-revert: five-day variance is
13% below what √t scaling from daily variance implies; six-week variance is 30% below. This is a
large, monotone, decade-long violation of the i.i.d. assumption — exactly the effect described.

The direct trade (sell long-dated variance, buy short-dated) is a **reverse calendar**, which
Alpaca rejects — the far short leg is uncovered. The effect still matters as a prior: **any
structure whose risk is quoted off √t scaling is priced off a distribution wider than the one that
shows up.**

## Test 3: across weekdays — NO

| Day | Daily ann. vol | vs avg | Overnight | Intraday |
|---|---|---|---|---|
| Mon | 18.57% | **1.055** | **14.98%** | 11.64% |
| Tue | 16.17% | **0.919** | 10.39% | 12.65% |
| Wed | 18.18% | 1.033 | 10.55% | 14.75% |
| Thu | 17.63% | 1.001 | 11.03% | 13.59% |
| Fri | 17.49% | 0.994 | 10.21% | 13.51% |

A ~15% spread between the calmest and most volatile weekday. Monday's overnight vol (14.98%) is
~45% above every other day's because it absorbs the weekend — yet it is priced as one trading day.

## Test 4: implied vs realised term structure

Comparing implied to *forward realised conditioned on the current regime* — not to trailing
realised, which is what earlier analysis did wrongly:

| Horizon | Implied | Realised median | Realised p75 | Implied/median |
|---|---|---|---|---|
| 1 | 7.88% | 6.24% | 12.30% | **1.263** |
| 2 | 8.86% | 8.20% | 12.49% | 1.080 |
| 5 | 10.62% | 9.29% | 12.53% | 1.143 |
| 22 | 11.82% | 10.86% | 13.39% | 1.089 |

> **This reverses an earlier conclusion.** `LIVE-READINGS.md` compared implied to *trailing*
> realised and concluded the front expiry was cheap (ratio 0.757, "BUY"). Compared to *forward*
> realised conditioned on regime — which is what you actually sell — the front is **rich at 1.263**.
> Forward is the correct comparison. Volatility mean-reverts, so trailing realised is a biased
> estimate of what you are selling.

The p75 column is the warning: 25% of the time realised 1-day vol exceeds 12.30% against 7.88%
implied. Median favourable, right tail brutal — the standard short-vol shape.

---

# Part 2 — A data problem that invalidated the first answer

The first pure-alpha run returned 10 regime-stable survivors, all far-OTM debit spreads, with
alpha/risk up to 8.4. **It was an artifact.**

Raw indicative-feed quotes, 2026-09-04 calls:

```
789   bid 0.04  ask 0.05   iv 0.0880   delta 0.0147
790   bid 0.06  ask 0.07   iv 0.0968   delta 0.0188     <-- worth MORE than the 789
795   bid 0.04  ask 0.05   iv 0.1109   delta 0.0120     <-- IV 20% above its neighbours
```

The 789 asks 0.05 while the 790 bids 0.06: a higher strike quoted above a lower strike is a
riskless arbitrage that does not exist in real SPY. Delta rises with strike, which is also
impossible. **The indicative feed assembles strikes from different moments, so the far wings are
internally inconsistent** — and that is precisely where the "alpha" was found.

**Any chain-driven strategy needs an arbitrage-consistency filter before it computes anything.**
`scripts/clean.py` rejects on relative spread > 35%, non-monotone price or delta across adjacent
strikes, and adjacent-strike vertical arbitrage. On this chain it rejected **82 of 265 strikes**.

*Known gap: a strike rejected for wide spread skips the monotonicity check against its neighbours,
so `785/795` survives and is still suspect on its IV alone. Treat far-wing results as unproven.*

---

# Part 3 — What survives a clean chain

Alpha redefined correctly: **total EV** is expected P&L under the real-world distribution with
drift included — that is what the strategy earns. **Alpha** is EV under the drift-neutralised
distribution — the part not explained by market exposure. (The previous linear initial-delta
benchmark badly understated the drift sensitivity of convex structures, which is what let far-OTM
call spreads show fake alpha.)

alpha/risk by regime, cleaned chain:

| Structure | pre-covid 16–19 | covid/infl 20–22 | recent 23–26 | ALL | low-vol cond |
|---|---|---|---|---|---|
| put debit 754/744 | 0.366 | 2.938 | 1.169 | 1.377 | 0.463 |
| put debit 754/751 | 0.211 | 2.346 | 1.100 | 1.113 | 0.497 |
| put debit 758/748 | 0.159 | 1.875 | 0.879 | 0.889 | 0.342 |
| put debit 762/752 | 0.129 | 1.156 | 0.653 | 0.593 | 0.272 |
| **put credit spreads (all)** | **−0.01 to −0.09** | **negative** | **negative** | **negative** | **negative** |

**12 of 106 structures show positive alpha in every regime. Every one is a debit spread.
Every credit spread is negative in every regime.**

Discarding the far-wing artifacts, the credible survivors sit at −1% to −3% — liquid, well-quoted
strikes: **long the near OTM put, short the farther OTM put.**

## Why this is the same answer three other methods gave

| Method | Says |
|---|---|
| P vs Q mispricing (`mispricing.py`) | near puts ratio **1.19** (cheap), far puts **0.20** (5× overpriced) |
| Regime-stable alpha (`clean.py`) | put **debit** spreads positive alpha everywhere; credit negative everywhere |
| Literature | Bondarenko, model-free: OTM puts systematically overpriced, decades |

A put debit spread is **long the cheap near put and short the expensive far put.** It harvests the
skew. Four independent routes — risk-neutral density, regime-partitioned alpha, published
model-free result, and the breakeven arithmetic `p_be ≈ 93.5%` — converge on the same structure.

**This is the answer to the thesis.** The market prices the put curve as though the return
distribution were more even than it is: it overcharges for the far tail relative to the near one.
That overcharge has persisted through three distinct market structures.

---

# Part 4 — The honest tension, and the fix

**Put debit spreads are short delta, so they fight the +15.8%/yr drift.**

`put debit 754/744`: alpha **+$56.4**, total EV **+$40.2**. Alpha exceeds total EV — the drift
takes back roughly $16 of a $56 edge. Real, but thinner than the alpha number alone suggests.

Two ways to handle it, both worth testing before Monday:

1. **Pair it with a long-delta leg.** A call debit spread is long delta and captures drift; the put
   debit spread carries the skew alpha. Together they neutralise the drift drag and keep the edge —
   a defined-risk long-convexity package. Both sides showed positive alpha independently.
2. **Accept the drag** and size on alpha rather than EV, since alpha is the regime-stable quantity
   and drift is the part most likely to differ over five sessions.

## Caveats that bind

- **Win rates are 11–25%.** These are convex, lottery-shaped payoffs. Over four sessions the modal
  outcome is losing on most of them. The edge is in the tail, and four draws will very likely not
  show it — which is a fact about the *sample*, not about the strategy.
- **Overlapping windows.** 2,653 five-day windows overlap 4-in-5; effective independent n ≈ 530.
- **Friday-close quotes throughout.** Re-run everything in Monday RTH.
- **The covid/inflation column carries the biggest alphas** (2.9, 2.3) because 2020 and 2022 handed
  put spreads enormous payoffs. Regime-stable *in sign*, not in magnitude. The pre-covid column
  (0.37, 0.21) is the conservative estimate and the one to size on.

---

# Part 5 — Cheap insurance: does a corridor exist?

`scripts/hedge.py`. Two questions: does the drift-aligned core have tail risk worth insuring, and
is tail insurance cheap?

## The core has no tail risk

`call debit 780/785` costs **$45/lot, and that is the max loss.** If SPY falls 20% it loses $45.
A long debit spread has no tail exposure. A book of them has an aggregate max loss equal to the sum
of debits, known before the open.

**There is nothing here for catastrophe insurance to protect.**

## Tail insurance is the most overpriced thing on the surface

Sample choice decides the answer, so both are shown:

| Hedge | Cost | %NAV | EV (unconditional) | **EV (conditioned)** | **premium burn** |
|---|---|---|---|---|---|
| long put −4% (739) | $20 | 0.020% | +$44.9 | **−$11.2** | **−56%** |
| long put −5% (731) | $14 | 0.014% | +$28.6 | −$9.9 | −71% |
| long put −6% (723) | $11 | 0.011% | +$19.1 | −$8.6 | −78% |
| long put −8% (708) | $8 | 0.008% | +$8.1 | −$7.6 | −95% |
| long put −10% (692) | $7 | 0.007% | +$0.5 | −$7.0 | **−100%** |

The unconditional column makes tail puts look like free money (+225% on cost). It is wrong: it
prices a calm-market hedge using a sample containing COVID, 2018 and 2022.

The conditioned sample is the right one and **it does not assume calm persists** — it measures how
often a calm state turned into a crash *within five days*. From a calm start, 5-day drops ≤ −4%
occurred 0.82% of the time (vs 3.59% unconditionally) and the worst was −8.49% (vs −15.63%).

Conditioned, every tail hedge burns **56% to 100% of its premium**, and the burn gets monotonically
worse the further out you go. That is Bondarenko's overpriced-puts result, measured on our own chain.

## Where the put curve is actually cheap

| Strike | % OTM | Implied P | Empirical P | emp/impl | Verdict |
|---|---|---|---|---|---|
| 762 | −1.0% | 18.50% | 17.18% | 0.93 | fair |
| **758** | **−1.5%** | 10.00% | 11.55% | **1.16** | **CHEAP** |
| 754 | −2.0% | 8.00% | 8.28% | 1.04 | fair |
| **750** | **−2.5%** | 3.00% | 4.81% | **1.60** | **CHEAP** |
| 746 | −3.0% | 4.00% | 2.86% | 0.72 | expensive |
| 739 | −4.0% | 4.00% | 0.82% | **0.20** | expensive |
| 731 | −5.0% | 3.00% | 0.31% | **0.10** | expensive |
| 723 | −6.0% | 2.00% | 0.20% | **0.10** | expensive |

**The cheap region is −1.5% to −2.5%. Everything beyond −3% is expensive and worsens monotonically.**

Cheap protection exists — but it is ordinary downside, not catastrophe cover. The further you go
toward genuine black-swan territory, the worse the price gets. That is the opposite of what the
"complacent market underprices shocks" intuition predicts, and it held across the whole surface.

*(It also hands over an exact skew trade for the drift-fighting side: long 750 at ratio 1.60, short
739 at 0.20 — buy the cheap put, sell the expensive one. Same family as the 9 rejected structures.)*

## Verdict on the corridor

| Request | Corridor |
|---|---|
| Alpha that moves with market bias | **OPEN** — `call debit 780/785`: positive alpha in all 5 regime partitions, netΔ +0.085, alpha $36.5, total EV $58.8 (drift adds $22.3) |
| Very cheap black-swan insurance | **CLOSED** — the tail is the most overpriced part of the surface (5–10×), and the core has no tail exposure to insure |

## The reframe that matters

**A black swan is not what threatens this strategy.** A book of long call debit spreads is immune to
a crash — max loss is the debit. What actually threatens it is the base case: a **74% chance each
spread expires worthless**. Death by a thousand small debits, not one catastrophe.

Insurance does not help with that. Position sizing and bet count do.

If the book ever includes short-premium structures, tail risk reappears and this analysis should be
re-run — but those showed negative alpha in every regime, so they should not be there.

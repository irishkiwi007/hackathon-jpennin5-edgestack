# Edge estimation and position sizing

The design: a decision matrix that takes any setup — breakout **or** reversion — but only when the
historical probability clears the bet's breakeven by enough to justify it, sized by how confident
the estimate is and how volatile the tape is.

This is the right design. It is also the one that is easiest to fool yourself with, so most of this
document is about not doing that.

---

# Part 1 — The data constraint, and the way around it

**Alpaca options history begins February 2024.** ~630 sessions, on the indicative feed. Bucket that
by setup and you have a few dozen observations per cell — far too few to estimate a win rate you
would then bet size on.

**SPY minute bars go back to 2016.** ~2,400 sessions.

### The split that resolves it

> **Estimate probabilities from the underlying. Take prices from the live chain.**

For a defined-risk structure held to expiry, the payoff is **deterministic** given the settlement
price of the underlying. You do not need historical option prices to know what a 765/760 put spread
paid on some day in 2019 — you only need where SPY settled, plus the credit, which you observe
*today* when you trade.

```
EV = Σ  P(settlement region | setup)  ×  payoff(region | strikes, credit)
    regions
        ^                                  ^
        └── 9 years of underlying          └── today's live chain
```

So the hard half of the problem gets 2,400 sessions and the easy half gets today's quotes. Options
history is then only needed to calibrate two things: `EM_straddle` and realistic round-trip spread
cost. Both tolerate 630 sessions fine.

### Normalise, or the estimate will not transfer

Never estimate `P(SPY stays between 760 and 775)`. That probability is specific to one price and one
volatility regime and is worthless tomorrow. Estimate:

```
P( |return from decision time → expiry| < x · EM )   conditional on setup
```

Expressed in units of the day's expected move, the estimate is vol-normalised and transfers across
2016–2026. This is the single most important modelling decision in the whole system.

---

# Part 2 — The edge gate

## Breakeven win rate falls out of the structure

For a credit spread with credit `C` and width `W`, held to expiry:

- win → `+C`
- lose → `−(W − C)`

Setting EV to zero:

```
p_be = (W − C) / W  =  1 − C/W
```

**Collect 20% of the width and you must win 80% of the time just to break even.** That number is
known at order construction, before any statistics. It is the bar every probability estimate has to
clear, and it is why "high win rate" means nothing on its own — an 80% win rate on a 20%-of-width
credit spread is exactly zero edge.

For debit structures the same identity runs the other way: a spread paying 4:1 needs only a 20% hit
rate. **Low win rate is not the same as no edge.** The matrix must compare `p` to `p_be`, never to
50%, and never to another setup's `p`.

## The edge

```
edge = p_lower − p_be
```

where `p_lower` is a *conservative* estimate — see Part 3. Trade only when `edge > θ`, with `θ`
set to cover round-trip spread cost plus a margin. Starting value: `θ = 0.05`.

---

# Part 3 — Estimating `p` without fooling yourself

Two mechanisms, both required.

## 3a. Beta-Binomial shrinkage toward *no edge*

Put a prior on each bucket's win rate centred on that bucket's **breakeven**, not on 50% and not on
the observed rate:

```
prior     ~ Beta(α₀, β₀)     with   α₀/(α₀+β₀) = p_be ,   α₀+β₀ = m
posterior ~ Beta(α₀ + wins, β₀ + losses)

p̂ = (α₀ + wins) / (α₀ + β₀ + n)
```

`m` is the prior strength in pseudo-observations. Start at `m = 50`.

The behaviour this buys is exactly what you asked for, and it is automatic:

| Bucket | Result |
|---|---|
| Few observations | `p̂ → p_be` → `edge → 0` → **no trade, or minimum size** |
| Many observations, genuine edge | `p̂ →` observed rate → edge survives → **full size** |
| Many observations, no edge | `p̂ ≈ p_be` → **no trade** |

The prior says *"assume this setup has no edge until the data insists otherwise."* Uncertainty stops
being something you eyeball and becomes something the arithmetic handles.

## 3b. Wilson lower bound, not the point estimate

The Wald interval is badly behaved at small `n` and near the extremes — which is precisely where
these estimates live. Use the **Wilson score interval**, which holds nominal coverage from about
`n = 10`:

```
             p̂ + z²/2n  ∓  z·√[ p̂(1−p̂)/n + z²/4n² ]
p_lower =   ─────────────────────────────────────────      (lower root, z = 1.64 for 95% one-sided)
                        1 + z²/n
```

Feed `p_lower` — never `p̂` — into the edge test and the sizing formula. Kelly is far more
punishing of overestimated edge than of underestimated edge, so the asymmetry of using a lower
bound is the correct asymmetry.

## 3c. The overfitting guard

Bucketing five measurements at three levels each is 243 cells and guaranteed self-deception.

**Keep the probability model to two axes, both about the underlying's path:**

| Axis | Levels |
|---|---|
| `loc` | `inside` · `trending` (above/below, held) · `failed_break` |
| `R = W / EM` | `low` (<0.5) · `high` (≥0.5) |

Six buckets. Across ~2,400 sessions that is a few hundred observations each — enough to move a
Beta(·, 50) prior meaningfully.

**Volatility risk premium selects the *structure*, not the *probability*.** VRP decides whether you
sell or buy premium; the six buckets decide how likely the path is. Keeping them on separate axes
is what stops the cell count exploding.

Then:

- **Pre-register** the buckets and thresholds in a committed file *before* running anything.
  `nilaymastaadmi` is doing this and it is provable from their git history.
- **Walk forward**: fit 2016–2023, validate 2024–2026. Never report in-sample.
- **Count your trials.** If you test 20 variants and keep the best, the winner's Sharpe is inflated
  even if every variant is noise. Report the **Deflated Sharpe Ratio** (Bailey & López de Prado),
  which corrects for exactly this selection bias plus non-normal returns and sample length.
- **Minimum `n` per bucket** before that bucket may exceed minimum size: 30.

---

# Part 4 — Sizing

## 4a. Kelly, in terms you already have

Standard Kelly with `b = C/(W−C)` simplifies, for this payoff, to:

```
f* = (p − p_be) / (1 − p_be)
```

Kelly fraction of capital-at-risk = **edge ÷ (1 − breakeven)**. Nothing else is needed — no separate
odds term, because the odds are already inside `p_be`.

`f*` is the fraction of equity to place **at risk**, and the stake *is* the structure's max loss,
which is fixed at construction. So sizing reduces to: how much max-loss do I buy?

## 4b. Fraction it, hard

Full Kelly is not a target. Half Kelly retains roughly 75% of the growth rate for half the
volatility, and drops the probability of ever halving your capital from about 1/2 to about 1/8.
Given that `p` here is *estimated* from a few hundred noisy observations:

```
f_used = 0.25 × f*(p_lower)
```

Quarter Kelly, on the lower confidence bound, of a shrunken estimate. Three independent layers of
conservatism, which is proportionate to how little the data actually says.

## 4c. Volatility scaling

Then scale by how violent the tape is right now, using Yang-Zhang realised vol:

```
vol_scalar = clamp( RV_target / RV_20d ,  0.5 , 1.5 )
```

`RV_target` is your reference regime — set it to the trailing 1-year median RV so the scalar sits
near 1.0 in normal conditions. Calm tape scales up, violent tape scales down. Cap both ends: an
uncapped inverse-vol term explodes precisely when vol is lowest, which is now (VIX ~14).

## 4d. The full sizing expression

```
risk_$ = equity × clamp( 0.25 × f*(p_lower) × vol_scalar ,  0.25% ,  2.0% )

contracts = floor( risk_$ / max_loss_per_structure )
```

with the portfolio caps from the rulebook still binding on top: 3 concurrent structures, 4%
aggregate risk, 2% daily loss halt.

The floor at 0.25% matters as much as the ceiling. It is what lets a thin-edge, high-uncertainty
setup still be *taken* — small — so the bucket keeps accumulating observations instead of going
dark. That is your "small safe positions on harder-to-know trades", made explicit.

## 4e. What this produces

| Setup | `n` | `p_lower − p_be` | `vol_scalar` | Risk |
|---|---|---|---|---|
| Well-measured, strong edge | 400 | +0.14 | 1.1 | **~2.0%** (capped) |
| Well-measured, thin edge | 400 | +0.06 | 1.0 | ~0.6% |
| Sparse bucket, apparent edge | 25 | +0.02 | 1.0 | **0.25%** (floor) |
| Any bucket, no edge | — | ≤ 0 | — | **no trade** |
| Strong edge, violent tape | 400 | +0.14 | 0.5 | ~1.0% |

---

# Part 5 — What breaks this

Stated plainly, because these belong in the write-up:

1. **Regime change.** 2016–2026 includes 2018, 2020 and 2022. A probability estimated across all of
   them is an average over regimes that will not repeat. The `R` and VRP axes are partial defences,
   not solutions.
2. **The payoff is not truly binary.** Between the short and long strike, a credit spread settles
   partially. Model three regions, not two, or you will overstate the loss and understate `p_be`.
3. **Early management changes the distribution.** A 50% profit target and a 2× stop mean you are no
   longer estimating `P(settle inside strikes)` — you are estimating `P(target hit before stop)`.
   These are different numbers. Pick one convention and estimate *that*.
4. **Assignment risk on SPY.** American-style, so a short leg in the money can be assigned early.
   SPX / XSP are European and cash-settled, which removes it entirely.
5. **n = 4.** Whatever this produces over four sessions is one draw from the distribution, not a
   measurement of it. Report the **minimum detectable effect** next to the P&L.

---

# Part 6 — Build order for the weekend

1. Pull SPY 1-min bars 2016 → now. Build the session table: OR, `W`, `loc`, close, settlement.
2. Pull option chains Feb 2024 → now. Calibrate `EM_straddle` and round-trip spread cost only.
3. **Commit the pre-registration**: buckets, thresholds, `θ`, `m`, Kelly fraction. Before step 4.
4. Estimate `P(|return| < x·EM | bucket)` on 2016–2023. Validate on 2024–2026.
5. Report Deflated Sharpe with the trial count stated honestly.
6. Only then wire the matrix to the live agent.

Steps 1–5 are the submission's actual differentiator. The trading is downstream of them.

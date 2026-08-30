# Strategy survey — institutional options strategies vs. this competition

Researched 2026-08-29. Question: is there a more statistically robust strategy than the
opening-range / VRP construction, drawing on documented institutional approaches?

> **Correction (2026-08-29).** An earlier version of this document opened by claiming "no strategy
> is statistically robust over four sessions." That was wrong, and the error mattered.
>
> **Robustness is a property of the strategy, estimated from its full history. It does not degrade
> because you deploy it for a week.** What varies with the window is the *dispersion of the realised
> outcome* — a separate quantity. Part 1 measures the second and previously mislabelled it as the
> first.
>
> The correction reranks the recommendation. Bet frequency was used below to rank 0DTE first; under
> a robustness criterion it should not influence strategy *selection* at all. And 0DTE has only
> ~3 years of history since daily SPX expiries began in 2022, so on evidence quality it ranks
> **below** the 30-year VRP and put-skew results, not above.

**Select on historical edge. Use the window only to set size.**

---

# Part 1 — The reality check

Run `scripts/universe.py`. Documented long-run performance, projected onto a 4-trading-day window:

| Strategy | Ann. return | Ann. vol | Sharpe | **4d mean** | **4d sd** | **P(positive)** |
|---|---|---|---|---|---|---|
| CBOE PUT (PutWrite), 1986–2015 | 10.1% | 10.1% | 1.00 | **+0.16%** | 1.27% | 55.0% |
| CBOE BXMD 30-delta buywrite | 10.7% | 11.8% | 0.90 | +0.17% | 1.49% | 54.5% |
| S&P 500 total return | 9.8% | 15.3% | 0.64 | +0.16% | 1.93% | 53.2% |
| 0DTE short straddle (optimistic claim) | 14.0% | 10.0% | 1.40 | **+0.22%** | 1.26% | 57.0% |

On $100,000, the best of these expects **+$160 with a standard deviation of ±$1,270**.

Placing in a P&L contest requires a result several standard deviations out. **That is not edge.
That is leverage plus luck.** Any competitor reporting +15% for the week got there by variance, and
no strategy choice available to us changes that.

## The one lever that does work, and its cost

Splitting the same total risk across N *independent* bets:

| N bets | sd of total | P(finish positive) |
|---|---|---|
| 1 | 1.27% | 55.0% |
| 4 | 0.64% | 59.9% |
| 8 | 0.45% | 63.9% |
| 16 | 0.32% | 69.3% |
| 32 | 0.22% | 76.2% |

The mean never moves. Only the spread narrows.

> **Variance reduction and winning the P&L category are in direct conflict.** More bets makes a
> positive finish more reliable *and* a spectacular finish less likely. This is a decision to make
> deliberately, not to stumble into.

Given five judging criteria and a large field, the higher-expected-score play is a tight positive
P&L plus a strong showing on the other four — not a lottery ticket. But it is a choice.

---

# Part 2 — Institutional strategies, assessed against our constraints

| Strategy | Evidence | Verdict here |
|---|---|---|
| **Short vol premium** (PUT/BXM/CNDR/BFLY indices) | 30+ yrs. PUT: Sharpe 0.67 vs S&P 0.47, 2/3 the vol, max DD 15% | **Strongest available prior.** But see Part 3 — the current regime is hostile |
| **Dispersion** (sell index vol, buy single-name) | Implied correlation runs 10–20pp above realised, persistently. Reported 14–26% annual | **Not feasible.** Needs many legs (4-leg cap), single-name liquidity we do not have, and is a vega trade needing weeks. Blows up exactly when correlation spikes |
| **Tail hedging** (buy cheap convexity) | Universa-style | **Contradicted.** Our own chain shows −4% puts at 5× low-vol-conditioned history. Tails are expensive, not cheap |
| **Overnight drift** ("night effect") | Documented, but *"not stable across subperiods"*, fails in the recent subperiod, and ES futures show the **opposite** sign | **Too unstable** to bet 4 sessions on |
| **Gamma scalping** (delta-hedge long straddle) | Sound when RV > IV | **Blocked by data.** Needs frequent rehedging against real-time option prices; ours are 15 min stale |
| **0DTE systematic short premium** | Claimed Sharpe 0.85–1.4, but daily SPX expiries only date from 2022 — a **~3-year** record, largely one regime | **Weaker evidence than it looks.** High bet frequency is a deployment convenience, not evidence quality |
| **Calendar / term-structure carry** | Standard | **Poorly compensated now.** `TS = 0.667` means selling the cheapest point on the curve |

### Ranking by evidence quality, not convenience

| Rank | Edge | Record | Independently verified here? |
|---|---|---|---|
| 1 | **Put / skew overpricing** | Bondarenko, model-free, decades | **Yes** — −4% puts at 5× low-vol history on our own chain |
| 2 | **Variance risk premium** | CBOE indices 1986–, replicated across assets | Partially — currently compressed |
| 3 | Implied correlation premium | Persistent, well documented | Not accessible (4-leg cap, liquidity) |
| 4 | 0DTE short premium | ~3 years, one regime | No |
| 5 | Opening-range / intraday patterns | Blog-level | No |
| 6 | Overnight drift | Documented but unstable, fails recent subsample | No |

The top two are the only ones with both a long record and live confirmation on our own data.

---

# Part 3 — The tradeable universe (corrected)

> **Correction.** The first version of this section ranked SPY, QQQ, IWM and DIA against NVDA,
> TSLA and AMZN on **median % bid-ask across the chain**. That is not an apples-to-apples
> comparison and the conclusion drawn from it was wrong.
>
> Percentage spread scales inversely with premium size. NVDA at 37% IV and SPY at 10.5% IV carry
> completely different premiums, so an identical absolute spread reads as a much smaller percentage
> on the single name. Strike spacing differs too ($1 on SPY vs $2.50–$5), and single names carry
> idiosyncratic and event risk that an index does not. The classes are not comparable on that
> metric, and were not comparable to each other at all.

**Corrected metric** (`scripts/liquidity.py`): build the *same* structure on every underlying —
a 16-delta put credit spread with width scaled to one expected move — and measure round-trip
bid-ask cost as a share of the credit collected. Unit-free, economically matched, comparable
within a class.

## Index / commodity ETFs

| Symbol | Spot | ATM IV | Short | Long | Credit | Credit/width | **Cost/credit** | Gate |
|---|---|---|---|---|---|---|---|---|
| **SPY** | 769.35 | 10.5% | 758 | 747 | 0.69 | 6.2% | **10.2%** | PASS |
| QQQ | 716.43 | 15.5% | 701 | 685 | 1.06 | 6.7% | 12.2% | PASS |
| IWM | 295.75 | 15.5% | 289 | 282 | 0.42 | 6.4% | 16.9% | PASS |
| TLT | 82.88 | 15.8% | 82 | 80 | 0.10 | 6.7% | 20.0% | PASS |
| GLD | 408.89 | 24.4% | 397 | 383 | 0.98 | 7.0% | 23.6% | PASS |
| DIA | 535.06 | 10.5% | 528 | 520 | 0.49 | 6.5% | 44.9% | **REJECT** |

## Single stocks

| Symbol | Spot | ATM IV | Credit/width | **Cost/credit** | Gate |
|---|---|---|---|---|---|
| TSLA | 348.75 | 37.9% | 7.9% | **5.8%** | PASS |
| AAPL | 319.70 | 24.9% | 6.8% | 10.4% | PASS |
| NVDA | 217.55 | 37.0% | 5.0% | 14.4% | PASS |
| AMZN | 266.43 | 28.7% | 8.0% | 15.0% | PASS |
| AMD | 465.58 | 49.2% | 6.1% | 19.5% | PASS |
| META | 578.02 | 36.3% | 6.7% | 23.6% | PASS |
| MSFT | 513.53 | 24.2% | 6.9% | 32.1% | **REJECT** |
| GOOGL | 346.59 | 26.1% | 7.7% | 52.1% | **REJECT** |

## What the corrected metric says

1. **SPY is the best ETF, not the worst.** 10.2% cost/credit, ahead of QQQ at 12.2%. The earlier
   "SPY quotes worse than QQQ" claim was purely an artifact of the wrong metric. **SPY stays the
   default.**
2. **DIA and GOOGL are genuinely unusable**, and MSFT is marginal — those survive the correction.
3. **Credit/width is near-constant at 5–8% across every underlying and both classes.** The market
   prices a 16-delta, one-expected-move-wide spread consistently everywhere. Good sanity check on
   the delta matching — and it has a sharp consequence, below.
4. Single names quote tighter *on this metric*, but that does not make them substitutes. They carry
   idiosyncratic and event risk an index does not, so equal spread cost is not equal risk.

## The consequence of credit/width ≈ 6.5%

`p_be = 1 − C/W ≈ 1 − 0.065 = **93.5%**`

A 16-delta short put has roughly an **84%** chance of finishing out of the money. So the standard
16-delta, one-expected-move-wide put credit spread — the structure most of the field is running —
**does not clear its own breakeven at current pricing.** Partial settlement between the strikes
softens this, but not enough to reverse the sign.

This is the same conclusion the VRP gate reached, arrived at independently from the price structure
rather than from a volatility estimator. That agreement is worth more than either result alone.

## The correlation problem that undoes naive diversification

SPY, QQQ, IWM, NVDA, AMZN and TSLA all load on one factor: equity beta. On a down day they lose
together. The √N benefit in Part 1 assumes **independence**, which these do not have. Nominal N of
12–20 positions probably buys effective independent N of 3–6 — roughly a 2× variance reduction, not
the 4.5× the table suggests.

> **Real diversification needs different risk factors, not more tickers.**
> Equity (SPY / QQQ) + **rates (TLT)** + **gold (GLD)** is three factors. Ten equity names is one.

*All quotes are Friday-close and therefore pessimistic. Re-run during Monday RTH.*

---

# Part 3b — Expected value, decomposed into beta and alpha

> **Correction.** An earlier version treated the drift-removed column as "the honest measure" and
> the drift-included columns as contaminated. That was backwards.
>
> Drift removal is correct for exactly one purpose: comparing **risk-neutral** to **real-world**
> probabilities to detect a mispricing. The risk-neutral measure is driftless by construction, so
> comparing it to a drifting sample measures the equity risk premium — compensation for risk, not a
> pricing error. That is why `mispricing.py` removes it and should continue to.
>
> But the **expected P&L of a position you will actually hold** is a real-world quantity. The drift
> is real, it will be experienced, and removing it designs for a market that does not exist.
> `scripts/alpha.py` includes it.

> **A second correction, to my own diagnosis.** I claimed conditioning on low volatility selects
> bull-market periods and inflates the drift. **The data says otherwise:** mean 5-day return is
> **+0.292% unconditional** vs **+0.298% low-vol-conditioned** — annualised **15.8%** vs **16.2%**.
> Essentially identical. The conditioning is not the problem. The drift is simply the drift.

## Measured drift, 2016–2026

| Sample | Mean 5-day return | Annualised |
|---|---|---|
| Unconditional (2,653 windows) | +0.292% | **+15.8%** |
| Low-vol conditioned (978) | +0.298% | **+16.2%** |

**Caveat worth stating in the write-up:** ~16%/yr is high against the long-run equity return of
~10%. 2016–2026 was an exceptional decade. Carrying it forward at full strength is the aggressive
assumption — not because drift is unreal, but because *this* drift is above the long-run mean.

## The right decomposition

Not drift-in vs drift-out. Instead: of the total EV, how much is market exposure you could buy more
cheaply by holding the underlying, and how much is options-specific edge?

```
total EV  =  beta component  +  alpha
             (net Δ × spot × μ)   (residual)
```

Low-vol conditioned, drift included, conservative fills, $ per 1-lot:

| Structure | net Δ | **total EV** | = beta | + **alpha** | alpha/risk | win% |
|---|---|---|---|---|---|---|
| call debit 777/787 | 0.20 | **+59.5** | +45.7 | +13.8 | 0.115 | 29.1% |
| **put credit 777/767** | 0.37 | **+38.1** | **+85.0** | **−46.8** | −0.096 | 53.9% |
| call debit 777/782 | 0.13 | +30.9 | +30.9 | 0.0 | 0.000 | 29.9% |
| call debit 785/795 | 0.04 | +29.6 | +8.9 | **+20.6** | 1.289 | 10.0% |
| call debit 785/790 | 0.03 | +19.4 | +7.4 | **+12.0** | 0.856 | 10.0% |
| call debit 762/772 | 0.34 | +8.8 | +77.2 | **−68.4** | −0.100 | 63.9% |
| put debit 754/744 | −0.06 | +2.7 | −14.7 | **+17.3** | 0.423 | 8.2% |

**Only 15 of 99 structures show positive alpha.**

## The headline finding

**The put credit spread — the structure most of this field is running — has positive EV and
negative alpha.**

`put credit 777/767` expects **+$38** with a 53.9% win rate. But a delta-matched underlying position
would have earned **+$85** over the same distribution. The spread captures less than half the drift
it is exposed to, and gives back the rest to premium and spread cost. **You would do better holding
the delta directly.**

That is the same verdict `p_be ≈ 93.5%` reached in Part 3 from price structure, and the same one the
VRP gate reached from volatility estimation — now confirmed a third way, from realised outcomes.
Three independent methods agreeing is the strongest evidence in this document.

## What this changes strategically

**Drift over the window is worth more than any options edge available.** At 16%/yr, five sessions
carries an expected **+0.32%** — roughly **$320** on $100k at full delta exposure. Every options
alpha measured above is smaller than that.

The VRP gate says "do not sell volatility," and on volatility grounds it is right. But it is blind
to drift, so "no trade" was the wrong conclusion to draw from it. **Long-delta defined-risk
structures have positive expected value here regardless of what volatility is doing** — and call
debit spreads express that with max loss fixed at construction.

The alpha column then says which of those *also* add options edge rather than merely renting beta:
`call debit 785/795` (+$20.6 alpha) and the put debit spreads (the skew harvest from Part 2)
survive; `call debit 777/782` is pure beta (alpha 0.0); the credit spreads are negative.

## Caveats that bind

- **Far-OTM alpha estimates are small-sample.** `call debit 785/795` wins 10% of the time — ~98 of
  978 windows — and its alpha/risk swings from 1.289 (low-vol) to 4.691 (unconditional). Apply the
  Wilson lower bound and Beta-Binomial shrinkage from `EDGE-AND-SIZING.md` before sizing on it.
- **The beta benchmark uses initial net delta**, a first-order approximation. Delta moves over the
  life of the structure; a path-dependent benchmark would be more honest.
- **Friday-close quotes.** Wide and possibly stale. Re-run in Monday RTH before acting.

# Part 4 — Recommendation

1. **Keep short volatility premium as the base strategy.** It carries the strongest prior available
   — thirty years, published, replicated. That prior does not need to be re-established from four
   sessions, which is the whole point.
2. **Gate it on the live VRP measurement and be genuinely willing to trade nothing.** The current
   regime is hostile (front IV 7.9–10.6%, `TS = 0.667`) and the gate is estimator-sensitive
   (`LIVE-READINGS.md`). Refusal is a legitimate output.
3. **Prefer short-dated, higher-frequency structures** — the only lever that raises bet count inside
   the window.
4. **Diversify across factors, not tickers.** QQQ/IWM for equity, TLT for rates, GLD for gold.
   Drop SPY unless Monday's live spreads beat QQQ's.
5. **Size per `EDGE-AND-SIZING.md`** — quarter Kelly on the Wilson lower bound of a shrunken
   estimate, floor 0.25%, cap 2%.
6. **Decide explicitly** whether you are optimising expected *score* or chasing the P&L category,
   and say which in the write-up. They pull in opposite directions and pretending otherwise is the
   most common unforced error in this format.

## The submission-level point

Nothing in the surveyed field has quantified the noise floor. **"A Sharpe-1.4 strategy yields
+0.22% ± 1.26% over this window, therefore four sessions of P&L cannot distinguish skill from
luck — here is what we did about it"** is a stronger paper than any strategy claim, and it is
defensible whatever the P&L turns out to be.

That framing also inoculates the submission against its own worst outcome: a losing week becomes
evidence the analysis was right, rather than evidence the agent was wrong.

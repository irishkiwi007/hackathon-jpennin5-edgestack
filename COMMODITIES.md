# Commodities — a structurally different surface

**Question: does the competition require equities?** No. The rules impose exactly three core
requirements — autonomous agent on the Trading API, MCP *or* CLI, and *"all strategies must
incorporate options trading."* The word "equity" appears **zero times** on the event page.

**Can we trade commodities?** Not futures — Alpaca has no futures product. But commodity **ETF
options** are tradeable and confirmed live: **GLD, SLV, GDX, USO** all return contracts. UNG lists
but has no usable chain. DBA, DBC, CORN, WEAT, PPLT have no options at all.

Scripts: `scripts/commodity.py`, `scripts/commodity2.py`.

---

## 1. The skew runs the opposite way

25-delta risk reversal, `RR25 = IV(25Δ call) − IV(25Δ put)`, live chains:

| Symbol | ATM IV | IV 25Δ put | IV 25Δ call | **RR25** | Shape |
|---|---|---|---|---|---|
| SPY | 11.7% | 13.9% | 9.9% | **−3.9** | put skew |
| QQQ | 16.9% | 19.1% | 15.4% | **−3.7** | put skew |
| GLD | 23.2% | 23.4% | 24.0% | +0.6 | flat |
| **SLV** | 42.3% | 41.7% | 45.3% | **+3.7** | **call skew** |
| **USO** | 39.1% | 39.1% | 42.2% | **+3.0** | **call skew** |
| **GDX** | 46.7% | 45.8% | 47.6% | **+1.8** | **call skew** |

Equity indices carry persistent put skew — institutions pay up for crash protection, and that is the
overpricing every earlier analysis converged on. **Commodities invert it.** Producers hedge
downside while consumers hedge upside, and supply shocks push prices *up*, so the call is the bid
wing. This is a genuinely different surface, not a different ticker on the same one.

## 2. Two corrections to my own first pass

**Split adjustment.** Alpaca bars default to `--adjustment raw`. It matters:

| Symbol | Raw drift | **Adjusted drift** |
|---|---|---|
| **USO** | **26.1%** | **3.7%** |
| SPY | 13.4% | 15.2% |
| GDX | 20.2% | 21.3% |

USO did a 1:8 reverse split in April 2020. Every earlier USO number — including the absurd
"+157%/yr" in the diversification scan — was a raw-data artifact. **Use `--adjustment all`.**

**The tail-frequency screen was contaminated.** My first pass compared implied vs empirical tail
probability across assets by √t-rescaling each expiry's move. But VR < 1 means √t overstates the
move, and the bias grows with IV — so high-vol commodities were penalised mechanically and all read
~0.50 while SPY read 0.83. That comparison was meaningless. The clean test is IV against each
asset's **own** realised vol.

## 3. The finding: commodity vol is at extreme highs, equity vol is not

| Symbol | ATM IV | RV20 now | RV median | **RV percentile** | IV/RVmed | Verdict |
|---|---|---|---|---|---|---|
| SPY | 11.7% | 10.5% | 12.2% | 38 | 0.96 | no edge |
| QQQ | 16.9% | 18.0% | 17.2% | 55 | 0.98 | no edge |
| IWM | 16.6% | 13.8% | 18.9% | 22 | 0.88 | buy premium |
| **GLD** | 23.2% | **25.2%** | 13.3% | **93rd** | **1.75** | **sell premium** |
| **GDX** | 46.7% | 53.8% | 31.9% | **91st** | 1.46 | sell premium |
| **USO** | 39.1% | 47.4% | 30.1% | **86th** | 1.30 | sell premium |
| **SLV** | 42.3% | 34.9% | 23.6% | **82nd** | 1.79 | sell premium |

**GLD realised vol is at the 93rd percentile of its own decade** — while SPY sits at the 38th.
The two complexes are in opposite volatility regimes right now.

## 4. Vol mean reversion holds everywhere

Same test that was established for SPY over 33 years, run per asset:

| Symbol | low-tercile fwd/trail | high-tercile fwd/trail | Mean-reverts? |
|---|---|---|---|
| SPY | 1.431 | 0.846 | yes |
| GLD | 1.248 | 0.855 | yes |
| SLV | 1.141 | 0.904 | yes |
| GDX | 1.223 | 0.876 | yes |
| USO | 1.325 | 0.817 | yes |

Universal. Vol falls from elevated levels in every one of these assets.

## 5. The hypothesis this generates

Commodities are at the **82nd–93rd** vol percentile, vol mean-reverts down from there, and IV sits
**1.30–1.79×** their long-run median realised vol.

Crucially, IV/RV against *current* realised is only 0.82–1.21 — meaning **the commodity option
market is discounting the coming mean reversion far less than the equity market does.** On SPY in
high-vol states, IV/RV compressed to 0.60; the sellers were already paid nothing extra. Commodities
show no such compression.

**That is a short-premium setup, and it is the first thing found that is not in the equity complex,
not correlated to it, and not already crowded by the competitor field.**

## What is NOT established

- **No backtest.** Commodity option history on Alpaca starts 2024 and the chains are thin. This is a
  cross-sectional observation, not a validated edge — the same category of evidence that has been
  overturned by walk-forward testing twice already in this project.
- **Liquidity is materially worse.** GLD median spread 6.26% of premium, GDX 13.8%, versus SPY's
  10.2% cost-to-credit on a matched structure. Wide markets eat exactly this kind of edge.
- **Defined risk still costs the edge.** Alpaca bans naked shorts, so any expression is an iron
  condor or butterfly — and that is precisely what collapsed the one significant equity result
  (t 3.62 → ≤1.56).
- **n = 1 regime.** One reading, one day.

The GLD straddle backtest is running to test leg one of this.

---

# 6. The GLD backtest — and why it kills both "significant" results

Same machinery, same buckets, GLD instead of SPY. 120 cycles, real prices:

| Vol tercile | n | mean RV | IV/RV | LONG $ | win% | SHORT $ | win% | **t** | |
|---|---|---|---|---|---|---|---|---|---|
| **LOW** | 40 | 12.2% | 0.82 | **+574** | 62.5% | −574 | 35.0% | **−3.54** | **SIG** |
| MID | 40 | 17.3% | 0.63 | +62 | 47.5% | −62 | 52.5% | −0.48 | – |
| HIGH | 40 | 30.3% | 0.55 | −54 | 47.5% | +54 | 52.5% | 0.23 | – |
| ALL | 120 | 19.9% | 0.67 | +194 | 52.5% | −194 | 46.7% | −1.80 | – |

## The two significant results point in opposite directions

| | Low-vol tercile | t |
|---|---|---|
| **SPY** | **SHORT** premium wins, +$567 | **+3.62** |
| **GLD** | **LONG** premium wins, +$574 | **−3.54** |

Same test, same bucket, same period, same method — **equal magnitude, opposite sign.**

If "sell premium when vol is low" were a structural fact it would not reverse across underlyings.
Two contradictory t≈3.5 results, drawn from ~628 tests where the expected max under pure noise is
3.31, is the signature of **noise, not edge**. Neither survives.

The supporting tell is the same one seen in the equity butterflies: non-monotone buckets. On GLD's
IV/RV split, the *middle* bucket is significant (t = −2.81) while both extremes are not. Real
effects are monotone in an ordered variable.

## What IS real, and interpretable

The **IV/RV level** differs systematically between the two complexes:

| | low tercile | mid | high | ALL |
|---|---|---|---|---|
| SPY IV/RV | 0.94 | 0.75 | 0.60 | 0.76 |
| GLD IV/RV | 0.82 | 0.63 | 0.55 | **0.67** |

GLD options are **cheaper relative to their own realised vol at every level**, and overall long
premium won on GLD (+$194/trade) while short premium won on SPY (+$190/trade). That is the variance
risk premium behaving exactly as the literature says: largest in equity indices where hedging demand
is one-sided, smaller in commodities where it is two-sided.

**That is a real cross-sectional difference. It is not, on this evidence, a tradeable one.**

## Correcting my own screen from Part 3

The `IV/RVmed = 1.75 → SELL premium` verdict on GLD was misleading. It compared today's IV to the
**long-run median** realised vol. What actually matters is IV versus **forward** realised — and from
a 93rd-percentile vol state, forward realised stays elevated (high-tercile fwd/trail = 0.855, so
≈21.5% against 23.2% IV). The edge is marginal at best, and the backtest finds nothing significant
in GLD's high-vol bucket, which is exactly where GLD sits today (RV20 27.8%, 83rd percentile).

## Net answer

**Yes, you can trade commodities** — no rule prevents it, GLD/SLV/GDX/USO options are live, they
carry the opposite skew, they are in the opposite vol regime, and they are uncorrelated to the
equity book the rest of the field is crowded into.

**No, that does not hand us an edge.** The one thing the wider surface did deliver is a clean
falsification: it took the single significant result of the whole project and showed it reverses on
another underlying.

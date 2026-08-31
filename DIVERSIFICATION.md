# Can we get independent bets? — measured, not assumed

Question: the drift-aligned core wins ~26% of the time. Over ~4 bets that is a 30% chance of zero
winners. Can uncorrelated assets supply independent bets and fix that without giving up edge?

**Answer: no. There is effectively one bet with genuine edge, and right now the diversification
is not even there to be had.** Scripts: `scripts/uncorr.py`, `scripts/gld.py`, `scripts/regime.py`.

---

## Step 1 — which assets are uncorrelated AND have liquid options?

26 candidates, 5-day returns, 2018–2026. Six passed |corr| < 0.55 with a usable chain:

| Symbol | Group | corr SPY | Ann. drift | Median spread |
|---|---|---|---|---|
| GLD | gold | +0.194 | **+16.6%** | 6.5% |
| GDX | gold | +0.318 | +27.2% | 13.8% |
| SLV | gold | +0.324 | +24.2% | 6.0% |
| TLT | rates | **+0.027** | −3.6% | 3.7% |
| IEF | rates | +0.042 | −1.1% | 5.3% |
| LQD | rates | +0.499 | −0.9% | 9.8% |

The whole equity complex is one factor: QQQ 0.92, DIA 0.94, IWM 0.86 to SPY. **Ten equity tickers
is one bet.** And the candidates cluster internally too — GLD/GDX/SLV run 0.74–0.83 with each
other, TLT/IEF 0.91. So the real factor count is three: equity, gold, rates.

*(USO's +157%/yr and UVXY's +1401%/yr are reverse-split artifacts, not returns. Ignore them.)*

## Step 2 — does the edge exist on the uncorrelated assets?

An uncorrelated asset with no edge adds variance without expected return. Same regime-partitioned
alpha test, applied to each:

| Underlying | Drift | Structures tested | **Positive alpha in every regime** | Best |
|---|---|---|---|---|
| **GLD** | +14.9% | 54 | **0** | — nothing survives |
| TLT | −3.3% | 8 | 2 | `call debit 83.5/84`: alpha $4.3, **risk $9**, chain only 15C/15P |
| SLV | +21.3% | 54 | 5 | all put **credit** spreads, alpha/risk **0.004–0.020** ≈ zero |
| **SPY** | +15.8% | 95 | 11 | `call debit 780/785`: alpha $36.5, risk $45, worst α/R **0.221** |

**GLD is the decisive result.** It has the profile you would design for — genuinely uncorrelated,
+14.9%/yr drift, liquid chain — and **zero of 54 structures** show regime-stable alpha. The SPY edge
does not generalise; it is specific to SPY's skew.

TLT's two survivors risk $9 each on a 15-strike chain and fight a negative drift. SLV's five are
penny-collecting credit spreads with essentially no edge.

> **There is one bet with genuine edge: SPY. Diversification cannot solve the zero-winner problem
> because there is nothing edge-bearing to diversify into.**

---

## Step 3 — correlations move, and the movement is the signal

The static table above is misleading, and dangerously so. Rolling 63-day correlation to SPY:

| | Decade average | **Current** |
|---|---|---|
| SPY–TLT | +0.03 | **+0.290** |
| SPY–GLD | +0.19 | **+0.477** |
| SPY–IWM | 0.86 | +0.775 |
| SPY–HYG | 0.76 | +0.658 |
| **Average \|corr\|** | — | **0.551 — 70th percentile of the decade** |

**GLD's current correlation to SPY is 2.5× its decade average.** The diversification implied by the
static table is not available today. TLT is *positively* correlated — bonds are not hedging equities
at all right now.

SPY–TLT ranged from **−0.69 to +0.57** over the decade, positive 35% of the time. The "bonds hedge
stocks" assumption held only 65% of the last decade — it is a regime, not a law.

### Correlation as a positioning indicator

| SPY–TLT | Regime | What it means for positioning |
|---|---|---|
| < −0.25 | flight-to-quality | Bonds genuinely offset equity drawdowns. A rates leg is real diversification. |
| −0.25 to +0.15 | transitional | Hedge relationship weak both ways. Do not rely on it. |
| **> +0.15** | **rates-driven** | **Bonds are a second bet on the same driver. Diversification unavailable.** |

**Currently +0.290 → rates-driven.** Both equities and bonds are being priced off the same rates
impulse. Adding a TLT leg would not hedge anything.

Average cross-asset |corr| at the **70th percentile** says the same thing from another angle: when
everything correlates, position size is the only remaining risk control. Rising correlation is also
a classic pre-stress signal, so this is worth re-checking each morning of the competition — it is a
cheap regime read and nothing in the surveyed field computes it.

---

## What follows

1. **Diversification across underlyings is closed** — on edge grounds (GLD has none) and on
   correlation grounds (it is 0.477 right now, not 0.19).
2. **The 26% win rate cannot be fixed by more bets.** With one edge-bearing underlying, extra
   positions are the same bet at different strikes.
3. **That leaves three honest options**: accept the ~30% zero-winner risk; buy the win rate with a
   complement and pay ~18× in risk-adjusted return; or cut size so the outcome matters less.
4. **Run the correlation regime check daily.** It is the cheapest useful signal found in this whole
   exercise, and it currently says: do not expect a hedge to hedge.

---

# Addendum (2026-08-30) — parking the flat hours: XLP / gold basket while the core is idle

Question (from the trader): the overnight core is flat every day session, and flat overnight
when the trend gate is closed — do we earn anything holding XLP or the gold-royalty basket
(WPM/RGLD/FNV, as in the older strategies) through those windows? The engine trial already
killed full-session risk-off parking (fails train; gold miners were lethal in the GFC). This
tests the two cuts that sweep did not cover. Script: `scripts/park_flat.py`, 33y record,
per-name round-trip costs (SPY 1bp, XLP 2bp, gold names 4bp), rule counts only if it helps
BOTH windows (train 2008-17, validation 2018-26).

## Anatomy first — the drift everywhere lives overnight

| series (gross, no costs) | intraday | overnight |
|---|---|---|
| SPY | Sharpe **-0.07** | Sharpe **0.72** |
| XLP | -0.04 | 0.36 |
| gold basket WPM/RGLD/FNV | -0.24 (CAGR -8.0%) | 0.80 (CAGR +26.5%) |

The intraday session carries no drift in ANY of these — the core's own founding measurement,
reproduced in the assets we would park in. (The gold basket's huge gross overnight number
leans on thin early-RGLD prices and survives no cost or discipline test below — recorded as
anatomy, not as an edge.)

## Verdicts — everything fails

| variant (net of costs) | full-record Sharpe | train | valid | verdict |
|---|---|---|---|---|
| core only (reference) | 0.76 | 0.02 | 0.58 | — |
| A. + XLP held intraday | 0.19 (DD -63%) | -0.10 | 0.35 | dead — no drift, daily costs |
| A. + gold held intraday | -0.28 (DD -99.6%) | -0.71 | -0.09 | dead |
| B. + XLP on gate-closed nights | 0.67 (DD -29%) | 0.41 | 0.48 | **fails validation** |
| B. + gold on gate-closed nights | 0.72 (DD -50%) | 0.57 | 0.35 | **fails validation, doubles DD** |

The B variants are the seductive ones: both improve the weak train window and give it back
in validation — the same shape that got full-session gold parking rejected in the engine
trial, now confirmed from the research-engine side. The gold version also doubles the max
drawdown (-50% vs -25%), destroying the property the stack exists for.

**Verdict: the flat hours stay in cash. Intraday parking is structurally dead (no intraday
drift in SPY, XLP, or gold, minus a round trip per day); gate-closed-night parking fails
the both-windows rule in every form tried, on top of its engine-trial rejection.**

---

# Addendum 2 (2026-08-30) — bill parking (SGOV) with a yield filter: ADOPTED in research

Same question as above but with the right asset: T-bills are rate capture, not a drift bet —
near-zero vol, no drawdown, deterministic accrual. Per the trader's standing rule, cash parks
in bills ONLY when the yield covers the round trip. Script: `scripts/park_sgov.py`, real
DGS3MO yields 1994-2026, bills modeled as y/252 accrual, 1bp round trip (2bp variant shown).

## The anatomy that makes it work

Gate-closed time is 18.4% of sessions in **49 stretches: median 3 days, mean 31, max 405** —
a long tail of bear-market stretches carries nearly all the parked days. One round trip per
stretch means ~24 round trips in 33 years: the cost side is almost irrelevant (results move
<1 bp/yr going from 1bp to 2bp costs). The breakeven for even a median 3-session stretch is
y > 252 x 0.01% / 3 ≈ 0.84% — so **y >= 1% is the principled filter**: it self-finances the
short stretches, and the long stretches self-finance at any yield.

## Result (filter y >= 1%, 1bp rt)

| | CAGR | vol | Sharpe | maxDD | train 08-17 | valid 18-26 |
|---|---|---|---|---|---|---|
| core only | 8.01% | 7.92% | 0.76 | -24.9% | 0.023 | 0.582 |
| **core + bill parking** | **8.40%** | 7.92% | **0.81** | -24.9% | **0.041** | **0.634** |

+36 bps/yr on the full record (+14 train, +46 validation), vol and drawdown untouched,
**helps both windows** — the first overlay to pass the discipline since the credit canary.
Filter sensitivity: 0.5% and 1.0% are equivalent; 2.0% skips the long bear stretches that
begin at crashing yields (GFC, covid) and forfeits most of the carry — the filter belongs at
the cost-breakeven, not higher.

The daily-churn variant (bills held intraday on gate-open days) self-filters to y >= 5.04%
and adds 3.9 bps/yr — not worth the order surface. Stretch parking only.

Honest caveats: the Sharpe lift is partly definitional (excess return measured against a
fixed 2% hurdle while capturing floating bills); the real claim is +36 bps/yr of carry at
unchanged risk. Bills modeled as pure accrual (SGOV NAV wiggle and settlement ignored —
immaterial at this cost sensitivity).

**Rollout: adopted in research. Live-agent implementation deliberately deferred until after
hackathon judging (Sep 4) — the running system is frozen on the rehearsed code path. With
the gate currently closed and bills at 3.84%, the rule would have the account parked today;
at ~1.5 bp/week it is immaterial to the judged window.**

# Edge portfolio

Independent edges, each established separately, then combined. The combination is the point:
edges that fire at the same times just double one bet.

Scripts: `scripts/overnight2.py`, `scripts/calendar2.py`, `scripts/edges34.py`,
`scripts/combine.py`, `scripts/vrp_new.py`, `scripts/vrp_risk.py`.

## The inventory

| # | edge | how established | strength |
|---|---|---|---|
| 1 | Variance risk premium | CBOE `^PUT` index, 30y real track record | Sharpe 0.43 vs SPX 0.34 |
| 2 | **Overnight drift** | SPY 1993-2026, 7/8 ETFs, 8/9 eras | **Sharpe 0.89 vs 0.05 intraday** |
| 3 | Turn of month | 6/6 ETFs directionally | weak, t 0.26-2.02 — **dropped** |
| 4 | 12-month trend filter | SPY fwd21 by trend state | +1.011% (t=5.77) vs +0.113% (t=0.17) |
| 5 | Calm-bond regime | out-of-sample on 4,359 events | t(diff) = 6.58 |

## Edge 1 — variance risk premium (verified against a real index)

After four internal option-pricing models disagreed by 10x, the question was settled with CBOE's
actual investable track record rather than any model:

| | CAGR | vol | Sharpe | max DD |
|---|---|---|---|---|
| `^PUT` (sell ATM SPX puts) | 8.54% | 15.23% | **0.43** | -37.1% |
| `^GSPC` | 8.53% | 19.11% | 0.34 | -56.8% |

**The entire edge is risk reduction, not excess return** — same CAGR, 20% less volatility, 35%
less drawdown. Worth ~+0.09 Sharpe. Note this makes it a poor *contest* strategy: a P&L
competition does not reward lower volatility.

## Edge 2 — overnight drift (the strongest single finding)

Overnight = close to next open. Intraday = open to close.

| | overnight ann | t | intraday ann | t |
|---|---|---|---|---|
| SPY | **+9.91%** | 5.35 | +0.77% | 0.30 |
| QQQ | **+13.74%** | 4.89 | **-2.69%** | -0.64 |
| SOXX | **+17.55%** | 4.30 | **-3.37%** | -0.66 |
| HYG | +8.14% | 5.20 | -2.94% | -1.47 |
| TLT | +0.39% | 0.19 | +3.31% | 1.53 |

7/8 ETFs; overnight beat intraday in **8/9 eras**. TLT is the exception — bonds again, consistent
with every other finding here.

Overnight carries **lower** volatility (0.671% vs 0.960% daily) *and* higher return:
**Sharpe 0.89 vs 0.05.** Net of 0.7bp round-trip cost: ~8% annualised.

Not a calendar effect in disguise — overnight is positive in every bucket tested
(TOM 0.0356% t=2.30, mid-month 0.0380% t=4.79, Mon-Tue 0.0458% t=3.80, Wed-Fri 0.0321% t=3.68).

## The combined stack (SPY, 1993-2026)

| strategy | CAGR | vol | Sharpe | max DD | exposure |
|---|---|---|---|---|---|
| buy and hold | 10.76% | 18.81% | 0.47 | -55.2% | 99% |
| overnight only | 7.83% | 10.75% | 0.54 | -35.0% | 100% |
| **overnight + trend filter** | **8.68%** | **7.92%** | **0.84** | **-24.9%** | 82% |
| overnight + trend + calm bonds | 7.01% | 6.20% | 0.81 | **-20.5%** | 57% |
| overnight + trend + TOM sizing | 7.90% | 7.56% | 0.78 | -24.1% | 82% |

**Sharpe 0.84 vs 0.47** at 42% of the volatility and 45% of the drawdown.

**Independence is measured, not assumed: corr(overnight, intraday) = 0.004.**

## Why it belongs in a bundle

| era | overnight+trend | buy & hold |
|---|---|---|
| 2000-2002 dotcom | **+5.41%** | -14.59% |
| 2008-2009 GFC | **+2.16%** | -10.62% |
| 2003-2007 | +9.41% | +12.64% |
| 2010-2015 bull | +3.01% | +12.88% |
| 2022-2023 | -1.14% | +1.62% |
| 2024-2026 | +11.91% | +20.94% |

It earns when the index loses and lags when the index runs — a genuinely different return
stream, which is the entire reason to hold more than one edge.

## Rejected

- **Turn-of-month sizing**: 6/6 directionally but adding it LOWERED Sharpe (0.78 vs 0.84).
- **Day of week / month of year**: all |t| < 1.7. Noise.
- **Time-series momentum cross-sectionally**: only 3/8 ETFs. Works as a broad-index *filter*
  (edge 4), not as a selection rule.
- **Leveraged ETFs**: spot/friction 33x worse than SPY (TQQQ 575 vs SPY 19,234), and the
  volatility drag, while real and significant (TQQQ -0.40%/21 sessions, t=-5.42; all 7 pairs
  negative), is an order of magnitude smaller than the drift — TQQQ still returned +4.87% in the
  most turbulent bucket. Nothing to short.

## Untested

- **VIX term structure** (VIX/VIX3M): `^VIX3M` and `^VXV` unavailable through the Yahoo path.
- **Earnings IV crush**: needs an earnings calendar.

## Caveats worth keeping

- The overnight anomaly is well documented in the literature and is a candidate for decay;
  2022-2023 was negative (-1.14%). 2024-2026 was strong (+11.91%), so no clear decay yet.
- Capturing it requires 252 round trips a year. 0.7bp is deducted; real open-auction slippage
  could exceed that.
- Overnight cannot be stopped out. Worst single overnight in sample: **-11.04%**.

---

# Edge 6 — earnings implied-move overpricing (established, with caveats)

Scripts: `scripts/earnings2.py` (attempt 1, wrong), `scripts/earnings2fix.py` (attempt 2, wrong),
`scripts/earn_final.py` (corrected), `scripts/val2.py` (validation).

## Two failed attempts, and why they failed

Both produced impossible answers, in opposite directions, from **selection bias**:

1. **Ratio 10.8x** (JNJ at 43x). Cause: Yahoo's `earningsHistory.quarter` is the fiscal
   quarter-END date, not the announcement date — so the "reaction" was a semi-random session.
   The implied side also used a straddle spanning 11-45 days, which prices the total move over
   its whole life, not the one-day jump.
2. **Ratio 0.35** ("options underprice earnings"). Cause: detecting earnings as ">2 sigma move on
   high volume" selects the largest moves *by construction*, guaranteeing realized > implied.
   The straddles priced mostly contained no earnings event at all.

## The corrected method

The bias is the whole problem, so earnings dates are located using information **independent of
the price move**:

- **ANCHOR**: Yahoo `calendarEvents.earningsCallDate` — an exact, confirmed announcement date.
- **PROJECT**: step back ~91 calendar days (earnings are quarterly).
- **REFINE**: within +/-7 days, pick the session with the highest volume *relative to its own
  60-day norm*.

Volume identifies the event; the move is measured afterwards. Since the move never selected the
day, the measured move is unbiased.

Implied jump is isolated from ordinary volatility rather than compared raw:

    implied_total^2  ~  ordinary^2 + jump^2   ->   jump = sqrt(total^2 - ordinary^2)

## Validation

| check | result | verdict |
|---|---|---|
| quarterly cadence | 3.7-3.9 events/year for most names | **passes** |
| move vs VOLUME-MATCHED non-located days | **1.31x** (median 1.34), 27/36 names | **passes** |
| news-headline cross-check | 7/13 = 54%, 95% CI [25%, 81%] | **inconclusive** (n too small) |

The move check is the important one: days were chosen by volume, so a larger move is independent
evidence. It also flags exactly where the locator FAILS — **PANW 0.48, COST 0.53** — which are
precisely the two names whose realized figures were implausible.

## Result

| name | implied jump | realized jump | ratio |
|---|---|---|---|
| NKE | 10.47% | 8.76% | 1.20 |
| MU | 8.79% | 6.70% | 1.31 |
| ADBE | 9.73% | 7.33% | 1.33 |
| ORCL | 13.72% | 10.31% | 1.33 |
| AVGO | 8.86% | 6.04% | 1.47 |
| PEP | 4.81% | 2.35% | 2.05 (low-vol, fragile) |
| COST | 3.42% | 1.26% | 2.71 (**locator failed**) |
| PANW | 10.84% | 2.00% | 5.42 (**locator failed**) |

Implied exceeded realized in **8/8**, +3.24 pct-points, **t=3.95**.

**On the five clean high-volatility names the ratio is 1.20-1.47, mean ~1.33** — options imply
about a third more than these names actually move. That matches the published earnings variance
risk premium (20-40%), which is meaningful corroboration: an independent method landing on the
established answer.

## Why this one matters more than the others

Every other edge here failed on one of two things — size per trade, or frequency. This one has
both:

- **Size**: ~2% of spot of overpricing. On a $200 name that is ~$400/contract gross against
  ~$40-80 of 4-leg friction on liquid names.
- **Frequency**: dozens of liquid names report every week. No 0.7-signals-per-window problem.

## Open

- **n=8** on the implied side (only names with earnings inside a currently-quotable expiry).
- Tail risk is real: a surprise can blow through the wings of a defined-risk structure. Not yet
  measured.
- The low-volatility names (COST, PEP) are numerically fragile because
  `sqrt(total^2 - ordinary^2)` is sensitive when the two terms are close. Restrict to names whose
  jump is large relative to their ordinary volatility.

---

# THE EQUITY EXPRESSION — where the edges actually pay

The recurring failure all session was never the edges. It was the wrapper. Retail option bid/ask
runs $50-400 per contract round trip, which is the same order of magnitude as the edges
themselves. **SPY equity crosses at about 1 basis point.**

The competition requires options to be *incorporated*, not exclusive — so the edges can be
expressed where they actually survive, with an options overlay alongside.

## Same signal, two wrappers

Capitulation events on SPY, 3-session hold:

| expression | gross | friction | net | capital at risk |
|---|---|---|---|---|
| SPY equity | +1.59% | 0.01% | **+1.58%** | full notional |
| SPY bull put spread (real VIX pricing) | — | — | +$38/contract | $3,597 |

Both positive; the option gives better return-on-risk but tiny absolute dollars and fires 1.9x
a year. In equity the same signal is directly capturable.

*(Correction to an earlier figure in this session: a friction comparison printed "-6.72% net in
options" — that divided $56 of friction by one share instead of the contract's 100 shares. Real
friction is 0.073% of notional, not 7.28%.)*

## The strategy

- **CORE**: long SPY **overnight only** (close to next open) when the 12-month trend is up.
- **SLEEVE**: capitulation basket at **0.5x weight** — stretch < -2.5 and volume 1.4x-2.5x,
  equal-weighted across signals, 3-session hold, across 7 ETFs.

Capitulation event counts (33 years): SPY 24, QQQ 14, SOXX 12, XLV 20, XLP 16, HYG 37, FDN 13 —
**136 total, 4.1/yr**. Net of real per-name equity costs: **+1.419%/event, 67.6% win, t=4.27**.

## Result (SPY-based, 1994-2026, costs included)

| configuration | CAGR | vol | Sharpe | max DD |
|---|---|---|---|---|
| buy and hold | 7.98% | 18.81% | 0.32 | -58.9% |
| core only | 8.01% | 7.92% | 0.76 | -24.9% |
| **core + sleeve 0.5x** | **9.72%** | **9.07%** | **0.85** | **-26.6%** |
| core + sleeve 1.0x | 11.25% | 12.03% | 0.77 | -28.5% |
| core + sleeve 1.0x, calm only | 9.81% | 9.38% | 0.83 | -24.9% |
| sleeve only | 2.99% | 9.25% | 0.11 | -14.2% |

**+1.74pp more CAGR than buy-and-hold, at 48% of the volatility, Sharpe 0.85 vs 0.32, drawdown
-26.6% vs -58.9%.** Correlation with buy-and-hold **+0.330**.

## Era stability — positive in 8/9

| era | stack | b&h | stack Sharpe | b&h Sharpe |
|---|---|---|---|---|
| 1994-1999 | +21.10% | +22.79% | **2.28** | 1.28 |
| 2000-2002 | **+7.77%** | -13.40% | **0.72** | -0.63 |
| 2003-2007 | +9.76% | +11.73% | **1.40** | 0.75 |
| 2008-2009 | **+6.15%** | -9.47% | **0.32** | -0.33 |
| 2010-2015 | +4.30% | +12.30% | 0.22 | 0.65 |
| 2016-2019 | +10.37% | +15.00% | **1.19** | 1.01 |
| 2020-2021 | +7.62% | +23.15% | 0.39 | 0.84 |
| 2022-2023 | -2.62% | +1.04% | -0.72 | -0.05 |
| 2024-2026 | +14.05% | +21.38% | 1.21 | 1.21 |

Beat buy-and-hold on Sharpe in 5/9 eras; **wins decisively in every bear market and lags in
strong bulls.** Worst single day -7.46% vs -10.94%.

## A bug worth recording

The first run of this test concluded the capitulation sleeve *hurt* (Sharpe 0.76 -> 0.71, sleeve
alone -0.15). That was an off-by-one: the simulation appended a position at the close of the
signal day, then began accruing returns from the NEXT day's close — **dropping the first and
largest day of every bounce** (+0.319% of the +0.669% three-day total). Corrected, the sleeve
adds Sharpe 0.76 -> 0.85.

## What more edges did NOT do

Stacking every validated edge was worse than stacking two: full stack Sharpe 0.60 vs
core+sleeve 0.85. Rarely-firing edges add volatility without adding enough return. **Two good
edges beat five.**

---

# CORRECTION — the earnings options strategy was rejected in error

The earnings structure was discarded on numbers that had already been flagged as unreliable in
the same output. Two compounding bugs, both pushing the same way:

**1. Friction overstated ~4x.** Cost was computed as `8 x median_half_spread_across_the_whole_
chain`, which included far-OTM strikes with very wide markets that were never going to be traded.
Using the actual per-strike half-spreads of the legs actually traded: an iron condor costs
**$97, not $384**.

**2. Strike selection unbounded.** `nearest()` returned the closest listed strike regardless of
distance from target, so on sparse chains the wings landed far from where intended — producing
mean credit $1,270 against mean risk $1,075, implying a $2,345 width that the structure could not
have. Fixed by requiring strikes to land within 1.5% of target or skipping the case.

## Corrected results

| structure | legs | n | mean $ | friction | win% | ret/risk | t |
|---|---|---|---|---|---|---|---|
| cash-secured put | 1 | 86 | +118 | 47 | 80.2% | 0.68% | 4.07 |
| short strangle | 2 | 70 | **+281** | 88 | 74.3% | 1.66% | **6.21** |
| put credit spread | 2 | 74 | +78 | 57 | 93.2% | 5.26% | 2.46 |
| **iron condor** | 4 | 58 | +194 | 97 | 89.7% | **16.07%** | 4.43 |

**All four positive and significant.** Method unchanged and still non-circular: implied from
today's live chain, realized from that name's own volume-located earnings history.

The short strangle is **not Alpaca-legal** (naked short call). Of the legal structures the
**iron condor is best**, at 16.07% return on risk.

## A reasoning error worth recording

Elsewhere in this session the conclusion was drawn that options strategies should **minimise leg
count**, since friction scales with crossings. Applied here that reasoning is wrong: the 4-leg
iron condor beats the 1-leg cash-secured put on return-on-risk by **24x** (16.07% vs 0.68%),
because the long wings cap the loss at the width instead of at the full strike. Fewer legs is not
better when the extra legs are what bound the tail.

## Standing against the rest of the session

| options strategy | return on risk | frequency |
|---|---|---|
| capitulation bull put spread (real VIX pricing) | 1.06% | 1.9/yr |
| rich-IV premium selling, calm regime | 0.75% | 54/yr |
| **earnings iron condor** | **16.07%** | **~4/name/yr across a wide universe** |

This is the strongest options result found, and unlike the others it has both size and frequency.

## Widened sample (149 names, 70-day forward window)

The result STRENGTHENED with more data:

| structure | legs | n | mean $ | friction | win% | ret/risk | t |
|---|---|---|---|---|---|---|---|
| cash-secured put | 1 | 116 | +123 | 53 | 82.8% | 0.69% | 4.01 |
| short strangle | 2 | 100 | +259 | 96 | 76.0% | 1.50% | 3.60 |
| put credit spread | 2 | 90 | +66 | 59 | 92.2% | 4.77% | 2.46 |
| **iron condor** | 4 | 74 | **+170** | 94 | 87.8% | **15.31%** | **4.79** |

Condor t rose 4.43 -> 4.79; return-on-risk held at ~15%. New names came in positive
(ABT +$177 / 81.2%, SNOW +$244 / 78.6%).

**The tail justified the wings.** On the wider sample the naked strangle's worst loss blew out
from -$1,166 to **-$5,209**, while the condor stayed capped at **-$1,425**. The strangle is also
not Alpaca-legal. The condor is the right structure on both counts.

## Open

- Only **8 names** had earnings inside a currently quotable expiry. That is a CALENDAR limit
  (late August sits between earnings seasons), not a method limit — in October the same screen
  qualifies dozens.
- **PEP remains negative (0% win)** — the known locator failure on that name.
- Tail runs to **-$1,166** on the strangle, **-$1,425** on the condor. Not yet stress-tested
  against a genuine earnings blowup.
- The realized histories are ~15 events per name over ~4 years. Longer history would help.

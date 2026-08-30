# Overshoot-and-reverse — VALIDATED

Tested 2026-08-29 on 8 ETFs from TrustyRustyEngine (`data/historical`), 1993–2026.
Scripts: `scripts/herd.py`, `scripts/herd2.py`, `scripts/herd3.py`.

Thesis (user): real information arrives only occasionally; between arrivals herding pushes price
past fair value and it retraces. The edge is **timing the turn**.

**Verdict: confirmed on the downside, rejected on the upside.**

## The core asymmetry

`stretch` = 5-day return / (trailing 20-day realized volatility x sqrt(5)). Newey-West t-stats
(lag = horizon) because daily sampling of h-day forward returns overlaps. Excess = vs each ETF's
own unconditional mean for that horizon, so market drift is retained in the raw column.

| 5-day stretch | n | f1 raw | f3 raw | t(f3) | f5 raw | t(f5) |
|---|---|---|---|---|---|---|
| deep down z<-2 | 1071 | +0.319% | **+0.669%** | **5.06** | +0.778% | 4.50 |
| down -2..-1 | 5678 | +0.105% | +0.240% | 3.17 | +0.387% | 3.38 |
| flat | 11714 | +0.037% | +0.103% | 0.06 | +0.172% | 0.08 |
| up 1..2 | 8247 | -0.021% | -0.023% | -5.03 | +0.019% | -4.29 |
| **extended up z>2** | 1016 | +0.002% | +0.017% | **-1.43** | +0.115% | -0.64 |

- Reversal after DOWN: **8/8 ETFs** agree on sign.
- Reversal after UP: only 5/8, and extreme-up is insignificant at every horizon.

**Panic is a fast fear response that overshoots and snaps back. Upside greed is slow and
grinding, so it does not overshoot the same way.** Long the panic; do not short the euphoria —
`up 1..2` underperforms (t=-4.6) but raw return is ~0, so drift eats the short.

## Surrogate

Shuffled returns, link between stretch and forward return destroyed, 300 draws:

- real deep-down f3 excess **+0.572%**
- surrogate **+0.002%**, 95% band [-0.126%, +0.148%] → **outside the band, REAL**

## Timing the turn: VOLUME, monotonically

Within deep-down days (z<-2), which exhaustion signal marks the bottom:

| volume vs 20d | n | f3 excess | t |
|---|---|---|---|
| light <1.0 | 217 | +0.170% | **0.65** |
| normal 1.0-1.4 | 274 | +0.528% | 2.73 |
| heavy 1.4-2.0 | 330 | +0.805% | **5.45** |
| climax >2.0 | 250 | +0.645% | 3.10 |

**A selloff on light volume does not bounce.** No flush = sellers still there. This is the
capitulation mechanism and it is directly actionable as a filter.

The volume filter improves the edge **monotonically at 4 of 5 stretch thresholds** — strong
evidence it is a real conditioning variable, not a fitted parameter.

Rejected as timing signals: streak (U-shaped, non-monotone), acceleration (non-monotone),
range expansion (noisy, n=44 in the climax bucket), gap (z-scale mis-specified — 817 of 1071
events landed in one bucket; do not interpret).

## Frequency vs edge (3-day hold)

| stretch | volume | n | per ETF-yr | f3 excess | t | win% |
|---|---|---|---|---|---|---|
| z<-2.5 | >1.4x | 203 | 0.8 | **+1.239%** | **5.88** | 66.5% |
| z<-2.0 | >1.4x | 580 | 2.2 | +0.736% | 5.44 | 63.3% |
| z<-1.5 | >1.4x | 1264 | 4.7 | +0.528% | 5.75 | 60.8% |
| z<-1.0 | >1.4x | 2261 | 8.5 | +0.298% | 4.42 | 58.1% |

Best exit is **5 days** (+0.414% excess, t=4.42, win 60.7%); 3-day ties on t; 10-day decays.

## Era stability

Deep-down (z<-2), f3 excess: **positive in 8 of 9 eras.** Critically it is **not a crisis
artifact** — GFC (t=1.23) and Covid (t=1.25) are among the *weakest*. Strongest are
2010-2015 (+0.995%, t=4.32) and **2024-2026, the current era (+1.364%, t=3.76)**.

The loosened signal (z<-1.0) is far less stable: positive 8/9 but t>1.5 in only 3 eras, with
2003-2007 negative and 2022-2023 exactly zero. **Edge degrades fast as the threshold loosens.**

## Per-ETF (z<-1.0, vol>1.4x)

Positive in **8/8**. Best: QQQ (+0.502%, t=2.43), XLV (+0.451%, t=2.59), HYG (+0.266%, t=2.74).
**TLT is dead** (+0.012%, t=0.11, win 45.7%) — bonds do not share the mechanism. Drop it.

## The competition problem

At z<-2.5 this fires 0.8x/ETF-year. Across 8 ETFs over a 5-session contest the expected count is
well under 1, and events **cluster** (a market-wide selloff fires the whole book at once, a quiet
week fires nothing). Feast or famine. Daily-bar version alone is not reliably tradeable in a
5-day window — see the intraday extension.

---

# THE TRADEABLE SIGNAL (final)

Validated twice on independent samples: 7 ETFs / 1993–2026 (engine data) and 50 ETFs / 2016–2026
(Alpaca). Scripts: `scripts/tiers.py`, `scripts/tierA33.py`, `scripts/wide.py`, `scripts/inday2.py`.

## Rule

**LONG when, on a daily close:**
- `stretch` = 5-day log return / (20-day realized volatility x sqrt(5)) **< -2.5**
- `volume` / 20-day average volume **between 1.8x and 2.5x**

**Hold 3 sessions.** (5 sessions performs similarly; 10 decays.)

## Performance, 33 years, 7 ETFs

| metric | value |
|---|---|
| n | 135 |
| raw return | **+1.646%** |
| excess vs own mean | +1.544% |
| Newey-West t | **5.42** |
| win rate | **68.1%** |
| Kelly f* | 0.34 |

**Drop-one-era: t stays 4.32–5.40 excluding ANY single era.** Removing 2024–2026 → t=5.16.
Not a single-regime artifact.

## The volume peak — why it matters

Disjoint cells at z<-2.5, 33 years:

| volume | n | raw | win | t |
|---|---|---|---|---|
| <1.0 | 38 | -0.172% | 47.4% | -0.53 |
| 1.0-1.4 | 47 | +0.184% | 48.9% | 0.21 |
| 1.4-1.8 | 59 | +0.721% | 64.4% | 2.67 |
| **1.8-2.5** | 77 | **+1.897%** | **70.1%** | **4.32** |
| >2.5 | 58 | +1.312% | 65.5% | 3.96 |

Monotone rise, then a **fall-off above 2.5x**. Interpretation: extreme volume means real
information genuinely arrived, so there is nothing to revert. Moderate-heavy volume is
capitulation with no news behind it. **The edge exists only when the move is emotional rather
than informational** — which is the original thesis, confirmed by its own boundary condition.

## What was tested and REJECTED

- **Intraday version** (5-min bars, 267k obs, time-of-day-normalised volume and volatility):
  dead and **wrong-signed**. Deep-down intraday → *further* decline (-1.07bp at 30min,
  -1.83bp at 60min), win 49-51%, |t|<2 everywhere. Volume filter does nothing intraday.
  Intraday shows mild *momentum* instead. **The mechanism requires overnight; it cannot be sped up.**
- **Cross-sectional pairs** (SOXX/QQQ, XBI/IBB, KRE/XLF + 11 more, 36,976 obs): every bucket
  |t|<0.7. No pairs mean-reversion. Closed as a route to more signals.
- **Shorting the upside overshoot**: extended-up (z>2) insignificant at every horizon, only
  5/8 ETFs on sign. `up 1..2` underperforms (t=-4.6) but raw ≈ 0, so drift eats the short.
- **TLT / bonds**: +0.012%, t=0.11, win 45.7%. No mechanism. Excluded.
- **Loose thresholds**: z<-1.5 is dead in the wide universe (t=0.30). Widening the universe
  buys frequency only at thresholds where there is no edge.

## The frequency constraint (unsolved, structural)

~4 signals/year across 7 ETFs; ~37/year across 50 ETFs = **0.15/day → ~0.7 expected signals in a
5-session window.** Signals also CLUSTER (a market-wide selloff fires many at once; a calm week
fires none). This is inherent to the edge, not a tuning problem — every attempt to raise the rate
(looser threshold, intraday, cross-sectional) destroyed the edge.

As of the last session in the data (2026-08-27) **nothing is near firing** — most stretched-down
is XLU at z=-0.73 on 0.82x volume.

---

# OPTIONS TRANSLATION — three structures tested, all land on zero

Alpaca options history starts Feb 2024, so this runs on tier events since then (~100 usable
per structure). Scripts: `scripts/optstruct.py`, `scripts/putspread.py`.

## The IV question (user hypothesis: calls should be cheap in a fear moment)

**Not confirmed.** Call IV rises 0.447 (calm) → **0.597** (signal). Relative to realized
volatility 1.798 vs 1.671, t=+0.87 — if anything slightly more expensive, not cheaper.

Caveat on our own measurement: ATM call IV 0.597 vs put IV 0.419 **at the same strike** violates
put-call parity, which is impossible. Cause: **daily option-bar closes are not synchronous** —
call and put last traded at different times with the underlying at different levels. The skew
number is therefore unreliable. The call-IV-vs-realized result stands (call prices used
consistently).

## Structure P&L, 3-day hold, one contract

| structure | n | mean $ | t | win% |
|---|---|---|---|---|
| SIGNAL long ATM call | 115 | +2.8 | 0.05 | 42.6% |
| SIGNAL ATM/+3% debit spread | 103 | +2.8 | 0.11 | 46.6% |
| SIGNAL bull put spread ATM/-5% | 100 | +5.2 | 0.22 | 60.0% |
| CONTROL long ATM call | 129 | -99.3 | -1.58 | 36.4% |
| CONTROL bull put spread | 117 | -73.6 | -2.28 | 53.0% |

Each shows **+$79 to +$100/contract of relative alpha** vs control (signal-minus-control t=1.96
for the put spread) but **zero absolute return**.

## The failed sanity check

A **bear CALL spread** is the bearish structure — it must lose if the bounce is real. It made
**+$25.6** on signal days (and +$53.3 on control). It beat the bullish structure on the very days
we predict a bounce.

**Conclusion: these tests are measuring "short premium beats long premium", not direction.**
The directional edge is swamped.

## Why the underlying edge does not survive

At entry, call IV 0.597 vs realized 0.374 — you pay **1.8x realized volatility**. Over a 3-day
hold on an ~8-day option, theta plus IV normalisation consumes approximately the entire +1.6%
expected move. The options market has already priced the capitulation bounce.

## Open limitation

n≈100 per structure, high variance, and entry/exit prices contaminated by the non-synchronous
daily-bar problem proven above. Underpowered and noisy — a zero here is a **failure to reject**,
not a demonstration that no edge exists. Re-test with minute bars at a fixed timestamp before
concluding.

---

# DATA FEED — Yahoo solves the same-day problem (IEX cannot)

## The problem

Alpaca's free tier refuses any SIP range reaching today:
`403 subscription does not permit querying recent SIP data`. The IEX feed it *does* allow for
today carries only **~3% of consolidated volume** (SPY 2026-08-28: IEX 1,162,974 vs SIP
36,806,117), which would destroy the volume ratio the entire strategy depends on. No amount of
averaging fixes a 3% sample of a volume distribution whose *level* is the signal.

Historical option **quotes** are also unavailable (404) — only trades — which is why the option
backtest could not be de-contaminated.

## Measured cost of entering late (scripts/delay.py, 33 years, 194 events)

| entry | mean | win | t |
|---|---|---|---|
| A. signal-day CLOSE | **+1.365%** | 67.0% | 6.21 |
| B. NEXT OPEN | +1.205% | 68.0% | 4.14 |
| C. next close | +0.606% | 61.9% | 2.24 |

Nearly free in aggregate — but **not uniform across tiers**:

| tier | close | next open | kept |
|---|---|---|---|
| SMALL 1.4-1.8x | +0.721% | **-0.223%** | **-31%** |
| FULL 1.8-2.5x | +1.897% | +2.019% | 106% |
| MEDIUM >2.5x | +1.312% | +1.578% | 120% |

**The SMALL tier inverts on delayed entry.** FULL and MEDIUM improve.

## The fix: Yahoo Finance

TrustyRustyEngine's `bin/src/fetcher.rs` already uses Yahoo (crumb + cookie, no API key).
Verified against Alpaca SIP, 2026-08-28:

| symbol | price diff | Yahoo vol / SIP vol |
|---|---|---|
| SPY | 0.00% | 99.7% |
| QQQ | 0.00% | 99.3% |
| SOXX | 0.00% | 99.9% |
| XLV | 0.00% | 99.3% |
| HYG | 0.00% | 100.0% |

True consolidated volume, no delay, no key. `meta.regularMarketPrice` and
`meta.regularMarketVolume` update live intraday, so today's provisional bar can be built during
the session and the signal traded at today's close.

**Volume completion curve** (4,432 symbol-sessions of 5-minute bars) — needed to scale
volume-so-far into a full-day estimate:

| by (ET) | median | p10 | p90 |
|---|---|---|---|
| 15:00 | 0.772 | 0.662 | 0.840 |
| 15:15 | 0.805 | 0.702 | 0.866 |
| 15:30 | 0.843 | 0.753 | 0.895 |
| **15:45** | **0.894** | 0.825 | 0.934 |

`stretch` needs no correction — it is a price ratio and the live price is exact. Only `volx` is
estimated, at roughly +/-8%. Because the cell below FULL loses money on delayed entry and is flat
(+0.184%, t=0.21) even on same-day entry, the same-day path raises the SMALL floor to **1.5x**
rather than 1.4x so estimation error cannot leak the flat cell into a tradeable tier.

## Result

The agent runs **dual-path**: Yahoo live -> `same_day` mode (close-entry tiers, all three
tradeable); Yahoo unavailable or outside RTH -> `next_open` mode (delayed tiers, SMALL refused
by a gate and journalled). Full edge when the feed cooperates, safe degradation when it does not.

---

# EXECUTION FRICTION — the thing that nearly killed it

Measured on live chains (Alpaca option snapshots, last RTH quotes 2026-08-28 15:59:59 ET).
Scripts: `scripts/fillcost.py`, `scripts/friction2.py`.

## The original design was negative-expectancy

`spread_builder` first priced the credit at the WORST realistic fill (short at bid, long at ask)
and then submitted a limit **at that price** — turning an honest estimate into an instruction to
pay the full spread on both legs, twice.

| item | per contract |
|---|---|
| gross edge, bull put spread | +$37.8 (t=1.26, not significant) |
| entry crossing | -$70 |
| exit crossing | -$70 |
| **net** | **-$102** |

The haircut was **35% of the mean credit**. Only 18/33 names even cleared the 12%-of-width
credit gate at the worst fill, versus 30/33 at mid — so the gate was silently selecting the
universe in a way that was never intended.

## Friction is concentrated, not uniform

One-way cost to cross a ~1wk ATM 5%-wide put spread:

| symbol | credit | friction | credit/friction |
|---|---|---|---|
| IWM | $231 | **$2** | 115 |
| SPY | $361 | **$4** | 90 |
| XLF | $30 | $2 | 12 |
| HYG | $22 | $3 | 9 |
| QQQ | $554 | $16 | 36 |
| XLV | $132 | $40 | 3.3 |
| SOXX | $658 | $105 | 6.3 |
| XME / FDN / IBB | — | $200-300 | — |

**A 50x range on the same structure.** The $70 broad-ETF average was an artifact of averaging a
liquid core with an illiquid tail. This is the single most important operational fact in the
strategy: *which names you trade matters more than any parameter in the signal.*

## DTE and moneyness are second-order

Credit per dollar of one-way friction:

| DTE | ATM | 3% OTM | 5% OTM |
|---|---|---|---|
| ~1wk | **10.44** | 3.57 | 2.36 |
| ~3wk | 6.75 | 4.09 | 3.68 |
| ~5wk | 4.71 | 2.79 | 2.74 |
| ~9wk | 4.15 | 3.27 | 3.71 |

ATM beats OTM at every maturity, and ~1wk beats longer. 8-12 DTE sits inside both this optimum
and the study's >=8 DTE requirement, so no compromise is needed.

## Fixes applied

1. **Quote at MID, not at the worst fill.** The limit is now the mid credit; the worst-fill
   price is still computed and journalled, but as information rather than as an order.
2. **`gate_friction`** refuses any trade whose round-trip crossing exceeds 40% of the
   structure's gross edge. This, not the universe list, is what keeps the strategy solvent —
   it works off live quotes, so an ordinarily-liquid name having a bad day is refused too.
3. **Universe cut to the liquid core**, ordered by measured crossing cost.

| | before | after |
|---|---|---|
| round-trip friction | -$140 | **-$8 to -$24** |
| gross edge | +$37.8 | +$37.8 |
| **net** | **-$102** | **+$14 to +$30** |

## Honest status

Friction is no longer the disqualifier. **This makes positive expectancy plausible, not proven.**
The gross edge it rests on is +$37.8/contract at t=1.26 — fixing the cost side left the edge
side exactly as unproven as it was. The underlying move remains the only thing established at
significance (+1.646%, t=5.42, 33 years).

---

# MACRO REGIME OVERLAY — the strongest conditioning variable found

Construction from TrustyRustyEngine's `spxlrealyields` strategy (already parameter-tested there).
Scripts: `scripts/regime_overlay.py`, `scripts/overlay_oos.py`, `scripts/calm_fix.py`,
`scripts/net_final.py`. Implemented in `agent/regime.py`.

## Five overlays tested, then re-tested out-of-sample

Tested on 115 ETF capitulation events, then re-run on 4,359 **single-name** events — a genuinely
independent sample using the same regime series.

| overlay | ETF (n=115) | single names (n=4,359) | verdict |
|---|---|---|---|
| credit healthy (HYG/IEF vs 50d mean) | -1.59, t=-2.80 | +0.15, t=0.66 | **contradicts** |
| risk_on (credit AND calm) | -1.38, t=-2.26 | +0.49, t=2.22 | **contradicts** (sign flip) |
| gold lagging market (60d) | +0.70, t=1.11 | -0.11, t=-0.52 | **contradicts** |
| calm AND gold lagging | +1.82, t=2.56 | +0.39, t=1.55 | **evaporated** |
| **macro calm (TLT vol)** | +1.12, t=1.64 | **+1.49, t=6.58** | **CONFIRMS** |

Four of five failed. The credit result had a tidy post-hoc story attached to it ("bad news
already priced") and was still noise — the story was invented after seeing the number. The
`calm AND gold lagging` pairing was chosen after seeing the individual results and behaved
exactly as a specification search should be expected to.

## The one that survived

    calm = TLT 21-day stdev < its own 90-day mean, 1.5% hysteresis

| regime | n | move | win |
|---|---|---|---|
| calm bonds | 1,598 | **+1.553%** | 63.3% |
| stressed bonds | 2,761 | **+0.066%** | 55.7% |

t(diff) = **6.58**. A 24x separation.

**It stacks with the volume tiers rather than duplicating them:**

| volume | CALM | STRESSED |
|---|---|---|
| 1.4-1.8x | +1.35%, t=6.0, 62.0% | -0.20%, t=-1.8, 53.8% |
| 1.8-2.5x | +1.84%, t=6.1, 66.8% | +0.15%, t=-0.1, 57.1% |
| 2.5-4.0x | +1.94%, t=2.9, 61.9% | +0.59%, t=0.8, 58.9% |
| >4.0x | +0.31%, t=0.1 | +0.40%, t=0.2 |

In a calm regime every volume cell works. In a stressed regime none does, and the lowest is
significantly negative. The >4.0x cell stays dead in both — the "real news arrived" ceiling
appearing a third time.

**Mechanism: it is the volume ceiling one level up.** Extreme volume means real information
arrived at the single-name level. Stressed bonds mean real risk is being repriced at the macro
level. Same thing, same consequence: nothing to revert.

Era stability is **3/5**. It failed in 2016-2017 (t(diff)=-2.01) and was neutral in 2018-2019 —
both periods when bond volatility barely varied, so the split carried little information. It
works hard in 2020-2026 (t(diff) = 3.49, 5.05, 2.57).

## It still does not make the strategy profitable

Net per contract, calm regime only, quoting at mid:

| friction budget | names | move% | t | gross $ | friction $ | **NET $** | sig/5d |
|---|---|---|---|---|---|---|---|
| <= $10 | 22 | +2.435% | 3.71 | 28 | 6 | **+16** | 0.10 |
| <= $20 | 52 | +1.473% | 1.90 | 16 | 12 | -9 | 0.23 |
| <= $35 | 89 | +1.647% | 3.16 | 27 | 18 | -10 | 0.37 |
| <= $60 | 141 | +1.972% | **5.10** | 45 | 28 | -10 | 0.58 |
| any | 316 | +1.674% | 6.90 | 52 | 78 | -103 | 1.24 |

Best cell: **+$16/contract firing 0.10 times per 5 sessions = +$2 per contract per contest
window.**

**The structural reason, and it is the important finding:** gross P&L scales with
spot x move%, but option bid/ask *also* scales with spot. Improving the signal does not outrun
the spread, because both grow together. That is why every friction budget lands within +/-$10 of
zero no matter how good the signal gets — t=5.10 at the <=$60 budget still nets -$10.

**A +1.5-2% underlying move over 3 sessions cannot be extracted through retail option spreads.**
The overlay is a real research result. It is not enough.

---

# WHY OPTIONS CANNOT CARRY THIS SIGNAL — the unifying result

Scripts: `scripts/csp.py`, `scripts/csp2.py`, `scripts/csp_risk.py`, `scripts/validate_bs.py`,
`scripts/ivrv_live.py`.

## The measurement

Live ATM put quotes (bid/ask mid — reliable, unlike daily option bars), 28 liquid names,
8-18 DTE, compared against each name's own trailing 20-day realized volatility:

    corr(trailing RV, IV/RV) = -0.684    t = -4.78    n = 28

| trailing RV | mean IV/RV |
|---|---|
| calm < 0.15 | **1.085** |
| normal 0.15-0.25 | 1.056 |
| active 0.25-0.40 | 0.888 |
| turbulent > 0.40 | **0.657** |

Implied volatility is forward-looking and volatility mean-reverts, so a name that has just moved
violently carries IV *below* its own trailing realized volatility.

## Why that is fatal here

**The capitulation signal fires when a name has fallen 2.5 sigma in five sessions. Trailing RV is
elevated by construction on exactly those days.** So the signal fires precisely into the
turbulent bucket, where IV/RV ~ 0.66 — the worst relative option pricing available.

- **Buying** premium there is expensive in absolute terms (IV is high).
- **Selling** premium there is cheap in relative terms (IV is low vs what the stock then does).

The signal sits in the worst quadrant for both directions. This is not a parameter problem.

## It explains every prior failure as one failure

| structure | measured | now explained by |
|---|---|---|
| long ATM call | +$2.8, t=0.05 | buying high absolute IV |
| ATM/+3% debit spread | +$2.8, t=0.11 | same, plus 4 leg crossings |
| bull put spread, 3-day | +$37.8, t=1.26 | selling cheap relative IV, 4 crossings |
| bull put spread, to expiry | negative at every horizon | credit 24.6% of width needs ~75% win rate |
| cash-secured put | model +$184 at IV/RV=1.798 | true signal-day ratio ~0.66 -> under +$51 |

## The cash-secured put was still the right idea

It was the only structure that attacked the cost side correctly:

| | bull put spread | cash-secured put |
|---|---|---|
| legs crossed, entry | 2 | 1 |
| legs crossed, exit if OTM | 2 | 0 |
| total crossings | 4 | **1** |
| SPY friction | ~$56 round trip | **~$4** |

A 14x friction reduction, and permitted (Alpaca level 3 includes level 1). It failed for a
different reason than everything before it, which is why it was worth testing.

Its risk profile, for the record (modelled, calm regime, n=689): mean +$184, median +$115,
sd $407, 83.6% win, **win/loss ratio 0.99**, p1 = -$1,117 (-17% of cash at risk),
p0.1 = -$2,186 (-33%). The COVID bucket held n=8 because the calm-bond overlay excluded the
crash — the overlay working as designed, but it means **the in-sample tail is not the true tail.**

Also decomposed: of the modelled +$184, only **+$47 (t=2.52) was signal alpha**; +$137 was beta
available by selling puts on any random day.

## Constructive implication

The property a tradeable premium-selling signal needs is now measurable: **it must fire when
trailing realized volatility is LOW**, where IV/RV is 1.085 and options are genuinely rich. That
is the opposite of a capitulation signal. Different strategy — but the requirement is no longer
guesswork.

## Rules note

Competition wording is "Every strategy must **incorporate** options trading" — incorporate, not
exclusively. Equity legs are permitted alongside options. Account is level 3, which includes
level 1 (covered calls and cash-secured puts), with $100,000 options buying power.

---

# FINAL: PRICED WITH REAL IMPLIED VOLATILITY

Scripts: `scripts/ratio.py`, `scripts/spy_real.py`, `scripts/vixtest.py`, `scripts/spy_vix.py`.

## Two model errors, both found and corrected

**Error 1 — uncapped delta approximation.** Estimating the spread's gain as
`0.35 x underlying move` produced $440/contract on a structure whose maximum possible gain is
its ~$401 credit. A linear delta cannot express the cap and is wrong for a 1.7% move on a
5%-wide spread.

**Error 2 — wrong sign on the volatility leg.** Replacing it with Black-Scholes priced off
*forward realized* volatility gave -$44/contract, because forward RV exceeds trailing RV, which
implies rising IV and a loss for a short-vega structure. But implied volatility does not track
realized upward after a panic - it crushes.

The two models disagreed by **$467/contract** purely on the IV assumption, so neither was
trustworthy. VIX settles it by measurement.

## What implied volatility actually does (VIX, 1992-2026)

Change in VIX over the 3 sessions after the signal:

| condition | n | mean | median | t |
|---|---|---|---|---|
| **capitulation (z<-2.5, vol>1.4x)** | 36 | **-6.86%** | **-7.99%** | -2.18 |
| any 2.5-sigma down | 38 | -5.69% | -7.99% | -1.85 |
| all days | 8,342 | +0.64% | -0.57% | +3.42 |

VIX falls in **69.4%** of capitulation events; -7.50 percentage points vs baseline (t=-2.40).
**The short-vega leg is a winner.** VIX at entry averaged 31.3 - which is the measured ATM
implied volatility on those days, not a modelled one.

## Spot / friction is the variable that decides viability

Gross P&L per contract = move% x spot x delta x 100, while friction is the option bid/ask.
The ratio spans **130x** across ETFs, and every earlier universe cut sliced on friction alone,
which mixed $50 stocks with $769 ETFs and buried it:

| ETF | spot | friction | spot/friction | n | move% | t |
|---|---|---|---|---|---|---|
| SPY | $769 | $4 | 19,234 | 36 | +1.371% | 3.24 |
| QQQ | $716 | $16 | 4,478 | 23 | +2.196% | 3.44 |
| HYG | $80 | $3 | 2,658 | 51 | +0.919% | 3.04 |
| XLV | $171 | $40 | 428 | 28 | +1.079% | 1.41 |
| FDN | $294 | $200 | 147 | 18 | +1.883% | 2.58 |

## The definitive result — real IV at both ends

| | n | IV entry | IV exit | credit | gross | friction | NET | t | win% |
|---|---|---|---|---|---|---|---|---|---|
| SPY | 36 | 0.313 | 0.286 | $335 | $46 | $8 | +$38 | 1.23 | 63.9% |
| QQQ | 22 | 0.331 | 0.303 | $257 | $76 | $32 | +$44 | 1.43 | 59.1% |
| **combined** | **58** | | | | | | **+$40** | **1.86** | **62.1%** |

The spread captures **14% of its credit** over the 3-day hold — the realistic figure, versus the
110% the delta model implied.

By era: +$36 / -$3 / +$78 / +$3, with 2020-2026 at a 43.8% win rate.
Worst -$559, p10 -$209, p90 +$311. **1.9 signals per year across both names.**

## Verdict

**Approximately zero expected value with a slight positive tilt.** Not negative — the earlier
-$102 conclusion was an artifact of quoting at the worst fill and of the delta approximation.
But +$40/contract at t=1.86, twice a year, is indistinguishable from zero:
1.9 x $40 x 3 contracts = **~$228/year on $100,000 = 0.23%**.

## What carries forward

The two findings worth keeping are specifications for a *future* strategy, not this one:

1. **IV/RV is inversely related to trailing realized volatility** (corr -0.684, t=-4.78).
   Any signal that fires after a large move sells options at their cheapest relative pricing.
2. **Spot / friction decides viability**, and spans 130x.

Together they specify what a tradeable options signal must look like: **it must fire when
trailing volatility is LOW, on a high-priced, ultra-liquid underlying.** Capitulation is the
exact opposite on the first count, which is why it resisted every structure tried.

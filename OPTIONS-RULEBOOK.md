# Structural options rulebook

Given the measurements taken on the day, which structure — if any — the agent should build.

Researched 2026-08-29. **Thresholds below are practitioner conventions, not laws.** Most come from
trading-desk convention (tastytrade-style IVR bands) rather than peer-reviewed work. Treat every
number as a *starting parameter to calibrate*, and say so in the write-up.

---

# Part 0 — The feasible set (Alpaca's hard constraints)

Everything downstream is bounded by what the broker will actually accept.

| Constraint | Value | Consequence |
|---|---|---|
| Max legs per MLeg order | **4** (CLI `--legs`) | No 6-leg structures |
| Leg coverage | **Every leg must be covered *within the same order*** | **Naked shorts impossible** |
| Ratios | Allowed, but must be simplest form (**GCD = 1**) | 1:2 OK, 2:4 rejected |
| Expirations | **May differ within one MLeg** | Calendars / diagonals are placeable |
| Equity legs | **Not supported in MLeg** | Covered calls / collars must be legged in separately |
| Order types | **Limit only** for MLeg | No native stop on any spread |
| Native stops | `stop` / `stop_limit` are **single-leg only** | All spread stops must be **synthetic** |
| Margin | "Universal spread rule" — theoretical max loss | Lower BP usage than leg-by-leg |

### What this BANS outright

- Short straddle / short strangle — two uncovered shorts, **rejected**
- 1x2 ratio spreads (front-ratio) — the extra short is uncovered, **rejected**
- Reverse calendars (sell far, buy near) — far short is uncovered
- Anything with an equity leg in the same ticket

### What this PERMITS

Verticals (credit + debit) · iron condors · iron butterflies · long butterflies ·
**broken-wing butterflies** (still fully covered) · long calendars & diagonals ·
long straddles / strangles.

**The permitted universe is exactly the defined-risk set.** Max loss is fixed at order
construction and enforced by the clearing broker — not by agent code. Lean on this in the write-up.

### Data constraints that shape the rules

- Option quotes on Basic plan are the **indicative feed, 15 min delayed**. The CLI's
  `data option chain --feed` **defaults to `opra`** — you must pass `--feed indicative` or the
  call fails on a free account.
- The **underlying** is real-time (IEX). Therefore: **all triggers key off the underlying**,
  options are the vehicle only.
- Paper fills simulate against **real-time** quotes with no slippage and no size check.
  You are deciding on stale data and filling on live data — assume worse fills than backtest.
- Index options (SPX, SPXW, XSP, VIX) are available in paper. **European, cash-settled → no
  assignment or pin risk** on held-to-expiry structures. Worth preferring over SPY *if* the
  indicative feed quotes them acceptably — verify before committing.

---

# Part 1 — The measurement vector

Taken at one fixed decision time each session. **10:30 ET** is the natural choice: the opening
hour has completed, and it is the documented window where opening volatility has subsided.

## M1 — Range and location

| Symbol | Definition |
|---|---|
| `ORH`, `ORL` | High / low of 09:30–10:30 ET |
| `W` | `ORH − ORL` (opening range width) |
| `W%` | `W / spot` |
| `loc` | `inside` \| `above` \| `below` \| `failed_break_up` \| `failed_break_down` |
| `gap` | `open − prior_close`, as % |
| `PDH`, `PDL` | Prior day high / low |
| `VWAP`, `VWAP_slope` | Session VWAP and its slope over the last 15 min |

`failed_break_*` = price traded outside the OR and then closed back inside on the decision bar.
**This is the highest-value state in the whole vector** — see Part 2.

## M2 — Realized volatility (three estimators, deliberately)

| Estimator | Uses | Efficiency vs close-to-close |
|---|---|---|
| Close-to-close | closes only | 1x |
| **Parkinson** | high-low range | ~5x |
| Garman-Klass | OHLC | ~7.4x |
| **Yang-Zhang** | OHLC + overnight gaps, drift-independent | **~14x** |

A 5-day Yang-Zhang window carries roughly the precision of a 70-day close-to-close window — which
matters enormously when you have days, not months.

> **Rule M2:** compute close-to-close, Parkinson and Yang-Zhang over 10 and 20 days.
> When acting as a **seller**, use `RV = max(all estimators)`. Underestimating realised vol is
> precisely how a premium seller gets hurt. When acting as a **buyer**, use the min.

> ⚠️ **This choice is the single most consequential parameter in the system.** Measured live on
> 2026-08-28 data, the estimators spanned **5.63% to 11.87%** — a 2.1x range on identical bars —
> and that range flips the sell/buy verdict for every expiry in the competition window. See
> `LIVE-READINGS.md`. **Pre-register the estimator and the thresholds**, or the rulebook is
> decorative and the real decision is being made by estimator selection.

## M3 — Implied volatility

- `IV_atm` — ATM IV of the target expiry, from the option snapshot
- `IVR = (IV − IV_low_52w) / (IV_high_52w − IV_low_52w) × 100`
- `IVP` — % of sessions in the past year with IV below today's

IVR is range-based and distorted by a single outlier year; IVP is distribution-based. **Require both
to agree** before acting on a volatility view. Backtest evidence cited by practitioners: short iron
condors entered when IVR *and* IVP both exceed 50 showed ~56.8% win rate vs 48.2% unfiltered.

## M4 — Volatility risk premium (the core signal)

```
VRP_points = IV_atm − RV        (vol points)
VRP_ratio  = IV_atm / RV
```

| Band | Reading | Posture |
|---|---|---|
| `VRP_ratio > 1.15` | Insurance is **dear** | **Sell** premium (defined risk) |
| `0.95 – 1.15` | Priced about right | **No trade** |
| `< 0.95` | Insurance is **cheap** | **Buy** premium, or stand aside |

## M5 — Term structure

Compute from the chain you actually trade rather than from VIX — same surface, no data dependency:

```
TS = IV_atm(front expiry) / IV_atm(~30d expiry)
```

- `TS < 1` — contango, normal (~85% of sessions). Front vol depressed → selling the front is
  *less* attractive. **Calendars are also less attractive**, not more: a long calendar sells the
  front, and steep contango means you are selling the cheapest thing on the curve. (An earlier
  draft said the opposite — it conflated "low absolute IV favours long vega" with "cheap front
  favours selling the front". Only the first is true here.)
- `TS > 1` — backwardation, ~8% of sessions. Stress. **Do not sell the front.**

If Alpaca's index feed carries VIX / VIX3M, `VIX/VIX3M` crossing 1.0 is the conventional regime
flip. **Availability unverified — confirm before depending on it.** The chain-derived `TS` is the
fallback and arguably the better primitive.

## M6 — Skew

```
RR25 = IV(25Δ call) − IV(25Δ put)
```

Negative (puts dearer) is the normal equity-index state. **More negative than usual = downside
insurance is bid.** Used to place the wings asymmetrically, never to form a directional view.

## M7 — Expected move, and the novel comparison

```
EM_iv       = spot × IV × √(DTE/365)
EM_straddle = ATM straddle mid × 0.85          ← prefer this; it is the market's own number
```

Then the measurement that no competitor appears to be using:

```
R = W / EM_straddle
```

**`R` is the whole thesis.** It asks whether the opening hour has already spent the day's
option-implied budget.

- `R` low (≈ <0.5) — the day is quiet relative to what options are charging → the range is
  overpriced → **selling the range is favoured**
- `R` high (≈ >1.0) — the opening hour alone has already consumed the implied daily move →
  **do not sell the range**; the market underpriced the day
- **Calibrate the cut-points on history before trusting them.** See Part 4.

## M8 — Liquidity gate (hard, pre-trade)

Per leg: `spread% = (ask − bid) / mid`. Reject if `spread% > 5%`, or OI < 100, or either side
unquoted. On a 4-leg condor you cross four spreads twice — round-trip cost is the single most
underrated drag on a short-window strategy.

## M9 — Event gate

| When | Event |
|---|---|
| Tue Sep 1, 10:00 ET | JOLTS |
| **Fri Sep 4, 08:30 ET** | **Nonfarm payrolls** |

No new short-premium position whose expiry crosses an unresolved macro print.

---

# Part 2 — The selection rules

## Gate 0 — Refusal conditions (evaluated first; any one blocks)

1. `VRP_ratio` in [0.95, 1.15] → no edge either way → **NO TRADE**
2. `TS > 1.0` (backwardation) → **no short premium** of any kind
3. Liquidity gate fails on any leg
4. Macro print inside the structure's life, unresolved
5. `spread%` round-trip cost > 25% of expected credit/debit
6. Existing position count or portfolio risk at cap
7. Decision time outside 10:30–14:00 ET

> Refusals are the product. Log every one with the number that caused it.

## Gate 1 — Direction from `loc`

| `loc` | Reading | Directional stance |
|---|---|---|
| `inside` | Balanced, range day forming | **Neutral** |
| `above` + VWAP slope > 0 | Trend day up. ~78% never returns to the far side | **Bullish — do not fade** |
| `below` + VWAP slope < 0 | Trend day down | **Bearish — do not fade** |
| `failed_break_up` | Breakout rejected — trapped longs | **Bearish (fade)** ← best signal |
| `failed_break_down` | Breakdown rejected — trapped shorts | **Bullish (fade)** ← best signal |

**This is the correction to the naive "fade both edges" plan.** Fading a *live* breakout fights the
78% continuation statistic. Fading a *failed* breakout trades with it — the failure is the evidence
that the move was rejected. Only take the fade on `failed_break_*`, never on `above` / `below`.

## Gate 2 — The structure matrix

Rows: direction from Gate 1. Columns: `VRP_ratio` from M4.

| | **Rich** `>1.15` | **Fair** `0.95–1.15` | **Cheap** `<0.95` |
|---|---|---|---|
| **Neutral** (`inside`) | **Iron condor** — shorts outside `ORH`/`ORL` | NO TRADE | **Long butterfly** centred at OR midpoint, *or* **long calendar** if `TS < 0.95` |
| **Bullish** | **Put credit spread** — short below `ORL` | NO TRADE | **Call debit spread** |
| **Bearish** | **Call credit spread** — short above `ORH` | NO TRADE | **Put debit spread** |
| **Neutral, high conviction on a level** | **Iron butterfly** at that level | NO TRADE | **Long butterfly**, tighter wings |

Notes on the diagonal cases:
- Iron butterfly only when `R` is very low *and* price is pinned near a level — it has a much
  narrower profit zone than the condor in exchange for a larger credit.
- Long calendar requires `TS < 0.95` (front cheap relative to back) **and** `VRP_ratio < 0.95`.
  It is the only structure here that is long vega and positive theta simultaneously.

## Gate 3 — `R` overrides the neutral row

| `R = W / EM_straddle` | Action |
|---|---|
| `< 0.5` | Range is overpriced. Neutral short-premium structures **permitted at full size** |
| `0.5 – 1.0` | Ambiguous. **Half size**, widen shorts by 0.25 × `EM` |
| `> 1.0` | Day has already exceeded its implied budget. **No neutral short premium.** Directional only, or no trade |

## Gate 4 — Strike placement

**Short strikes (credit structures):**
```
short_put_strike  = min(ORL, spot − k × EM_straddle)
short_call_strike = max(ORH, spot + k × EM_straddle)
```
with `k` starting at 1.0 and calibrated. Taking the *further* of the two anchors means the opening
range can only ever push strikes **outward**, never inward. That is the safe direction for the
novel signal to be wrong in.

**Skew adjustment (M6):** when `RR25` is more negative than its 20-day median, push the put side out
by one additional strike and finance it by pulling the call side in one strike, or convert to a
**broken-wing butterfly** with the wider wing downside. Never let skew create a directional view.

**Wing width:** at least 2 strikes, and wide enough that
`credit ≥ 0.20 × width` — otherwise the risk/reward does not clear the round-trip spread cost.

**Delta cross-check:** the resulting short strikes should land in the 0.10–0.20 delta band. If the
OR-derived strike implies delta > 0.25, the range signal is fighting the surface — **defer to
delta** and log the disagreement. It is a measurement worth reporting either way.

## Gate 5 — Expiry selection

| Condition | DTE |
|---|---|
| Default | **1–2 DTE** |
| `R > 0.8` or elevated realised vol | **2–3 DTE** (reduce gamma) |
| Never | **0DTE held overnight or unmanaged** — a 1% move takes a condor to max loss in minutes |
| Conditional | **0DTE opened ≥10:30 and force-flat by 15:45** is defensible *if* intraday realised vol is materially below implied — see `LIVE-READINGS.md`, where range-based RV is running ~30% under close-to-close, i.e. gaps dominate and intraday is quiet |
| **Any position entered Wed Sep 2 or later** | **Expire Thursday Sep 3, not Friday** |

The last row matters: judging happens Friday **11:00 ET**, options expire 16:00 ET. A Friday-expiry
spread is still open, still 0DTE, and still marked at an unresolved price when judges look at the
account. `gatekeeper` has already reasoned its way to this.

## Gate 6 — Position management (all triggers off the **underlying**, not the option)

| Trigger | Action |
|---|---|
| Underlying touches a short strike | Close the tested side at market |
| Structure at **50% of max profit** | Close (resting GTC limit, placed at fill) |
| Loss reaches **2x credit received** | Close at market |
| **15:45 ET** on expiry day | Flatten regardless |
| Underlying re-enters the OR after a `failed_break` fade | Take profit |

Because native stops do not exist for spreads, every one of these is a **synthetic stop**: a
real-time underlying price check driving a market close. Poll the underlying, never the option.

---

# Part 3 — Sizing

```
risk_per_trade  = 1.0% of equity          (max loss of the structure, known at construction)
max_concurrent  = 3 structures
portfolio_risk  = 4% of equity, aggregate
daily_loss_halt = 2% of equity → no new positions for the session
```

With ~4 sessions and n≈4–12 trades total, **the sizing choice matters more than the signal.** Any
single structure large enough to move the P&L meaningfully is also large enough to end it.

---

# Part 4 — What to calibrate before trusting any of this

Free-tier historical bars go back to 2016 (only the last 15 min is restricted), so this is a
weekend-sized job on 1-min SPY data:

1. **Distribution of `k = day_range / W`** — does the opening hour actually predict the day's range?
2. **Distribution of `R = W / EM_straddle`**, and realised outcomes conditioned on `R` buckets.
   *Does `R` beat the IV-implied expected move as a range estimator?* ← the paper-worthy question
3. **Base rate of each `loc` state**, and forward returns from each — especially whether
   `failed_break_*` genuinely outperforms fading `above`/`below`.
4. **Round-trip spread cost** on 1–2 DTE SPY condors, measured from the chain, not assumed.

Pre-register the thresholds **before** running these, and commit that file first — `nilaymastaadmi`
is doing exactly this and it is provable from git history. It converts "I tuned until it worked"
into "I predicted, then measured."

---

# Part 5 — Honest reporting

Four sessions is n≈4 independent bets. Realised P&L over n=4 says almost nothing about whether the
rules work. Report the **minimum detectable effect** alongside the P&L, and state plainly which
rules fired, which refused, and which never got the chance. `honest-wheel` has already claimed this
framing; doing it better is still available.

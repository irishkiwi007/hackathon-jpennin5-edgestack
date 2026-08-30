# When does implied volatility expand around news?

Both timestamps are available at minute resolution: **news carries second precision**
(`2026-08-27T19:42:27Z`) and **option minute bars exist** on the free tier. So this is directly
measurable rather than inferred.

Scripts: `scripts/intraday_iv.py`, `scripts/single_event.py`, `scripts/multi_event.py`,
`scripts/openclose.py`.

---

## The answer: neither. It happens overnight.

41 news-volume-spike days vs 39 control days, implied volatility recomputed by Black-Scholes
inversion **every minute** from that minute's spot, normalised to each day's 09:30–10:00 average:

| ET | spike | control | difference |
|---|---|---|---|
| **09:30** | **1.0185** | 1.0051 | +0.0134 |
| 10:15 | 0.9767 | 1.0031 | −0.0265 |
| 12:00 | 0.9735 | 1.0049 | −0.0314 |
| 14:00 | 0.9797 | 1.0283 | −0.0485 |
| **15:30** | 0.9847 | **1.0546** | **−0.0699** |
| 16:00 | 0.9907 | 1.0518 | −0.0611 |

On spike days implied volatility **opens at its high and drifts down**. On control days it does the
opposite, rising steadily into the close — the normal pattern of pricing overnight risk. On spike
days that afternoon rise is **absent**, and the gap widens monotonically to 7 percentage points.

**The expansion is complete before the opening bell. There is nothing to catch intraday.**

## The individual events confirm the mechanism

Twelve largest news-volume spikes since Sept 2025:

| | Finding |
|---|---|
| First article time | **04:01–07:11 ET on 9 of 12** — pre-market |
| Implied-volatility peak | **09:32–09:47 on 7 of 12** — within minutes of the open |
| Open→close direction | 6 up, 6 down — no consistent direction |

Worked example, **AMD 2026-05-06** — the largest spike of 2026 (45 articles vs a 6.7/day baseline,
news_z 9.8). First article **09:09 ET, pre-market**. Implied volatility opened at **77.8%**, fell to
70.4% by 11:00, closed at **74.9%** — down 3.7% on the day of its own biggest news event.

And the five largest one-minute implied-volatility jumps that day — +6.9%, +4.7%, +4.6%, +4.5%,
+4.4% — **all occurred in minutes with zero articles.** Individual prints during the session produce
no visible response.

## The divergence is statistically significant

Session change in implied volatility, open to close:

| Group | n | open | close | change | t | down-days |
|---|---|---|---|---|---|---|
| **spike** | 41 | 56.0% | 54.9% | **−2.90%** | −1.79 | **68%** |
| **control** | 39 | 43.1% | 45.5% | **+5.11%** | 2.51 | 31% |

**Spike minus control: −8.00 percentage points, t = −3.08. Significant.**

## What this means for trading it

The −8pp divergence is a **vega** gain. Capturing it means being short volatility from the open on a
spike day — but spike days also *move* more (the established 1.935× next-day move), so **gamma works
against the position**. The vega number is gross; the net requires the realised intraday move.

That test is running: short the ATM straddle at 09:30, cover at 16:00, actual option prices,
slippage charged. It settles whether the effect is economically real or merely a repricing you
cannot monetise.

*(A naked short straddle is not Alpaca-legal. If the effect survives, the defined-risk iron
butterfly version is the next step — and on the SPY work that structure retained ~72% of the edge
at a better t-statistic.)*

## Practical constraint regardless

News breaks **pre-market**, options reprice **at the open**, and the free-tier option feed is
**15 minutes delayed**. An agent watching the wires during the session is watching the aftermath.
Any strategy built on this has to act at or before the open, not react to intraday prints.

---

# Follow-up: three corrections and the tradeability verdict

## Correction 1 — the VIEW A magnitude was inflated by my own bug

The first pass decayed time-to-expiry by **a full calendar day across a 6.5-hour session**,
overstating theta ~3.7×. A frozen option price with shrinking T mechanically forces implied
volatility upward:

| DTE | spurious implied-volatility drift per session |
|---|---|
| 5 | **+12.2%** |
| 9 | **+6.3%** |
| 20 | +2.8% |

The control group's reported "+5.11% rise into the close" sat squarely in that range.

Rerun with correct calendar-time decay (`scripts/intraday_iv2.py`), at 16:00:

| | original (buggy) | **corrected** |
|---|---|---|
| spike | 0.9907 | **0.9288** |
| control | 1.0518 | **0.9689** |
| difference | −0.0611 | **−0.0401** |

**Both groups decline** — matching the independent overnight test, which required a real trade in
each window and never had the bug. The direction survives; the magnitude was ~50% overstated.

## Correction 2 — individual article prints do nothing

Event study aligned to the **article timestamp**, 787 events, 500+ observations per minute bin
(`scripts/article_event.py`):

| minutes from print | implied volatility ratio |
|---|---|
| −90 | 1.0058 |
| −30 | 0.9940 |
| −2 | 0.9900 |
| **+0** | **0.9908** |
| +2 | 0.9903 |
| +20 | 0.9880 |
| +85 | 0.9852 |

**The response at the print is +0.0008 — zero, inside the minute-to-minute noise.** A smooth
monotone decline across the whole window. No step, no kink at t=0.

Confirmed three ways: this event study; AMD's biggest-spike day where the five largest one-minute
jumps contained **zero** articles; and the earlier finding that price movement is symmetric around
the headline timestamp.

## The trade that emerged — and what killed it

Shorting the ATM straddle 09:30 → 16:00 on spike days, **actual option prices**, $12/straddle
slippage (`scripts/straddle_intraday.py`):

| group | n | mean P&L | t | win% | intraday move |
|---|---|---|---|---|---|
| **spike** | 57 | **+$82.8** | **2.61** | 64.9% | 1.75% |
| control | 53 | +$8.0 | 0.27 | 71.7% | 1.32% |

Spike days moved *more* (1.75% vs 1.32%), so gamma worked against the position — and the vega gain
still exceeded it. Spike-minus-control is only t = 1.73, so the honest claim is "this works on spike
days," not "spike days are special."

**But the Alpaca-legal version does not survive** (`scripts/butterfly_intraday.py`):

| structure | n | mean $ | t |
|---|---|---|---|
| iron butterfly, 4% wings | 34 | −1.1 | −0.03 |
| iron butterfly, 6% wings | 39 | −2.6 | −0.10 |
| iron butterfly, 9% wings | 38 | +34.4 | 1.65 |
| *naked straddle* | *57* | *+82.8* | *2.61* |

The gradient is unambiguous — **the edge lives in the uncovered tail Alpaca forbids.** Wings recover
it only as they widen toward naked. By period it also decays: 2025-H2 +16.0, 2026-H1 −2.9,
2026-H2 **−47.9**.

---

## What the mechanism actually is

The profitable trade is **not a news trade**. Nothing happens when the article prints. What happens
is that options open elevated — repriced overnight, before anyone can act — and then decay through
the session. Shorting that decay is what makes the money.

That has one useful consequence: **the 15-minute option-feed delay does not matter for it.** The
decision is made at the open from the underlying's news history, not from watching the tape. The
delay only blocks strategies that react intraday, and this one doesn't.

It also has one fatal consequence for the competition: the version that works is naked short
volatility, and the defined-risk version that Alpaca permits gives the edge back to the wings.

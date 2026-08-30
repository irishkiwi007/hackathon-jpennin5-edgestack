# Strategy research — opening-range mean reversion

Researched 2026-08-29. Sources are a mix of peer-reviewed and trading-blog; quality flagged inline.

## The idea as stated

> Use the opening hour as a loose guide to the day's range, then look for mean-reversion
> opportunities at the top and bottom of that range, with stop losses if the move is invalidated.

## Evidence against the directional-fade version

**The best-documented intraday SPY effect is the opposite trade.** Zarattini, Aziz & Barbon,
*"Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)"* (Swiss Finance
Institute) reports a **2.4 Sharpe, beta ≈ 0** for opening-range **breakout** / intraday momentum.
Fading the opening range takes the other side of that.

**Breakouts tend not to round-trip.** Once price breaks out of the opening-hour range, **~78% of the
time it only breaks that side** and does not return to tag the opposite edge. Fading *both* edges
therefore loses its symmetry the moment the range breaks. *(Source: trading blogs — tradethatswing,
edgeful. Not peer-reviewed. Treat as directional, not precise.)*

## Evidence for

- Range-bound / choppy phases are ~65–70% of sessions; mean reversion dominates in those. *(blog)*
- Mid-sized opening moves mean-reverted 67% / 62% of the time. *(blog)*
- Gap statistics: ~50% of 1%+ gaps fill intraday; prior-day high/low gets tagged ~71% of the time
  when price opens beyond it. *(blog)*

Net: the *regime filter* decides. Fading works in a range; it is a losing trade in a trending tape.
Which means the opening hour cannot be the only input — something has to classify the regime.

## Three mechanical problems with the intraday version

1. **15-minute delayed options data.** You cannot manage an intraday option position on stale quotes.
   *Workaround:* signal and stop trigger from **SPY itself** (real-time on free IEX), option used only
   as the vehicle, entered with marketable limits.
2. **Alpaca native stops are single-leg only** for options — `stop` and `stop_limit` are not available
   on multi-leg orders. Any spread needs a **synthetic** stop driven off the underlying.
3. **0DTE gamma.** A 1% SPY move can take an iron condor from profit to max loss in minutes. With only
   ~4 sessions left, one bad 0DTE day ends the P&L score. Argues for 1–2 DTE, or very small size.

## The reframe that fixes it

Don't fade directionally with stops. Use the opening hour to **estimate the day's range**, then take a
**defined-risk options structure** whose strikes sit relative to that range. Same market view, but:

- one entry, held to expiry → immune to the 15-min data delay
- max loss fixed at order construction → no stop needed on the option leg
- expresses "price stays in / returns to the range" directly

**The differentiator:** everyone else in this field selects strikes by **delta** (−0.15/−0.20),
**IV rank**, or **IV/RV**. Nobody is using the **realised opening-hour range**. That is an original,
empirical, testable strike-selection rule.

**The research question that makes it a strong submission:**
*Does the opening-hour range predict the day's range better than the IV-implied expected move does?*
Standard practice places condor strikes at 1.2–1.5 SD of the IV-implied move. If the opening range is
a better estimator, that is real edge with a clean story. If it isn't, you report that honestly — and
this field visibly rewards honesty (see `honest-wheel`, `underwriter`, `nilaymastaadmi`).

Testable this weekend on free-tier historical 1-min SPY bars (history back to 2016 is free; only the
last 15 minutes is restricted).

## Regime check — this matters more than the strategy choice

As of late Aug 2026 *(from financial press, not live data — verify Monday)*:

| Signal | Level | Implication |
|---|---|---|
| VIX | **~14.2 — 2026 YTD low** | Options are **cheap**. Bad for premium sellers. |
| Implied daily move | **< 0.8%** | Market pricing a tight range. |
| SPY | **All-time highs, +16% YTD** | Strong uptrend — fading the *top* fights the trend. |
| VIX futures | Sep ~17.4, Oct ~19, Nov ~19.7 | Steep contango; front vol unusually depressed. |

**Two consequences.**

*The field is mispositioned.* Most competitors are premium sellers (`ThetaGuard`, `spread-sentinel`,
`theta-shepherd`, `underwriter`, `honest-wheel`, `alpaca-vrp-engine`) selling into the cheapest vol of
the year. `nilaymastaadmi`'s agent **already refused its first live run** — IV 12.81 vs realised 13.28,
i.e. vol was cheap, nothing worth selling. That is a real headwind for most of the leaderboard.

*If IV < RV, be long gamma, not short.* The mean-reversion view can be expressed with **debit** spreads —
buy a put spread at the top of the range, a call spread at the bottom. Long gamma, defined risk, no stop
required, and structurally opposite to where the field is crowded.

Do **not** hard-code this regime read. Measure IV/RV live and let it pick the side — that is also the
honest version for the write-up.

## Macro calendar inside the window

| When | Event | Effect |
|---|---|---|
| **Tue Sep 1, 10:00 ET** | JOLTS | Mid-window vol event |
| **Fri Sep 4, 08:30 ET** | **Nonfarm payrolls** | Lands 1h before the final session opens |

The last session is **post-NFP**, with the deadline at 11:00 ET — only 90 minutes of trading.
`gatekeeper` has already concluded it should use **Thursday** expiry, not Friday, so nothing is
open and 0DTE when judges look. That reasoning applies to any structure held into Friday.

## The n=4 problem

Four sessions gives roughly four independent bets. Realised P&L over n=4 carries almost no
information about whether a strategy works. `mamartih/honest-wheel` has already built its pitch
around this — it "reports its P&L next to its minimum detectable effect." Stating the confidence
interval on your own result is cheap, correct, and differentiating regardless of which strategy wins.

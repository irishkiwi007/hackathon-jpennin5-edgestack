# Options data sources — what's actually available for free

Investigated 2026-08-29, driven by the backtest's binding constraint: Alpaca's option history is
too short and single-regime to distinguish a Sharpe of 0.4 from zero.

## Alpaca — measured, not assumed

Probed expired contracts directly. **Earliest option data: 2024-01-18.** Nothing before it.
`SPY230317C...` and `SPY231215C...` return no data at all.

Alpaca did **not** recently launch extended options history. Option *trading* launched in 2024 and
the data begins where the product did. What is free is the **indicative feed** (15-min delayed
quotes, no OPRA agreement needed) — that is a *feed* concession, not a *history* extension.

| | Alpaca |
|---|---|
| Range | 2024-01-18 → now (~2.6 yrs) |
| Expirations | full weeklies ✓ |
| Strikes | $1 spacing ✓ |
| **Bid/ask history** | **✗ — trade bars only** |
| Greeks/IV history | ✗ (live snapshots only) |

The missing bid/ask is why the backtest had to sweep an assumed slippage rather than measure it.

## DoltHub `post-no-preference/options` — free, SQL, and *nearly* right

Live and queryable with no key: `https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q=...`

Schema is excellent — `date, act_symbol, expiration, strike, call_put, bid, ask, vol, delta,
gamma, theta, vega, rho`. Real quotes and full greeks, back to at least 2020-03-16 (a sample from
the COVID crash shows IV 1.0832 — exactly the regime the analysis lacks).

**But it cannot resolve our structures:**

| Check | Finding |
|---|---|
| Expirations on 2026-08-27 | only **4**: 09-11, 09-25, 10-02, 10-16 — **no weeklies**; nearest is 15 DTE |
| Expirations on 2024-06-03 | only 3: 14, 25, 58 DTE |
| Strike spacing near ATM (2024-06-03) | 500, 507, 510, 517, 528, 538, 540, 549… — irregular **$7–11 gaps** |
| Date coverage | patchy — 2019-01-03, 2021-06-01, 2023-06-01 all return 0 rows |
| Full-table aggregates | time out; queries must be date-scoped |

SPY at $528 means ±1% ≈ $5. **The dataset cannot express a ±1% spread.** Usable for monthly,
wide-strike studies; not for the 5-day, ±1–2% structures under test.

## The rest

| Source | Verdict |
|---|---|
| **Alpha Vantage** `HISTORICAL_OPTIONS` | 15+ yrs with greeks, **but requires the 600/1200 req-min premium plan.** Free keys receive placeholder/demo data. Not free. |
| **OptionsDX** | Genuinely free historical intraday SPY/SPX/VIX with greeks + IV. Manual file download, no API; free-category URL 404s and coverage is unconfirmed. **The most promising unexplored lead.** |
| Polygon.io free tier | ~2 yrs, 5 calls/min — no better than Alpaca |
| Finnhub free | limited options coverage |
| historicaloptiondata.com / OptionMetrics / Databento | paid |

---

## The important caveat: more data would not rescue this strategy

The instinct is that a longer history fixes the inconclusive backtest. **The arithmetic says
otherwise.**

```
put debit -1.0%/1.0% :  Sharpe 0.39  ±0.72 (1 s.e.)  over n=108
```

Standard error scales as 1/√n. Going from 2.6 years to 7 would take the error bar to roughly
**±0.44** — and 0.39 ± 0.44 is *still* not significant. Getting significance would require the true
Sharpe to be **higher** than what was measured, which more data cannot create.

And the backtest's other diagnostics point at absence of edge rather than lack of precision:

- **21 of 40 strike cells positive** — a coin flip. A real edge appears across a neighbourhood.
- **Sub-periods alternate sign**, two of five half-years losing.
- The one strong-looking gradient (far-OTM call debit, Sharpe → 1.40) improves monotonically with
  OTM distance in a bull-only sample — the signature of leveraged beta, already flagged twice.

> **The binding constraint is not sample size. It is that the point estimate is near zero.**

## Where longer data *would* pay

Not on this strategy — on the one finding that survived everything:

**The variance-ratio violation.** VR(q) < 1 at every horizon in all six eras 1993–2026
(0.92 / 0.84 / 0.76 / 0.74 / 0.69). That is established on *underlying* data, which we already have
33 years of via TrustyRustyEngine. It needs no more data.

It needs an **expression** that survives Alpaca's uncovered-short rule — the direct trade is a
reverse calendar, which is rejected. That is a structuring problem, not a data problem, and it is
the highest-value open question left.

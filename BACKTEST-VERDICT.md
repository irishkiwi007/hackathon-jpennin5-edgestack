# Backtest verdict — are we onto something?

**No, not yet.** The walk-forward test on real option prices contradicts the cross-sectional
analysis that produced the recommendation. One structural finding survives everything; the
tradeable edge does not.

Scripts: `scripts/backtest.py`, `scripts/bt2.py`, `scripts/vr33.py`.

---

## What changed methodologically

Everything before this was **cross-sectional EV**: one chain snapshot (Fri 2026-08-28 close) scored
against a historical return distribution. That is not a backtest. It conflates *one day's option
prices* with *ten years of returns* — so if that day's calls happen to be cheap relative to history,
every call structure scores well, and nothing about it repeats.

The backtest walks forward: for each Monday it builds the structure from the chain **as it was that
day**, holds to Friday expiry, and settles against SPY's actual close. 111 cycles, Feb 2024 →
Aug 2026.

## Result: the recommended structure loses

Real prices, Mon→Fri, 1 lot, slippage swept:

| Structure | n | total (slip $0) | (slip $2/leg) | Sharpe @$2 | win% |
|---|---|---|---|---|---|
| **call debit +1.4/+2.0** | 107 | **−$289** | **−$717** | **−0.42** | 17.8% |
| call debit +0.5/+1.5 | 108 | −$2,564 | −$2,996 | −0.86 | 35.2% |
| **put debit −1.0/−2.0** | 108 | **+$1,787** | **+$1,355** | **+0.39** | 21.3% |
| put credit −2.0/−3.0 | 108 | +$355 | −$77 | −0.04 | 87.0% |
| iron condor ±2% w5 | 99 | −$1,952 | −$2,744 | −1.06 | 76.8% |
| *SPY buy & hold* | 111 | — | — | **+0.69** | 58.6% |

**`call debit 780/785` — the structure I recommended — lost money.** The cross-sectional analysis
ranked it best; real prices say otherwise.

The put credit spread and iron condor losing confirms the negative-alpha finding from a second
direction. **Nothing beat buy-and-hold SPY.**

## The one winner is not statistically significant

`put debit −1.0% / width 1.0%`, the skew harvest:

```
n = 108   total $1,355   mean $12.5/wk   win 21.3%
annualised Sharpe 0.39  ±0.72 (1 s.e.)   t = 0.54   -> NOT significant
```

Sub-periods alternate sign — **two of five half-years lose**:

| Period | n | total | mean |
|---|---|---|---|
| 2024 H1 | 19 | **−$818** | −$43.1 |
| 2024 H2 | 22 | +$1,102 | +$50.1 |
| 2025 H1 | 19 | **−$692** | −$36.4 |
| 2025 H2 | 22 | +$236 | +$10.7 |
| 2026 YTD | 26 | +$1,527 | +$58.7 |

## The strike sweep says coin flip

Annualised Sharpe across 40 strike/width cells: **21 positive, 19 negative.** A real edge should
appear across a neighbourhood, not scattered.

The put-debit positive region is narrow — the −1.0% row works (0.19–0.39) but −2.0% and −2.5% are
strongly negative (down to −1.80).

The call-debit side shows a clean monotone gradient improving with distance OTM (+2.5% long, 2.0%
wide → Sharpe **1.40**). **Do not believe it.** Monotone improvement with OTM distance, in a sample
containing only a bull market, is the exact signature of leveraged beta — the same drift artifact
the alpha analysis already flagged twice.

---

## What 33 years of history adds (TrustyRustyEngine data)

`data/historical/SPY.csv` runs **1993-01-29 → 2026-05-01**, 8,371 sessions — 33 years vs Alpaca's
10, including the dot-com bust and the GFC. No option prices (the engine has no options support;
`Option` in the Rust source is the language type), so it extends the *distributional* work only.

### The variance-ratio finding survives every regime

`VR(q) = Var(q-day) / (q × Var(1-day))`:

| Era | q=2 | q=5 | q=10 | q=21 | q=42 |
|---|---|---|---|---|---|
| dot-com 1993–2002 | 0.964 | 0.866 | 0.758 | 0.746 | 0.674 |
| recovery 2003–2007 | 0.909 | 0.845 | 0.726 | 0.655 | 0.565 |
| GFC 2008–2012 | 0.909 | 0.775 | 0.703 | 0.684 | 0.741 |
| QE bull 2013–2019 | 0.970 | 0.910 | 0.838 | 0.715 | 0.581 |
| covid/infl 2020–2022 | 0.813 | 0.825 | 0.829 | 0.871 | 0.742 |
| recent 2023–2026 | 0.949 | 0.864 | 0.790 | 0.713 | 0.639 |
| **ALL 1993–2026** | **0.920** | **0.837** | **0.763** | **0.740** | **0.691** |

**VR < 1 at every horizon in all six eras across 33 years.** This is the single most robust result
in the entire investigation. Multi-day variance runs persistently below √t scaling.

The problem remains expression: the direct trade is a reverse calendar, which Alpaca rejects on the
uncovered-short rule. **Finding an expressible version of this is the highest-value open problem.**

### The drift assumption is NOT stable

| Era | Ann. drift | Ann. vol |
|---|---|---|
| dot-com 1993–2002 | 9.2% | 18.5% |
| recovery 2003–2007 | 11.9% | 13.1% |
| **GFC 2008–2012** | **1.8%** | 26.2% |
| QE bull 2013–2019 | 14.2% | 12.8% |
| covid/infl 2020–2022 | 7.3% | 25.1% |
| recent 2023–2026 | **22.7%** | 15.2% |
| **ALL 1993–2026** | **10.7%** | 18.6% |

The +15.8%/yr I used throughout came from 2016–2026 and is **well above the 33-year 10.7%**. There
was a five-year era where drift was **1.8%**. Any strategy leaning on drift would have been dead
for the whole of 2008–2012.

*(SPY.csv ends 2026-05-01 — four months stale. Fine for distributional work, not for pricing.)*

---

## Where this leaves us

**Retire the cross-sectional EV method as a selection tool.** It produced the opposite conclusion
from the walk-forward test on the same structures. It is useful for *describing* a chain, not for
choosing what to trade.

**Three things are now established:**
1. Credit spreads and iron condors lose on real prices — confirmed twice, independently.
2. The variance-ratio violation is real and regime-stable across 33 years.
3. The drift is real but far less reliable than the 2016–2026 window suggested.

**Three things are needed before there is harvestable alpha:**
1. **A longer option-price history.** Feb 2024 is 2.5 years of one regime — too short to
   distinguish a Sharpe of 0.4 from zero. This is the binding constraint.
2. **An expressible form of the variance-ratio edge** that survives the uncovered-short rule.
3. **Honest treatment of the far-OTM call gradient** — it must be tested in a non-bull sample
   before it can be called anything but beta.

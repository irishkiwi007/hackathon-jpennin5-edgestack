# Can we sell SPY premium for a small edge?

**Historically yes, and the defined-risk version keeps most of it. But the edge has decayed to zero
and is currently slightly negative.** SPY ATM straddles, Monday entry → Friday expiry ~2 weeks out,
120 cycles Jan 2024 → Aug 2026, real option prices, $0.03/leg slippage. `scripts/spypremium.py`.

---

## 1. The edge is real — and it has been decaying steadily

| Period | n | implied move | actual move | ratio | **IV/RV** |
|---|---|---|---|---|---|
| 2024 | 43 | 3.21% | 2.11% | 0.656 | **1.52** |
| 2025 | 48 | 2.77% | 2.28% | 0.821 | **1.22** |
| **2026** | 29 | 2.34% | **2.54%** | **1.082** | **0.92** |
| ALL | 120 | 2.83% | 2.28% | 0.806 | 1.24 |
| **last 12 cycles** | 12 | 2.02% | 1.94% | **0.962** | **1.04** |

**1.52 → 1.22 → 0.92.** In 2026 the relationship has **inverted** — the actual move has been
*exceeding* what the straddle charged. The last 12 cycles sit at 1.04, essentially fair.

The gap closed from both sides: implied compressed hard (3.21% → 2.02%) while realised barely moved
(2.11% → 2.54%). This independently confirms the separate live reading of front IV at **7.88%**
against trailing realised of **10.40%** — implied *below* realised, which is the opposite of a
rich-premium setup.

**Selling SPY premium today means selling something priced at or below fair value.**

## 2. Correction — the defined-risk version does NOT collapse the edge

I said earlier that making this defined-risk destroys it. **That was true of a different
construction and is wrong here.**

| Structure | n | total $ | mean $ | sd | **t** | win% | worst $ | maxDD $ |
|---|---|---|---|---|---|---|---|---|
| naked straddle *(Alpaca bans)* | 120 | 37,057 | 308.8 | 1,019.6 | 3.32 | 71.7% | −5,052 | −9,619 |
| iron butterfly w10 | 117 | 5,848 | 50.0 | 316.9 | 1.71 | 36.8% | −383 | −2,933 |
| **iron butterfly w20** | 111 | 24,615 | **221.8** | 630.5 | **3.71** | 61.3% | **−901** | −6,993 |
| iron butterfly w30 | 95 | 27,810 | 292.7 | 807.3 | 3.53 | 69.5% | −1,522 | −9,348 |

**The w20 iron butterfly has a *higher* t-statistic than the naked straddle (3.71 vs 3.32)**, keeps
72% of the mean, and cuts the worst loss from −$5,052 to −$901.

The earlier collapse I reported (t 3.62 → ≤1.56) came from a different setup — 21-day holds, low-vol
tercile only, different wings. At ~10-day holds across the full sample, the wings cost far less
relative to what they protect. **The construction matters more than I implied.**

## 3. The tail is survivable in the defined-risk version

| | mean | median | p5 | p1 | min | worst loss = |
|---|---|---|---|---|---|---|
| naked straddle | +309 | +481 | −1,150 | −3,159 | −5,052 | **16 average wins** |
| iron butterfly w30 | +293 | +407 | −1,267 | −1,522 | −1,522 | **5 average wins** |

Naked short vol is uninvestable at this size — one bad week erases sixteen good ones. The butterfly
caps that at five, which is a normal short-premium profile rather than a ruin risk.

---

## Verdict

| Question | Answer |
|---|---|
| Is SPY premium systematically rich? | **Yes, over 2024–2026 as a whole** — IV/RV 1.24, t = 3.3–3.7 |
| Does defined risk keep the edge? | **Yes** — w20 butterfly retains 72% of the mean at a *better* t and 1/5 the tail |
| Is it rich **right now**? | **No.** 2026 ratio 1.082, last 12 cycles 0.962. Fair to slightly inverted |
| So: sell premium today? | **Not on this evidence** |

**On multiple testing:** unlike everything else in this project, the variance risk premium is not a
hypothesis found by searching — it is a 30-year documented result (CBOE PutWrite, 1986–2015,
Sharpe 0.67). The Bonferroni correction applied elsewhere does not bite the same way, so t = 3.71
here means more than an identical t found by data-mining would.

**Caveats:** 2.5 years and one broad regime. The 2026 estimate rests on n = 29 and the "last 12" on
n = 12, so the decay is directionally clear but imprecisely measured. Given the 30-year record, the
decay is more likely cyclical than structural — which means the edge should return, just not on a
timetable anyone can trade.

**The tradeable reading:** the structure is sound and the risk is manageable. The entry condition is
not met. A gate on IV/RV — sell only when implied meaningfully exceeds trailing realised — would
have been long premium or flat through most of 2026, which is the correct call in hindsight.

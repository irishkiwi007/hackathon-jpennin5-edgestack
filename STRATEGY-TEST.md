# News-screened premium selling — tested and rejected

Alpaca-legal iron condor (short 1.0× expected move, wings 2.0×, all four legs, defined risk),
weekly Monday entry → Friday expiry ~7 sessions out, 10 names, 834 tradeable events,
296,950 option price marks, $0.03/leg slippage. `scripts/strategy.py`.

---

## 1. The screen does not help — and the base strategy loses money

| Screen | n | total $ | mean | t | win% | worst |
|---|---|---|---|---|---|---|
| ALL (no screen) | 834 | **−24,518** | −29.4 | −1.24 | 72.4% | −4,920 |
| nz < −0.5 (very quiet) | 298 | −8,369 | −28.1 | −0.75 | 73.5% | −4,715 |
| nz < 0 (quiet) | 498 | −19,180 | −38.5 | −1.31 | 73.3% | −4,715 |
| nz < 1.0 | 736 | −17,343 | −23.6 | −0.98 | 73.1% | −4,715 |
| **nz ≥ 2.0 (spike)** | 47 | **+7,308** | **+155.5** | **2.23** | 70.2% | −943 |

**Every quiet screen loses.** Filtering harder toward quiet names does not improve anything — the
gradient runs the wrong way.

Note the **72–73% win rate alongside a losing total**. That is the short-premium signature: many
small wins, occasional large losses. One −$4,920 loss erases roughly fifty average wins.

## 2. Correction — my "avoid noisy names" conclusion does not replicate

Last section I concluded that the variance risk premium vanishes on coverage-spike days, so a
premium seller should screen them out. **This test shows the opposite subset was the profitable
one** (nz ≥ 2.0: +155.5/trade, t = 2.23).

I do not believe that either. n = 47, one of six screens tested, and it contradicts the ratio
analysis it was supposed to confirm. **The correct reading is that the news screen carries no
reliable information for premium selling in either direction.** The earlier conclusion was drawn
from a difference of t = 0.70–1.78 that I flagged as unproven at the time; it did not survive.

## 3. Per-symbol — a coin flip

Screened (nz < 1.0):

| Symbol | mean | t | | Symbol | mean | t |
|---|---|---|---|---|---|---|
| SPY | +87.6 | 1.74 | | AAPL | −90.0 | **−2.34** |
| NVDA | +40.6 | 1.26 | | GOOGL | −98.6 | −1.69 |
| MSFT | +28.0 | 0.43 | | AMD | −90.8 | −0.97 |
| TSLA | +3.5 | 0.03 | | META | −68.2 | −0.54 |

**Profitable in 4 of 10.** The only individually significant result is AAPL, and it is a *loss*.

## 4. The decay — and this is the real finding

| Year | n | total $ | mean | t |
|---|---|---|---|---|
| 2024 | 136 | +1,779 | +13.1 | 0.25 |
| 2025 | 373 | +15,154 | +40.6 | 1.51 |
| **2026** | 227 | **−34,276** | **−151.0** | **−2.71** |

**2026 is significantly negative.** Not merely decayed to zero — inverted, at t = −2.71.

---

## Three independent measurements now agree

| Method | Reading |
|---|---|
| SPY straddle ratio by year | 1.52 → 1.22 → **0.92** (2026 inverted) |
| Live chain, front expiry | IV **7.88%** vs trailing realised **10.40%** |
| Iron condor backtest, 2026 | mean **−151/trade**, t = **−2.71** |

Three unrelated routes — an index ratio, a live snapshot, and a multi-name defined-risk backtest —
all say the same thing: **implied volatility is currently at or below realised. Premium is cheap,
not rich.**

## What that implies

**Selling premium is contraindicated right now**, and the news screen does not rescue it.

The same evidence points the other way. From the 33-year vol study: current RV20 sits at the **31st
percentile**, and from comparable low-vol states forward vol *rose* **58.8%** of the time, averaging
11.8% against today's 10.40%. Combined with implied trading below trailing realised, the indicated
position is **long premium, not short**.

That is not a validated edge — it is a coherent read from several angles, which is a weaker claim.
But it is the opposite of what a premium-selling strategy assumes, and it is what the field of
competitors is mostly positioned against.

## Where the news thread finally lands

| Claim | Verdict |
|---|---|
| Coverage spikes predict larger moves | **Established** — monotone, 10/10 symbols |
| Options price that spike correctly | **Established** — t = 0.54 at entry, no lag works |
| Coverage screen improves premium selling | **Rejected** — every quiet screen loses |
| "Avoid noisy names when selling premium" | **Retracted** — did not replicate |
| Premium selling works currently | **Rejected** — 2026 t = −2.71 |

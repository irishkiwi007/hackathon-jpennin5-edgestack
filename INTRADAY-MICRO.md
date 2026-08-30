# Intraday micro-oscillations — tick data, and whether options can capture them

Alpaca's free tier gives full **raw trades and NBBO quotes** with nanosecond timestamps, plus
1-minute SIP bars. Everything needed. Scripts: `scripts/micro.py`, `scripts/predict.py`,
`scripts/optcost.py`, `scripts/minrev.py`.

Three questions, in order: is the oscillation real, is it big enough, and is it predictable.

---

## 1. At the shortest timeframes it is mostly an artifact

Roll (1984): bid-ask bounce induces negative serial correlation in **trade** prices even when the
true price is a pure random walk — trades alternate between hitting the bid and lifting the offer.
You cannot trade that zig-zag, because you would be paying the very spread that creates it.
**Midquotes are immune.** SPY, 3 sessions, ~409k trades and 1.7M quotes:

| Sample | Trade AC1 | **Midquote AC1** | Bounce share |
|---|---|---|---|
| 1s | −0.4320 | **+0.0720** | **117%** |
| 2s | −0.3650 | +0.0144 | 104% |
| 5s | −0.3120 | −0.0343 | 89% |
| 10s | −0.2189 | −0.0678 | 69% |
| 30s | −0.2083 | **−0.1156** | 44% |
| 1m | −0.0814 | −0.0381 | 53% |

**At 1–2 seconds the apparent oscillation is 100%+ artifact** — trade prices reverse at −0.43 while
midquotes are flat or slightly *positive*. That is precisely where tick data tempts you.

Genuine midquote reversion does appear at **30s–1min** (−0.04 to −0.12). Real, not artifact — but
small. The Roll-implied spread comes out 2.8–3.7× the quoted $0.02, confirming trade-price serial
correlation is dominated by the spread mechanism.

*Minute-bar cross-check over 63 sessions:* close-price AC1 is −0.004 at 1min, −0.059 at 5min
(se 0.016). SPY's spread is only 0.26bp, so bounce contributes little at minute bars — the trap is
severe at seconds, mild at minutes.

## 2. Amplitude is the wall

| Horizon | median \|move\| | p75 | p90 | **vs 4.5bp hurdle** |
|---|---|---|---|---|
| 1m | 1.43 bp | 2.77 | 4.71 | **0.32×** |
| 5m | 3.34 bp | 6.39 | 10.71 | **0.74×** |
| 10m | 4.66 bp | 8.91 | 14.63 | 1.04× |
| 30m | 8.32 bp | 16.19 | 25.01 | 1.85× |

Measured option costs from the live chain:

| Vehicle | Round-trip cost | SPY move needed |
|---|---|---|
| Single ATM option (3–5 DTE) | $2–3 | **0.5–0.8 bp** |
| **Defined-risk vertical spread** | $6–9 | **4.2–4.7 bp** |

**A defined-risk vertical cannot work here.** The entire median 10-minute move barely equals its
round-trip cost — you would need to capture ~100% of a typical swing, perfectly timed, to break
even.

**A single long option is 6× cheaper** at 0.7bp, and is still defined-risk (max loss = premium).
Long call for the bottom, long put for the top. On cost grounds that is the only viable vehicle.

## 3. Predictability — real, but two orders of magnitude too small

27,722 observations, causal rules only, excess over the unconditional forward return:

| Rule | Hold | n | Excess | t | Clears 4.5bp? |
|---|---|---|---|---|---|
| **≥4 consecutive down bars** | 30m | 1487 | **−1.389 bp** | **−3.07** | no |
| sharp 5m drop (<p5) | 10m | 1387 | +0.827 | 1.95 | no |
| ≥4 consecutive up bars | 30m | 1606 | +0.765 | 1.96 | no |
| deep z-score low (<p5) | 5m | 1387 | +0.499 | **2.13** | no |
| z-score p75–p95 | 10m | 5544 | +0.424 | **3.82** | no |

**The largest effect anywhere is 1.389 bp**, against a 4.5bp vertical hurdle. Nothing comes close.
Against the 0.7bp single-option hurdle a few clear it — by 1.1–2.0×, with no margin for anything
going wrong.

### The direction is the opposite of the premise

The strongest and most significant results are **continuation, not reversion**:

- After **4+ consecutive down bars**, the next 30 minutes runs **1.389 bp below** baseline (t=−3.07).
  The dip keeps going. Fading it is the losing side.
- z-scores in the **p75–p95** band show **+0.424 bp at 10m (t=3.82)** and **+0.681 bp at 30m
  (t=3.52)** — momentum, not exhaustion.
- The mild reversion that does exist sits in the *extreme* tails only: deep-low z gives +0.499 bp
  over 5 minutes (t=2.13), and a sharp 5-minute drop gives +0.827 bp over 10 minutes (t=1.95).

So intraday tops and bottoms are not where the conditional signal lives. Streaks and moderate
extensions **continue**; only genuinely extreme dislocations bounce, and they bounce by ~0.5–0.8 bp.

---

## Verdict

| Question | Answer |
|---|---|
| Are micro-oscillations real? | **Below 10 seconds, no** — 70–117% bid-ask bounce. At 30s–1min, yes but small (−0.04 to −0.12) |
| Big enough to trade? | **Not with spreads.** Median 1-min move 1.43bp vs 4.5bp cost. Single long options (0.7bp) are the only viable vehicle |
| Tops/bottoms predictable? | **Marginally, and mostly the wrong way.** Largest effect 1.389bp — and it is continuation after down-streaks, not a bottom |
| Best available signal | Extreme z-score lows → +0.5bp over 5min (t=2.13). Real, ~0.7× the vertical hurdle, ~0.7× a single option round trip |

**Two further constraints that bind before any of this matters:**

1. **Option quotes are 15 minutes delayed on the free tier.** An oscillation lasting minutes is over
   before its price is visible. Paper *fills* execute against real-time quotes so the fill is honest,
   but the decision is made blind and no limit price can be set sensibly. The underlying is real-time;
   the options are not.
2. **Paper fills flatter this badly.** No slippage, no size check against NBBO depth. A strategy
   whose entire edge is ~1bp is exactly the kind that survives in paper and dies live.

The tape does contain structure at 30s–1min. It is simply an order of magnitude smaller than the
cost of expressing it in options, and where it is strongest it points toward continuation rather
than the reversal the design assumes.

"""Verify the production engine reproduces the research numbers.

If signal_engine.py does not regenerate the same events and the same statistics as the study in
HERD-REVERSAL.md, the engine is wrong and nothing downstream can be trusted. This walks the
33-year history bar by bar through the SAME public entry point the live agent calls
(`evaluate`), so any drift between research and production shows up here.

Run:  python agent/test_signal_engine.py
"""
from __future__ import annotations

import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signal_engine import (Bar, HOLD_SESSIONS, MIN_BARS, TIERS, evaluate, classify)

BASE = (r"C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main"
        r"\data\historical")
ETFS = ["SPY", "QQQ", "SOXX", "HYG", "XLP", "XLV", "FDN"]   # TLT excluded: no mechanism

# From HERD-REVERSAL.md. Two separate claims:
#
#   Per-cell (disjoint volume cells, raw 3-day return)
#   Combined "tier A" = z<-2.5 AND volume>1.8x = FULL + MEDIUM = 135 events, +1.646%, t=5.42.
#   The study's t is computed on EXCESS returns (vs each ETF's own unconditional 3-day mean),
#   so this test computes excess the same way rather than comparing raw t to excess t.
PER_TIER = {                       # label -> (n, raw_pct, win_pct)
    "SMALL":  (59, 0.721, 64.4),
    "FULL":   (77, 1.897, 70.1),
    "MEDIUM": (58, 1.312, 65.5),
}
COMBINED = {"n": 135, "raw_pct": 1.646, "win_pct": 68.1, "excess_t": 5.42}
TOL = {"n": 2, "raw_pct": 0.02, "win_pct": 0.5, "excess_t": 0.4}


def load(symbol: str) -> list[Bar]:
    path = os.path.join(BASE, symbol + ".csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [Bar(date=r["date"], close=float(r["adj_close"]), volume=float(r["volume"]))
            for r in rows]


def newey_west_t(xs: list[float], lag: int) -> float:
    n = len(xs)
    if n < 15:
        return float("nan")
    mean = sum(xs) / n
    err = [x - mean for x in xs]
    gamma0 = sum(e * e for e in err) / n
    s = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        gk = sum(err[i + k] * err[i] for i in range(n - k)) / n
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    return mean / math.sqrt(s / n) if s > 0 else float("nan")


def main() -> int:
    fired: dict[str, list[float]] = {t[0]: [] for t in TIERS}
    excess: dict[str, list[float]] = {t[0]: [] for t in TIERS}
    total_bars = 0

    for symbol in ETFS:
        bars = load(symbol)
        n = len(bars)
        # this ETF's unconditional 3-day mean, the baseline the study measured excess against
        every = [math.log(bars[i + HOLD_SESSIONS].close / bars[i].close) * 100.0
                 for i in range(MIN_BARS, n - HOLD_SESSIONS)]
        baseline = sum(every) / len(every)
        for i in range(MIN_BARS, n - HOLD_SESSIONS):
            total_bars += 1
            sig = evaluate(symbol, bars[: i + 1])
            if sig is None:
                continue
            pnl = math.log(bars[i + HOLD_SESSIONS].close / bars[i].close) * 100.0
            fired[sig.tier].append(pnl)
            excess[sig.tier].append(pnl - baseline)

    print(f"walked {total_bars:,} bars across {len(ETFS)} ETFs\n")
    print(f"{'tier':<9} {'n':>5} {'mean %':>9} {'win %':>8} {'excess t':>9}")
    results = {}
    for tier_row in TIERS:
        label = tier_row[0]
        pnl = fired[label]
        if not pnl:
            print(f"{label:<9} {0:>5}   (never fired)")
            continue
        mean = sum(pnl) / len(pnl)
        win = 100.0 * sum(1 for x in pnl if x > 0) / len(pnl)
        t = newey_west_t(excess[label], HOLD_SESSIONS)
        results[label] = dict(n=len(pnl), raw_pct=mean, win_pct=win, excess_t=t)
        exp_n, exp_mean, exp_win = PER_TIER[label]
        print(f"{label:<9} {len(pnl):>5} {mean:>9.3f} {win:>7.1f}% {t:>9.2f}"
              f"    (study: n={exp_n}, {exp_mean:+.3f}%, {exp_win:.1f}%)")

    print()
    ok = True

    # 1. each disjoint cell must match its own measured numbers
    for label, (exp_n, exp_raw, exp_win) in PER_TIER.items():
        got = results.get(label)
        if got is None:
            print(f"  FAIL  tier {label} never fired")
            ok = False
            continue
        for key, expected in (("n", exp_n), ("raw_pct", exp_raw), ("win_pct", exp_win)):
            delta = abs(got[key] - expected)
            passed = delta <= TOL[key]
            ok &= passed
            print(f"  {'PASS' if passed else 'FAIL'}  {label:<7} {key:<8} "
                  f"engine {got[key]:>8.3f}   study {expected:>8.3f}   diff {delta:>6.3f}")

    # 2. FULL + MEDIUM together are the study's "tier A" (z<-2.5, volume>1.8x)
    combo = fired["FULL"] + fired["MEDIUM"]
    combo_ex = excess["FULL"] + excess["MEDIUM"]
    got = {"n": len(combo), "raw_pct": sum(combo) / len(combo),
           "win_pct": 100.0 * sum(1 for x in combo if x > 0) / len(combo),
           "excess_t": newey_west_t(combo_ex, HOLD_SESSIONS)}
    print()
    for key, expected in COMBINED.items():
        delta = abs(got[key] - expected)
        passed = delta <= TOL[key]
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  tier A (FULL+MEDIUM) {key:<9} "
              f"engine {got[key]:>8.3f}   study {expected:>8.3f}   diff {delta:>6.3f}")

    print()
    # the volume ceiling is load-bearing: FULL must beat MEDIUM
    full, med = results.get("FULL"), results.get("MEDIUM")
    if full and med:
        passed = full["raw_pct"] > med["raw_pct"]
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  volume ceiling holds: FULL "
              f"{full['raw_pct']:.3f}% > MEDIUM {med['raw_pct']:.3f}%")

    # the no-flush cell must be refused outright
    passed = classify(-3.0, 1.1) is None and classify(-3.0, 0.5) is None
    ok &= passed
    print(f"  {'PASS' if passed else 'FAIL'}  light-volume selloffs refused (no capitulation)")
    passed = classify(-1.0, 2.0) is None
    ok &= passed
    print(f"  {'PASS' if passed else 'FAIL'}  shallow selloffs refused (stretch gate)")

    print("\n" + ("ALL CHECKS PASSED - engine matches the study"
                  if ok else "MISMATCH - engine does NOT match the study"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Parking idle capital in T-bills (SGOV/BIL) with a yield filter.

Unlike XLP/gold (risk-asset drift bets - tested and killed in park_flat.py), bills are
rate capture: near-zero vol, no drawdown, deterministic accrual. The question is purely
yield vs churn. Per the trader's rule, cash parks in bills ONLY when the 3-month yield
clears the round-trip cost of getting in and out.

Two implementable cuts, modeled on the 33y record with real DGS3MO yields:

  B. STRETCH parking - hold bills through gate-closed stretches (enter at the close the
     gate shuts, exit the close it reopens). One round trip per stretch.
  C. FULL CHURN - additionally hold bills intraday on gate-open days (sell at 15:58 to
     fund SPY, rebuy at 09:31). One round trip per open day; captures ~half a day's
     accrual. Its breakeven yield is 252*cost/0.5 - steep by construction.

Bills modeled as accrual y/252 per held day (SGOV NAV behavior; vol ~ 0). Costs 1bp per
round trip (Alpaca zero commission, penny spread on ~$100 NAV); 2bp variant reported.
"""
import csv
import io
import math
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = ("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/"
        "data/historical")


def load(sym):
    rows = list(csv.DictReader(open(BASE + "/" + sym + ".csv", encoding="utf-8")))
    d = [r["date"] for r in rows]
    o = np.array([float(r["open"]) for r in rows])
    c = np.array([float(r["close"]) for r in rows])
    ac = np.array([float(r["adj_close"]) for r in rows])
    fac = np.where(c > 0, ac / np.maximum(c, 1e-9), 1.0)
    return d, o * fac, ac


SPYd, SPYo, SPYc = load("SPY")
n = len(SPYc)

# 3m bill yield, forward-filled onto SPY dates (percent, annualized)
yld_by_date = {}
for r in csv.DictReader(open(BASE + "/DGS3MO.csv", encoding="utf-8")):
    v = r["DGS3MO"]
    if v not in ("", "."):
        yld_by_date[r["observation_date"]] = float(v)
Y = np.zeros(n)
last = 0.0
for i, d in enumerate(SPYd):
    last = yld_by_date.get(d, last)
    Y[i] = last

TREND = np.zeros(n, dtype=bool)
TREND[252:] = SPYc[252:] / SPYc[:-252] > 1.0
START = 253
IDX = list(range(START, n - 1))
DATES = [SPYd[i] for i in IDX]


def perf(a):
    a = np.asarray(a, float)
    eq = np.cumprod(1 + a / 100.0)
    yrs = len(a) / 252.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = a.std(ddof=1) * math.sqrt(252) / 100.0
    peak = np.maximum.accumulate(eq)
    return dict(cagr=cagr, vol=vol, sharpe=(cagr - 0.02) / vol if vol > 0 else 0.0,
                dd=float((eq / peak - 1).min()))


core = np.array([(SPYo[i + 1] / SPYc[i] - 1) * 100 - 0.01
                 if TREND[i] and SPYc[i] > 0 else 0.0 for i in IDX])

# ---- closed-stretch anatomy --------------------------------------------------------------
stretches = []
i = 0
flags = [not TREND[i] for i in IDX]
while i < len(flags):
    if flags[i]:
        j = i
        while j < len(flags) and flags[j]:
            j += 1
        stretches.append((i, j))          # [i, j) closed
        i = j
    else:
        i += 1
lens = [j - i for i, j in stretches]
closed_days = sum(lens)
print(f"gate-closed: {closed_days}/{len(IDX)} sessions ({100*closed_days/len(IDX):.1f}%), "
      f"{len(stretches)} stretches, median {int(np.median(lens))}d, mean {np.mean(lens):.0f}d, "
      f"max {max(lens)}d")
print(f"bill yield by era: ", end="")
for lo, hi in (("1994", "2008"), ("2008", "2018"), ("2018", "2022"), ("2022", "2027")):
    m = [k for k, d in enumerate(DATES) if lo <= d[:4] < hi]
    print(f"{lo}-{hi}: {np.mean([Y[IDX[k]] for k in m]):.2f}%  ", end="")
print("\n")


def stretch_parking(rt_cost, y_min):
    """Bills through gate-closed stretches, iff yield at entry >= y_min. One rt/stretch."""
    add = np.zeros(len(IDX))
    parked_days = parked_stretches = 0
    for i0, j0 in stretches:
        y_entry = Y[IDX[i0]]
        if y_entry < y_min:
            continue
        parked_stretches += 1
        for k in range(i0, j0):
            add[k] += Y[IDX[k]] / 252.0
            parked_days += 1
        add[j0 - 1] -= rt_cost
    return add, parked_days, parked_stretches


def churn_component(rt_cost):
    """Bills held intraday on gate-open days, iff yield covers the daily round trip."""
    breakeven = rt_cost * 252 / 0.5
    add = np.zeros(len(IDX))
    active = 0
    for k, i in enumerate(IDX):
        if TREND[i] and Y[i] >= breakeven:
            add[k] += Y[i] / 252.0 * 0.5 - rt_cost
            active += 1
    return add, active, breakeven


def added_bps(add):
    out = []
    for lo, hi in (("1994", "2027"), ("2008", "2018"), ("2018", "2027")):
        m = [k for k, d in enumerate(DATES) if lo <= d[:4] < hi]
        out.append(np.mean(add[m]) * 252 * 100)   # bps/yr
    return out


print("=" * 100)
print("B. STRETCH PARKING - net carry added (bps/yr) by yield filter  [1bp rt | 2bp rt]")
print("=" * 100)
print(f"{'filter':<26} {'parked':<22} {'full':>14} {'train 08-17':>14} {'valid 18-26':>14}")
for y_min in (0.0, 0.5, 1.0, 2.0):
    a1, pd1, ps1 = stretch_parking(0.01, y_min)
    a2, _, _ = stretch_parking(0.02, y_min)
    b1, b2 = added_bps(a1), added_bps(a2)
    print(f"y >= {y_min:.1f}%{'':<18} {ps1}/{len(stretches)} stretches, {pd1}d"
          f"{'':<2} {b1[0]:>6.1f} | {b2[0]:>5.1f} {b1[1]:>7.1f} | {b2[1]:>5.1f} {b1[2]:>7.1f} | {b2[2]:>5.1f}")

a_churn, act, brk = churn_component(0.01)
bc = added_bps(a_churn)
print(f"\nC. FULL CHURN (open-day intraday holds; self-filter y >= {brk:.2f}%): "
      f"active {act}/{len(IDX)} days; adds {bc[0]:.1f} bps/yr full, {bc[1]:.1f} train, {bc[2]:.1f} valid")

print()
print("=" * 100)
print("CORE vs CORE + STRETCH PARKING (filter y >= 0.5%, 1bp rt)")
print("=" * 100)
park, _, _ = stretch_parking(0.01, 0.5)
for label, a in (("core only", core), ("core + bill parking", core + park),
                 ("core + parking + churn", core + park + a_churn)):
    p = perf(a)
    print(f"{label:<28} CAGR {100*p['cagr']:>5.2f}%  vol {100*p['vol']:>5.2f}%  "
          f"Sharpe {p['sharpe']:>5.2f}  maxDD {100*p['dd']:>6.1f}%")
print()
print("both-windows Sharpe (train / valid):")
for label, a in (("core only", core), ("core + bill parking", core + park)):
    row = []
    for lo, hi in (("2008", "2018"), ("2018", "2027")):
        m = [k for k, d in enumerate(DATES) if lo <= d[:4] < hi]
        row.append(perf(a[m])["sharpe"])
    print(f"  {label:<28} {row[0]:.3f} / {row[1]:.3f}")

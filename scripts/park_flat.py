"""Parking the flat hours: does holding XLP or a gold basket while EdgeStack is flat help?

The overnight core is flat during every day session, and flat overnight when the trend
gate is closed. The engine trial already killed full-session risk-off parking (XLP/XLV
fails train 0.67; +WPM/RGLD fails train 0.70 with a 33% GFC drawdown). This tests the
two cuts that sweep did NOT cover, in the research engine over the 33-year record:

  A. INTRADAY overlay - hold XLP / gold basket open->close every session (the hours the
     core never touches), charged a full round trip per day.
  B. GATE-CLOSED-NIGHT parking - hold XLP / gold basket close->open only on nights the
     trend gate keeps the core in cash.

Discipline: same as ENGINE-TRIAL - a variant counts only if it helps on BOTH the train
window (2008-2017) and the disjoint validation window (2018-2026). Costs are per-name
round trips (SPY 1bp, XLP 2bp, gold names 4bp).
"""
import csv
import io
import math
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = ("C:/Users/Lenovo/Downloads/TrustyRustyEngine-main/TrustyRustyEngine-main/"
        "data/historical")
COST_RT = {"SPY": 0.01, "XLP": 0.02, "WPM": 0.04, "RGLD": 0.04, "FNV": 0.04}
GOLD = ["WPM", "RGLD", "FNV"]


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
DIDX = {d: i for i, d in enumerate(SPYd)}

# per-symbol intraday (close/open - 1) and overnight (next open / close - 1), by SPY date
def sessions(sym):
    d, o, c = load(sym)
    intra = np.full(n, np.nan)
    night = np.full(n, np.nan)
    for k, dt in enumerate(d):
        i = DIDX.get(dt)
        if i is None:
            continue
        if o[k] > 0:
            intra[i] = (c[k] / o[k] - 1) * 100
        if k + 1 < len(d) and c[k] > 0:
            night[i] = (o[k + 1] / c[k] - 1) * 100
    return intra, night


INTRA, NIGHT = {}, {}
for s in ["SPY", "XLP"] + GOLD:
    INTRA[s], NIGHT[s] = sessions(s)

def basket(table, names):
    m = np.vstack([table[s] for s in names])
    with np.errstate(invalid="ignore"):
        return np.nanmean(m, axis=0)

def basket_cost(names):
    return float(np.mean([COST_RT[s] for s in names]))

TREND = np.zeros(n, dtype=bool)
TREND[252:] = SPYc[252:] / SPYc[:-252] > 1.0
START = 253
IDX = list(range(START, n - 1))


def perf(a, dates):
    a = np.asarray(a, float)
    eq = np.cumprod(1 + a / 100.0)
    yrs = len(a) / 252.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = a.std(ddof=1) * math.sqrt(252) / 100.0
    peak = np.maximum.accumulate(eq)
    dd = float((eq / peak - 1).min())
    return dict(cagr=cagr, vol=vol, sharpe=(cagr - 0.02) / vol if vol > 0 else 0.0, dd=dd)


def show(label, a, dates):
    p = perf(a, dates)
    print(f"{label:<44} CAGR {100*p['cagr']:>6.2f}%  vol {100*p['vol']:>6.2f}%  "
          f"Sharpe {p['sharpe']:>5.2f}  maxDD {100*p['dd']:>6.1f}%")
    return p


def windowed(label, a, dates):
    a = np.asarray(a, float)
    out = [label]
    for lo, hi in (("2008", "2018"), ("2018", "2027")):
        m = [k for k, d in enumerate(dates) if lo <= d[:4] < hi]
        p = perf(a[m], [dates[k] for k in m])
        out.append(f"{p['sharpe']:.2f} (DD {100*p['dd']:.0f}%)")
    print(f"{out[0]:<44} train {out[1]:>18}   valid {out[2]:>18}")


DATES = [SPYd[i] for i in IDX]

# streams, aligned to IDX sessions -------------------------------------------------------
def stream_core():
    out = []
    for i in IDX:
        out.append((NIGHT["SPY"][i] - COST_RT["SPY"]) if TREND[i] and np.isfinite(NIGHT["SPY"][i]) else 0.0)
    return np.array(out)

def stream_intraday(table_row, cost):
    out = []
    for i in IDX:
        v = table_row[i]
        out.append((v - cost) if np.isfinite(v) else 0.0)
    return np.array(out)

def stream_closed_nights(table_row, cost):
    out = []
    for i in IDX:
        v = table_row[i]
        out.append((v - cost) if (not TREND[i]) and np.isfinite(v) else 0.0)
    return np.array(out)


core = stream_core()
gold_intra = basket(INTRA, GOLD)
gold_night = basket(NIGHT, GOLD)
gc = basket_cost(GOLD)

print("=" * 100)
print("ANATOMY - where the drift lives (gross, no costs, full record where data exists)")
print("=" * 100)
for s in ["SPY", "XLP"]:
    for nm, row in (("intraday", INTRA[s]), ("overnight", NIGHT[s])):
        m = [k for k, i in enumerate(IDX) if np.isfinite(row[i])]
        a = np.array([row[IDX[k]] for k in m])
        d0 = DATES[m[0]]
        show(f"{s} {nm} (from {d0})", a, None)
for nm, row in (("intraday", gold_intra), ("overnight", gold_night)):
    m = [k for k, i in enumerate(IDX) if np.isfinite(row[i])]
    a = np.array([row[IDX[k]] for k in m])
    show(f"GOLD basket (WPM/RGLD/FNV) {nm} (from {DATES[m[0]]})", a, None)

print()
print("=" * 100)
print("VARIANTS - full record, net of costs (overlay charged a round trip per use)")
print("=" * 100)
V = {
    "core only (overnight SPY, trend-gated)": core,
    "A1. XLP intraday standalone": stream_intraday(INTRA["XLP"], COST_RT["XLP"]),
    "A2. gold basket intraday standalone": stream_intraday(gold_intra, gc),
    "A3. core + XLP intraday overlay": core + stream_intraday(INTRA["XLP"], COST_RT["XLP"]),
    "A4. core + gold intraday overlay": core + stream_intraday(gold_intra, gc),
    "B1. XLP on gate-closed nights standalone": stream_closed_nights(NIGHT["XLP"], COST_RT["XLP"]),
    "B2. gold on gate-closed nights standalone": stream_closed_nights(gold_night, gc),
    "B3. core + XLP closed-night parking": core + stream_closed_nights(NIGHT["XLP"], COST_RT["XLP"]),
    "B4. core + gold closed-night parking": core + stream_closed_nights(gold_night, gc),
}
for label, a in V.items():
    show(label, a, DATES)

print()
print("=" * 100)
print("BOTH-WINDOWS CHECK - Sharpe train (2008-2017) vs validation (2018-2026)")
print("=" * 100)
for label in ("core only (overnight SPY, trend-gated)",
              "A3. core + XLP intraday overlay",
              "A4. core + gold intraday overlay",
              "B3. core + XLP closed-night parking",
              "B4. core + gold closed-night parking"):
    windowed(label, V[label], DATES)

# QuantConnect RESEARCH NOTEBOOK — paste into a new Research notebook cell in the cloud IDE.
#
# PURPOSE: use 14 years of multi-regime option data to SEARCH a wide structure space and find
# what is stable, rather than to re-test a structure already chosen from a snapshot.
#
# Run CELL 1 first to validate the data API on a short span. Only scale up once it returns rows.

# ============================== CELL 1 — validate the API ==============================
from AlgorithmImports import *
from datetime import datetime, timedelta
import pandas as pd, numpy as np

qb = QuantBook()
equity = qb.add_equity("SPY", Resolution.DAILY)
opt = qb.add_option("SPY")
opt.set_filter(-25, 25, timedelta(0), timedelta(12))

start = datetime(2024, 1, 2)
end = datetime(2024, 3, 1)

# Newer LEAN: historical option universe (strikes, greeks, OI) via OptionUniverse
try:
    chains = qb.history(OptionUniverse, opt.symbol, start, end, flatten=True)
    print("OptionUniverse OK  rows:", len(chains))
    print(chains.columns.tolist())
    display(chains.head(10))
except Exception as e:
    print("OptionUniverse failed:", type(e).__name__, e)
    chains = None

# Fallback: contract-level history
if chains is None or len(chains) == 0:
    try:
        chains = qb.history(opt.symbol, start, end, Resolution.DAILY, flatten=True)
        print("fallback qb.history OK  rows:", len(chains))
        display(chains.head(10))
    except Exception as e:
        print("fallback failed:", type(e).__name__, e)

# >>> PASTE THE OUTPUT BACK. Column names drive everything below. <<<


# ============================== CELL 2 — the search ==============================
# Only run after CELL 1 confirms columns. Adjust COL_* to match what CELL 1 printed.

COL_STRIKE, COL_RIGHT, COL_EXPIRY = "strike", "right", "expiry"
COL_BID, COL_ASK = "bidprice", "askprice"
COL_DELTA, COL_IV = "delta", "impliedvolatility"

START, END = datetime(2012, 1, 3), datetime(2026, 8, 1)
HOLD_DAYS = 5                      # Mon -> Fri, matching the competition horizon
SLIP = 0.02                        # $/leg, applied against you on entry

# Search grid — deliberately WIDE. The point is to let the data pick, not to confirm a prior.
LONG_OFFSETS = [-0.030, -0.025, -0.020, -0.015, -0.010, -0.005,
                0.005, 0.010, 0.015, 0.020, 0.025, 0.030]
WIDTHS = [0.005, 0.010, 0.015, 0.020]
SIDES = ["C", "P"]
DIRECTIONS = ["debit", "credit"]   # debit = long near / short far; credit = the reverse

REGIMES = [
    ("2012-2014 lowvol",  datetime(2012, 1, 1), datetime(2014, 12, 31)),
    ("2015-2016 chop",    datetime(2015, 1, 1), datetime(2016, 12, 31)),
    ("2017 ultralow",     datetime(2017, 1, 1), datetime(2017, 12, 31)),
    ("2018 volmageddon",  datetime(2018, 1, 1), datetime(2018, 12, 31)),
    ("2019 melt-up",      datetime(2019, 1, 1), datetime(2019, 12, 31)),
    ("2020 covid",        datetime(2020, 1, 1), datetime(2020, 12, 31)),
    ("2021 bull",         datetime(2021, 1, 1), datetime(2021, 12, 31)),
    ("2022 bear",         datetime(2022, 1, 1), datetime(2022, 12, 31)),
    ("2023-2024 recovery",datetime(2023, 1, 1), datetime(2024, 12, 31)),
    ("2025-2026 recent",  datetime(2025, 1, 1), datetime(2026, 12, 31)),
]

# IN-SAMPLE / OUT-OF-SAMPLE SPLIT — decided before looking at any result.
IS_END = datetime(2019, 12, 31)    # fit on 2012-2019, validate on 2020-2026

spy = qb.history(qb.symbol("SPY"), START, END, Resolution.DAILY)
px = spy["close"].droplevel(0) if isinstance(spy.index, pd.MultiIndex) else spy["close"]
px.index = pd.to_datetime(px.index).normalize()
print("SPY sessions:", len(px), px.index.min(), "->", px.index.max())

chains = qb.history(OptionUniverse, opt.symbol, START, END, flatten=True)
print("chain rows:", len(chains))


def build_cycles(px, hold):
    """Monday entries with a matching session `hold` days later."""
    out = []
    days = list(px.index)
    for i, d in enumerate(days):
        if d.weekday() != 0 or i + hold >= len(days):
            continue
        out.append((d, days[i + hold]))
    return out


cycles = build_cycles(px, HOLD_DAYS)
print("cycles:", len(cycles))


def price_leg(day_chain, right, strike, side):
    """side='buy' pays ask+slip, 'sell' receives bid-slip."""
    r = day_chain[(day_chain[COL_RIGHT] == right) &
                  (np.isclose(day_chain[COL_STRIKE], strike))]
    if len(r) == 0:
        return None
    bid, ask = float(r.iloc[0][COL_BID]), float(r.iloc[0][COL_ASK])
    if bid <= 0 or ask <= bid:
        return None
    return (ask + SLIP) if side == "buy" else (bid - SLIP)


def run_one(side, direction, off, width):
    trades = []
    for d0, d1 in cycles:
        try:
            day = chains.xs(d0, level=0)
        except Exception:
            continue
        S0, S1 = float(px.loc[d0]), float(px.loc[d1])
        exp_target = d1
        day = day[pd.to_datetime(day[COL_EXPIRY]).dt.normalize() == exp_target]
        if len(day) == 0:
            continue
        ks = np.unique(day[COL_STRIKE].astype(float))
        if len(ks) < 4:
            continue
        k1 = ks[np.argmin(np.abs(ks - S0 * (1 + off)))]
        k2t = S0 * (1 + off + width) if side == "C" else S0 * (1 + off - width)
        cand = ks[ks > k1] if side == "C" else ks[ks < k1]
        if len(cand) == 0:
            continue
        k2 = cand[np.argmin(np.abs(cand - k2t))]
        b1 = "buy" if direction == "debit" else "sell"
        b2 = "sell" if direction == "debit" else "buy"
        p1, p2 = price_leg(day, side, k1, b1), price_leg(day, side, k2, b2)
        if p1 is None or p2 is None:
            continue
        cost = (p1 - p2) if direction == "debit" else (p2 - p1)
        intr = ((max(S1 - k1, 0) - max(S1 - k2, 0)) if side == "C"
                else (max(k1 - S1, 0) - max(k2 - S1, 0)))
        val = intr if direction == "debit" else -intr
        trades.append((d0, (val - cost) * 100))
    return trades


def stats(tr, lo=None, hi=None):
    p = [x for d, x in tr if (lo is None or lo <= d <= hi)]
    n = len(p)
    if n < 20:
        return None
    m, sd = float(np.mean(p)), float(np.std(p, ddof=1))
    sr = m / sd * np.sqrt(52) if sd else 0.0
    se = np.sqrt((1 + 0.5 * sr * sr) / n) * np.sqrt(52)
    return dict(n=n, total=float(np.sum(p)), mean=m, sharpe=sr, se=se, t=sr / se if se else 0,
                win=float(np.mean([x > 0 for x in p])))


rows = []
for side in SIDES:
    for direction in DIRECTIONS:
        for off in LONG_OFFSETS:
            for w in WIDTHS:
                tr = run_one(side, direction, off, w)
                s_is = stats(tr, START, IS_END)
                if not s_is:
                    continue
                s_oos = stats(tr, IS_END + timedelta(1), END)
                per = {nm: stats(tr, a, b) for nm, a, b in REGIMES}
                pos = sum(1 for v in per.values() if v and v["sharpe"] > 0)
                tot = sum(1 for v in per.values() if v)
                rows.append(dict(
                    side=side, dir=direction, off=off, width=w,
                    n_is=s_is["n"], sharpe_is=s_is["sharpe"], t_is=s_is["t"],
                    sharpe_oos=(s_oos or {}).get("sharpe"), n_oos=(s_oos or {}).get("n"),
                    regimes_pos=f"{pos}/{tot}", win=s_is["win"]))

res = pd.DataFrame(rows)
print(f"\ntested {len(res)} structures\n")

# THE ONLY FILTER THAT MATTERS: strong in-sample AND holds up out-of-sample AND broad across regimes
res["survives"] = (res.sharpe_is > 0.5) & (res.t_is > 2.0) & (res.sharpe_oos > 0.3)
surv = res[res.survives].sort_values("sharpe_oos", ascending=False)

print("=== IN-SAMPLE LEADERS (2012-2019) ===")
display(res.sort_values("sharpe_is", ascending=False).head(15))
print("\n=== SURVIVED OUT-OF-SAMPLE (2020-2026) ===")
display(surv.head(20) if len(surv) else "NOTHING SURVIVED — that is a real answer, report it")
print(f"\nsurvivors: {len(surv)} of {len(res)}")
print("Expected under pure noise at these thresholds: a small handful. If survivors ~= that,")
print("there is no edge here and the honest conclusion is a negative result.")

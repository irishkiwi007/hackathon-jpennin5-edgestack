"""Adoption review — should a lab ADOPT_CANDIDATE go into the live strategy?

Runs on the PRODUCTION TrustyRustyEngine (CT 200), never the research lab, so
nothing here touches the sealed lab, its journal or its single-use holdout
ledger. The lab's verdict answers "did the change move the objective by more
than the zone floor in both windows"; promotion into live money deserves more:

  windows      train / valid (the lab's), full, and the SEALED window the lab
               has never seen (2025-01-01 onward) - the human's look
  cost stress  2x and 5x costs on train and valid: does the sign survive
  per year     Sortino, return and max-drawdown delta by calendar year, from
               one full-history run each - where does the improvement live
  drop-one     the full-window Sortino delta with each year removed: is the
               effect carried by a single year
  paired t     daily return differences (variant - baseline), full and sealed
  ablation     each flag alone, so a two-flag candidate is not credited for
               a gain only one of its flags produced

Everything is arithmetic on engine output; the thresholds are the lab
protocol's (cited inline). The verdict at the end is a recommendation built
from those numbers alone.

    python agent/adoption_review.py            # both edgestack candidates
"""
from __future__ import annotations

import datetime
import json
import math
import os
import shlex
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "journal", "reproductions")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", os.environ.get("EDGESTACK_PVE", "pve")]
CT = os.environ.get("EDGESTACK_ENGINE_CT", "200")            # production engine, NOT the lab
ENGINE_URL = "http://127.0.0.1:3000/api/python-strategies/backtest"
STRATEGY = "edgestack_live.py"

# Lab protocol v1 (protocol_v1.toml, read 2026-09-02): windows, costs, zones.
PROTOCOL = {
    "train": ("2008-01-01", "2017-12-31"), "valid": ("2018-01-01", "2024-12-31"),
    "full": ("2008-01-01", "2024-12-31"),
    "sealed": ("2025-01-01", None),                     # end = last common data date
    "slippage_bps": 5.0, "commission_bps": 5.0, "capital": 100_000.0,
    "sortino": {"adopt_min": 0.05, "reject_max": -0.05, "dd_worse_max": 0.02},
    "max_drawdown": {"adopt_min": 0.02, "reject_max": -0.02, "sortino_guard": -0.05},
    "noise_floor": 0.01, "min_effect": 0.02,
}
CANDIDATES = {
    "H-E002":   {"objective": "sortino_ratio", "params": {"tier_mode": 1},
                 "what": "sleeve never trades the MEDIUM volume cell (>= 2.5x): the earlier "
                         "engine port's hard ceiling"},
    "H-E003.3": {"objective": "max_drawdown", "params": {"tier_mode": 1, "vol_scale_mode": 1},
                 "what": "the ceiling above PLUS the core scaled to 0.6 when realized vol is "
                         "above its trailing 2y median"},
}
ABLATIONS = {"vol_scale_only": {"vol_scale_mode": 1}}


# ----------------------------------------------------------------------------- engine
def ct(cmd: str, timeout: int = 1800) -> str:
    r = subprocess.run(SSH + [f"pct exec {CT} -- bash -c {shlex.quote(cmd)}"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"container command failed rc={r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    return r.stdout


RUNNER_IN_CT = r'''
import json, sys, urllib.request
jobs = json.load(open("/tmp/ar_jobs.json"))
out = []
for j in jobs:
    req = urllib.request.Request("%s", data=json.dumps(j).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read().decode())
    except Exception as exc:
        d = {"error": str(exc)[:300]}
    out.append({"metrics": d.get("metrics"), "error": d.get("error"),
                "curve": [(p["ts_nanos"], p["cumulative_pnl_raw"]) for p in (d.get("equity_curve") or [])]})
print(json.dumps(out))
''' % ENGINE_URL


def run_many(jobs: list[dict]) -> list[dict]:
    """One ssh session, N sequential engine calls; returns the N results. The job
    list and the runner travel base64-encoded so no quoting survives three shells."""
    import base64
    bodies = [{"filename": STRATEGY, "start_date": j["start"], "end_date": j["end"],
               "initial_capital": PROTOCOL["capital"],
               "slippage_bps": PROTOCOL["slippage_bps"] * j.get("mult", 1.0),
               "commission_bps": PROTOCOL["commission_bps"] * j.get("mult", 1.0),
               "params": j["params"]} for j in jobs]
    # 28 jobs overflow the argv the exec hop will carry (observed: the line was
    # cut mid-quote), so the files travel by scp + pct push and the command
    # stays short.
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ar_")
    jobs_path, py_path = os.path.join(tmp, "ar_jobs.json"), os.path.join(tmp, "ar_run.py")
    with open(jobs_path, "w", encoding="utf-8") as fh:
        json.dump(bodies, fh)
    with open(py_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(RUNNER_IN_CT)
    host = SSH[-1]
    for p in (jobs_path, py_path):
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", p, f"{host}:/tmp/{os.path.basename(p)}"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"scp failed: {r.stderr[-200:]}")
    r = subprocess.run(SSH + [f"pct push {CT} /tmp/ar_jobs.json /tmp/ar_jobs.json && "
                              f"pct push {CT} /tmp/ar_run.py /tmp/ar_run.py"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"pct push failed: {(r.stderr or r.stdout)[-200:]}")
    return json.loads(ct("python3 /tmp/ar_run.py"))


def daily(curve) -> list[tuple[datetime.date, float]]:
    return [(datetime.datetime.fromtimestamp(ts / 1e9, datetime.timezone.utc).date(), raw / 100.0)
            for ts, raw in curve]


def returns(eq: list[tuple[datetime.date, float]]) -> dict[datetime.date, float]:
    out = {}
    for (d0, a), (d1, b) in zip(eq, eq[1:]):
        if a > 0:
            out[d1] = (b - a) / a
    return out


# ----------------------------------------------------------------------------- metrics (engine's definitions)
def sortino(rets: list[float], years: float) -> float:
    """CAGR / downside deviation, Lean-style target semideviation, as weight_engine.rs."""
    if not rets or years <= 0:
        return 0.0
    growth = 1.0
    for r in rets:
        growth *= 1 + r
    cagr = growth ** (1 / years) - 1 if growth > 0 else 0.0
    neg = [r for r in rets if r < 0]
    dd = math.sqrt(sum(r * r for r in neg) / len(neg) * 252) if neg else 0.0
    return cagr / dd if dd > 0 else 0.0


def max_dd(eq: list[float]) -> float:
    peak, worst = eq[0] if eq else 0.0, 0.0
    for e in eq:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


def window_stats(rb: dict, rv: dict, eb: dict, ev: dict, d0: datetime.date, d1: datetime.date) -> dict:
    days = [d for d in sorted(rb) if d0 <= d <= d1 and d in rv]
    if len(days) < 30:
        return {"n": len(days)}
    years = max((days[-1] - days[0]).days, 1) / 365.25
    b, v = [rb[d] for d in days], [rv[d] for d in days]
    diff = [x - y for x, y in zip(v, b)]
    m = statistics.mean(diff)
    sd = statistics.stdev(diff) if len(diff) > 1 else 0.0
    t = m / (sd / math.sqrt(len(diff))) if sd > 0 else 0.0
    eqb = [eb[d] for d in days]
    eqv = [ev[d] for d in days]
    grow = lambda rs: math.prod(1 + r for r in rs) - 1          # noqa: E731
    return {"n": len(days), "sortino_b": round(sortino(b, years), 4), "sortino_v": round(sortino(v, years), 4),
            "d_sortino": round(sortino(v, years) - sortino(b, years), 4),
            "ret_b": round(grow(b), 4), "ret_v": round(grow(v), 4), "d_ret": round(grow(v) - grow(b), 4),
            "dd_b": round(max_dd(eqb), 4), "dd_v": round(max_dd(eqv), 4),
            "dd_delta": round(max_dd(eqv) - max_dd(eqb), 4),
            "t_paired": round(t, 2), "mean_daily_diff_bps": round(m * 1e4, 3),
            "days_variant_differs": sum(1 for x in diff if abs(x) > 1e-12)}


def zone(delta: float, z: dict) -> str:
    return "ADOPT" if delta >= z["adopt_min"] else "REJECT" if delta <= z["reject_max"] else "INSUFFICIENT"


# ----------------------------------------------------------------------------- the review
def review() -> dict:
    t0 = time.time()
    variants = {"baseline": {}} | {k: v["params"] for k, v in CANDIDATES.items()} | ABLATIONS
    last_data = ct("cd /opt/trustyrusty && for s in SPY QQQ SOXX XLV XLP HYG FDN; do tail -n1 data/historical/$s.csv | cut -d, -f1; done",
                   timeout=60).split()
    sealed_end = min(last_data)
    windows = {"train": PROTOCOL["train"], "valid": PROTOCOL["valid"], "full": PROTOCOL["full"],
               "sealed": (PROTOCOL["sealed"][0], sealed_end)}

    # every (variant, window) at base cost, plus 2x/5x on train and valid for the candidates
    jobs, index = [], []
    for vname, params in variants.items():
        for wname, (s, e) in windows.items():
            jobs.append({"start": s, "end": e, "params": params}); index.append((vname, wname, 1.0))
        if vname in CANDIDATES:
            for wname in ("train", "valid"):
                for mult in (2.0, 5.0):
                    s, e = windows[wname]
                    jobs.append({"start": s, "end": e, "params": params, "mult": mult})
                    index.append((vname, wname, mult))
    # baseline at stressed costs too (a delta needs both sides at the same cost)
    for wname in ("train", "valid"):
        for mult in (2.0, 5.0):
            s, e = windows[wname]
            jobs.append({"start": s, "end": e, "params": {}, "mult": mult}); index.append(("baseline", wname, mult))
    print(f"running {len(jobs)} backtests on CT {CT} ...", flush=True)
    res = run_many(jobs)
    R = {}
    for (vname, wname, mult), r in zip(index, res):
        if r.get("error"):
            raise RuntimeError(f"{vname}/{wname}/x{mult}: {r['error']}")
        R[(vname, wname, mult)] = r

    def met(v, w, mult=1.0):
        m = R[(v, w, mult)]["metrics"] or {}
        return {"sortino": m.get("sortino_ratio"), "dd": m.get("max_drawdown"), "cagr": m.get("cagr"),
                "trades": m.get("total_trades")}

    out = {"engine": f"TrustyRustyEngine CT {CT} (production)", "strategy": STRATEGY,
           "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "windows": windows, "protocol": PROTOCOL, "sealed_data_through": sealed_end,
           "baseline": {w: met("baseline", w) for w in windows}, "candidates": {}}

    full_eq = {v: daily(R[(v, "full", 1.0)]["curve"]) for v in variants}
    full_ret = {v: returns(full_eq[v]) for v in variants}
    full_eqd = {v: dict(full_eq[v]) for v in variants}
    seal_eq = {v: daily(R[(v, "sealed", 1.0)]["curve"]) for v in variants}
    seal_ret = {v: returns(seal_eq[v]) for v in variants}
    seal_eqd = {v: dict(seal_eq[v]) for v in variants}

    for vname, params in variants.items():
        if vname == "baseline":
            continue
        spec = CANDIDATES.get(vname, {"objective": "sortino_ratio", "params": params, "what": "ablation"})
        obj = spec["objective"]
        z = PROTOCOL["sortino"] if obj == "sortino_ratio" else PROTOCOL["max_drawdown"]
        c = {"what": spec["what"], "params": params, "objective": obj, "windows": {}, "cost_stress": {},
             "per_year": {}, "drop_one_year": {}, "paired": {}}
        for w in windows:
            b, v = met("baseline", w), met(vname, w)
            d_sort = round(v["sortino"] - b["sortino"], 4)
            dd_delta = round(v["dd"] - b["dd"], 4)
            odelta = d_sort if obj == "sortino_ratio" else round(b["dd"] - v["dd"], 4)
            c["windows"][w] = {"baseline": b, "variant": v, "delta_objective": odelta, "d_sortino": d_sort,
                               "dd_delta": dd_delta, "d_cagr": round((v["cagr"] or 0) - (b["cagr"] or 0), 4),
                               "d_trades": (v["trades"] or 0) - (b["trades"] or 0), "zone": zone(odelta, z)}
        for w in ("train", "valid") if vname in CANDIDATES else ():
            for mult in (2.0, 5.0):
                b, v = met("baseline", w, mult), met(vname, w, mult)
                d_sort = round(v["sortino"] - b["sortino"], 4)
                odelta = d_sort if obj == "sortino_ratio" else round(b["dd"] - v["dd"], 4)
                c["cost_stress"][f"{w}_x{int(mult)}"] = {"delta_objective": odelta, "d_sortino": d_sort,
                                                        "dd_delta": round(v["dd"] - b["dd"], 4)}
        # per year from the full-history runs
        rb, rv = full_ret["baseline"], full_ret[vname]
        years = sorted({d.year for d in rb} & {d.year for d in rv})
        for y in years:
            c["per_year"][str(y)] = window_stats(rb, rv, full_eqd["baseline"], full_eqd[vname],
                                                 datetime.date(y, 1, 1), datetime.date(y, 12, 31))
        c["paired"]["full"] = window_stats(rb, rv, full_eqd["baseline"], full_eqd[vname],
                                           datetime.date(2000, 1, 1), datetime.date(2099, 1, 1))
        c["paired"]["sealed"] = window_stats(seal_ret["baseline"], seal_ret[vname], seal_eqd["baseline"],
                                             seal_eqd[vname], datetime.date(2000, 1, 1), datetime.date(2099, 1, 1))
        # drop one year: Sortino delta over the full window with that year removed
        for y in years:
            keep_b = {d: r for d, r in rb.items() if d.year != y}
            keep_v = {d: r for d, r in rv.items() if d.year != y}
            days = sorted(set(keep_b) & set(keep_v))
            yrs = max((days[-1] - days[0]).days, 1) / 365.25
            c["drop_one_year"][str(y)] = round(sortino([keep_v[d] for d in days], yrs)
                                               - sortino([keep_b[d] for d in days], yrs), 4)
        # summary judgements, all from the numbers above
        tw, vw, sw = c["windows"]["train"], c["windows"]["valid"], c["windows"]["sealed"]
        cs = c["cost_stress"]
        obj_sign_ok = all(x["delta_objective"] > 0 for x in cs.values())
        d1 = c["drop_one_year"]
        c["summary"] = {
            "lab_zones": {"train": tw["zone"], "valid": vw["zone"]},
            "both_windows_adopt": tw["zone"] == "ADOPT" and vw["zone"] == "ADOPT",
            "constraint_ok": (all(x["dd_delta"] <= z.get("dd_worse_max", 9) for x in (tw, vw)) if obj == "sortino_ratio"
                              else all(x["d_sortino"] > z["sortino_guard"] for x in (tw, vw))),
            "cost_sign_stable": obj_sign_ok,
            "sealed_delta_objective": sw["delta_objective"], "sealed_zone": sw["zone"],
            "sealed_d_sortino": sw["d_sortino"], "sealed_dd_delta": sw["dd_delta"], "sealed_d_cagr": sw["d_cagr"],
            "full_d_cagr": c["windows"]["full"]["d_cagr"], "full_d_sortino": c["windows"]["full"]["d_sortino"],
            "full_dd_delta": c["windows"]["full"]["dd_delta"],
            "paired_t_full": c["paired"]["full"].get("t_paired"),
            "paired_t_sealed": c["paired"]["sealed"].get("t_paired"),
            "years_sortino_improved": sum(1 for y in c["per_year"].values() if y.get("d_sortino", 0) > 0),
            "years_total": len(c["per_year"]),
            "drop_one_year_min": min(d1.values()) if d1 else None,
            "drop_one_year_max": max(d1.values()) if d1 else None,
            "drop_one_year_sign_stable": all(v > 0 for v in d1.values()) if d1 else None,
        }
        out["candidates"][vname] = c
    out["elapsed_s"] = round(time.time() - t0, 1)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"adoption_review_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    out["path"] = path
    return out


def report(out: dict) -> str:
    L = [f"ADOPTION REVIEW - {out['strategy']} on {out['engine']}  ({out['elapsed_s']}s)",
         f"sealed window data through {out['sealed_data_through']}", ""]
    f = lambda x: "  —  " if x is None else f"{x:+.4f}"                       # noqa: E731
    for name, c in out["candidates"].items():
        s = c["summary"]
        L.append(f"=== {name}: {c['what']}   params {c['params']}   objective {c['objective']}")
        L.append(f"{'window':8} {'Δobj':>8} {'ΔSortino':>9} {'ΔmaxDD':>8} {'ΔCAGR':>8} {'Δtrades':>8}  zone")
        for w, x in c["windows"].items():
            L.append(f"{w:8} {f(x['delta_objective']):>8} {f(x['d_sortino']):>9} {f(x['dd_delta']):>8} "
                     f"{f(x['d_cagr']):>8} {x['d_trades']:>8}  {x['zone']}")
        L.append("cost stress (Δobj): " + "  ".join(f"{k} {f(v['delta_objective'])}" for k, v in c["cost_stress"].items()))
        L.append("per year ΔSortino:  " + "  ".join(f"{y} {f(v.get('d_sortino'))}" for y, v in c["per_year"].items()))
        L.append("per year Δreturn:   " + "  ".join(f"{y} {f(v.get('d_ret'))}" for y, v in c["per_year"].items()))
        L.append(f"drop-one-year ΔSortino range: {f(s['drop_one_year_min'])} .. {f(s['drop_one_year_max'])}"
                 f"  sign stable: {s['drop_one_year_sign_stable']}")
        L.append(f"paired t (variant-baseline daily): full {s['paired_t_full']}  sealed {s['paired_t_sealed']}"
                 f"   days the variant differs: full {c['paired']['full'].get('days_variant_differs')}"
                 f" sealed {c['paired']['sealed'].get('days_variant_differs')}")
        L.append(f"years Sortino improved: {s['years_sortino_improved']}/{s['years_total']}")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    o = review()
    print(report(o))
    print("saved", o["path"])

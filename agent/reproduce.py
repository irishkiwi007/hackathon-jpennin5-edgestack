"""Reproduce an adoption dossier: did the change deliver what was predicted?

Every number the lab wrote into a dossier came from ONE engine, the research
container's Rust backtester, run over the protocol's train and valid windows
at the protocol's costs. This tool re-runs exactly that - baseline and variant,
both windows, same engine, same protocol - and lays three columns side by side:

    predicted   what the agent pre-registered before any run
    lab         what the lab's verdict recorded
    reproduced  what the engine says now

then answers two questions with the protocol's own thresholds, no judgement
involved:

  1. Does the verdict REPRODUCE?  every reproduced delta within the protocol's
     measured noise floor of the lab's delta.
  2. Did the change deliver the PREDICTION?  direction per window, error per
     window, and the verdict zone the reproduced deltas fall in, re-derived
     with the protocol's zones and constraints.

Deterministic by construction: the hypothesis comes from the journal's
pre-registration and verdict events (structured JSON, not the markdown); the
windows, costs, capital, zones and noise floor come from the protocol file in
the container; the engine is reached over ssh exactly as the root audit tools
reach it. The sealed holdout is refused here as everywhere: a window that
touches it is never run.

    python agent/reproduce.py H-E003.3
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LAB_REPORTS = os.environ.get("EDGESTACK_LAB_REPORTS",
                             r"C:\Users\Lenovo\edgestack-deploy\lab-journal\reports")
LAB_EVENTS = os.path.join(os.path.dirname(LAB_REPORTS), "events.jsonl")
OUT = os.path.join(ROOT, "journal", "reproductions")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", os.environ.get("EDGESTACK_PVE", "pve")]
CT = os.environ.get("EDGESTACK_LAB_CT", "203")
ENGINE_URL = "http://127.0.0.1:3000/api/python-strategies/backtest"
PROTOCOL_PATH = "/opt/agent-lab/protocol/protocol_v1.toml"

_lock = threading.Lock()
_running: set[str] = set()
_proto_cache: tuple[float, dict] | None = None


# ----------------------------------------------------------------------------- the container
def ct(cmd: str, timeout: int = 900) -> str:
    """Run one shell command as root inside the lab container, exactly the way the
    root audit tools are driven; returns stdout."""
    r = subprocess.run(SSH + [f"pct exec {CT} -- bash -c {shlex.quote(cmd)}"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"container command failed (rc={r.returncode}): {(r.stderr or r.stdout)[-300:]}")
    return r.stdout


def protocol() -> dict:
    """The lab's protocol, fetched from the container and cached for ten minutes."""
    global _proto_cache
    if _proto_cache and time.time() - _proto_cache[0] < 600:
        return _proto_cache[1]
    p = tomllib.loads(ct(f"cat {PROTOCOL_PATH}", timeout=60))
    _proto_cache = (time.time(), p)
    return p


def engine_backtest(filename: str, start: str, end: str, params: dict,
                    slip: float, comm: float, capital: float) -> dict:
    body = {"filename": filename, "start_date": start, "end_date": end,
            "initial_capital": capital, "slippage_bps": slip, "commission_bps": comm,
            "params": params}
    out = ct(f"curl -s -m 800 -X POST {ENGINE_URL} -H 'Content-Type: application/json' "
             f"-d {shlex.quote(json.dumps(body))}")
    try:
        res = json.loads(out or "{}")
    except ValueError:
        raise RuntimeError(f"engine returned no JSON: {out[-200:]}")
    if res.get("error"):
        raise RuntimeError(f"engine error: {str(res['error'])[:300]}")
    m = res.get("metrics") or {}
    if m.get("sortino_ratio") is None:
        raise RuntimeError("engine returned no sortino_ratio")
    return {"sortino": float(m["sortino_ratio"]), "dd": float(m.get("max_drawdown") or 0),
            "cagr": m.get("cagr"), "trades": m.get("total_trades")}


# ----------------------------------------------------------------------------- the journal
def events():
    with open(LAB_EVENTS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def servable(filename: str | None) -> bool:
    """A dossier may be shown only if its strategy is one THIS instance holds.
    The journal mirror on the host carries every dossier, including those of
    the operator's private strategies; the public instance's strategy set is
    the allowlisted copy, so this is the same privacy line the Backtest tab
    already draws (2026-09-02)."""
    import backtests
    try:
        backtests.strategy_path(str(filename or ""))
        return True
    except (ValueError, FileNotFoundError):
        return False


def hypothesis(hid: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", hid or ""):
        raise ValueError("bad hypothesis id")
    pre = ver = None
    for e in events():
        if e.get("id") != hid:
            continue
        if e.get("type") == "prereg":
            pre = e
        elif e.get("type") == "verdict":
            ver = e
    if not pre or not servable(pre.get("filename")):
        raise KeyError(f"no pre-registration for {hid} in this instance's journal view")
    return {"prereg": pre, "verdict": ver}


def dossiers() -> list[dict]:
    """Every dossier in the mirror with the structured facts beside it."""
    verdicts, pre = {}, {}
    for e in events():
        if e.get("type") == "verdict":
            verdicts[e.get("id")] = e
        elif e.get("type") == "prereg":
            pre[e.get("id")] = e
    out = []
    try:
        names = sorted(os.listdir(LAB_REPORTS))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".md"):
            continue
        hid = n[:-3]
        v, p = verdicts.get(hid, {}), pre.get(hid, {})
        if not servable(p.get("filename")):
            continue
        rep = latest(hid)
        out.append({"id": hid, "strategy": p.get("filename"), "family": v.get("family_root") or p.get("family_root"),
                    "objective": v.get("objective") or p.get("objective"), "verdict": v.get("verdict"),
                    "delta": v.get("delta"), "predicted": p.get("predicted"),
                    "reproduction": {k: rep.get(k) for k in ("status", "finished", "reproduces", "prediction_held")}
                    if rep else None})
    return out


def markdown(hid: str) -> str:
    hypothesis(hid)                        # raises KeyError unless servable here
    with open(os.path.join(LAB_REPORTS, f"{hid}.md"), encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ----------------------------------------------------------------------------- the comparison
def zone_of(delta: float, z: dict) -> str:
    if delta >= z["adopt_min"]:
        return "ADOPT"
    if delta <= z["reject_max"]:
        return "REJECT"
    return "INSUFFICIENT"


def _path(hid: str) -> str:
    return os.path.join(OUT, f"{hid}.json")


def latest(hid: str) -> dict | None:
    try:
        with open(_path(hid), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _save(rec: dict) -> None:
    os.makedirs(OUT, exist_ok=True)
    tmp = _path(rec["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    os.replace(tmp, _path(rec["id"]))


def reproduce(hid: str, who: str = "operator") -> dict:
    """Run it. Blocks for the four engine runs; see start() for the threaded form."""
    h = hypothesis(hid)
    pre, ver = h["prereg"], h["verdict"] or {}
    proto = protocol()
    fn = pre["filename"]
    bp = dict(pre.get("base_params") or {})
    vp = {**bp, **(pre.get("variant_params") or {})}
    wsrc = (proto.get("family_windows", {}).get(pre.get("windows_family"))
            if pre.get("windows_family") else None) or proto["windows"]
    W = {"train": tuple(wsrc["train"]), "valid": tuple(wsrc["valid"])}
    holdout = proto["windows"].get("holdout")
    if holdout:
        for w, (s, e) in W.items():
            if e >= holdout[0]:
                raise RuntimeError(f"{w} window {s}..{e} touches the sealed holdout {holdout[0]}+; refused")
    objective = pre.get("objective") or ver.get("objective") or "sortino_ratio"
    if objective == "max_drawdown":
        oz = proto["objectives"]["max_drawdown"]
        zones = {"adopt_min": oz["adopt_min"], "reject_max": oz["reject_max"]}

        def odelta(b, v):
            return round(b["dd"] - v["dd"], 4)
    else:
        oz = None
        zones = proto["verdict_zones"]

        def odelta(b, v):
            return round(v["sortino"] - b["sortino"], 4)
    costs = proto.get("costs") or {}
    slip = float(costs.get("slippage_bps", 5.0))
    comm = float(costs.get("commission_bps", 5.0))
    # protocol [strategy_capital]: a candidate inherits its baseline's capital
    # (agentctl._capital_for, FIX-009), anything unlisted uses default.
    sc = proto.get("strategy_capital") or {}
    root_fn = re.sub(r"_c\d+\.py$", ".py", fn)
    capital = float(sc.get(fn) or sc.get(root_fn) or sc.get("default")
                    or costs.get("initial_capital", 100_000.0))
    noise = float(proto["metrics"].get("noise_floor_sortino", 0.01))
    min_eff = float(proto["metrics"].get("min_effect_sortino", 0.02))

    runs, rows = {}, {}
    for w, (s, e) in W.items():
        b = engine_backtest(fn, s, e, bp, slip, comm, capital)
        v = engine_backtest(fn, s, e, vp, slip, comm, capital)
        runs[w] = {"baseline": b, "variant": v, "window": [s, e]}
        rows[w] = {"delta": odelta(b, v),
                   "d_sortino": round(v["sortino"] - b["sortino"], 4),
                   "dd_delta": round(v["dd"] - b["dd"], 4)}

    # 1. reproduction: every recorded delta within the noise floor
    diffs = {}
    for w in W:
        for k in ("delta", "d_sortino", "dd_delta"):
            lab = (ver.get(k) or {}).get(w) if ver else None
            if isinstance(lab, (int, float)):
                diffs[f"{w}.{k}"] = round(rows[w][k] - lab, 4)
    reproduces = bool(diffs) and all(abs(d) <= noise for d in diffs.values())

    # 2. prediction: direction and error per window, then the protocol's verdict
    pred = pre.get("predicted") or {}
    prediction = {}
    for w in W:
        p = pred.get(w)
        r = rows[w]["delta"]
        if isinstance(p, (int, float)):
            both_null = abs(p) < min_eff and abs(r) < min_eff
            prediction[w] = {"predicted": p, "reproduced": r, "error": round(r - p, 4),
                             "direction_held": both_null or ((p >= 0) == (r >= 0)),
                             "within_effect_floor": abs(r - p) <= min_eff}
    zone = {w: zone_of(rows[w]["delta"], zones) for w in W}
    zt = zone["train"] if zone["train"] == zone["valid"] else "INSUFFICIENT"
    if objective == "max_drawdown":
        guard_bust = any(rows[w]["d_sortino"] <= oz["sortino_guard"] for w in W)
        constraint = "REJECT_SORTINO_CONSTRAINT"
    else:
        guard_bust = any(rows[w]["dd_delta"] > proto["verdict_zones"]["dd_worse_max"] for w in W)
        constraint = "REJECT_DD_CONSTRAINT"
    if zt == "ADOPT":
        rederived = constraint if guard_bust else "ADOPT_CANDIDATE"
    elif zt == "REJECT":
        rederived = "REJECT"
    else:
        rederived = "INSUFFICIENT_EVIDENCE"
    held = bool(prediction) and all(x["direction_held"] for x in prediction.values())

    # 3. plain words, derived from the numbers above and nothing else
    parts = []
    if not ver:
        parts.append("The lab has recorded no verdict for this hypothesis yet.")
    elif reproduces:
        parts.append(f"The lab's verdict reproduces: every recorded delta is within the protocol's "
                     f"noise floor ({noise}) of what the engine says now.")
    else:
        worst = max(diffs.items(), key=lambda kv: abs(kv[1]))
        parts.append(f"The lab's verdict does NOT reproduce: {worst[0]} differs by {worst[1]:+.4f} "
                     f"(noise floor {noise}). Data or code has changed since the verdict.")
    if prediction:
        for w, x in prediction.items():
            parts.append(f"{w}: predicted {x['predicted']:+.4f}, delivered {x['reproduced']:+.4f} "
                         f"({'direction held' if x['direction_held'] else 'DIRECTION WRONG'}, "
                         f"error {x['error']:+.4f}).")
        parts.append("The change delivered the predicted direction in both windows."
                     if held else "The change did not deliver the predicted direction in every window.")
    parts.append(f"Re-derived under the protocol: {rederived}"
                 + (f" (lab recorded {ver.get('verdict')})." if ver else "."))

    rec = {"id": hid, "strategy": fn, "objective": objective, "windows": W,
           "windows_family": pre.get("windows_family"), "costs": {"slippage_bps": slip, "commission_bps": comm,
                                                                  "capital": capital},
           "base_params": bp, "variant_params": pre.get("variant_params") or {},
           "runs": runs, "reproduced": rows,
           "lab": {k: ver.get(k) for k in ("verdict", "delta", "d_sortino", "dd_delta", "zones")} if ver else None,
           "predicted": pred, "diffs": diffs, "noise_floor": noise, "min_effect": min_eff,
           "reproduces": reproduces if ver else None, "prediction": prediction,
           "prediction_held": held if prediction else None, "zones_now": zone,
           "verdict_rederived": rederived, "conclusion": " ".join(parts),
           "status": "done", "by": who, "engine": f"lab container {CT} :3000",
           "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    _save(rec)
    try:                                   # the lab's own record of the check, non-fatal
        ev = {"type": "reproduction", "id": hid, "by": who, "reproduces": rec["reproduces"],
              "prediction_held": rec["prediction_held"], "verdict_rederived": rederived,
              "note": "operator re-ran baseline vs variant on both windows from the dashboard"}
        ct("python3 -c " + shlex.quote(
            "import sys,json; sys.path.insert(0,'/opt/agent-lab/bin'); import agentctl; "
            f"agentctl.journal(json.loads({json.dumps(json.dumps(ev))}))"), timeout=60)
    except Exception:                                      # noqa: BLE001
        pass
    return rec


def start(hid: str, who: str = "operator") -> dict:
    """Threaded: returns the placeholder record immediately; poll latest(hid)."""
    hypothesis(hid)                                        # validates before we promise anything
    with _lock:
        if hid in _running:
            raise RuntimeError("a reproduction of this dossier is already running")
        _running.add(hid)
    _save({"id": hid, "status": "running", "by": who,
           "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})

    def work():
        try:
            reproduce(hid, who)
        except Exception as exc:                           # noqa: BLE001
            _save({"id": hid, "status": "error", "error": str(exc)[:600], "by": who,
                   "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
        finally:
            with _lock:
                _running.discard(hid)

    threading.Thread(target=work, name=f"repro-{hid}", daemon=True).start()
    return latest(hid)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        for d in dossiers():
            print(f"{d['id']:12} {str(d['strategy']):26} {str(d['verdict']):22} "
                  f"delta {d['delta']}  predicted {d['predicted']}")
        raise SystemExit(0)
    r = reproduce(sys.argv[1], who="cli")
    print(json.dumps({k: r[k] for k in ("reproduced", "lab", "predicted", "diffs", "reproduces",
                                        "prediction_held", "verdict_rederived", "conclusion")}, indent=1))

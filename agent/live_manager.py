"""Live Manager — deploy a strategy module against an account slice, with a kill switch.

A port of the TrustyRustyEngine Live Manager (crates/api/src/live_manager) onto EdgeStack's
Python stack, driving orders through the same Alpaca MCP route the competition agent uses
(agent/broker.py). Same model, same words:

  account profile   a named Alpaca (paper) account; keys resolved from env-var NAMES, so the
                    registry never holds a secret. "competition" is PA3ZCDDOPR2N from .env.
  deployment        a PINNED copy of a strategy module (edits to the source never reach a
                    running deployment) attached to an account at `alloc_pct` of its equity,
                    or run as a SHADOW (virtual ledger, never traded).
  rule              max_drawdown_kill {threshold_pct, resolution}: trips when the model NAV is
                    `threshold_pct` below its since-launch high-water mark, checked at the
                    close of each bar of the chosen resolution. The HWM only advances on
                    observations at that resolution: with daily bars an intraday spike
                    neither raises the mark nor trips it.
  kill              flatten every model position (live) / freeze (shadow) and mark the
                    deployment Killed. Terminal; re-arming is a relaunch.
  global kill       a flag file; while it exists NO order leaves this process, rescues included.

Execution mirrors the backtest runner's fill model: the strategy is run after the close (by
the SAME engine/run_backtest.py that backtests it) to get target weights, and the rebalance
executes at the next open (09:35 ET). Weights x (equity x alloc_pct) -> whole shares ->
market orders via MCP. A deployment flattens only the positions it put on itself.

    python agent/live_manager.py            # the loop (supervised: host/run.py live)
    python agent/live_manager.py --status   # print state
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
ENGINE = os.path.join(ROOT, "engine")
STRATS = os.path.join(ENGINE, "strategies")
DATA = os.path.join(ENGINE, "data")
RUNNER = os.path.join(ENGINE, "run_backtest.py")
STATE = os.path.join(ROOT, "journal", "live_manager")
ACCOUNTS = os.path.join(STATE, "accounts.json")
DEPLOYMENTS = os.path.join(STATE, "deployments.json")
MODULES = os.path.join(STATE, "modules")
JOURNAL = os.path.join(STATE, "journal.jsonl")
KILL_FLAG = os.path.join(STATE, "kill_switch")
LOCK = os.path.join(STATE, ".lock")
TICK_SECS = 60
EXEC_AFTER_ET = datetime.time(9, 35)          # "next open": after the opening auction
MODEL_RUN_AFTER_ET = datetime.time(16, 15)    # after the close, once per session
MODEL_HISTORY_DAYS = 900                      # enough to warm any lookback (504 max seen)
RES_ORDER = {"minute": 0, "hourly": 1, "daily": 2}
COMPETITION_ACCOUNT = "competition"


def now_et() -> datetime.datetime:
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/New_York"))


def utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- persistence
class _Locked:
    """Cross-process file lock (dashboard writes, manager loop reads/writes)."""

    def __enter__(self):
        os.makedirs(STATE, exist_ok=True)
        deadline = time.time() + 20
        while True:
            try:
                self.fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(LOCK) > 60:
                        os.remove(LOCK)                   # stale: holder died
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError("live manager state lock held too long")
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            os.close(self.fd)
            os.remove(LOCK)
        except OSError:
            pass


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(path, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)
    os.replace(tmp, path)


def journal(event: dict) -> None:
    event = {"ts": utc_iso(), **event}
    os.makedirs(STATE, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def journal_tail(n: int = 40) -> list[dict]:
    out = []
    try:
        with open(JOURNAL, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out[-n:]


def load_deployments() -> list[dict]:
    return _read(DEPLOYMENTS, [])


def save_deployments(deps: list[dict]) -> None:
    _write(DEPLOYMENTS, deps)


# ----------------------------------------------------------------------------- accounts
def load_accounts() -> list[dict]:
    """The registry never holds a secret: profiles name the env vars that do."""
    accts = _read(ACCOUNTS, None)
    if accts is None:
        accts = [{"id": COMPETITION_ACCOUNT, "label": "Competition paper (PA3ZCDDOPR2N)",
                  "key_env": "ALPACA_API_KEY", "secret_env": "ALPACA_SECRET_KEY",
                  "base_url": "https://paper-api.alpaca.markets",
                  "note": "the judged account: the EdgeStack agent trades here; a deployment on "
                          "it changes the P&L judges pull"}]
        _write(ACCOUNTS, accts)
    return accts


def account(acct_id: str) -> dict | None:
    return next((a for a in load_accounts() if a.get("id") == acct_id), None)


def account_public(a: dict) -> dict:
    key = os.environ.get(a.get("key_env", ""), "")
    sec = os.environ.get(a.get("secret_env", ""), "")
    return {"id": a["id"], "label": a.get("label", a["id"]), "base_url": a.get("base_url"),
            "is_paper": "paper-api" in str(a.get("base_url", "")),
            "is_competition": a["id"] == COMPETITION_ACCOUNT,
            "credentials_ok": bool(key and sec), "key_hint": key[:4] if key else a.get("key_env"),
            "note": a.get("note", "")}


def upsert_account(acct: dict) -> dict:
    aid = str(acct.get("id", "")).strip()
    if not aid or not aid.replace("_", "").replace("-", "").isalnum():
        raise ValueError("account id must be alphanumeric")
    if aid == COMPETITION_ACCOUNT:
        raise ValueError("the competition profile is fixed")
    row = {"id": aid, "label": str(acct.get("label") or aid)[:60],
           "key_env": str(acct.get("key_env") or "")[:80],
           "secret_env": str(acct.get("secret_env") or "")[:80],
           "base_url": "https://paper-api.alpaca.markets"}     # paper only, by construction
    if not row["key_env"] or not row["secret_env"]:
        raise ValueError("give the NAMES of the env vars holding the key and secret")
    with _Locked():
        accts = [a for a in load_accounts() if a["id"] != aid] + [row]
        _write(ACCOUNTS, accts)
    journal({"type": "account_upserted", "id": aid})
    return account_public(row)


def broker_for(acct_id: str):
    from broker import Alpaca, load_env
    load_env(os.path.join(ROOT, ".env"))
    a = account(acct_id)
    if not a:
        raise ValueError(f"no account profile {acct_id!r}")
    key, sec = os.environ.get(a["key_env"], ""), os.environ.get(a["secret_env"], "")
    if not key or not sec:
        raise ValueError(f"account {acct_id}: env vars {a['key_env']}/{a['secret_env']} unset")
    return Alpaca(key, sec)


# ----------------------------------------------------------------------------- rules (pure)
def evaluate_rule(rule: dict | None, hwm: float, nav: float, observed: str) -> tuple[float, dict]:
    """One max_drawdown_kill rule against one observation.

    `observed` is the resolution of the bar that just closed ('minute', 'hourly',
    'daily'). A daily close concludes the day's hourly and minute bars too, so a rule
    observes any close at or above its own resolution, and only those: the HWM neither
    advances nor trips on finer bars. Returns (new_hwm, decision) where decision is
    {"kill": bool, "reason": str, "dd_pct": float}."""
    if not rule or rule.get("kind") != "max_drawdown_kill":
        return hwm, {"kill": False, "reason": "", "dd_pct": 0.0}
    res = rule.get("resolution", "daily")
    if RES_ORDER.get(observed, 2) < RES_ORDER.get(res, 2):
        return hwm, {"kill": False, "reason": "bar below rule resolution", "dd_pct": 0.0}
    if nav <= 0:
        return hwm, {"kill": False, "reason": "nav not priceable", "dd_pct": 0.0}
    if nav > hwm:
        hwm = nav
    dd = (hwm - nav) / hwm * 100.0 if hwm > 0 else 0.0
    thr = float(rule.get("threshold_pct") or 0)
    if thr > 0 and dd >= thr:
        return hwm, {"kill": True, "dd_pct": round(dd, 3),
                     "reason": (f"max-drawdown kill ({res} bars): NAV {nav:,.2f} is {dd:.2f}% "
                                f"below the high-water mark {hwm:,.2f} >= threshold {thr:.2f}%")}
    return hwm, {"kill": False, "reason": "", "dd_pct": round(dd, 3)}


def size_targets(weights: dict, capital: float, prices: dict) -> dict:
    """Whole-share targets for a capital slice. Weights outside [0, 1] are clamped; a
    symbol without a price gets no target (and is left alone)."""
    out = {}
    for sym, w in (weights or {}).items():
        px = float(prices.get(sym) or 0)
        if px <= 0:
            continue
        w = min(1.0, max(0.0, float(w)))
        out[sym] = int(math.floor(capital * w / px))
    return out


def order_deltas(targets: dict, positions: dict) -> list[tuple[str, int]]:
    """(symbol, signed qty) to move model positions to targets; symbols dropped from the
    target set are sold in full."""
    out = []
    for sym, tq in targets.items():
        d = int(tq) - int(positions.get(sym, 0))
        if d:
            out.append((sym, d))
    for sym, q in positions.items():
        if sym not in targets and int(q):
            out.append((sym, -int(q)))
    return out


# ----------------------------------------------------------------------------- deployments API
def _module_hash(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def kill_switch_armed() -> bool:
    return os.path.exists(KILL_FLAG)


def set_kill_switch(armed: bool, who: str = "operator") -> None:
    os.makedirs(STATE, exist_ok=True)
    if armed:
        with open(KILL_FLAG, "w", encoding="utf-8") as fh:
            fh.write(f"{utc_iso()} {who}\n")
    else:
        try:
            os.remove(KILL_FLAG)
        except OSError:
            pass
    journal({"type": "kill_switch", "armed": armed, "by": who})


def deploy(req: dict, who: str = "operator") -> dict:
    """Pin the module and create the deployment. Nothing trades until the loop's next tick
    (immediately if the market is open, else at the next open)."""
    import backtests
    stem = str(req.get("stem") or "")
    src = backtests.strategy_path(stem)
    info = backtests.inspect(stem)
    if info.get("error"):
        raise ValueError(f"strategy does not inspect: {info['error'][:200]}")
    mode = "shadow" if str(req.get("mode", "shadow")) != "live" else "live"
    alloc = float(req.get("alloc_pct") or 0)
    if mode == "live":
        acct = account(str(req.get("account_id") or ""))
        if not acct:
            raise ValueError("live deployment needs an account profile")
        if not (0 < alloc <= 100):
            raise ValueError("alloc_pct must be in (0, 100]")
        if acct["id"] == COMPETITION_ACCOUNT and not req.get("confirm_competition"):
            raise ValueError("deploying on the competition account changes the judged P&L: "
                             "tick the confirmation to proceed")
        others = sum(float(d.get("alloc_pct") or 0) for d in load_deployments()
                     if d.get("mode") == "live" and d.get("account_id") == acct["id"]
                     and d.get("status", {}).get("state") == "active")
        if others + alloc > 100 and not req.get("force"):
            raise ValueError(f"account already has {others:.0f}% allocated; "
                             f"{others + alloc:.0f}% would exceed 100% (force to override)")
        account_id = acct["id"]
    else:
        account_id, alloc = None, 0.0
    rule = None
    r = req.get("rule") or {}
    if r and float(r.get("threshold_pct") or 0) > 0:
        res = str(r.get("resolution", "daily"))
        if res not in RES_ORDER:
            raise ValueError("resolution must be minute, hourly or daily")
        rule = {"kind": "max_drawdown_kill", "threshold_pct": float(r["threshold_pct"]),
                "resolution": res}
    params = {}
    for k, v in (req.get("params") or {}).items():
        if k in (info.get("params") or {}) and isinstance(v, (int, float, str)):
            params[k] = v
    dep_id = uuid.uuid4().hex[:12]
    mdir = os.path.join(MODULES, dep_id)
    os.makedirs(mdir, exist_ok=True)
    pinned = os.path.join(mdir, stem)
    shutil.copyfile(src, pinned)
    dep = {"id": dep_id, "stem": stem, "display_name": str(req.get("display_name") or stem[:-3])[:60],
           "mode": mode, "account_id": account_id, "alloc_pct": alloc,
           "shadow_capital": float(req.get("shadow_capital") or 2_500.0) if mode == "shadow" else None,
           "params": params, "rule": rule, "module_hash": _module_hash(pinned),
           "universe": info.get("symbols") or [], "launched_at": utc_iso(), "by": who,
           "status": {"state": "active"}, "positions": {}, "model_cash": None,
           "capital_basis": None, "hwm": 0.0, "last_nav": None, "nav_series": [],
           "pending_targets": None, "pending_flatten": False, "needs_model_run": True,
           "last_model_run": None, "signals": {}, "fills": 0, "orders": [],
           "last_error": None, "rule_alert": None, "hour_mark": None}
    with _Locked():
        deps = load_deployments()
        deps.append(dep)
        save_deployments(deps)
    journal({"type": "deployed", "id": dep_id, "stem": stem, "mode": mode,
             "account_id": account_id, "alloc_pct": alloc, "rule": rule, "params": params,
             "module_hash": dep["module_hash"][:16], "by": who})
    return public(dep)


def _mutate(dep_id: str, fn) -> dict:
    with _Locked():
        deps = load_deployments()
        dep = next((d for d in deps if d["id"] == dep_id), None)
        if not dep:
            raise KeyError(dep_id)
        fn(dep)
        save_deployments(deps)
        return dep


def stop(dep_id: str, who: str = "operator") -> dict:
    """Stop: flatten at the next opportunity, then stay stopped."""
    def fn(d):
        if d["status"].get("state") == "active":
            d["status"] = {"state": "stopped", "at": utc_iso(), "by": who}
            d["pending_targets"] = None
            d["pending_flatten"] = bool(d.get("positions"))
    dep = _mutate(dep_id, fn)
    journal({"type": "stopped", "id": dep_id, "by": who, "flatten_pending": dep["pending_flatten"]})
    return public(dep)


def set_rule(dep_id: str, rule: dict | None, who: str = "operator") -> dict:
    new = None
    if rule and float(rule.get("threshold_pct") or 0) > 0:
        res = str(rule.get("resolution", "daily"))
        if res not in RES_ORDER:
            raise ValueError("bad resolution")
        new = {"kind": "max_drawdown_kill", "threshold_pct": float(rule["threshold_pct"]),
               "resolution": res}

    def fn(d):
        d["rule"] = new
    dep = _mutate(dep_id, fn)
    journal({"type": "rule_set", "id": dep_id, "rule": new, "by": who})
    return public(dep)


def purge(dep_id: str, who: str = "operator") -> None:
    """Remove a non-active deployment's record (positions must already be flat)."""
    with _Locked():
        deps = load_deployments()
        dep = next((d for d in deps if d["id"] == dep_id), None)
        if not dep:
            raise KeyError(dep_id)
        if dep["status"].get("state") == "active" or dep.get("pending_flatten"):
            raise ValueError("stop it first; purge only a flat, inactive deployment")
        deps = [d for d in deps if d["id"] != dep_id]
        save_deployments(deps)
    shutil.rmtree(os.path.join(MODULES, dep_id), ignore_errors=True)
    journal({"type": "purged", "id": dep_id, "by": who})


def public(d: dict) -> dict:
    """The shape the dashboard shows (no order ids beyond a count)."""
    ser = d.get("nav_series") or []
    return {k: d.get(k) for k in ("id", "stem", "display_name", "mode", "account_id", "alloc_pct",
                                  "shadow_capital", "params", "rule", "module_hash", "universe",
                                  "launched_at", "status", "positions", "hwm", "last_nav",
                                  "pending_targets", "pending_flatten", "last_model_run",
                                  "signals", "fills", "last_error", "rule_alert",
                                  "capital_basis")} | {
        "metrics": metrics_for(d), "nav_points": len(ser), "orders": len(d.get("orders") or []),
        "dd_pct": (round((d["hwm"] - d["last_nav"]) / d["hwm"] * 100, 2)
                   if d.get("hwm") and d.get("last_nav") else None)}


def metrics_for(d: dict) -> dict:
    ser = d.get("nav_series") or []
    if len(ser) < 2 or not d.get("capital_basis"):
        return {}
    try:
        sys.path.insert(0, ENGINE)
        import importlib.util
        spec = importlib.util.spec_from_file_location("_runner_", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                      # type: ignore[union-attr]
        m = mod._compute_metrics([{"date": p["date"], "equity": p["nav"]} for p in ser], [],
                                 float(d["capital_basis"]))
        return {k: m.get(k) for k in ("total_return", "max_drawdown", "sharpe_ratio", "cagr")}
    except Exception:                                      # noqa: BLE001
        return {}


def status() -> dict:
    deps = load_deployments()
    return {"kill_switch": kill_switch_armed(), "deployments": [public(d) for d in deps],
            "accounts": [account_public(a) for a in load_accounts()],
            "loop_alive": _loop_alive(), "journal": journal_tail(30)}


HEARTBEAT = os.path.join(STATE, "heartbeat")


def _loop_alive() -> bool:
    try:
        return time.time() - os.path.getmtime(HEARTBEAT) < 3 * TICK_SECS
    except OSError:
        return False


# ----------------------------------------------------------------------------- market data
def refresh_history(symbols: list[str], api) -> dict:
    """Extend engine/data CSVs through the last completed session from Alpaca SIP (no `end`,
    adjustment=all). Rows keep the CSV's 7-column shape; adj_close = close for the tail.
    Symbols with no Alpaca series (SPYON, the synthetic overnight index) are left as they
    are and reported."""
    report = {}
    for sym in symbols:
        path = os.path.join(DATA, f"{sym}.csv")
        if not os.path.isfile(path):
            report[sym] = "no history file"
            continue
        try:
            with open(path, "rb") as fh:
                fh.seek(0, 2)
                size = fh.tell()
                fh.seek(max(0, size - 300))
                last = fh.read().decode(errors="replace").strip().splitlines()[-1].split(",")[0]
            last_d = datetime.date.fromisoformat(last)
        except Exception:                                  # noqa: BLE001
            report[sym] = "unreadable tail"
            continue
        start = (last_d + datetime.timedelta(days=1)).isoformat()
        if last_d >= now_et().date() - datetime.timedelta(days=1) and now_et().hour < 16:
            report[sym] = f"current ({last})"
            continue
        try:
            bars = api.daily_bars([sym], start).get(sym) or []
        except Exception as exc:                           # noqa: BLE001
            report[sym] = f"fetch failed: {str(exc)[:80]}"
            continue
        rows = []
        for b in bars:
            d = str(b.get("t", ""))[:10]
            if d <= last:
                continue
            rows.append(f"{d},{b['o']},{b['h']},{b['l']},{b['c']},{b['c']},{b.get('v', 0)}")
        if rows:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")
        report[sym] = f"+{len(rows)} rows (through {rows[-1].split(',')[0] if rows else last})"
    return report


def latest_prices(api, symbols: list[str]) -> dict[str, float]:
    return api.latest_prices(symbols) if symbols else {}


def run_model(dep: dict) -> dict:
    """Run the pinned module through the runner up to today; returns the runner's result."""
    pinned = os.path.join(MODULES, dep["id"], dep["stem"])
    today = now_et().date()
    opts = {"start_date": (today - datetime.timedelta(days=MODEL_HISTORY_DAYS)).isoformat(),
            "end_date": today.isoformat(), "initial_capital": 100_000.0,
            "param_overrides": dep.get("params") or {}}
    r = subprocess.run([sys.executable, RUNNER, pinned, DATA, json.dumps(opts)],
                       capture_output=True, text=True, timeout=900, cwd=ENGINE)
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {"error": f"runner produced no JSON: {r.stderr[-300:]}"}


# ----------------------------------------------------------------------------- the loop
class Manager:
    def __init__(self) -> None:
        self._brokers: dict[str, object] = {}
        self._clock: tuple[float, dict] = (0.0, {})

    def broker(self, acct_id: str):
        if acct_id not in self._brokers:
            self._brokers[acct_id] = broker_for(acct_id)
        return self._brokers[acct_id]

    def any_broker(self):
        """A broker for market data (the competition profile's keys)."""
        return self.broker(COMPETITION_ACCOUNT)

    def clock(self) -> dict:
        if time.time() - self._clock[0] > 45:
            try:
                self._clock = (time.time(), self.any_broker().clock())
            except Exception as exc:                       # noqa: BLE001
                journal({"type": "clock_error", "error": str(exc)[:200]})
                self._clock = (time.time(), {"is_open": False})
        return self._clock[1]

    # ---- one tick -----------------------------------------------------------------------
    def tick(self) -> None:
        os.makedirs(STATE, exist_ok=True)
        with open(HEARTBEAT, "w", encoding="utf-8") as fh:
            fh.write(utc_iso())
        deps = load_deployments()
        if not deps:
            return
        et = now_et()
        clk = self.clock()
        is_open = bool(clk.get("is_open"))
        for dep in deps:
            try:
                self._tick_one(dep, et, is_open)
            except Exception as exc:                       # noqa: BLE001
                dep["last_error"] = f"{utc_iso()} {str(exc)[:300]}"
                journal({"type": "tick_error", "id": dep["id"], "error": str(exc)[:300]})
        with _Locked():
            # merge: operator edits (rule, stop) may have landed during the tick
            current = {d["id"]: d for d in load_deployments()}
            merged = []
            for dep in deps:
                cur = current.get(dep["id"])
                if cur is None:
                    continue                               # purged meanwhile
                for k in ("rule", "status", "pending_flatten"):
                    if cur.get(k) != dep.get(k) and k != "pending_flatten":
                        dep[k] = cur[k]
                if cur.get("status", {}).get("state") != "active" and dep["status"].get("state") == "active":
                    dep["status"] = cur["status"]
                    dep["pending_targets"] = None
                    dep["pending_flatten"] = bool(dep.get("positions"))
                merged.append(dep)
            save_deployments(merged)

    def _tick_one(self, dep: dict, et: datetime.datetime, is_open: bool) -> None:
        state = dep["status"].get("state")
        today = et.date().isoformat()

        # 1. model run: at launch, and once after each session's close
        if state == "active" and (dep.get("needs_model_run") or
                                  (et.time() >= MODEL_RUN_AFTER_ET and not is_open
                                   and dep.get("last_model_run") != today and et.weekday() < 5)):
            try:
                rep = refresh_history(dep.get("universe") or [], self.any_broker())
            except Exception as exc:                       # noqa: BLE001
                rep = {"error": str(exc)[:200]}
            res = run_model(dep)
            if res.get("error"):
                dep["last_error"] = f"{utc_iso()} model run: {res['error'][:300]}"
                journal({"type": "model_error", "id": dep["id"], "error": res["error"][:300]})
            else:
                dep["pending_targets"] = res.get("final_weights") or {}
                dep["signals"] = res.get("final_signals") or {}
                dep["last_model_run"] = today
                dep["needs_model_run"] = False
                dep["last_error"] = None
                journal({"type": "model_run", "id": dep["id"], "as_of": res.get("last_bar_date"),
                         "weights": dep["pending_targets"], "data": rep})
            # daily close observation for the rule + NAV history
            if dep.get("positions") or dep.get("model_cash") is not None:
                self._observe(dep, "daily", record_day=today)

        # 2. execution at the open: flatten first, else rebalance to pending targets
        if is_open and et.time() >= EXEC_AFTER_ET:
            if dep.get("pending_flatten"):
                self._flatten(dep, "flatten")
            elif state == "active" and dep.get("pending_targets") is not None:
                self._rebalance(dep)

        # 3. intraday kill checks (hourly / minute rules) while open
        rule = dep.get("rule") or {}
        if is_open and state == "active" and rule.get("resolution") in ("minute", "hourly") \
                and dep.get("positions"):
            observed = "minute"
            if rule["resolution"] == "hourly":
                mark = et.strftime("%Y-%m-%d %H")
                if dep.get("hour_mark") == mark:
                    return
                dep["hour_mark"] = mark
                observed = "hourly"
            self._observe(dep, observed)

    # ---- marks and rules ----------------------------------------------------------------
    def _nav(self, dep: dict) -> float | None:
        syms = [s for s, q in (dep.get("positions") or {}).items() if q]
        prices = latest_prices(self.any_broker(), syms) if syms else {}
        if any(s not in prices for s in syms):
            dep["rule_alert"] = f"{utc_iso()} unpriceable position; kill switch is flying blind"
            return None
        dep["rule_alert"] = None
        cash = float(dep.get("model_cash") or 0.0)
        return cash + sum(float(q) * prices[s] for s, q in dep["positions"].items() if q)

    def _observe(self, dep: dict, observed: str, record_day: str | None = None) -> None:
        nav = self._nav(dep)
        if nav is None:
            return
        dep["last_nav"] = round(nav, 2)
        if record_day:
            ser = [p for p in (dep.get("nav_series") or []) if p["date"] != record_day]
            ser.append({"date": record_day, "nav": round(nav, 2)})
            dep["nav_series"] = ser[-2000:]
        hwm, dec = evaluate_rule(dep.get("rule"), float(dep.get("hwm") or 0.0), nav, observed)
        dep["hwm"] = hwm
        if dec["kill"] and dep["status"].get("state") == "active":
            dep["status"] = {"state": "killed", "at": utc_iso(), "reason": dec["reason"],
                             "rule": dep.get("rule")}
            dep["pending_targets"] = None
            journal({"type": "killed", "id": dep["id"], "reason": dec["reason"], "nav": nav})
            if dep.get("mode") == "live" and dep.get("positions"):
                if bool(self.clock().get("is_open")):
                    self._flatten(dep, "kill")
                else:
                    dep["pending_flatten"] = True          # post-close kill: flatten at open
            else:
                dep["positions"] = {}                      # shadow: freeze

    # ---- orders -------------------------------------------------------------------------
    def _submit(self, dep: dict, sym: str, qty: int, why: str, price: float) -> bool:
        if qty == 0:
            return True
        if dep.get("mode") == "shadow":
            dep["model_cash"] = float(dep.get("model_cash") or 0.0) - qty * price
            dep["positions"][sym] = int(dep["positions"].get(sym, 0)) + qty
            dep["fills"] = int(dep.get("fills") or 0) + 1
            journal({"type": "shadow_fill", "id": dep["id"], "symbol": sym, "qty": qty,
                     "price": price, "why": why})
            return True
        if kill_switch_armed():
            journal({"type": "order_refused", "id": dep["id"], "symbol": sym, "qty": qty,
                     "reason": "global kill switch armed"})
            return False
        api = self.broker(dep["account_id"])
        payload = {"symbol": sym, "qty": str(abs(qty)), "side": "buy" if qty > 0 else "sell",
                   "type": "market", "time_in_force": "day"}
        out = api.submit_order(payload)
        oid = out.get("id") if isinstance(out, dict) else None
        dep["orders"] = (dep.get("orders") or [])[-200:] + [{"id": oid, "symbol": sym, "qty": qty,
                                                             "why": why, "ts": utc_iso()}]
        dep["model_cash"] = float(dep.get("model_cash") or 0.0) - qty * price
        dep["positions"][sym] = int(dep["positions"].get(sym, 0)) + qty
        dep["fills"] = int(dep.get("fills") or 0) + 1
        journal({"type": "order", "id": dep["id"], "symbol": sym, "qty": qty, "why": why,
                 "order_id": oid, "route": (api.route_log or ["?"])[-1], "ref_price": price})
        return True

    def _rebalance(self, dep: dict) -> None:
        weights = dep.get("pending_targets") or {}
        if dep.get("mode") == "live":
            if kill_switch_armed():
                journal({"type": "rebalance_skipped", "id": dep["id"], "reason": "kill switch"})
                return
            api = self.broker(dep["account_id"])
            equity = float(api.account().get("equity") or 0)
            capital = equity * float(dep["alloc_pct"]) / 100.0
        else:
            capital = float(dep.get("shadow_capital") or 2_500.0)
        if dep.get("capital_basis") is None:
            dep["capital_basis"] = round(capital, 2)
            dep["model_cash"] = round(capital, 2)
            dep["hwm"] = 0.0
        # the model's own book is what gets rebalanced, sized to its slice at launch and
        # re-sized to the live slice on every rebalance (equity drift included)
        basis = capital if dep.get("mode") == "live" else (
            float(dep.get("model_cash") or 0.0) + sum(
                float(q) * p for q, p in self._pos_values(dep).items()))
        syms = sorted(set(weights) | set(dep.get("positions") or {}))
        prices = latest_prices(self.any_broker(), syms)
        targets = size_targets(weights, basis, prices)
        deltas = order_deltas(targets, dep.get("positions") or {})
        sells = [d for d in deltas if d[1] < 0]
        buys = [d for d in deltas if d[1] > 0]
        ok = True
        for sym, q in sells + buys:                        # sells first: frees the slice
            ok = self._submit(dep, sym, q, "rebalance", prices.get(sym, 0.0)) and ok
        dep["positions"] = {s: q for s, q in dep["positions"].items() if q}
        if ok:
            dep["pending_targets"] = None
        journal({"type": "rebalanced", "id": dep["id"], "capital": round(basis, 2),
                 "targets": targets, "orders": len(deltas), "complete": ok})

    def _pos_values(self, dep: dict) -> dict:
        syms = [s for s, q in (dep.get("positions") or {}).items() if q]
        prices = latest_prices(self.any_broker(), syms) if syms else {}
        return {int(q): prices.get(s, 0.0) for s, q in dep["positions"].items() if q}

    def _flatten(self, dep: dict, why: str) -> None:
        pos = {s: int(q) for s, q in (dep.get("positions") or {}).items() if int(q)}
        if not pos:
            dep["pending_flatten"] = False
            return
        prices = latest_prices(self.any_broker(), list(pos)) if dep.get("mode") == "live" else {}
        ok = True
        for sym, q in pos.items():
            ok = self._submit(dep, sym, -q, why, prices.get(sym, 0.0)) and ok
        dep["positions"] = {s: q for s, q in dep["positions"].items() if q}
        dep["pending_flatten"] = not ok
        journal({"type": "flattened", "id": dep["id"], "why": why, "complete": ok,
                 "positions_sold": pos})


def main() -> int:
    if "--status" in sys.argv:
        print(json.dumps(status(), indent=1, default=str))
        return 0
    from broker import load_env
    load_env(os.path.join(ROOT, ".env"))
    load_accounts()
    journal({"type": "manager_up", "pid": os.getpid()})
    m = Manager()
    while True:
        t0 = time.time()
        try:
            m.tick()
        except Exception as exc:                           # noqa: BLE001
            journal({"type": "loop_error", "error": str(exc)[:300]})
        time.sleep(max(5.0, TICK_SECS - (time.time() - t0)))


if __name__ == "__main__":
    raise SystemExit(main())

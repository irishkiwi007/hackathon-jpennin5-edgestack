"""Pre-Monday dress rehearsal — verify every path the agent can take, before the open.

    python agent/rehearsal.py

Five stages, strictest last:
  A. unit suites (engine must reproduce research; every gate must fire for its reason)
  B. live plumbing (MCP server, account via MCP, market clock, Yahoo feed, TLT regime, gate)
  C. forced-path dry exercise — synthetic signals push the FULL pipeline (spread builder ->
     14 gates -> MLeg payload; equity entry/exit builders) without touching the market
  D. real order acceptance: submit-and-cancel the exact order types Monday will use
     (MOC equity via MCP, MLeg credit spread via MCP) — weekend = zero fill risk, and the
     spread's limit is set near max-credit so it could not fill even if left alone
  E. cleanup + open-order audit (must end with zero open orders)

Exit code 0 = cleared for Monday. Any FAIL prints loudly and exits nonzero.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def stage(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:                                     # noqa: PLR0915
    from broker import Alpaca, load_env
    load_env(os.path.join(HERE, "..", ".env"))

    # ---------------- A. unit suites ----------------
    stage("A. UNIT SUITES")
    for f in ("test_signal_engine.py", "test_risk_gates.py"):
        r = subprocess.run([sys.executable, os.path.join(HERE, f)],
                           capture_output=True, text=True, timeout=600)
        tail = (r.stdout or "").strip().splitlines()[-1] if r.stdout else r.stderr[:80]
        check(f, r.returncode == 0, tail)

    # ---------------- B. live plumbing ----------------
    stage("B. LIVE PLUMBING")
    api = Alpaca()
    acct = api.account()
    check("account via MCP", any("account: via MCP" in x for x in api.route_log),
          f"{acct.get('account_number')} equity ${float(acct.get('equity', 0)):,.0f}")
    check("options level 3", str(acct.get("options_trading_level")) == "3")

    clock = api._unwrap(api._mcp.call("get_clock")) if api._mcp else api.clock()
    nxt = str(clock.get("next_open", ""))[:16]
    check("market clock via MCP", bool(clock.get("next_open")),
          f"next open {nxt} (is_open={clock.get('is_open')})")

    import run_agent
    today = datetime.date.today()
    bars, mode, note = run_agent.build_universe_bars(api, today)
    check("universe feed", len(bars) >= 12, f"{len(bars)} symbols, mode={mode}")
    spy_n = len(bars.get("SPY", []))
    check("SPY history depth", spy_n >= 60, f"{spy_n} bars (signals need 26+)")

    import equity_core
    import regime as regime_mod
    tlt = api.daily_bars(["TLT"], (today - datetime.timedelta(days=420)).isoformat())
    rows = tlt.get("TLT") or []
    reg = regime_mod.evaluate([float(b["c"]) for b in rows], [b["t"][:10] for b in rows])
    check("TLT regime", reg is not None, reg.reason if reg else "no data")

    def long_closes(sym):
        from yahoo_feed import YahooFeed
        r2, _ = YahooFeed().daily(sym, days=430)
        return [x["close"] for x in r2 if x["close"] > 0]

    gate_open, gate_reason = equity_core.compute_gate(long_closes("SPY"),
                                                      long_closes("HYG"))
    check("equity gate computes", "insufficient" not in gate_reason, gate_reason)

    # ---------------- C. forced-path dry exercise ----------------
    stage("C. FORCED-PATH PIPELINE (synthetic signal, dry)")
    import risk_gates as rg
    import signal_engine as se
    from spread_builder import Contract, build, pick_expiration, to_mleg_order

    sig = se.Signal(symbol="SPY", date=today.isoformat(), stretch=-2.8, volx=2.0,
                    tier="FULL", size_weight=1.0,
                    spot=float(bars["SPY"][-1].close), hold_sessions=3,
                    hist_win_rate=0.701, hist_mean_pct=1.897, hist_t=4.32,
                    tradeable=True, mode=mode)
    exp_lo = (today + datetime.timedelta(days=8)).isoformat()
    exp_hi = (today + datetime.timedelta(days=21)).isoformat()
    contracts = api.option_contracts("SPY", exp_lo, exp_hi, kind="put")
    check("option chain fetch", len(contracts) > 10, f"{len(contracts)} puts")
    expiry = pick_expiration(today, {datetime.date.fromisoformat(c["expiration_date"])
                                     for c in contracts})
    chain = [c for c in contracts if c["expiration_date"] == expiry.isoformat()
             and c.get("tradable")
             and 0.85 * sig.spot <= float(c["strike_price"]) <= 1.05 * sig.spot]
    quotes = api.option_snapshots([c["symbol"] for c in chain])
    puts = [Contract(occ=c["symbol"], strike=float(c["strike_price"]), expiration=expiry,
                     kind="put", bid=quotes[c["symbol"]]["bid"],
                     ask=quotes[c["symbol"]]["ask"],
                     open_interest=c.get("open_interest"))
            for c in chain if c["symbol"] in quotes]
    check("live quotes on chain", len(puts) >= 4, f"{len(puts)} quotable strikes")
    proposal, bnote = build(sig, puts, float(acct["equity"]), today)
    check("spread builder", proposal is not None, bnote[:90])
    if proposal is None:
        return finish()

    account_state = rg.AccountState(
        equity=float(acct["equity"]),
        buying_power=float(acct.get("options_buying_power", 0)),
        open_positions=[], today=today, regime_calm=True,
        regime_reason="rehearsal: forced calm")
    market = {c.occ: {"bid": c.bid, "ask": c.ask, "open_interest": c.open_interest}
              for c in puts}
    approved, results = rg.evaluate_all(proposal, account_state, market)
    fails = [r.name for r in results if not r.passed]
    # weekend quotes can be stale-wide; liquidity may legitimately object — anything else may not
    hard_fails = [f for f in fails if f not in ("liquidity", "friction")]
    check("14 gates run clean", not hard_fails,
          ("all passed" if approved else f"objections: {fails} (liquidity/friction "
           "acceptable on weekend quotes)"))
    payload = to_mleg_order(proposal)
    check("MLeg payload shape",
          payload["order_class"] == "mleg" and len(payload["legs"]) == 2
          and all(k in payload["legs"][0] for k in
                  ("symbol", "ratio_qty", "side", "position_intent")),
          f"{proposal.short_strike}/{proposal.long_strike} credit {proposal.limit_credit}")

    eq_actions = equity_core.equity_entry(
        api, float(acct["equity"]), True, "rehearsal: forced open",
        [("QQQ", "rehearsal synthetic")], {s: b[-1].close for s, b in bars.items()},
        today, dry_run=True)
    kinds = {a["action"] for a in eq_actions}
    check("equity entry builder (dry)", "would_enter_core" in kinds
          and "would_enter_sleeve" in kinds, str(sorted(kinds)))

    # ---------------- D. real order acceptance (submit + cancel) ----------------
    stage("D. REAL ORDER ACCEPTANCE — submit & cancel, zero fill risk")
    # D1: the Monday equity path — market-on-close via MCP
    try:
        r1 = api.submit_order({"symbol": "SPY", "qty": "1", "side": "buy",
                               "type": "market", "time_in_force": "cls"})
        oid = r1.get("id")
        via = any("order SPY: via MCP" in x for x in api.route_log)
        api._mcp.call("cancel_order_by_id", {"order_id": oid})
        import time
        time.sleep(1.5)
        st = api._unwrap(api._mcp.call("get_order_by_id", {"order_id": oid}))
        check("MOC (cls) order via MCP", via and st.get("status") == "canceled",
              f"accepted->{st.get('status')}")
    except Exception as exc:                           # noqa: BLE001
        check("MOC (cls) order via MCP", False, str(exc)[:120])

    # D2: the Monday options path — MLeg credit spread, limit at 90% of width
    try:
        unfillable = dict(payload)
        unfillable["limit_price"] = f"{proposal.width * 0.90:.2f}"
        r2 = api.submit_order(unfillable)
        oid2 = r2.get("id")
        via2 = any("order mleg: via MCP" in x for x in api.route_log)
        api._mcp.call("cancel_order_by_id", {"order_id": oid2})
        import time
        time.sleep(1.5)
        st2 = api._unwrap(api._mcp.call("get_order_by_id", {"order_id": oid2}))
        check("MLeg spread via MCP", via2 and st2.get("status") == "canceled",
              f"{len(unfillable['legs'])} legs accepted->{st2.get('status')}")
    except Exception as exc:                           # noqa: BLE001
        check("MLeg spread via MCP", False, str(exc)[:200])

    # ---------------- E. cleanup audit ----------------
    stage("E. CLEANUP AUDIT")
    open_orders = api.orders("open")
    check("zero open orders", len(open_orders) == 0, f"{len(open_orders)} open")
    positions = api.positions()
    check("zero positions", len(positions) == 0, f"{len(positions)} held")
    return finish()


def finish() -> int:
    fails = [(n, d) for n, ok, d in RESULTS if not ok]
    print(f"\n{'=' * 78}")
    if fails:
        print(f"REHEARSAL: {len(fails)} FAILURE(S) — NOT cleared for Monday:")
        for n, d in fails:
            print(f"  FAIL {n}: {d}")
        return 1
    print(f"REHEARSAL: all {len(RESULTS)} checks passed — cleared for Monday's open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

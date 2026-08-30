"""Live runner. One pass per session, near the close.

    scan universe -> signal engine -> build spread -> risk gates -> submit -> journal

The model's role is bounded by construction: the signal is arithmetic, the structure is
arithmetic, and every gate is a pure function. Nothing here asks a model whether to trade.
What an LLM is good for - narrating the day, summarising the journal, explaining a refusal -
happens downstream of the decision, never upstream of it.

Usage
    python agent/run_agent.py --dry-run     # decide and journal, submit nothing
    python agent/run_agent.py               # decide, submit, journal
    python agent/run_agent.py --manage      # only manage exits on open positions
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import equity_core
import journal
import risk_gates as rg
from broker import Alpaca, BrokerError, load_env
from signal_engine import Bar, HOLD_SESSIONS, scan, near_misses
from yahoo_feed import YahooFeed, FeedError, provisional_bar, SAME_DAY_FULL_FLOOR
import regime as regime_mod
from spread_builder import Contract, build, pick_expiration, to_mleg_order, to_closing_order

# Liquid, optionable ETFs, ordered by measured option-crossing cost (one-way $/contract on a
# ~1wk ATM 5%-wide put spread, live chains 2026-08-28). Bonds excluded - no mechanism
# (+0.012%, t=0.11, win 45.7%).
#
#   IWM 2 · SPY 4 · XLF 2 · HYG 3 · XLE 6 · XLP 7 · GDX 11 · EEM 11 · EFA 12 · QQQ 16 · XLI 20
#
# Names beyond this cost 35-105 per contract to cross (XLV 40, SOXX 105, and the illiquid tail
# far worse), which exceeds the structure's entire gross edge. gate_friction enforces this on
# live quotes; the list is the cheap first cut.
UNIVERSE = ["SPY", "QQQ", "IWM", "HYG", "XLP", "XLE", "XLF", "XLI", "GDX", "EEM", "EFA",
            "XLK", "XLV", "XLY", "XLU", "XLB"]

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "journal", "open_trades.json")


def _load_state() -> list[dict]:
    import json
    if not os.path.exists(STATE_PATH):
        return []
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_state(rows: list[dict]) -> None:
    import json
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)


def build_universe_bars(api: Alpaca, today: datetime.date
                        ) -> tuple[dict[str, list[Bar]], str, str]:
    """(bars, mode, note).

    Yahoo first: it serves today's live consolidated price and volume, which lets the agent
    decide at ~15:45 and trade at today's close (+1.365% historically). Alpaca's free SIP cannot
    do this - it refuses any range reaching today, and its IEX alternative carries ~3% of
    consolidated volume, which would corrupt the volume ratio. Falling back to SIP means the
    prior session's signal at the next open (+1.205%, and the SMALL tier turns negative).
    """
    try:
        feed = YahooFeed()
        out: dict[str, list[Bar]] = {}
        provisional_count = 0
        now_et = _now_et()
        in_session = _is_rth(now_et)
        for sym in UNIVERSE:
            try:
                rows, meta = feed.daily(sym, days=90)
            except FeedError:
                continue
            bars = [Bar(date=r["date"], close=r["close"], volume=r["volume"])
                    for r in rows if r["close"] > 0 and r["volume"] >= 0]
            if len(bars) < 30:
                continue
            if in_session:
                prov = provisional_bar(meta, now_et)
                # Yahoo's last completed bar can already be today's once the session ends;
                # only append a provisional bar for a date we do not already have.
                if prov and (not bars or bars[-1].date != prov["date"]):
                    avg = sum(b.volume for b in bars[-20:]) / min(20, len(bars))
                    # sanity: a scaled volume wildly outside anything plausible means the live
                    # meta is not what we think it is - drop it rather than trade on it
                    if avg > 0 and prov["volume"] / avg < 8.0:
                        bars.append(Bar(date=prov["date"], close=prov["close"],
                                        volume=prov["volume"]))
                        provisional_count += 1
            out[sym] = bars
        if len(out) >= 10 and provisional_count >= len(out) // 2 and in_session:
            return (out, "same_day",
                    f"Yahoo live feed, {provisional_count}/{len(out)} provisional bars "
                    f"at {now_et:%H:%M} ET (volume scaled by completion factor)")
        if len(out) >= 10:
            return (out, "next_open",
                    f"Yahoo completed sessions only ({len(out)} symbols); "
                    f"{'outside RTH' if not in_session else 'no live meta'} "
                    f"-> prior-session signal, next-open entry")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  Yahoo feed unavailable ({exc}); falling back to Alpaca SIP")

    start = (today - datetime.timedelta(days=90)).isoformat()
    raw = api.daily_bars(UNIVERSE, start)          # no `end`: free SIP rejects ranges reaching today
    out = {}
    for sym, rows in raw.items():
        bars = [Bar(date=r["t"][:10], close=float(r["c"]), volume=float(r["v"]))
                for r in rows if r.get("c") and r.get("v") is not None]
        if len(bars) >= 30:
            out[sym] = bars
    return out, "next_open", f"Alpaca SIP completed sessions ({len(out)} symbols)"


def _now_et() -> datetime.datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                          # noqa: BLE001
        return datetime.datetime.now()


def _is_rth(now_et: datetime.datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    minute = now_et.hour * 60 + now_et.minute
    return 570 <= minute < 960          # 09:30 .. 16:00 ET


def manage_exits(api: Alpaca, today: datetime.date, dry_run: bool) -> list[dict]:
    """Close anything that has reached its 3-session hold."""
    actions = []
    state = _load_state()
    still_open = []
    for tr in state:
        entered = datetime.date.fromisoformat(tr["entry_date"])
        sessions_held = _sessions_between(entered, today)
        if sessions_held < HOLD_SESSIONS:
            still_open.append(tr)
            continue
        quotes = api.option_snapshots([tr["short_leg"], tr["long_leg"]])
        s, l = quotes.get(tr["short_leg"]), quotes.get(tr["long_leg"])
        if not s or not l or s["ask"] <= 0:
            actions.append({"action": "exit_deferred",
                            "detail": f"{tr['symbol']}: no usable quote, retry next session"})
            still_open.append(tr)
            continue
        # buy back the short at its ask, sell the long at its bid - worst realistic fill
        debit = round(s["ask"] - l["bid"], 2)
        payload = to_closing_order(_proposal_from(tr), max(debit, 0.01))
        if dry_run:
            actions.append({"action": "would_close",
                            "detail": f"{tr['symbol']} after {sessions_held} sessions, "
                                      f"net debit {debit:.2f} (credit in was "
                                      f"{tr['credit']:.2f})"})
            still_open.append(tr)
            continue
        try:
            res = api.submit_order(payload)
            actions.append({"action": "closed",
                            "detail": f"{tr['symbol']} order {res.get('id')} debit {debit:.2f} "
                                      f"vs credit {tr['credit']:.2f}"})
        except BrokerError as exc:
            actions.append({"action": "close_failed", "detail": f"{tr['symbol']}: {exc}"})
            still_open.append(tr)
    if not dry_run:
        _save_state(still_open)
    return actions


def _sessions_between(a: datetime.date, b: datetime.date) -> int:
    """Weekday count, exclusive of the entry day. Holidays are not modelled; the exit gate
    tolerates a day of slack because the 5-day hold performed as well as the 3-day."""
    n, cur = 0, a
    while cur < b:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _proposal_from(tr: dict) -> rg.Proposal:
    return rg.Proposal(
        symbol=tr["symbol"], structure="bull_put_spread",
        short_leg=tr["short_leg"], long_leg=tr["long_leg"],
        short_strike=tr["short_strike"], long_strike=tr["long_strike"],
        expiration=datetime.date.fromisoformat(tr["expiration"]),
        contracts=tr["contracts"], limit_credit=tr["credit"],
        tier=tr["tier"], size_weight=tr["size_weight"],
        stretch=tr["stretch"], volx=tr["volx"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="decide and journal, submit nothing")
    ap.add_argument("--manage", action="store_true", help="only manage exits")
    args = ap.parse_args()

    load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
    api = Alpaca()
    acct = api.account()
    for r in api.route_log:
        print(f"  broker: {r}")
    equity = float(acct["equity"])
    today = datetime.date.today()

    print(f"session {today}  equity ${equity:,.0f}  "
          f"options level {acct.get('options_trading_level')}")

    actions = manage_exits(api, today, args.dry_run)
    actions += equity_core.equity_exit(api, args.dry_run)
    for a in actions:
        print(f"  {a['action']}: {a['detail']}")
    if args.manage:
        journal.record(today.isoformat(),
                       {"equity": equity, "open_positions": len(_load_state())},
                       [], [], [], actions, [], notes="exit management pass")
        return 0

    bars, mode, feed_note = build_universe_bars(api, today)
    print(f"  feed: {feed_note}")
    print(f"  mode: {mode}  ({'today close entry' if mode == 'same_day' else 'next-open entry'})")
    print(f"  universe with usable history: {len(bars)}")
    signals = scan(bars, mode)
    misses = near_misses(bars, limit=10, mode=mode)

    positions = _load_state()

    # macro overlay: capitulation reverts only when the selling is emotional. Stressed bonds
    # mean real risk is being repriced and the edge measures ~0 (+0.066% vs +1.553%, t=6.58).
    reg = None
    try:
        tlt = api.daily_bars(["TLT"], (today - datetime.timedelta(days=420)).isoformat())
        rows = tlt.get("TLT") or []
        reg = regime_mod.evaluate([float(b["c"]) for b in rows],
                                  [b["t"][:10] for b in rows])
    except Exception as exc:                                   # noqa: BLE001
        print(f"  regime lookup failed ({exc}); treating as STRESSED (refuse)")
    if reg is None:
        regime_calm, regime_reason = False, "regime unavailable - refusing rather than guessing"
    else:
        regime_calm, regime_reason = reg.calm, reg.reason
    print(f"  regime: {regime_reason}")

    account_state = rg.AccountState(
        equity=equity,
        buying_power=float(acct.get("options_buying_power", acct.get("buying_power", 0))),
        open_positions=[{"underlying": p["symbol"], "max_loss": p["max_loss"]}
                        for p in positions],
        today=today,
        regime_calm=regime_calm,
        regime_reason=regime_reason)

    proposals, gate_records = [], []
    if not signals:
        print("  no signal fired")
        for m in misses[:5]:
            print(f"    {m['symbol']:<6} stretch {m['stretch']:+.2f}  "
                  f"volume {m['volx']:.2f}x  <- {'; '.join(m['blocked_by'])}")

    for sig in signals:
        print(f"  SIGNAL {sig.symbol} stretch {sig.stretch:+.2f} volume {sig.volx:.2f}x "
              f"tier {sig.tier}")
        exp_lo = (today + datetime.timedelta(days=8)).isoformat()
        exp_hi = (today + datetime.timedelta(days=21)).isoformat()
        try:
            contracts = api.option_contracts(sig.symbol, exp_lo, exp_hi, kind="put")
        except BrokerError as exc:
            print(f"    chain lookup failed: {exc}")
            continue
        if not contracts:
            print("    no contracts in the expiry window")
            continue
        expirations = {datetime.date.fromisoformat(c["expiration_date"]) for c in contracts}
        expiry = pick_expiration(today, expirations)
        if expiry is None:
            print("    no expiry inside the tested window")
            continue
        chain = [c for c in contracts
                 if c["expiration_date"] == expiry.isoformat() and c.get("tradable")]
        # only strikes near the money matter; keep the request small
        chain = [c for c in chain
                 if 0.85 * sig.spot <= float(c["strike_price"]) <= 1.05 * sig.spot]
        if len(chain) < 2:
            print("    chain too thin near the money")
            continue
        quotes = api.option_snapshots([c["symbol"] for c in chain])
        puts = []
        for c in chain:
            q = quotes.get(c["symbol"])
            if not q:
                continue
            puts.append(Contract(occ=c["symbol"], strike=float(c["strike_price"]),
                                 expiration=expiry, kind="put",
                                 bid=q["bid"], ask=q["ask"],
                                 open_interest=c.get("open_interest")))
        proposal, note = build(sig, puts, equity, today)
        print(f"    {note}")
        if proposal is None:
            gate_records.append({"symbol": sig.symbol, "approved": False,
                                 "checks": [{"name": "structure_available", "passed": False,
                                             "reason": note}]})
            continue

        market = {c.occ: {"bid": c.bid, "ask": c.ask, "open_interest": c.open_interest}
                  for c in puts}
        approved, results = rg.evaluate_all(proposal, account_state, market)
        gate_records.append({
            "symbol": sig.symbol, "approved": approved,
            "checks": [{"name": r.name, "passed": r.passed, "reason": r.reason}
                       for r in results]})
        for r in results:
            print(f"      [{'x' if r.passed else ' '}] {r.name}: {r.reason}")

        proposals.append({"symbol": proposal.symbol, "tier": proposal.tier,
                          "short": proposal.short_leg, "long": proposal.long_leg,
                          "contracts": proposal.contracts,
                          "credit": proposal.limit_credit,
                          "max_loss": proposal.max_loss, "max_gain": proposal.max_gain})
        if not approved:
            actions.append({"action": "rejected",
                            "detail": f"{sig.symbol}: " +
                                      "; ".join(r.reason for r in results if not r.passed)})
            continue
        if args.dry_run:
            actions.append({"action": "would_submit",
                            "detail": f"{proposal.symbol} {proposal.contracts}x "
                                      f"{proposal.short_strike}/{proposal.long_strike}p "
                                      f"credit {proposal.limit_credit:.2f}"})
            continue
        try:
            res = api.submit_order(to_mleg_order(proposal))
            actions.append({"action": "submitted",
                            "detail": f"{proposal.symbol} order {res.get('id')} "
                                      f"{proposal.contracts}x credit "
                                      f"{proposal.limit_credit:.2f}"})
            positions.append({"symbol": proposal.symbol, "entry_date": today.isoformat(),
                              "short_leg": proposal.short_leg, "long_leg": proposal.long_leg,
                              "short_strike": proposal.short_strike,
                              "long_strike": proposal.long_strike,
                              "expiration": proposal.expiration.isoformat(),
                              "contracts": proposal.contracts,
                              "credit": proposal.limit_credit,
                              "max_loss": proposal.max_loss, "tier": proposal.tier,
                              "size_weight": proposal.size_weight,
                              "stretch": proposal.stretch, "volx": proposal.volx})
            _save_state(positions)
            account_state.open_positions.append(
                {"underlying": proposal.symbol, "max_loss": proposal.max_loss})
        except BrokerError as exc:
            actions.append({"action": "submit_failed", "detail": f"{sig.symbol}: {exc}"})

    # ---- equity core + sleeve (EDGE-PORTFOLIO.md / ENGINE-TRIAL.md) ----
    def _long_closes(sym, days=430):
        try:
            rows, _meta = YahooFeed().daily(sym, days=days)
        except FeedError:
            return []
        closes = [r["close"] for r in rows if r["close"] > 0]
        dates = [r["date"] for r in rows]
        b = bars.get(sym)
        if b and (not dates or b[-1].date > dates[-1]):
            closes.append(b[-1].close)          # provisional today (same_day mode)
        return closes

    gate_open, gate_reason = equity_core.compute_gate(
        _long_closes("SPY"), _long_closes("HYG"))
    print(f"  equity gate: {'OPEN' if gate_open else 'CLOSED'} — {gate_reason}")
    sleeve_sigs = [(sg.symbol, f"stretch {sg.stretch:+.2f} vol {sg.volx:.2f}x {sg.tier}")
                   for sg in signals
                   if sg.symbol in equity_core.SLEEVE_UNIVERSE and sg.tradeable]
    last_px = {sym: b[-1].close for sym, b in bars.items() if b}
    eq_actions = equity_core.equity_entry(api, equity, gate_open, gate_reason,
                                          sleeve_sigs, last_px, today, args.dry_run)
    for a in eq_actions:
        print(f"  {a['action']}: {a['detail']}")
    actions += eq_actions

    journal.record(
        today.isoformat(),
        {"equity": equity, "open_positions": len(positions),
         "regime": regime_reason, "equity_gate": gate_reason,
         "broker_routes": api.route_log[-10:]},
        [s.as_dict() for s in signals], proposals, gate_records, actions, misses,
        notes=("dry run; " if args.dry_run else "") + feed_note)
    print(f"\n  journal updated: {len(signals)} signal(s), {len(actions)} action(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

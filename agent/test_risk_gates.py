"""Every gate must reject what it claims to reject. A gate that never fires is not a control.

Run:  python agent/test_risk_gates.py
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import risk_gates as rg

TODAY = datetime.date(2026, 8, 31)          # Monday, contest open
EXPIRY = datetime.date(2026, 9, 11)         # 11 DTE


def good_proposal(**over) -> rg.Proposal:
    # XLV ~ $171: 5%-wide spread risks ~$640/contract, so a full-size trade genuinely fits the
    # 2% cap on a $100k account. A 5%-wide SPY spread ($3,846/contract) never does - that is a
    # real constraint of this account size, not a test detail.
    kw = dict(symbol="XLV", structure="bull_put_spread",
              short_leg="XLV260911P00170000", long_leg="XLV260911P00162500",
              short_strike=170.0, long_strike=162.5, expiration=EXPIRY,
              contracts=2, limit_credit=1.10, tier="FULL", size_weight=1.0,
              stretch=-2.8, volx=2.0, friction=0.07)   # XLV-ish: $7/contract one-way
    kw.update(over)
    return rg.Proposal(**kw)


def good_account(**over) -> rg.AccountState:
    kw = dict(equity=100_000.0, buying_power=90_000.0, open_positions=[], today=TODAY,
              regime_calm=True, regime_reason="TLT 21d sd 0.555 vs 90d mean 0.760 -> CALM")
    kw.update(over)
    return rg.AccountState(**kw)


def good_market(**over) -> dict:
    m = {"XLV260911P00170000": {"bid": 2.40, "ask": 2.55, "open_interest": 4200},
         "XLV260911P00162500": {"bid": 1.30, "ask": 1.40, "open_interest": 3100}}
    m.update(over)
    return m


CASES = []


def case(name, expect_pass, gate_name, p=None, a=None, m=None):
    CASES.append((name, expect_pass, gate_name,
                  p or good_proposal(), a or good_account(), m or good_market()))


# baseline must be approved, otherwise every rejection below is meaningless
case("clean full-size trade", True, None)

case("equity below floor", False, "equity_floor", a=good_account(equity=1_000.0))
case("position cap reached", False, "position_count",
     a=good_account(open_positions=[{"underlying": x, "max_loss": 100.0}
                                    for x in ("QQQ", "IWM", "XLV", "HYG")]))
case("already holding this name", False, "duplicate_underlying",
     a=good_account(open_positions=[{"underlying": "XLV", "max_loss": 100.0}]))
case("inverted strikes", False, "structure_valid",
     p=good_proposal(short_strike=665.0, long_strike=700.0))
case("negative credit", False, "structure_valid", p=good_proposal(limit_credit=-1.0))
case("expiry too near", False, "expiry_window",
     p=good_proposal(expiration=datetime.date(2026, 9, 3)))
case("expiry too far", False, "expiry_window",
     p=good_proposal(expiration=datetime.date(2026, 11, 20)))
case("macro blackout day", False, "macro_blackout",
     a=good_account(today=datetime.date(2026, 9, 4)))
case("credit too thin vs width", False, "credit_quality",
     p=good_proposal(limit_credit=0.50))          # 6.7% of a 7.5 width, below the 12% floor
case("oversized for tier cap", False, "per_trade_risk", p=good_proposal(contracts=40))
case("small tier caps size", False, "per_trade_risk",
     p=good_proposal(contracts=2, tier="SMALL", size_weight=0.35))
# MEDIUM was retired 2026-09-01 by the clustered-t audit (per-event t 3.5-4.0
# collapses to ~1.0 once the 27 signal days are clustered). It must be REFUSED,
# and refused at the tier gate with a reason, not silently sized away. This case
# exists so a future edit cannot quietly revive it.
case("retired MEDIUM tier refused", False, "tier_tradeable",
     p=good_proposal(tier="MEDIUM", size_weight=0.60, volx=3.1, tradeable=False))
# ...and the retirement must not leak into the tier that survived the audit.
case("FULL tier still tradeable", True, None,
     p=good_proposal(tier="FULL", size_weight=1.0, tradeable=True))
case("portfolio risk exceeded", False, "portfolio_risk",
     a=good_account(open_positions=[{"underlying": x, "max_loss": 2_000.0}
                                    for x in ("QQQ", "IWM")] +
                                   [{"underlying": "HYG", "max_loss": 1_900.0}]))
case("insufficient buying power", False, "buying_power",
     a=good_account(buying_power=100.0))
case("leg missing a quote", False, "liquidity",
     m={"XLV260911P00170000": {"bid": 2.40, "ask": 2.55, "open_interest": 4200}})
case("leg spread too wide", False, "liquidity",
     m=good_market(**{"XLV260911P00162500": {"bid": 0.60, "ask": 2.10,
                                             "open_interest": 3100}}))
# friction: measured $2/contract on IWM vs $105 on SOXX for the same structure. The gate must
# let the cheap one through and refuse the expensive one.
# macro regime: the edge is +1.553% calm vs +0.066% stressed (t(diff)=6.58 out-of-sample),
# so a stressed regime must block outright rather than merely shrink size.
case("stressed bond regime blocks", False, "macro_regime",
     a=good_account(regime_calm=False,
                    regime_reason="TLT 21d sd 1.20 vs 90d mean 0.76 -> STRESSED"))
case("cheap to cross (IWM-like)", True, None, p=good_proposal(friction=0.02))
case("friction eats the edge (SOXX-like)", False, "friction",
     p=good_proposal(friction=1.05))
case("friction marginal (XLV-like)", False, "friction", p=good_proposal(friction=0.40))
case("open interest too low", False, "liquidity",
     m=good_market(**{"XLV260911P00162500": {"bid": 1.30, "ask": 1.40,
                                             "open_interest": 12}}))


def main() -> int:
    print(f"{'case':<34} {'expect':>8} {'got':>8}  {'gate that fired':<24} result")
    print("-" * 92)
    failures = 0
    for name, expect_pass, gate_name, p, a, m in CASES:
        approved, results = rg.evaluate_all(p, a, m)
        failed = [r for r in results if not r.passed]
        fired = failed[0].name if failed else "-"

        ok = (approved == expect_pass)
        if not expect_pass and gate_name is not None:
            # the RIGHT gate must be the one objecting
            ok = ok and any(r.name == gate_name for r in failed)
        failures += 0 if ok else 1
        print(f"{name:<34} {str(expect_pass):>8} {str(approved):>8}  {fired:<24} "
              f"{'PASS' if ok else 'FAIL'}")
        if not ok and failed:
            for r in failed:
                print(f"      -> {r.name}: {r.reason}")

    # sizing helper must respect the tier weight
    print()
    eq = 100_000.0
    full = rg.size_for_tier(eq, 1.00, width=7.5, credit=1.10)
    small = rg.size_for_tier(eq, 0.35, width=7.5, credit=1.10)
    med = rg.size_for_tier(eq, 0.60, width=7.5, credit=1.10)
    # integer contracts: MEDIUM and SMALL can tie when risk/contract is coarse
    # relative to the cap. What must hold is monotonicity and a real FULL>SMALL gap.
    sized_ok = full >= med >= small >= 0 and full > small
    failures += 0 if sized_ok else 1
    print(f"sizing ladder  FULL={full}  MEDIUM={med}  SMALL={small}   "
          f"{'PASS' if sized_ok else 'FAIL'}")

    print()
    print(f"{len(CASES) + 1} checks, {failures} failed")
    print("ALL GATES BEHAVE AS SPECIFIED" if failures == 0 else "GATE FAILURES ABOVE")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

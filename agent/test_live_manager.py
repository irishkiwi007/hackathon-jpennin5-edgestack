"""Kill-switch semantics and sizing, mirroring the TrustyRustyEngine rule tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_manager as lm  # noqa: E402


def rule(thr, res="daily"):
    return {"kind": "max_drawdown_kill", "threshold_pct": thr, "resolution": res}


class Rules(unittest.TestCase):
    def test_daily_replay_trips_at_first_crossing(self):
        hwm, killed = 0.0, None
        for nav in (100_000.0, 110_000.0, 98_000.0, 120_000.0):
            hwm, dec = lm.evaluate_rule(rule(10.0), hwm, nav, "daily")
            if dec["kill"]:
                killed = dec
                break
        self.assertIsNotNone(killed)
        self.assertIn("10.9", killed["reason"])           # 98k is 10.9% under 110k
        self.assertEqual(hwm, 110_000.0)

    def test_hwm_advances_and_holds_below_threshold(self):
        hwm = 0.0
        for nav in (100_000.0, 110_000.0, 101_000.0):
            hwm, dec = lm.evaluate_rule(rule(10.0), hwm, nav, "daily")
            self.assertFalse(dec["kill"])
        self.assertEqual(hwm, 110_000.0)

    def test_minute_close_trips_minute_rule_not_daily_rule(self):
        hwm, dec = lm.evaluate_rule(rule(5.0, "minute"), 100_000.0, 94_000.0, "minute")
        self.assertTrue(dec["kill"])
        hwm2, dec2 = lm.evaluate_rule(rule(5.0, "daily"), 100_000.0, 94_000.0, "minute")
        self.assertFalse(dec2["kill"])
        self.assertEqual(hwm2, 100_000.0)

    def test_daily_rule_never_sees_intraday_spike(self):
        hwm, _ = lm.evaluate_rule(rule(5.0, "daily"), 100_000.0, 120_000.0, "minute")
        self.assertEqual(hwm, 100_000.0)
        hwm, _ = lm.evaluate_rule(rule(5.0, "daily"), 100_000.0, 120_000.0, "daily")
        self.assertEqual(hwm, 120_000.0)

    def test_daily_close_concludes_hourly_and_minute_bars(self):
        _, dec = lm.evaluate_rule(rule(5.0, "hourly"), 100_000.0, 90_000.0, "daily")
        self.assertTrue(dec["kill"])

    def test_no_rule_never_kills(self):
        hwm, dec = lm.evaluate_rule(None, 100.0, 1.0, "daily")
        self.assertFalse(dec["kill"])
        self.assertEqual(hwm, 100.0)

    def test_unpriceable_nav_does_not_trip_or_move_hwm(self):
        hwm, dec = lm.evaluate_rule(rule(1.0), 100.0, 0.0, "daily")
        self.assertFalse(dec["kill"])
        self.assertEqual(hwm, 100.0)


class Sizing(unittest.TestCase):
    def test_whole_shares_of_the_slice(self):
        t = lm.size_targets({"SPY": 0.7, "HYG": 0.3}, 10_000.0, {"SPY": 500.0, "HYG": 80.0})
        self.assertEqual(t, {"SPY": 14, "HYG": 37})

    def test_weights_clamped_and_unpriced_skipped(self):
        t = lm.size_targets({"SPY": 1.5, "XXX": 0.2, "QQQ": -1}, 1_000.0, {"SPY": 100.0, "QQQ": 50.0})
        self.assertEqual(t, {"SPY": 10, "QQQ": 0})

    def test_deltas_sell_dropped_symbols_in_full(self):
        d = lm.order_deltas({"SPY": 10}, {"SPY": 4, "HYG": 7})
        self.assertEqual(sorted(d), [("HYG", -7), ("SPY", 6)])

    def test_no_delta_no_order(self):
        self.assertEqual(lm.order_deltas({"SPY": 4}, {"SPY": 4}), [])


if __name__ == "__main__":
    unittest.main()

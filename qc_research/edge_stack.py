"""EDGE STACK — QuantConnect trial of the validated equity strategy.

Paste this file as main.py in a new QuantConnect Python algorithm and run.

WHAT THIS IMPLEMENTS (each component measured separately, 1993-2026, see EDGE-PORTFOLIO.md):

  CORE   Long SPY OVERNIGHT ONLY (close -> next open), gated by the 12-month trend.
           - overnight Sharpe 0.89 vs intraday 0.05; positive in 8/9 eras, 7/8 ETFs
           - trend gate: fwd returns +1.011% (t=5.77) trend-up vs +0.113% (t=0.17) trend-down
  SLEEVE Capitulation basket at 0.5x weight, 3-session hold, across 7 liquid ETFs.
           - signal: 5-day stretch < -2.5 sigma AND volume 1.4-2.5x its 20-day mean
           - +1.419%/event net, 67.6% win, t=4.27 over 136 events / 33 years
           - the 2.5x volume CEILING is load-bearing: above it "real news arrived"
             and the bounce disappears. Do not remove it.

REFERENCE RESULT from the research backtest (SPY-based, 1994-2026, 1bp costs):

    configuration          CAGR     vol    Sharpe   maxDD
    buy and hold           7.98%   18.81%   0.32    -58.9%
    core only              8.01%    7.92%   0.76    -24.9%
    core + sleeve 0.5x     9.72%    9.07%   0.85    -26.6%   <- this algorithm

Expect QC numbers to differ somewhat: QC models its own fills/slippage, uses its own
dividend-adjusted data, and this implementation enters sleeve positions at ~15:58 using a
volume ESTIMATE (see VOLUME_COMPLETION below) rather than the exact end-of-day print.

NOT included in this trial: the earnings iron-condor options sleeve (needs QC option chains
plus an earnings calendar; separate file, separate trial).
"""
from AlgorithmImports import *
from collections import deque
import math


class EdgeStack(QCAlgorithm):

    # ---------------- parameters (all traceable to measured evidence) ----------------
    SLEEVE_UNIVERSE = ["SPY", "QQQ", "SOXX", "XLV", "XLP", "HYG", "FDN"]
    CORE_SYMBOL = "SPY"

    CORE_WEIGHT = 1.00        # overnight core exposure when the trend gate is open
    SLEEVE_WEIGHT = 0.50      # per signal-day batch; best measured config (Sharpe 0.85)
    MAX_TOTAL_SLEEVE = 1.00   # cap on summed sleeve exposure across overlapping batches

    TREND_LOOKBACK = 252      # 12-month trend gate on the core
    USE_CREDIT_CANARY = True  # core gate also requires HYG > its own 100d SMA.
    CREDIT_CANARY_SMA = 100   # Borrowed from the user's `canaries` strategy after passing
                              # BOTH disjoint windows in the TrustyRustyEngine trial:
                              # Sharpe 0.80->0.98 train, 0.65->1.02 valid, DD ~halved
                              # (ENGINE-TRIAL.md). Engine-validated on a FULL-TIME core;
                              # this overnight-core application is what THIS backtest tests.
    STRETCH_TRIGGER = -2.5    # capitulation depth, in 20d-vol-normalised 5-day sigma
    VOL_FLOOR = 1.5           # research floor is 1.4x at the exact close; +0.1 margin because
                              # 15:45 volume is an estimate with ~+/-8% error and the cell
                              # just below the floor measured flat (+0.18%, t=0.2)
    VOL_CEILING = 2.5         # ABOVE this the edge dies ("real news arrived"). Load-bearing.
    HOLD_SESSIONS = 3         # 3-day hold: t=4.42; 10-day decays

    VOLUME_COMPLETION = 0.894  # median fraction of a session's volume done by 15:45 ET,
                               # measured over 4,432 symbol-sessions of 5-minute bars

    RV_WINDOW = 20
    STRETCH_LOOKBACK = 5

    def Initialize(self):
        self.SetStartDate(2010, 1, 1)          # all 7 ETFs have data; includes 2011/2015/
        self.SetEndDate(2026, 8, 1)            # 2018/2020/2022 stress windows
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage,
                               AccountType.Margin)

        self.syms = {}
        for t in self.SLEEVE_UNIVERSE:
            sec = self.AddEquity(t, Resolution.Minute)
            sec.SetLeverage(4)
            self.syms[t] = sec.Symbol

        # rolling completed-daily history per symbol: (close, volume)
        self.daily = {t: deque(maxlen=300) for t in self.SLEEVE_UNIVERSE}
        for t in self.SLEEVE_UNIVERSE:
            self.Consolidate(self.syms[t], Resolution.Daily,
                             (lambda bar, tt=t: self._on_daily(tt, bar)))

        # seed history so signals are live from day one
        for t in self.SLEEVE_UNIVERSE:
            hist = self.History(self.syms[t], 300, Resolution.Daily)
            if not hist.empty:
                for _, row in hist.loc[self.syms[t]].iterrows():
                    self.daily[t].append((float(row["close"]), float(row["volume"])))

        # intraday running volume + last price (for the 15:45 provisional bar)
        self.intraday_vol = {t: 0.0 for t in self.SLEEVE_UNIVERSE}
        self.last_price = {t: None for t in self.SLEEVE_UNIVERSE}
        self.cur_day = None

        # open sleeve positions: list of {"sym": str, "w": float, "left": int}
        self.sleeve = []
        self.core_on = False

        spy = self.syms[self.CORE_SYMBOL]
        self.Schedule.On(self.DateRules.EveryDay(spy),
                         self.TimeRules.AfterMarketOpen(spy, 1), self.MorningExit)
        self.Schedule.On(self.DateRules.EveryDay(spy),
                         self.TimeRules.BeforeMarketClose(spy, 15), self.ComputeSignals)
        self.Schedule.On(self.DateRules.EveryDay(spy),
                         self.TimeRules.BeforeMarketClose(spy, 2), self.EveningEntry)

        self.SetWarmUp(5, Resolution.Daily)

    # ---------------- data plumbing ----------------
    def _on_daily(self, ticker, bar):
        self.daily[ticker].append((float(bar.Close), float(bar.Volume)))

    def OnData(self, data):
        day = self.Time.date()
        if day != self.cur_day:
            self.cur_day = day
            for t in self.SLEEVE_UNIVERSE:
                self.intraday_vol[t] = 0.0
        for t in self.SLEEVE_UNIVERSE:
            s = self.syms[t]
            if data.Bars.ContainsKey(s):
                b = data.Bars[s]
                self.intraday_vol[t] += float(b.Volume)
                self.last_price[t] = float(b.Close)

    # ---------------- signal computation, 15:45 ET ----------------
    def _capitulation(self, t):
        """(fires, stretch, volx) using completed dailies + today's provisional bar."""
        hist = self.daily[t]
        if len(hist) < self.RV_WINDOW + self.STRETCH_LOOKBACK + 2:
            return False, None, None
        px_now = self.last_price[t]
        if px_now is None or px_now <= 0:
            return False, None, None

        closes = [c for c, _ in hist]
        vols = [v for _, v in hist]

        # CONVENTION (matches the validated research exactly): the 20-day realized-volatility
        # window and the 20-day volume mean both INCLUDE the signal day itself. Today's large
        # move raises rv and today's heavy volume raises the volume mean, making the trigger
        # STRICTER. Using completed sessions only produced 190 weaker events instead of the
        # validated 136 (+1.42%, 67.6% win) - verified against the 33-year record.
        est_vol = self.intraday_vol[t] / self.VOLUME_COMPLETION

        # 19 completed daily returns + today's provisional return = 20
        rets = []
        for i in range(len(closes) - (self.RV_WINDOW - 1), len(closes)):
            if closes[i - 1] > 0 and closes[i] > 0:
                rets.append(math.log(closes[i] / closes[i - 1]))
        rets.append(math.log(px_now / closes[-1]))
        if len(rets) < self.RV_WINDOW - 2:
            return False, None, None
        mean = sum(rets) / len(rets)
        rv = math.sqrt(sum((x - mean) ** 2 for x in rets) / (len(rets) - 1))
        if rv <= 0:
            return False, None, None

        # stretch: today's live price vs the close 5 sessions ago
        ref = closes[-self.STRETCH_LOOKBACK]
        if ref <= 0:
            return False, None, None
        stretch = math.log(px_now / ref) / (rv * math.sqrt(self.STRETCH_LOOKBACK))

        # 19 completed volumes + today's full-day estimate = 20
        avg_vol = (sum(vols[-(self.RV_WINDOW - 1):]) + est_vol) / self.RV_WINDOW
        if avg_vol <= 0:
            return False, None, None
        volx = est_vol / avg_vol

        fires = (stretch < self.STRETCH_TRIGGER
                 and self.VOL_FLOOR <= volx < self.VOL_CEILING)
        return fires, stretch, volx

    def _trend_up(self):
        closes = [c for c, _ in self.daily[self.CORE_SYMBOL]]
        if len(closes) < self.TREND_LOOKBACK + 1:
            return False
        return closes[-1] / closes[-self.TREND_LOOKBACK - 1] - 1.0 > 0.0

    def _credit_ok(self):
        """canaries' credit canary: HYG above its own 100d SMA. Deteriorating credit marks
        INFORMATIONAL risk — the same emotional-vs-informational boundary as the volume
        ceiling and the TLT-vol overlay, measured in the credit market."""
        if not self.USE_CREDIT_CANARY:
            return True
        closes = [c for c, _ in self.daily["HYG"]]
        n = self.CREDIT_CANARY_SMA
        if len(closes) < n:
            return False
        return closes[-1] > sum(closes[-n:]) / n

    def _gate_open(self):
        return self._trend_up() and self._credit_ok()

    def ComputeSignals(self):
        if self.IsWarmingUp:
            return
        # age existing sleeve positions; those reaching 0 exit at today's close
        for p in self.sleeve:
            p["left"] -= 1

        fired = []
        for t in self.SLEEVE_UNIVERSE:
            fires, stretch, volx = self._capitulation(t)
            if fires:
                fired.append(t)
                self.Log(f"CAPITULATION {t}: stretch {stretch:.2f}, volume {volx:.2f}x")

        if fired:
            current = sum(p["w"] for p in self.sleeve if p["left"] > 0)
            budget = max(0.0, min(self.SLEEVE_WEIGHT,
                                  self.MAX_TOTAL_SLEEVE - current))
            if budget > 0:
                w = budget / len(fired)
                for t in fired:
                    self.sleeve.append({"sym": t, "w": w,
                                        "left": self.HOLD_SESSIONS})

        self.core_on = self._gate_open()

    # ---------------- execution ----------------
    def _apply_targets(self, include_core):
        """Net core + sleeve into one target weight per symbol and trade the difference."""
        targets = {t: 0.0 for t in self.SLEEVE_UNIVERSE}
        for p in self.sleeve:
            if p["left"] > 0:
                targets[p["sym"]] += p["w"]
        if include_core and self.core_on:
            targets[self.CORE_SYMBOL] += self.CORE_WEIGHT

        self.sleeve = [p for p in self.sleeve if p["left"] > 0]

        port = [PortfolioTarget(self.syms[t], w) for t, w in targets.items()]
        self.SetHoldings(port)

    def EveningEntry(self):
        """15:58 ET: core enters for the overnight session; new sleeve positions enter;
        expired sleeve positions exit."""
        if self.IsWarmingUp:
            return
        self._apply_targets(include_core=True)

    def MorningExit(self):
        """09:31 ET: core exits (overnight only). Sleeve positions ride through the day."""
        if self.IsWarmingUp:
            return
        self._apply_targets(include_core=False)

    def OnEndOfAlgorithm(self):
        self.Log(f"final equity: {self.Portfolio.TotalPortfolioValue:.2f}")

# Demo video script (~4 minutes, 3 screens)

lablab's own guidance: clarity over production value; problem -> working demo -> value;
three screens max. Record screen + voice, no fancy editing needed.

## Screen 1 — the README hero (0:00-0:50)
> "Ask an LLM for a trading strategy and it gives you one — confident, plausible, untested.
> I built EdgeStack to answer the question nobody makes the agent answer: what evidence does
> a trading rule need before it deserves to exist? Evidence opens the door to
> opportunity: thirty-three years of data, surrogate tests, two validation windows
> where every parameter tuning FAILED and was thrown away, and three backtest engines that
> had to agree — including my own Rust engine and QuantConnect."

## Screen 2 — the live dashboard (0:50-2:30)
Open the public URL. Point at, in order:
- the account equity card ("real Alpaca paper account, judges can pull it")
- the MCP card ("orders route through Alpaca's MCP server — the journal logs every route")
- the equity gate card ("right now credit is deteriorating, so the core is in cash — the
  agent explains why it is NOT trading; refusal is a decision with evidence attached")
- the decision journal table ("every session, including the boring ones")
- one capitulation event if one fired; otherwise the near-miss list

## Screen 3 — the evidence (2:30-3:40)
Scroll EDGE-PORTFOLIO.md briefly, stop on two tables:
- the overnight/intraday split (Sharpe 0.89 vs 0.05)
- ENGINE-TRIAL.md validation table ("every tuning failed validation — the untuned rules won.
  That failure is why I trust the defaults.")
> "The graveyard is the point. Elliott waves, Fibonacci levels, five macro overlays, my own
> first options design — tested, killed, documented. What survived is small and gated."

## Close (3:40-4:00)
> "The P&L window is five sessions and my edges are risk-adjusted — I won't pretend
> otherwise. What EdgeStack demonstrates is the discipline that survives any market: rules
> that earned their existence, an engine that provably implements them, and an agent that
> can explain every trade — and every refusal."

# lablab submission form — paste-ready

**Title**

> EdgeStack

**Short description** (winners' house style: one sentence, what + how + for whom)

> An autonomous Alpaca trading agent built on one idea — evidence opens the door to
> opportunity: 33 years of data, three backtest engines, and a public graveyard of rejected
> ideas behind an equity-plus-options strategy that journals every trade and every refusal.

**Long description**

> **The problem.** LLM trading agents lose money confidently, because their rules come from
> vibes. Ask a model for a strategy and it gives you one — plausible, articulate, untested.
> Nobody makes the agent answer the harder question: *what evidence does a trading rule need
> before it deserves to exist?*
>
> **The answer.** EdgeStack was built backward: months of compute spent trying to *disprove*
> candidate edges, and the agent only trades what survived — 33 years of data, surrogate-null
> tests, drop-one-era checks, and two disjoint validation windows on an independently built
> engine where **every parameter tuning failed validation and was rejected**. The graveyard
> (Elliott waves, Fibonacci levels, five macro overlays, our own first options design) is
> published with the number that killed each idea.
>
> **What survived.** Long SPY overnight-only (Sharpe 0.89 vs 0.05 intraday), gated by the
> 12-month trend and a credit canary mined from the trader's own older strategies (adopted
> only after passing both validation windows, 0.80→0.98 / 0.65→1.02 Sharpe); a capitulation
> basket (+1.42%/event, t=4.27, 136 events/33y); and defined-risk options spreads on the
> same signal behind 14 deterministic gates. The unifying, thrice-measured finding: markets
> revert *emotional* moves and honor *informational* ones.
>
> **The machine.** Orders and account reads route through **Alpaca's MCP Server v2**
> (REST fallback, every route journaled). The production engine reproduces the research
> record to three decimals; a 22-case suite requires the *right* gate to refuse in every
> scenario; an append-only decision journal explains every trade — and every refusal — and
> feeds the public live dashboard.
>
> **Honest limits, on purpose.** These are risk-adjusted edges; a 5-session P&L window is
> mostly noise for every entrant. What EdgeStack demonstrates is the discipline that
> survives any market: rules that earned their existence, an engine that provably
> implements them, and an agent that can explain why it did nothing.
>
> Live dashboard: https://jpennin5.github.io/edgestack/ ·
> Repo: https://github.com/jpennin5/edgestack · Paper account: PA3ZCDDOPR2N

**Tech / category tags**

> Alpaca MCP Server, Alpaca Trading API, Python, options trading, autonomous agent,
> quantitative research, risk management, paper trading

**Other form fields**

- Cover image: `docs/cover.png`
- Video: `docs/demo.mp4` (3:35, MP4, 1080p)
- Slide deck: `docs/slides.pdf`
- GitHub repo: https://github.com/jpennin5/edgestack
- Live application URL: https://jpennin5.github.io/edgestack/
- Alpaca paper account ID: PA3ZCDDOPR2N

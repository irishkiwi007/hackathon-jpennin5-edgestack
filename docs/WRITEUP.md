# EdgeStack — one-page write-up

**Team:** EdgeStack (solo) · **Paper account:** `PA3ZCDDOPR2N` · **Repo:** this one ·
**Live URL:** https://jpennin5.github.io/edgestack/

## The idea

Most trading agents are built forward: pick a strategy, add risk rules, go live. EdgeStack
was built backward: months of compute were spent trying to *disprove* candidate edges, and
the agent only trades what survived. Three rules made it through 33 years of data,
surrogate-null testing, drop-one-era checks, and two disjoint validation windows on a
second, independently-built backtest engine — where every attempt at parameter tuning
*failed* validation and was rejected, which is precisely why the surviving defaults can be
trusted.

The scientific through-line: **markets revert emotional moves and honor informational
ones.** We measured that boundary three independent ways — a volume ceiling (above 2.5× of
normal volume, "real news arrived" and panic-bounces die), a bond-volatility regime (the
same capitulation signal earns +1.55% when bonds are calm vs +0.07% when stressed,
t(diff)=6.58 out-of-sample, n=4,359), and a credit canary (HYG below its 100-day SMA closes
the equity core; adopted from the trader's own pre-existing strategy library only after it
passed both validation windows: Sharpe 0.80→0.98 train, 0.65→1.02 validation).

## AI logic

The LLM's role is deliberately bounded — it proposes, narrates the journal, and explains
refusals; it never sizes, prices, or authorizes. Signals are arithmetic (a 5-day
volatility-normalized stretch, volume ratios, SMA gates); proposals are fully-specified
structures (symbol, strikes, expiry, quantity, limit); and a deterministic layer decides
whether each proposal is allowed to exist. The production signal engine reproduces the
33-year research record **to three decimals** (`agent/test_signal_engine.py`) — research
and production cannot drift apart silently.

## Risk gates

Fourteen pure functions, each rejecting for its own measured reason: equity floor,
structure legality (Alpaca MLeg: ≤4 legs, every short covered), delayed-entry tier
tradability, position count, duplicate underlying, expiry window, macro blackout calendar,
**macro regime** (stressed bonds refuse capitulation trades), credit-to-width floor,
**friction** (round-trip crossing cost may not exceed 40% of measured gross edge — this
gate, learned from measuring a 50× spread-cost range across ETFs, is what keeps the options
book solvent), per-trade risk, portfolio risk, buying power, per-leg liquidity. A 22-case
suite requires the *right* gate to object in every scenario. No-trade sessions journal
their near-misses: an agent that can explain why it did nothing is the point.

## Alpaca infrastructure

Account reads and order submission route through **Alpaca's MCP Server v2** (pinned 2.3.0,
streamable-http, launched via uvx) through a hand-written MCP client
(`agent/mcp_gateway.py`); direct REST is a logged fallback, and the journal records which
path served every call. Orders: MLeg limit spreads for options; market-on-close and
market-at-open for the equity core (long SPY overnight-only — Sharpe 0.89 vs 0.05 intraday
— gated by trend and credit). Everything runs unattended on dedicated self-hosted hardware:
ensure-running supervisors, logon persistence, live dashboard tunneled publicly. Sessions:
signals at 15:45 ET off a measured 89.4% volume-completion estimate; exits 09:31 ET.

## What we want judges to take away

The P&L window is five sessions; our edges are risk-adjusted and fire rarely — we will not
pretend otherwise. What this entry demonstrates is the thing that survives contact with any
market: a research discipline that kills its own ideas, an engine that proves it implements
the research, and an audit trail where every trade — and every refusal — carries its
evidence.

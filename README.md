# EdgeStack

**The problem: LLM trading agents lose money confidently, because their rules come from
vibes.** Ask a model for a trading strategy and it will give you one — plausible,
articulate, and untested. The question nobody makes the agent answer is: *what evidence
does a rule need before it deserves to exist?*

**EdgeStack's answer: evidence opens the door to opportunity — no rule trades here
until our best attempts to kill it have failed.**

Thirty-three years of data. Surrogate nulls. Two disjoint validation windows where every
parameter tuning *failed* and was rejected. Three independent backtest engines that had to
agree. A documented graveyard of ideas that didn't make it — Elliott waves, Fibonacci
levels, five macro overlays, and our own first options design. What remains is small,
gated, and explains every refusal.

**Live dashboard:** [https://jpennin5.github.io/edgestack/](https://jpennin5.github.io/edgestack/) · **Paper account:**
`PA3ZCDDOPR2N` · Built for the [lablab.ai × Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon)
on **Alpaca's MCP Server v2**.

Like every serious entry in this event, the LLM here cannot touch capital — deterministic
gates stand between proposal and order. The difference is where the *rules themselves* come
from: **every gate constant in this repo is a measurement with a t-statistic attached**, not
a judgment call. The unifying finding behind all of them: markets revert *emotional* moves
and honor *informational* ones — measured three independent ways (a volume ceiling, a
bond-volatility regime, a credit canary).

---

## What it trades

Three components, each carrying its own validated evidence:

| component | rule | evidence |
| --- | --- | --- |
| **Overnight core** | Long SPY close→open only, when the 12-month trend is up AND credit is healthy (HYG > its 100d SMA) | Overnight Sharpe **0.89** vs **0.05** intraday, positive in 8/9 eras since 1993. Credit gate passed two disjoint validation windows: Sharpe 0.80→0.98 (train), 0.65→**1.02** (validation), drawdown halved |
| **Capitulation sleeve** | Buy 5-day panics (stretch < −2.5σ) on heavy-but-not-extreme volume (1.4–2.5×), basket of 7 ETFs, 3-session hold | **+1.42%/event, 67.6% win, t=4.27** across 136 events / 33 years — surrogate-tested, era-robust |
| **Options component** | Defined-risk bull put spreads on the capitulation signal, behind 14 deterministic risk gates | Direction validated in the underlying; option expression sized small because our own tests showed retail spreads eat most of the edge — and we say so |

The signature finding that shapes all three: **markets revert emotional moves and honor
informational ones.** Above 2.5× volume, "real news arrived" and the bounce dies. When bond
volatility is stressed, the same signal returns +0.07% instead of +1.55% (t(diff)=6.58,
out-of-sample, n=4,359). When credit deteriorates, the core stands down. Same boundary,
measured three independent ways.

## Architecture

```text
                     ┌─────────────────────────────┐
   Yahoo (signals)──▶│  signal_engine  (pure math) │   nothing in this box
   TLT/HYG regimes──▶│  equity_core    (gates)     │   consults a model
                     │  risk_gates     (14 gates)  │
                     └──────────────┬──────────────┘
                                    │ fully-specified proposals
                     ┌──────────────▼──────────────┐
                     │  broker.py                  │──▶ Alpaca MCP Server v2 (:8000)
                     │  (MCP first, REST fallback, │        │ streamable-http
                     │   every route journaled)    │        ▼
                     └──────────────┬──────────────┘    Alpaca Paper API
                                    ▼
                     journal/ (append-only decisions) ──▶ dashboard (:8787, live URL)
```

- **MCP integration is real, not decorative**: account reads and order submission route
  through the Alpaca MCP Server (`agent/mcp_gateway.py`, streamable-http JSON-RPC), with
  REST as a logged reliability fallback. The decision journal records which path served
  every call.
- **Determinism**: signals are arithmetic; gates are pure functions; the engine reproduces
  its 33-year research record exactly (`agent/test_signal_engine.py` — n, mean and win rate
  match to three decimals; `agent/test_risk_gates.py` — 22 cases, every gate must fire for
  its own reason).
- **The journal is the product**: no-trade sessions record the near-misses and which gate
  refused them. An agent that can explain why it did nothing is the point.

## Run it

```bash
cp .env.example .env            # paper keys from app.alpaca.markets
python host/run.py mcp          # Alpaca MCP Server v2.3.0 (pinned, via uvx)
python host/run.py scheduler    # session passes: entries 15:45 ET, exits 09:31 ET
python host/run.py dashboard    # dashboard on :8787 — Live / Research / Backtest tabs
python host/run.py live         # Live Manager loop: deployments + kill switches
python agent/run_agent.py --dry-run   # one decision pass, no orders
```

Supervisors are ensure-running (restart on crash, never double-bind) and registered at
logon. A Docker path for the MCP server ships in `Dockerfile`/`docker-compose.yml`.

### Dashboard tabs

| tab | what | writes |
| --- | --- | --- |
| **Live** | the competition agent (equity, gate, MCP route, positions, decision journal) and the **Live Manager**: deploy any strategy module against a slice of an account with a drawdown kill switch — the TrustyRustyEngine model (`agent/live_manager.py`): pinned module, `equity × alloc%` sizing, rebalance at the open from the same runner that backtests it, kill when model NAV falls the threshold below its since-launch high-water mark at daily/hourly/minute resolution, global kill switch, shadow mode | operator key |
| **Research** | the read-only public replica of the research lab | none |
| **Backtest** | the borrowed TrustyRustyEngine runner (`engine/`, see `engine/BORROWED.md`) on the submitted strategy's lineage and the buy-and-hold benchmark it must beat, with the adoption dossier behind each candidate. The operator's other strategies are private and stay in the container | operator key to run |

Reads are public; anything that runs code or moves money is keyed, because the tunnel puts the page on the open internet. From a browser **on the host** the dashboard just works: whoever is at the console can already read the key file, so writes are allowed there without it, guarded against cross-site abuse by an Origin check and a JSON content type that forces a preflight the server never answers. The same trust extends to the operator's **tailnet**: a request from a Tailscale address (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) has already been authenticated by WireGuard to the operator's own account, a stronger proof than a pasted string, so `https://edgestack.tail054462.ts.net`, or simply `http://edgestack:3000` (the MagicDNS short name, the way the trustyrusty container is reached), works from any tailnet device with no key; the research lab's own dashboard is `http://edgestack:8080` there. Only names the dashboard knows itself by are trusted as origins, never the `.ts.net` suffix, because anyone with a Tailscale account can mint one of those. LAN addresses are not trusted. Everyone else — the tunnel included, which cloudflared proxies from loopback and is told apart by its forwarding headers — sends the key from `journal/operator_token` (generated on first start, never committed) in `X-Operator-Token`; the stable landing page fills it in by itself on the host.

## The research behind it

~110 scripts of primary research are in [`scripts/`](scripts/); the findings documents are
the audit trail:

- [EDGE-PORTFOLIO.md](EDGE-PORTFOLIO.md) — the validated edges and the combined stack
- [ENGINE-TRIAL.md](ENGINE-TRIAL.md) — out-of-sample discipline: every parameter tuning
  failed validation; the untuned rules won. One borrowed rule (the credit canary) passed
  both windows and was adopted
- [qc_research/README.md](qc_research/README.md) — third-engine replay: QuantConnect at
  minute resolution with real fee/fill models, 2010-2026. Agrees with the research engine
  year-by-year (correlation +0.87) and lands above its period-matched twin — Sharpe 0.56
  vs 0.47 — under ~4x the research's cost assumption
- [HERD-REVERSAL.md](HERD-REVERSAL.md) — the capitulation edge, 33 years, surrogate-tested
- [PLAYBOOK.md](PLAYBOOK.md) — how this submission was assembled

**Tested and rejected, in writing**: Elliott waves (surrogates reproduce the "patterns"),
Fibonacci levels (rank 4th–14th of 28 arbitrary bands), intraday mean reversion (bid-ask
bounce), leveraged-ETF decay shorting (drag is real, drift swamps it), five macro overlays
(four contradicted out-of-sample), and our own first options design (negative expectancy
from quoting at the worst fill — found, measured, fixed). The negative results are load-
bearing: they are why the surviving rules can be trusted.

## Who this is for

Retail systematic traders who want agent autonomy with institutional discipline. The
pattern generalizes beyond trading: any domain where LLM confidence outruns LLM
correctness needs exactly this shape — proposals from the model, existence decided by
evidence-calibrated gates, and an audit trail that explains every refusal.

## Roadmap

1. **More edges through the same kill-test pipeline** — the earnings implied-move premium
   (measured at ~1.33× realized, t=3.95) is researched and next in line for gating.
2. **Graduation criteria for real capital** — pre-registered: 60 live sessions, realized
   Sharpe within 1σ of backtest, zero gate violations.
3. **The framework generalizes** — evidence-gated agents for any domain where LLM
   confidence outruns LLM correctness.

## Honest limits

- The equity edges are **risk-adjusted** edges; a 5-session P&L window is mostly noise and
  we do not pretend otherwise.
- Signals are rare by design (gates refuse most sessions). Flat is a position.
- Option-level expectancy could not be established from free historical data (no quote
  history exists on this tier). The options book therefore trades the same validated
  capitulation signal, priced from live quotes only, with position sizing capped by the
  measured friction — integral to the strategy, deliberately bounded by the evidence.

## Judging-criteria map

| criterion | where it lives |
| --- | --- |
| **P&L Performance** | paper account `PA3ZCDDOPR2N` (judges pull it); equity + open positions on the live dashboard |
| **Technology Implementation** | MCP-routed brokerage (`agent/mcp_gateway.py`), engine that reproduces its research record to 3 decimals (`agent/test_signal_engine.py`), 22-case gate suite, ensure-running supervisors (`host/run.py`) |
| **Creativity & Originality** | the research program itself: [EDGE-PORTFOLIO.md](EDGE-PORTFOLIO.md), [ENGINE-TRIAL.md](ENGINE-TRIAL.md) — including a rule mined from the trader's own prior strategies and validated before adoption |
| **Presentation & Execution** | this README, the live dashboard, the decision journal, [docs/WRITEUP.md](docs/WRITEUP.md) |
| **Social engagement** | build-in-public thread (see write-up) |

## Hackathon compliance

| requirement | where |
| --- | --- |
| Autonomous agent on Alpaca | `agent/scheduler.py` + session passes, unattended |
| **Uses Alpaca MCP server** | `agent/mcp_gateway.py` → `broker.py` routing, journaled |
| Options incorporated | bull put spreads via MLeg (≤4 legs, all shorts covered) |
| Fresh $100k paper account | `PA3ZCDDOPR2N` |
| Live application URL | [https://jpennin5.github.io/edgestack/](https://jpennin5.github.io/edgestack/) — stable redirect, auto-updated on every tunnel rotation |
| Write-up / video / deck | generated from the decision journal |

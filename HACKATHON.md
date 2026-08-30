# Alpaca AI Trading Agents Hackathon — brief & prep

Source: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
Researched 2026-08-25, updated 2026-08-29. The event page IS edited mid-event — re-check it.

## Facts

| | |
|---|---|
| Window | **2026-08-28 15:00 UTC → 2026-09-04 15:00 UTC** (7 days) |
| Status | **LIVE — kicked off Aug 28 15:00 UTC.** Kickoff stream + Discord Q&A already happened. |
| Registered | 2,407 (Aug 25) → **3,093 (Aug 29)** |
| Prizes | **$6,300 pool** ($6,000 cash + $300 credits). 1st $2,500 **+ $300 Featherless credits** · 2nd $1,500 · 3rd $1,000 · **2 × $500 social** + 1mo Algo Trader Plus per member |
| Tech partner | **Featherless AI** — $25 inference credits per participant, first-come first-served |
| Teams | 1–6 people, 18+ |
| Judging | P&L Performance · Technology Implementation · Creativity & Originality · Presentation & Execution · Social engagement |

## Hard requirements

1. Autonomous AI trading agent built on Alpaca's Trading API.
2. Must use Alpaca's **MCP server or CLI**.
3. **Every strategy must incorporate options trading.**
4. **Brand-new paper account** dedicated to this hackathon. Reused accounts are *not eligible for judging*.
5. Competition account starting balance set to **$100,000**.
6. **One-page write-up**: AI logic, risk gates, Alpaca infrastructure.
7. Submission payload: title · short + long description · tech/category tags · cover image ·
   video presentation · slide deck · **public GitHub repo** · demo platform · live application URL ·
   **Alpaca paper account ID** (judges use it to pull your P&L).
8. Optional: up to 5 X/LinkedIn post links tagging **@lablabai** and **@AlpacaHQ**.

## Three findings that should shape the entry

### 1. Only ~4.2 trading sessions remain, and raw P&L is a lottery

Friday Aug 28's session is already gone. Remaining: **Mon Aug 31 · Tue Sep 1 · Wed Sep 2 ·
Thu Sep 3** (full) · **Fri Sep 4, 09:30–11:00 ET** (deadline is 15:00 UTC = 11:00 ET).
Labor Day is Sep 7 — after the deadline, no holiday in window.

**The agent must be live and trading by Mon Aug 31 09:30 ET.** Today (Sat) and Sunday are
market-closed build days — that is the entire runway. A theta strategy also wants positions on
early, so slipping past Monday's open costs a disproportionate share of the P&L score.

Top raw P&L across the field will belong to whoever bought 0DTE calls and got lucky. That is not
a winnable race. The winnable position is a *positive, risk-gated, explainable* P&L that also
scores on the other four criteria.

### 2. Free-tier options data is 15 min delayed — but paper fills use real-time quotes

- Basic (free) plan: options = **indicative feed** (OPRA derivative), historical option queries
  capped to "latest 15 minutes". Stocks = IEX only, 200 API calls/min.
- Algo Trader Plus ($99/mo): full **OPRA**, all US stock exchanges (SIP), 10,000 calls/min.
- Paper orders are **simulated against real-time quotes**, with *no slippage* and *no check against
  NBBO size*. You can fill orders far larger than real liquidity.

Consequences:
- Strategies needing current option quotes (scalping, tight-spread arb) are structurally broken on
  free tier. Design for stale quotes: decide from the **underlying** (real-time on free IEX),
  use marketable limits with a staleness guard, hold days not minutes.
- Almost no one in the field will notice this. Naming it in the write-up and handling it explicitly
  is the cheapest credibility win available.
- $99 for one month of Algo Trader Plus is defensible against a $2,500 first prize. Note Alpaca is
  *giving it away* as the social prize — they assume the field is on free tier.

### 3. Determinism is the Technology Implementation score

Most of the field ships "Claude + MCP server + a prompt that says trade options." The differentiator
for brokerage engineers judging: **the LLM proposes, a deterministic rule engine disposes.**

Risk gates as code, outside the model: per-trade max loss · daily loss halt · defined-risk only
(never naked short) · buying-power floor · symbol whitelist · no-new-positions blackout near close ·
position count cap. Plus a **decision journal** logging every input, rationale, gate evaluation and
resulting order.

That journal is also the demo video and the slide deck — it pays into three criteria at once.

### 4. Featherless AI is the announced tech partner — cheap to integrate, and prize-linked

$25 of inference credits per participant (first-come, first-served, pay-per-request until exhausted),
and 1st place carries **+$300 in Featherless credits**. The page states: *"To be eligible for partner
prizes, the relevant partner technology must be integrated into a project submitted under the
hackathon challenge."*

It is a serverless host for open-source models behind an **OpenAI-compatible API**, so integration is
a base-URL swap. But $25 is small — do not put the main reasoning loop on it. The defensible use is a
bounded, parallel sub-task: news/sentiment scoring across the watchlist, or a cheap second-opinion
ensemble vote that a trade proposal must clear before it reaches the risk gates. That checks the
partner box *and* reads as real architecture rather than logo-stapling.

## Strategy posture (recommendation)

Over ~5 sessions, short premium wins far more often than it loses — the highest-probability route to
a positive P&L. **Defined-risk credit spreads** (put credit spreads / iron condors) on SPY / QQQ / IWM,
1–7 DTE, small size, hard daily loss gate. Tail risk is a gap; defined risk + sizing caps it.

Alternative — directional 0DTE — has better tail upside and ~10× the chance of finishing Sep 4 at
-60%, which torches the P&L score *and* contradicts the "risk gates" section of the write-up.

Level 3 options (multi-leg: spreads, straddles, strangles, condors) are **enabled by default on
paper accounts** — nothing to request.

## Local setup status (checked 2026-08-25)

- README / Dockerfile / compose are sound. Version pin `2.3.0` is current (released 2026-08-24).
- **Docker is NOT installed on this machine** — the documented container path does not work today.
  The `uvx` fallback does; smoke-tested OK.
- `.env` has no keys yet. Fine — the judged account has to be a fresh one anyway.
- Go 1.25.6 present → Alpaca CLI installs via `go install github.com/alpacahq/cli/cmd/alpaca@latest`.
  (CLI is Go, alpha preview, no confirmation prompts — every command executes immediately.)
- Toolsets: `account,trading,assets,options-data,stock-data` is right. `trading` is what carries
  `place_option_order` / `exercise_options_position`; `options-data` alone cannot trade.

## Open items

- [x] ~~Is pre-hackathon code allowed?~~ **Moot** — the event is live, so all build time is in-window.
- [ ] **Hosting.** Needs a live application URL *and* the agent must trade unattended for 5 sessions
      while you sleep. Cannot be this laptop. Decide a cloud host before kickoff.
- [ ] Buy Algo Trader Plus for the week? ($99)
- [ ] Solo or recruit a team (1–6)?

## Useful resources

- Alpaca MCP server — https://github.com/alpacahq/alpaca-mcp-server (v2, FastMCP+OpenAPI)
- Alpaca CLI — https://github.com/alpacahq/cli
- **Alpaca Skills** — https://github.com/alpacahq/alpaca-skills — drop-in SKILL.md files, incl.
  `trading-api/backtest`, `trading-api/paper-trading-mcp`, `trading-api/paper-trading-cli`.
  Drop into `.claude/skills/`. The backtest skill enables a strong slide:
  backtest → live result → divergence.
- Multi-agent trading writeup — https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca

---

# Competitive landscape (surveyed 2026-08-29)

**~36 public GitHub repos** tagged for this hackathon. Sampled 8 in depth.

## The field has converged on one architecture

Not "LLM trades on instructions", and not "LLM writes an algo then steps out". A third thing:

> **The LLM supplies opinion. Deterministic code supplies authority.**

The strategy is human-designed and hard-coded. The LLM picks direction / contract / strikes
*within* it. Python sizes the position, vetoes it, and executes. In their own words:

| Repo | The line |
|---|---|
| `matthewchung74/alpaca-gatekeeper` | "Claude decides what to trade. Deterministic Python decides whether that trade is allowed to exist." 14 gates. "The model never states a dollar risk figure." |
| `felixleung888/norman` | "Opinion is not permission." Separates *market opinion* from *capital authority*. |
| `kOkO34344/MultiAgentTrader` | "The most dangerous failure mode of an LLM trading system is a persuasive argument for an oversized position." `risk_guard.py` has no LLM calls and no network access. |
| `Ander-IbBi/alpaca-collar-overlay` | LLM demoted to **soft veto only; unknown reasons fail open**. Cross-checks the book against the CLI as a second auth path. |
| `owlsowo/finly-bot` | "It does not ask a language model to guess a contract or do payoff arithmetic." |
| `Sebastian0890/onenode-options-agent` | Proposer / Risk Officer / Hard Gate. |

Nobody credible is letting an LLM free-trade on instructions. The *strategy-authoring* pattern
(agent designs an algo offline, algo trades alone) is rare — `drone1337llc-lgtm/riskfirst` is
closest, with a walk-forward 4-fold OOS gate as a hard keep/kill on a lane. Alpaca's own reference
architecture goes further and puts a **human approval gate** between LLM and execution.

## Strategy space is converged too

Defined-risk options structures, near-universally:
put credit spreads (`ThetaGuard`) · collars (`alpaca-collar-overlay`) · credit+debit barbell
(`gatekeeper`) · CSP/covered-call wheel (`riskfirst`) · debit spreads (`finly-bot`).

## Bar-setters (already ahead of a standing start)

- **`gatekeeper`** — deployed live dashboard, Claude Opus 5, 14 gates, full journaling. Already
  reasoned that it should use **Thursday** expiry, not Friday, because the deadline is 11:00 ET Fri
  and Friday-expiry spreads would still be open and 0DTE at judging.
- **`ThetaGuard`** — macro blackouts already calendared: **Sep 1 JOLTS 10:00 ET**, **Sep 4 NFP 08:30 ET**.
  Forces liquidation before blackout. IV-rank floor ≥30, short delta −0.15/−0.20.
- **`finly-bot`** — technical paper, public dashboard, tagged "judge package" release, and an
  explicitly labelled *honest status* table separating implemented from not.

## Implication

The "LLM proposes / deterministic gates dispose / decision journal" plan is now **table stakes,
not a differentiator** — and so is "defined-risk credit spreads on SPY/QQQ". Anything winning has
to differentiate somewhere else: the evidence model, the execution quality under the 15-min data
delay, the calibration/backtest story, or presentation.

## Tracks — UNRESOLVED, verify in Discord

I earlier called these nonexistent. That was overconfident. Evidence now points the other way:

- `ThetaGuard` — *"Track: Income & Portfolio Overlay Agents"*
- `nilaymastaadmi` — *"Track 2: Volatility and Event"*
- `Ander-IbBi` — *"track Options Alpha Agents"*
- a search result independently described tracks for "options alpha, volatility trading, hedging and
  portfolio overlays"

Three competitors naming **consistently numbered** tracks is not coincidence. Against that: the live
page contains zero occurrences of "volatility", "overlay", "hedging" or "income", and only
**01 Options Alpha Agents** is populated — though its HTML carries `.alp-track-num` scaffolding
clearly built for a numbered set.

Most likely tracks were announced at the **Aug 28 kickoff stream / Discord** and never reflected on
the page, or were removed from it. **Ask in Discord before positioning the submission.**

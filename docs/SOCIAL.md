# Build-in-public — one LinkedIn post per day through judging (Social Engagement is scored)

Five posts, five form slots (`social_media_post_link_1..5`). After each post goes up,
edit the lablab submission and paste that post's URL into the next empty slot — same day.
Tag the **Alpaca** and **lablab.ai** company pages in every post (type @ and pick them so
they become real mentions). Attach an image where noted — posts with images travel further.

---

## Day 1 — Sun Aug 30 (submission live)
Attach: the cover (Downloads/EdgeStack-cover.png)

> Most AI trading agents lose money confidently — their rules come from vibes. Ask a model
> for a strategy and it gives you one: plausible, articulate, untested.
>
> For the @Alpaca × @lablab.ai AI Trading Agents Hackathon I built EdgeStack around one
> idea: evidence opens the door to opportunity. 33 years of data, three backtest engines
> forced to agree, and a public graveyard of every idea that failed. The agent journals
> every trade — and every refusal.
>
> Submission is live. Dashboard: https://jpennin5.github.io/edgestack/
> Repo: https://github.com/jpennin5/edgestack

## Day 2 — Mon Aug 31 (first live session) — READY TO POST, real numbers
Attach: `docs/day1_journal.png` (rendered from the actual 2026-08-31 journal entry —
rebuild with `python video/build_day1_card.py`). What happened: the trend gate passed
(+18.6%), the credit canary failed by 7 cents (HYG 79.78 vs SMA100 79.85), so the
equity gate closed and the core never went on; no capitulation signal came close
(deepest XLI −1.29 vs −2.50 trigger, 0.95x vs 1.40x volume floor). Equity flat at
$100,000, zero trades. Source: `journal/decisions.jsonl`, `journal/scheduler.log`.

> First live market session for EdgeStack in the @Alpaca × @lablab.ai hackathon.
>
> The agent stood down. One decision, zero trades, equity flat at $100,000 — and the
> reason is in the public journal to the penny.
>
> The 12-month trend gate was open: SPY +18.6%. The credit canary wasn't — HYG closed
> at 79.78 against its 100-day average of 79.85. Seven cents low. That one rule closed
> the equity gate, so the overnight SPY core never went on. The capitulation sleeve
> didn't come close either: the deepest stretch in the universe was XLI at −1.29
> against a −2.50 trigger, on 0.95x volume against a 1.40x floor.
>
> Seven cents is exactly the margin you talk yourself past. But deleting that canary
> costs 0.08–0.25 Sortino across two disjoint validation windows — and a rule you
> overrule on a quiet Monday isn't a rule, it's a suggestion.
>
> Most trading-agent demos show you the trades. The refusals are where the discipline
> lives. The journal auto-commits to the repo after every session, so you can check
> this one yourself. https://jpennin5.github.io/edgestack/

## Day 3 — Tue Sep 1 (retiring a live rule without touching anything else)
The graveyard angle was already used, so Day 3 is the engineering story from today:
hot-swapping a rule on a RUNNING trading agent mid-competition. Shipped as commit
75cd343 (signal_engine + risk_gates + spread_builder + 2 new gate tests).
Attach: `docs/day3_retire.png` (rebuild with `python video/build_day3_card.py`).

> Today I changed a rule on a live trading agent while it was running. The
> interesting part is everything that didn't happen.
>
> EdgeStack has traded a "MEDIUM" tier since day one: capitulation on ≥2.5x normal
> volume. It shipped with a t-statistic of 3.5–4.0, which reads as decisive. It
> isn't. That number assumes every signal is an independent event, and mine aren't
> — the 27 signal days cluster in 2015, 2018 and 2020, and several "events" are one
> panic hitting several ETFs at once. Cluster the statistic by signal day, re-check
> with a block bootstrap, and t falls to about 1.0. Noise wearing a good suit.
>
> So I retired it mid-competition, on the running system. Three properties made
> that safe to do on a trading day:
>
> It can only refuse. The change flips a `tradeable` flag — it cannot open a
> position or resize one. The worst case is a trade that doesn't happen.
>
> Open positions still manage out. Exit proposals get rebuilt from the journal and
> default to tradeable, so anything opened under the old rule is still managed to
> its exit. You retire a rule going forward, never retroactively — otherwise you
> strand real money mid-trade.
>
> The refusal is visible. It isn't quietly sized to zero; it's refused at the gate
> and the reason lands in the public journal: "tier MEDIUM retired by clustered-t
> audit." An unexplained absence is indistinguishable from a bug.
>
> 24 gate tests — two of them written today — pin the behaviour so a later edit
> can't quietly revive it. And the old numbers stay in the table on purpose: the
> journal should show what I believed and what killed it.
>
> Deleting your own edge is not a setback. It's the job.
>
> @Alpaca × @lablab.ai AI Trading Agents Hackathon.
> https://github.com/jpennin5/edgestack

## Day 4 — Wed Sep 2 (what survived + the third engine)

> EdgeStack trades only what survived the attempt to kill it: long SPY overnight-only
> (Sharpe 0.89 vs 0.05 intraday), a capitulation basket across 7 ETFs (+1.42% per event,
> t=4.27 over 33 years), and a credit canary mined from my own older strategies — adopted
> only after it passed two disjoint validation windows (0.65 → 1.02 Sharpe).
>
> Then the part I care about most: an independent QuantConnect replay, scored against a
> pre-registered expectations table, agreed with my research engine year by year
> (correlation +0.87) and beat its period-matched twin under ~4x my assumed costs.
>
> Three engines, one record. @Alpaca × @lablab.ai hackathon.
> https://github.com/jpennin5/edgestack

## Day 5 — Thu Sep 3 (the machine — closer before judging)
Attach: the cover with gate callouts, or a journal screenshot

> How EdgeStack actually runs, before tomorrow's judging:
>
> Orders and account reads route through @Alpaca's MCP Server v2, every route journaled.
> The production engine reproduces the 33-year research record to three decimals. A
> 24-case test suite requires the RIGHT gate to refuse in every scenario. And the
> append-only decision journal explains every trade — and every refusal — in public.
>
> The LLM proposes. The evidence decides. That's the whole design.
>
> @lablab.ai judging is tomorrow. https://jpennin5.github.io/edgestack/ ·
> https://github.com/jpennin5/edgestack

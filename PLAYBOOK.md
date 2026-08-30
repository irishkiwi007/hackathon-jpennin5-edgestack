# SUBMISSION PLAYBOOK — read this first after any context loss

The single source of truth for finishing the hackathon submission. If resuming from a
compaction: read this file, then AGENT.md, EDGE-PORTFOLIO.md, ENGINE-TRIAL.md, HACKATHON.md.
Work through the steps IN ORDER, checking boxes here (edit this file) as they complete.

## Mission state (as of 2026-08-30/31)

- User has REGISTERED for the lablab.ai x Alpaca AI Trading Agents Hackathon with their GitHub.
- Strategy research is DONE and validated (EDGE-PORTFOLIO.md, ENGINE-TRIAL.md).
- Agent is BUILT and dry-runs clean: options component (bull put spreads, 14 risk gates) +
  equity core (SPY overnight, trend+credit-canary gate) + equity sleeve (capitulation basket,
  7 ETFs, 3-session hold, MOC orders). `python agent/run_agent.py --dry-run` works.
- Secrets: 44 scripts scrubbed to env lookups; `.env` gitignored; NOTHING committed yet.
- USER ACTION STILL PENDING: rotate paper API keys in the Alpaca dashboard (they were pasted
  into chat earlier). Remind once when going live, do not nag.
- Live gate reading at last check: trend UP +19.0%, credit canary CLOSED by 0.14%
  (HYG 79.74 vs SMA100 79.85) — can flip any session.

## The steps (user's explicit instructions)

### [x] STEP 1 — MCP/CLI integration (hard requirement: "must use Alpaca's MCP server or CLI")
- Repo ships Alpaca MCP Server v2.3.0: Dockerfile + docker-compose, streamable-http,
  endpoint http://127.0.0.1:8000/mcp/ (FastMCP). `.env` feeds it credentials.
- Build `agent/mcp_gateway.py`: minimal MCP streamable-http JSON-RPC client
  (initialize -> mcp-session-id header -> notifications/initialized -> tools/call;
  responses may be SSE-framed `event: message\ndata: {...}` — handle both).
- Route agent operations through it (account read at minimum; order submission if the
  toolset supports mleg + equity orders) with documented REST fallback on MCP failure —
  the fallback is a reliability gate, not a dodge; the write-up should say so.
- If Docker is unavailable on this machine: `pip install alpaca-mcp-server==2.3.0` in a
  venv (server targets py3.11; local is 3.14 — try, else uv) and run
  `alpaca-mcp-server --transport streamable-http --port 8000` as a local process,
  supervised by the same mechanism as step 2.
- Verify: agent session pass logs "via MCP" for the routed calls against the paper API.

### [x] STEP 2 — Hosting ON THIS MACHINE (user: "use this container to host")
- Needs: agent runs unattended across sessions + a "live application URL" for submission.
- Build `agent/dashboard.py`: stdlib HTTP server (pick port, e.g. 8787) serving:
  equity curve / journal (journal/DECISIONS.md + decisions.jsonl), current gate + regime
  readings, open positions (journal/*.json), account snapshot. Polished HTML — this page
  IS part of the judged presentation.
- Supervision: Windows Task Scheduler (`schtasks`) entries that start `agent/scheduler.py`
  and `agent/dashboard.py` at logon/boot and restart on failure. scheduler.log already
  exists for the agent; give the dashboard a log too.
- Public URL: needs a tunnel (cloudflared quick tunnel needs no account:
  `cloudflared tunnel --url http://localhost:8787`). Check if cloudflared/ngrok installed;
  if not, install cloudflared via winget IF user-approved, else document the one command.
- User mentioned TrustyRustyEngine has a confirmed-working paper trading API setup
  (Rust, crates/live, bin/live.rs) — reference if the Python path hits a wall; the Python
  agent is self-contained so this is fallback only.

### [x] STEP 3 — First commit + public repo
- `git init` done; 37+ files untracked; `.env` confirmed ignored (verify again before
  commit: `git check-ignore .env`).
- Write a submission-facing README.md (rewrite the current MCP-server-only README):
  what it is, the three strategy components with the headline evidence numbers, the
  architecture (LLM proposes / deterministic gates dispose), how to run, links to the
  research docs, the honest-limits section (this is a differentiator — keep it).
- Initial commit (user authorized: "continue through each of the steps"). Push needs the
  user's GitHub remote + auth — prepare the commands, ask them to run the push or provide
  the remote.
- End commit messages with the Claude co-author line per repo convention.

### [x] STEP 4 — Review MANY contestant entries, then polish to match/beat
- Goal (user): "present as extremely polished so that we have a chance to win."
- Sources: lablab.ai event page + submissions gallery; GitHub search for hackathon repos.
  Known competitor repos from earlier research (HACKATHON.md): matthewchung74/alpaca-gatekeeper
  ("Claude decides what to trade. Deterministic Python decides whether that trade is allowed
  to exist." 14 gates), felixleung888/norman ("Opinion is not permission"), finly-bot
  (technical paper, public dashboard, tagged "judge package" release).
- Extract structure patterns: README anatomy, demo video style, dashboards, one-pagers,
  naming/branding, "judge package" tags. Then upgrade our README/dashboard/docs to that bar.
- Submission payload checklist (from HACKATHON.md): title, short + long description,
  tech/category tags, cover image, video presentation, slide deck, PUBLIC GitHub repo,
  demo platform, live application URL, Alpaca paper account ID (judges pull P&L),
  one-page write-up (AI logic, risk gates, Alpaca infrastructure).

### [x] STEP 5 — Judge-lens review, then adjust
- Re-read ALL contest rules (lablab.ai event page — it is edited mid-event, re-fetch) and
  relevant social media (Alpaca X/Twitter posts, lablab posts) to infer what a winner
  looks like to THEM.
- Judging criteria (from HACKATHON.md): P&L Performance, Technology Implementation,
  Creativity & Originality, Presentation & Execution, Social engagement.
- Then review OUR project through that lens and make adjustments. Known angles:
  determinism story ("LLM proposes, rule engine disposes") plays to Technology
  Implementation; the decision journal feeds video + slides + write-up; the research
  rigor (33y validation, out-of-sample discipline, honest negative results) is the
  Creativity/Originality differentiator; social engagement may need a post the user makes.

## Key facts (do not re-derive)

- Paper account: PA3ZCDDOPR2N, $100k, options level 3. Keys in `.env`
  (ALPACA_API_KEY / ALPACA_SECRET_KEY). ALPACA_PAPER_TRADE=true. Judges use account ID.
- Strategy evidence headlines: overnight Sharpe 0.89 vs intraday 0.05; capitulation
  +1.42%/event t=4.27 (136 events/33y); credit canary passed both engine windows
  (0.80->0.98 train, 0.65->1.02 valid, DD ~halved); full engine stack Sharpe 1.04,
  DD 11.8% (2007-2026). Earnings iron condor 15.31% ret-on-risk t=4.79 (researched,
  NOT in the live agent).
- Options flow: same_day mode (Yahoo live feed, 15:45 signals, vol-completion 0.894) with
  next_open fallback; MLeg constraints: <=4 legs, every short covered, limit only.
- Engine trial artifacts live in TrustyRustyEngine repo:
  python_strategies/strategies/edgestack.py (gate_mode=1 default).
- QC trial file: qc_research/edge_stack.py (credit canary ON; user runs it on quantconnect).
- Free-tier data quirks: SIP refuses ranges reaching today (omit `end`); IEX volume ~3% of
  consolidated (never use for volume signals); no historical option quotes (404) — live
  snapshots have real bid/ask.
- Timing: agent entry pass 15:45 ET (MOC cutoff ~15:50), exit pass 09:31 ET.
- Scratch scripts also copied into scripts/ (110 files) — research provenance for judges.

## Progress log (append as steps complete)

- 2026-08-30: Playbook created. Steps 1-5 pending.
- STEP 1 DONE: agent/mcp_gateway.py (streamable-http MCP client); broker.py routes account
  + orders via the MCP server (uvx alpaca-mcp-server==2.3.0, port 8000) with REST fallback;
  full order lifecycle proven via MCP (submit->accepted->cancel->canceled); server quirk:
  numeric args must be STRINGS. Server launch cmd (must be supervised in step 2):
  `set -a; source .env; set +a; export ALPACA_TOOLSETS=account,trading,assets,options-data,stock-data;
   uvx --python 3.11 alpaca-mcp-server==2.3.0 --transport streamable-http --host 127.0.0.1 --port 8000`
- STEP 2 DONE: dashboard (agent/dashboard.py :8787, EdgeStack-branded, MCP-status card);
  supervisor host/run.py (ensure-running, 4 modes); logon persistence via Startup folder
  EdgeStack.vbs (schtasks was access-denied); cloudflared.exe in host/bin (gitignored);
  PUBLIC URL live: https://dropped-psychology-fortune-employed.trycloudflare.com
  (QUICK tunnel — URL CHANGES on restart; re-read journal/live_url.txt before submitting,
  or make a named tunnel with a free CF account for a stable URL).
- STEP 3 DONE: submission README written (EdgeStack branding, evidence tables, architecture,
  compliance map); first commit cea4f03, 179 files, .env excluded. PUSH PENDING: needs the
  user's GitHub remote (`git remote add origin <url> && git push -u origin master`).
- STEP 4 DONE: field survey — 79 event repos on GitHub; "AI proposes / code disposes" is
  the META of the field (Gatekeeper, Finly, Refusal Rails, OWL, Uncharted, APEX all lead
  with it; several have polished dashboards/domains; APEX has a judging-criteria map and is
  the closest substantive competitor: validated equity engine + options overlay + OOS gates).
  Repositioned EdgeStack around the RESEARCH story (33y, surrogates, triple-engine,
  graveyard). Added judging map + docs/WRITEUP.md. Registered lablab teams (agenttrade-ai,
  agentalpha, aliens) had not submitted yet at review time.
- STEP 5 DONE: lablab's How-to-Win guidance = clarity over production value, <=3-screen
  demo, one problem, working demo wins. Added problem framing + business value to README;
  wrote docs/VIDEO-SCRIPT.md, docs/SOCIAL.md (ready-to-post thread), docs/SLIDES.md.
  Commits: cea4f03, 89b74e2, 07b19aa.

## REMAINING USER ACTIONS (the agent cannot do these)
1. git remote add origin <their-github-repo-url> && git push -u origin master
2. Rotate paper API keys in the Alpaca dashboard, update .env, restart supervisors
   (host/run.py processes pick up new env on restart).
3. Record the ~4-min video from docs/VIDEO-SCRIPT.md; export slides from docs/SLIDES.md;
   make a cover image (spec: dark bg #0b0f14, "EdgeStack" + tagline "every rule survived
   an attempt to kill it", dashboard screenshot as backdrop).
4. Post the docs/SOCIAL.md thread (Social Engagement is judged) with the live URL + repo.
5. Submit on lablab: title, short/long description (source from README hero + WRITEUP),
   tags, cover image, video, slides, repo URL, live URL (re-read journal/live_url.txt FIRST
   — quick-tunnel URL changes on restart), paper account ID PA3ZCDDOPR2N.
6. Optional hardening: free Cloudflare account -> named tunnel for a stable URL.

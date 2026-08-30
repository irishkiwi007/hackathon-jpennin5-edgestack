# Sentiment and news — what's actually available

Direct answers to: does Alpaca have sentiment, and can the agent scrape message boards live?

---

## 1. Alpaca has NEWS, not sentiment — but the news is good

`data news` / `GET /v1beta1/news`. Source is **Benzinga**. No sentiment scoring — raw articles.

| Property | Finding |
|---|---|
| Cost | **Free tier** ✓ |
| **Archive depth** | **Back to at least 2016** — verified by direct probe at 2016/2018/2020/2022/2024/2025/2026 |
| Volume | **396 articles in one RTH session = ~61/hour** |
| Symbol tagging | **392 of 396** tagged with ≥1 symbol |
| Full body text | ✓ via `include_content` — 5,000-char articles, not just headlines |
| Fields | headline, summary, content, author, symbols, source, created_at, url |

Top-covered symbols in a sample session: NVDA 37, CRM 30, OKTA 26, CRWD 20, SPY 19.

**This is the important find: ten years of timestamped, symbol-tagged, full-text news, free.**
Unlike every other data source in this project, it is deep enough to backtest.

> ⚠️ **CLI bug:** `alpaca data news` returns inconsistent results with `--start`/`--end` — a 4-day
> range returned 0 articles while a 1-day range inside it returned 2, and market-wide queries
> without `--symbols` returned 0. **Use the REST endpoint directly.** Verified working with
> pagination via `page_token`.

## 2. Message boards — StockTwits is open, Reddit effectively is not

### StockTwits — **works, no auth, free**

`https://api.stocktwits.com/api/2/streams/symbol/{SYMBOL}.json` → HTTP 200, no API key.

- 30 messages per page, `max=<id>` for pagination
- **Native bullish/bearish tags**: ~17 of 30 messages carry `entities.sentiment.basic`
- Live: newest message timestamped within seconds of the request

> ⚠️ **Not backtestable.** Twelve pages of pagination reached only ~10 hours back (360 messages,
> and that was over a weekend when traffic is light — a trading day would cover far less). There is
> no archive. You can collect it forward from today, but you cannot reconstruct what sentiment
> looked like at 10:30am on any past date.

**That is the same trap this project has hit repeatedly: a live-only signal that cannot be
validated before it is deployed.** Everything tested that way so far has failed on contact with a
real backtest.

### Reddit — effectively closed

Free tier is nominally 100 queries/min for public data, but **self-service OAuth registration
closed in late 2025** under the Responsible Builder Policy; new tokens require manual approval
through a contact form. Commercial access is $12,000/month. Academic access is a multi-week
application. Not a realistic path.

### X/Twitter — paid tiers only, not evaluated further.

## 3. Scraping in real time — feasible, with caveats

The agent *can* poll StockTwits' public JSON endpoint during the session. Practical points:

- No auth, no documented rate limit, but be conservative — one poll per symbol per 30–60s
- Only ~57% of messages carry a sentiment tag; the rest need scoring
- **This is where the Featherless AI partner credits fit.** $25/participant of open-model
  inference is well suited to classifying a stream of short messages, and it gives the partner
  integration a real function rather than a logo. Scoring headlines from the Alpaca news feed is
  the same job and is backtestable.
- Respect robots.txt and terms; the public JSON API is the sanctioned surface, not HTML scraping.

## 4. Recommended split

| Purpose | Source |
|---|---|
| **Backtesting and validation** | **Alpaca/Benzinga news** — 10 years, timestamped, symbol-tagged |
| **Live enrichment** | StockTwits stream, scored by an open model via Featherless |
| Not worth pursuing | Reddit (closed), X (paid) |

Build and validate on the news archive. Treat StockTwits as an unvalidated overlay, and size it
accordingly — or leave it out of the trading decision and use it only for the write-up narrative.

---

# 5. Does the news actually predict anything? — tested

5 symbols, 2026-05-01 → 2026-08-28: **6,686 articles** against 367k minute bars.
`scripts/newsstudy.py`, `scripts/newsclean.py`.

## Headlines report; they do not predict

Absolute move in bp, measured around each article's timestamp:

| Symbol | n | −30m..−5m | **−5m..0** | **0..+5m** | +5m..+30m |
|---|---|---|---|---|---|
| NVDA | 2203 | 26.79 | **12.28** | **12.08** | 26.29 |
| TSLA | 1200 | 24.13 | **11.78** | **9.85** | 22.43 |
| AAPL | 994 | 19.80 | **10.59** | **8.68** | 19.61 |
| AMD | 640 | 52.52 | **22.27** | **22.09** | 49.73 |
| SPY | 2615 | 9.39 | **4.88** | **4.07** | 9.21 |

**The five minutes before a headline are as volatile as the five after — slightly more, in every
single symbol.** The distribution is essentially symmetric around the print. A Benzinga headline is
not an information shock; it is coincident with, or lagging, activity already underway.

## News does not predict elevated volatility either

Post-news 30-minute move vs a **time-of-day-matched** baseline (news clusters at the open, when
volatility is naturally high — without this control the result is badly misleading):

| Symbol | post-news | baseline | ratio | t |
|---|---|---|---|---|
| NVDA | 31.56b | 31.31b | 1.01 | 0.28 |
| TSLA | 29.55b | 33.02b | **0.89** | **−3.10** |
| AAPL | 24.59b | 21.21b | **1.16** | **2.61** |
| AMD | 59.91b | 58.93b | 1.02 | 0.30 |
| SPY | 10.06b | 10.24b | 0.98 | −0.89 |

Mixed and mostly null. TSLA is significantly *calmer* after news than at the same clock time on an
ordinary day. **The "buy a straddle on the news" idea does not survive the time-of-day control.**

## The one large result was an artifact

Raw analysis showed AAPL `corr(pre-5m, post-30m) = +0.445` — a huge effect. With ~12 articles a day,
article A's 30-minute forward window overlaps article B's 5-minute lookback, which manufactures
correlation.

Control: keep only **isolated** articles, with no other article for that symbol within ±60 minutes.

| Symbol | corr30 **all** | corr30 **isolated** | n (all → iso) |
|---|---|---|---|
| **AAPL** | **+0.445** | **−0.097** | 994 → 327 |
| SPY | −0.015 | +0.189 | 2615 → 157 |
| TSLA | −0.019 | +0.154 | 1200 → 400 |
| AMD | +0.076 | +0.154 | 641 → 269 |
| NVDA | −0.077 | −0.125 | 2205 → 305 |

**AAPL's +0.445 collapsed to −0.097 and flipped sign.** Pure clustering artifact.

What remains is incoherent: three symbols positive, two negative, marginal t-statistics, opposite
signs on similar mega-cap tech names. That is the same noise signature seen throughout this project.

## What this does and does not rule out

**Ruled out:** *article arrival* as a signal. Timing, volatility, and pre-move continuation all fail.

**Not tested:** the **content**. Everything above treats every article identically — a Federal
Reserve decision and *"Pentagon Is in Talks With Venezuelan Mogul"* (a real headline tagged to SPY)
count the same. Scored sentiment, or filtering to high-impact categories such as earnings,
guidance, analyst actions and M&A, is a genuinely different hypothesis and remains open.

**That untested gap is precisely where the Featherless credits belong** — classifying 10 years of
archived headlines is backtestable, unlike anything StockTwits can offer.

Frequency, incidentally, is not the constraint: ~61 articles/hour market-wide is far more than the
"more than once or twice a day" requirement. Signal quality is the constraint.

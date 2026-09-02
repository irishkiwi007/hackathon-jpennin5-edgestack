# engine/ — borrowed from TrustyRustyEngine

Copied on 2026-09-02 from the `trusty-lab` container (`/opt/trustyrusty`, the same tree the
production `trustyrusty` container runs), so the Backtest tab and the Live Manager use the
engine the research record was produced on, not a re-implementation.

| here | there | what |
| --- | --- | --- |
| `bridge/strategy_interface.py` | `bridge/strategy_interface.py` | the isomorphic strategy contract (`TrustyStrategy`, `StrategyConfig`, `BarSnapshot`). `bridge/__init__.py` is EdgeStack's own two-liner: the container's also exports the QuantConnect shim, which is not borrowed |
| `run_backtest.py` | `python_strategies/run_backtest.py` | bar-by-bar runner: T+1 open fills, 5+5 bps costs, metrics, SPY benchmark. **One addition**: the result carries `final_weights`, `final_signals`, `last_bar_date`, `universe` so the live manager can drive a deployment from the same code path |
| `inspect_strategy.py` | `python_strategies/inspect_strategy.py` | name / universe / lookback / params of a strategy file |
| `strategies/edgestack*.py`, `strategies/bench_spy_hold.py` | `python_strategies/strategies/` | **only** the submitted strategy's lineage and the buy-and-hold benchmark |
| `data/*.csv` | `data/historical/*.csv` | Yahoo daily OHLCV (+ `adj_close`) for the eight symbols those two strategies reference; `SPYON` is the synthetic overnight index |

`host/sync_engine.ps1` re-pulls all of it. The live manager appends completed sessions to the
CSVs from Alpaca SIP bars (`adjustment=all`, `adj_close = close` on the appended tail).

## What is deliberately NOT here

The operator's own strategies — and the agent's candidates derived from them — run live
money elsewhere and stay in the container. They are excluded from this repo by `.gitignore`,
are not copied by `host/sync_engine.ps1`, and are never named on the public research page
(`host/lab_page.py` derives the private set from the lab journal and withholds those cards).
A local working copy may still hold them untracked, which is why the ignore rules are an
allowlist: new private strategies are excluded by default, and a new `edgestack*` one is
published only because its name says so.

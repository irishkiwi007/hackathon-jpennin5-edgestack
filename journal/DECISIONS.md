# Decision journal

Capitulation-reversal strategy. The model proposes; `risk_gates.py` disposes.
Every session is recorded, including the majority that do not trade.

## 2026-09-02

### ADR — Backtest tab and Live Manager borrow the TrustyRustyEngine, not a re-implementation

**Decision.** `engine/` is a verbatim copy of the container engine's strategy contract, bar-by-bar runner, inspector, the lab's strategy files and the CSV history they reference (`engine/BORROWED.md`). The dashboard's Backtest tab runs that runner as a subprocess exactly as the Rust API server does. The Live Manager (`agent/live_manager.py`) ports the engine's Live Manager model: pinned modules, `equity × alloc%` slices, a `max_drawdown_kill` rule with bar-resolution semantics (the HWM only advances on observations at the rule's resolution), shadow deployments, a global kill switch, and orders through the same Alpaca MCP route as the competition agent. The runner gained one addition — `final_weights` in its result — so a deployment is driven by the same code path that backtested it.

**Why.** One engine, one fill model, one set of numbers: a candidate that adopts in the lab, backtests here, and deploys here is the same strategy at every step.

**Safety.** The page is on the open internet through the tunnel, so every write (run a backtest, deploy, stop, arm the kill switch) requires the operator key in `journal/operator_token` (generated locally, git-ignored). Account profiles hold env-var NAMES, never secrets, and are paper-only by construction. A live deployment on the competition account requires an explicit confirmation because it changes the judged P&L; shadow is the default mode. A deployment flattens only positions it put on itself.

## 2026-09-02
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

**Actions**

- fill_reconciled: SGOV buy x697 (bills_entry) ref 100.41 -> fill 100.41 = +0.50bps vs sizing price
- slippage_running: 1 fills measured, mean +0.50bps vs sizing price (overnight-core breakeven is 0.3-0.6bps/night round trip)

> exit management pass

---

## 2026-09-01
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

**Actions**

- core_gated: trend UP (12m +18.0%) | credit DETERIORATING (HYG 79.07 vs SMA100 79.83)
- bills_enter: SGOV x697 MOC (~$69,982) while the gate is shut, 3m yield 3.90% (FRED DGS3MO 2026-08-28), order 49289eaf

<details><summary>Closest to firing</summary>

| symbol | stretch | volume | blocked by |
|---|---|---|---|
| XLI | -1.76 | 1.29x | stretch -1.76 > -2.5; volume 1.29x < 1.4x (no capitulation) |
| XLY | -1.49 | 0.87x | stretch -1.49 > -2.5; volume 0.87x < 1.4x (no capitulation) |
| XLF | -1.38 | 0.78x | stretch -1.38 > -2.5; volume 0.78x < 1.4x (no capitulation) |
| HYG | -1.34 | 1.29x | stretch -1.34 > -2.5; volume 1.29x < 1.4x (no capitulation) |
| GDX | -1.29 | 0.75x | stretch -1.29 > -2.5; volume 0.75x < 1.4x (no capitulation) |
| XLP | -1.28 | 0.86x | stretch -1.28 > -2.5; volume 0.86x < 1.4x (no capitulation) |
| IWM | -1.23 | 1.12x | stretch -1.23 > -2.5; volume 1.12x < 1.4x (no capitulation) |
| XLB | -1.21 | 1.05x | stretch -1.21 > -2.5; volume 1.05x < 1.4x (no capitulation) |

</details>

> Yahoo completed sessions only (16 symbols); no live meta -> prior-session signal, next-open entry

---

## 2026-09-01
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

> exit management pass

---

## 2026-08-31
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

**Actions**

- core_gated: trend UP (12m +18.6%) | credit DETERIORATING (HYG 79.78 vs SMA100 79.85)

<details><summary>Closest to firing</summary>

| symbol | stretch | volume | blocked by |
|---|---|---|---|
| XLI | -1.29 | 0.95x | stretch -1.29 > -2.5; volume 0.95x < 1.4x (no capitulation) |
| IWM | -0.95 | 1.00x | stretch -0.95 > -2.5; volume 1.00x < 1.4x (no capitulation) |
| XLV | -0.83 | 0.66x | stretch -0.83 > -2.5; volume 0.66x < 1.4x (no capitulation) |
| XLB | -0.73 | 0.91x | stretch -0.73 > -2.5; volume 0.91x < 1.4x (no capitulation) |
| XLU | -0.65 | 1.37x | stretch -0.65 > -2.5; volume 1.37x < 1.4x (no capitulation) |
| EFA | -0.60 | 0.65x | stretch -0.60 > -2.5; volume 0.65x < 1.4x (no capitulation) |
| XLY | -0.56 | 0.65x | stretch -0.56 > -2.5; volume 0.65x < 1.4x (no capitulation) |
| GDX | -0.55 | 0.54x | stretch -0.55 > -2.5; volume 0.54x < 1.4x (no capitulation) |

</details>

> Yahoo completed sessions only (16 symbols); no live meta -> prior-session signal, next-open entry

---

## 2026-08-31
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

> exit management pass

---

## 2026-08-30
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

**Actions**

- core_gated: trend UP (12m +19.0%) | credit DETERIORATING (HYG 79.74 vs SMA100 79.85)

<details><summary>Closest to firing</summary>

| symbol | stretch | volume | blocked by |
|---|---|---|---|
| XLI | -0.86 | 1.36x | stretch -0.86 > -2.5; volume 1.36x < 1.4x (no capitulation) |
| XLV | -0.76 | 0.57x | stretch -0.76 > -2.5; volume 0.57x < 1.4x (no capitulation) |
| IWM | -0.69 | 1.14x | stretch -0.69 > -2.5; volume 1.14x < 1.4x (no capitulation) |
| XLE | -0.46 | 0.79x | stretch -0.46 > -2.5; volume 0.79x < 1.4x (no capitulation) |
| GDX | -0.41 | 1.53x | stretch -0.41 > -2.5 |
| EFA | -0.38 | 1.51x | stretch -0.38 > -2.5 |
| XLP | -0.31 | 0.76x | stretch -0.31 > -2.5; volume 0.76x < 1.4x (no capitulation) |
| XLB | -0.31 | 1.27x | stretch -0.31 > -2.5; volume 1.27x < 1.4x (no capitulation) |

</details>

> dry run; Yahoo completed sessions only (16 symbols); outside RTH -> prior-session signal, next-open entry

---

## 2026-08-30
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

<details><summary>Closest to firing</summary>

| symbol | stretch | volume | blocked by |
|---|---|---|---|
| XLI | -0.86 | 1.36x | stretch -0.86 > -2.5; volume 1.36x < 1.4x (no capitulation) |
| XLV | -0.76 | 0.57x | stretch -0.76 > -2.5; volume 0.57x < 1.4x (no capitulation) |
| IWM | -0.69 | 1.14x | stretch -0.69 > -2.5; volume 1.14x < 1.4x (no capitulation) |
| XLE | -0.46 | 0.79x | stretch -0.46 > -2.5; volume 0.79x < 1.4x (no capitulation) |
| GDX | -0.41 | 1.53x | stretch -0.41 > -2.5 |
| EFA | -0.38 | 1.51x | stretch -0.38 > -2.5 |
| XLP | -0.31 | 0.76x | stretch -0.31 > -2.5; volume 0.76x < 1.4x (no capitulation) |
| XLB | -0.31 | 1.27x | stretch -0.31 > -2.5; volume 1.27x < 1.4x (no capitulation) |

</details>

> dry run; Yahoo completed sessions only (16 symbols); outside RTH -> prior-session signal, next-open entry

---

## 2026-08-30
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

> exit management pass

---

## 2026-08-30
Equity $100,000 · open positions 0

**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.

<details><summary>Closest to firing</summary>

| symbol | stretch | volume | blocked by |
|---|---|---|---|
| XLI | -0.86 | 1.35x | stretch -0.86 > -2.5; volume 1.36x < 1.4x (no capitulation) |
| XLRE | -0.84 | 0.76x | stretch -0.84 > -2.5; volume 0.76x < 1.4x (no capitulation) |
| VNQ | -0.80 | 0.75x | stretch -0.80 > -2.5; volume 0.75x < 1.4x (no capitulation) |
| XLV | -0.76 | 0.57x | stretch -0.76 > -2.5; volume 0.57x < 1.4x (no capitulation) |
| IWM | -0.69 | 1.14x | stretch -0.69 > -2.5; volume 1.14x < 1.4x (no capitulation) |
| IBB | -0.49 | 0.90x | stretch -0.49 > -2.5; volume 0.90x < 1.4x (no capitulation) |
| FXI | -0.49 | 0.95x | stretch -0.49 > -2.5; volume 0.95x < 1.4x (no capitulation) |
| XLE | -0.46 | 0.79x | stretch -0.46 > -2.5; volume 0.79x < 1.4x (no capitulation) |

</details>

> dry run; Yahoo completed sessions only (33 symbols); outside RTH -> prior-session signal, next-open entry

---

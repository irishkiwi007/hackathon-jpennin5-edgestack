"""Decision journal.

Every session writes one record whether or not it trades - and most sessions will not trade,
because the signal fires roughly 0.15 times a day across the universe. A journal that only
records fills cannot show that the gates were doing anything, so no-trade days record the
near-misses and the specific reason each candidate was refused.

Append-only JSONL, one record per run, plus a human-readable markdown rendering for the demo.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Any

JOURNAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "journal")
JSONL_PATH = os.path.join(JOURNAL_DIR, "decisions.jsonl")
MD_PATH = os.path.join(JOURNAL_DIR, "DECISIONS.md")


def _ensure_dir() -> None:
    os.makedirs(JOURNAL_DIR, exist_ok=True)


def record(session_date: str,
           account: dict[str, Any],
           signals: list[dict],
           proposals: list[dict],
           gate_results: list[dict],
           actions: list[dict],
           near_misses: list[dict],
           notes: str = "") -> dict:
    """Write one session record. Returns the record for immediate display."""
    _ensure_dir()
    rec = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_date": session_date,
        "strategy": "capitulation-reversal / bull put spread",
        "account": account,
        "signals_fired": signals,
        "proposals": proposals,
        "gate_results": gate_results,
        "actions_taken": actions,
        "near_misses": near_misses,
        "notes": notes,
    }
    with open(JSONL_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    _render_markdown()
    return rec


def _render_markdown() -> None:
    """Rebuild the readable journal from the JSONL, newest first."""
    if not os.path.exists(JSONL_PATH):
        return
    records = []
    with open(JSONL_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    records.reverse()

    out = ["# Decision journal",
           "",
           "Capitulation-reversal strategy. The model proposes; `risk_gates.py` disposes.",
           "Every session is recorded, including the majority that do not trade.",
           ""]
    for r in records:
        out.append(f"## {r['session_date']}")
        acct = r.get("account", {})
        if acct:
            out.append(f"Equity ${float(acct.get('equity', 0)):,.0f} · "
                       f"open positions {acct.get('open_positions', 0)}")
        out.append("")

        if r["signals_fired"]:
            out.append("**Signals fired**")
            out.append("")
            out.append("| symbol | stretch | volume | tier | hist win |")
            out.append("|---|---|---|---|---|")
            for s in r["signals_fired"]:
                out.append(f"| {s['symbol']} | {s['stretch']:+.2f} | {s['volx']:.2f}x | "
                           f"{s['tier']} | {s.get('hist_win_rate', 0) * 100:.1f}% |")
            out.append("")
        else:
            out.append("**No signal.** Nothing met `stretch < -2.5` with volume >= 1.4x.")
            out.append("")

        if r.get("gate_results"):
            out.append("**Gate evaluation**")
            out.append("")
            for g in r["gate_results"]:
                sym = g.get("symbol", "?")
                out.append(f"- `{sym}` — {'APPROVED' if g.get('approved') else 'REJECTED'}")
                for chk in g.get("checks", []):
                    mark = "x" if chk["passed"] else " "
                    out.append(f"  - [{mark}] {chk['name']}: {chk['reason']}")
            out.append("")

        if r["actions_taken"]:
            out.append("**Actions**")
            out.append("")
            for a in r["actions_taken"]:
                out.append(f"- {a.get('action')}: {a.get('detail')}")
            out.append("")

        if r.get("near_misses"):
            out.append("<details><summary>Closest to firing</summary>")
            out.append("")
            out.append("| symbol | stretch | volume | blocked by |")
            out.append("|---|---|---|---|")
            for m in r["near_misses"][:8]:
                blockers = "; ".join(m.get("blocked_by", [])) or "-"
                out.append(f"| {m['symbol']} | {m['stretch']:+.2f} | {m['volx']:.2f}x | "
                           f"{blockers} |")
            out.append("")
            out.append("</details>")
            out.append("")

        if r.get("notes"):
            out.append(f"> {r['notes']}")
            out.append("")
        out.append("---")
        out.append("")

    with open(MD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))

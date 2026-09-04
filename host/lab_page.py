"""Public, read-only replica of the research-lab dashboard.

    python host/lab_page.py             # render docs/lab-demo.html from the journal mirror
    python host/lab_page.py --publish   # ...and publish it as /lab/ on the stable Pages site

WHY THIS SHAPE. The research agent runs in a private container on a private
network, on the operator's own Claude subscription. Judges should be able to
watch it think, pre-register, get adjudicated, be refused by the code gate,
and be stood down by the watchdog - but nothing on the internet may reach the
container, spend a model call, or read anything private. So this is
OUTBOUND-ONLY: the container's scribe already mirrors its hash-chained journal
to a private forge; this script pulls that mirror (read-only), renders a static
page with NO controls, and pushes it through the same GitHub Contents API path
the stable dashboard page already uses. The container is never involved.

WHAT IS REDACTED, and why:
  * account and quota material (usage percentages, spend, limit messages,
    per-call cost, driver error text) - the operator's subscription is theirs;
  * the operator's chat with the agent;
  * anything that looks like an address or an internal path;
  * strategy CODE: dossier diffs and candidate sources never leave the forge;
    the public sees hypotheses, flag names, verdicts and gate decisions;
  * sealed-holdout and shadow-forward numbers - never in the journal at all.

Every card here is derived from a journal event the agent itself produced or
was subjected to; nothing is written for the demo that is not in the record.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
MIRROR = os.environ.get("LAB_MIRROR_DIR", r"C:\Users\Lenovo\edgestack-deploy\lab-journal")
FORGE_HOST = os.environ.get("FORGE_HOST", "")          # host config, never committed
MIRROR_REPO = "jacob/lab-journal"
OUT_LOCAL = os.path.join(ROOT, "docs", "lab-demo.html")
PAGES_PATH = "lab/index.html"
FEED_CARDS = 120

SCRUB = [
    (re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[addr]"),
    (re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"), "[addr]"),
    (re.compile(r"\b[a-z0-9-]+\.tail[0-9a-f]+\.ts\.net\b"), "[host]"),
    (re.compile(r"/opt/agent-lab/[A-Za-z0-9_./-]*"), "lab/…"),
    (re.compile(r"/opt/trustyrusty/[A-Za-z0-9_./-]*"), "engine/…"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]+"), "[secret]"),
]
# event types the public may see; everything else is counted, never shown
PUBLIC = {
    "llm_trace", "prereg", "verdict", "driver_cycle_start", "driver_run_end",
    "driver_rest", "operator_stop", "driver_held", "family_note",
    "rule_audit_summary", "candidate_written", "candidate_admitted",
    "candidate_rejected", "birth_check", "family_created", "adoption_report",
    "proxy_refused", "request_unverified", "tripwire_stop", "tripwire_reset",
    "mining_null_result", "brain_changed", "adr", "harness_fix",
    "harness_incident", "policy_update", "graveyard_repetition_blocked",
    "stop_request", "stop_armed", "resume_applied", "candidate_superseded",
    "name_allocated", "holdout_audit", "holdout_refused", "shadow_forward_run",
    "discovery_rate", "discovery_spike", "budget_wind_down",
}


# ------------------------------------------------------------------ privacy
# The operator's own strategies (and the agent's candidates derived from them)
# are PRIVATE: this page is the competition's public demo, and those are live
# money elsewhere (2026-09-02). Only the submitted strategy's lineage and the
# buy-and-hold benchmark may be named here. Everything else about the LAB
# itself - containment, refusals, null calibration, discovery rates, ADRs - has
# no strategy identity in it and is still shown.
PUBLIC_STRATEGY_PREFIXES = ("edgestack", "bench_")
# Symbols no public strategy trades: seeing one means the card came from a
# private strategy's universe, whatever its family says.
PRIVATE_SYMBOLS = ("SPXL", "TQQQ", "WPM", "FNV", "RGLD", "VLUE", "QUAL", "MTUM",
                   "SPHB", "SPLV", "USMV", "RSP", "BIL")
# (TLT, IEF and GLD left this list on 2026-09-03: agent-authored families trade them.)


def _base_stem(filename):
    """canaries_c900.py -> canaries; SPXLrealyields_c001.py -> SPXLrealyields."""
    stem = str(filename or "")[:-3] if str(filename or "").endswith(".py") else str(filename or "")
    return re.sub(r"(_c\d+|_manual)$", "", stem)


def private_index(evs):
    """Derive what must not be named, from the journal itself, so the filter
    stays correct as the lab authors new families without anyone editing a
    list. A family is private if ANY pre-registration in it names a strategy
    file outside PUBLIC_STRATEGY_PREFIXES."""
    fam_files, pub_params, priv_params = {}, set(), set()
    # Agent-authored families are publishable by the operator's rule
    # ("anything created in the container"): a family_created root is public
    # whatever its name (2026-09-03; new ones are allocated an edgestack_ prefix).
    authored = {str(e.get("root")) for e in evs if e.get("type") == "family_created" and e.get("root")}

    def is_public(fn):
        stem = _base_stem(fn)
        return stem.startswith(PUBLIC_STRATEGY_PREFIXES) or stem in authored
    for e in evs:
        if e.get("type") != "prereg":
            continue
        fn = str(e.get("filename") or "")
        fam = str(e.get("family_root") or str(e.get("id", "")).split(".")[0])
        if fam:
            fam_files.setdefault(fam, set()).add(fn)
        keys = set((e.get("variant_params") or {}))
        (pub_params if is_public(fn) else priv_params).update(keys)
    families, files = set(), set()
    for fam, fns in fam_files.items():
        if any(not is_public(f) for f in fns):
            families.add(fam)
            files.update(f for f in fns if not is_public(f))
    tokens = {t for t in
              ({_base_stem(f) for f in files} | families
               | (priv_params - pub_params)          # a name both share is no marker
               | set(PRIVATE_SYMBOLS)) if t}
    return {"families": families, "files": files, "authored": authored,
            "rx": re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(sorted(map(re.escape, tokens),
                                                                     key=len, reverse=True))
                             + r")(?![A-Za-z0-9_])", re.I) if tokens else None}


def is_private(e, c, idx):
    """True if this event/card could name a private strategy. Conservative: a
    card is dropped whole rather than partly redacted, because free-text agent
    reasoning cannot be safely edited into something still true."""
    fam = e.get("family_root") or str(e.get("id", "")).split(".")[0]
    if fam and fam in idx["families"]:
        return True
    for k in ("filename", "candidate", "baseline", "strategy", "stem"):
        v = e.get(k)
        if not isinstance(v, str) or not v.endswith(".py"):
            continue                       # only a strategy FILE names a strategy
        if v in idx["files"] or (not _base_stem(v).startswith(PUBLIC_STRATEGY_PREFIXES)
                                 and _base_stem(v) not in idx.get("authored", set())):
            return True
    rx = idx["rx"]
    if rx and c:
        blob = " ".join(str(c.get(k, "")) for k in ("title", "body", "meta"))
        if rx.search(blob):
            return True
    return False


def scrub(s):
    s = str(s if s is not None else "")
    for rx, rep in SCRUB:
        s = rx.sub(rep, s)
    return s


def _num(v):
    return f"{v:+.3f}" if isinstance(v, (int, float)) else str(v)


def _pair(d, n=None):
    if not isinstance(d, dict):
        return str(d)
    items = list(d.items())[:n] if n else d.items()
    return " · ".join(f"{k} {_num(v)}" for k, v in items)


# ------------------------------------------------------------------ mirror
def sync_mirror():
    if not FORGE_HOST:
        raise SystemExit("FORGE_HOST is not set (host configuration, see forge.env.ps1)")
    url = f"{FORGE_HOST}/{MIRROR_REPO}.git"
    token_file = os.environ.get("FORGE_TOKEN_FILE",          # host configuration, never committed
                                "/c/Users/Lenovo/edgestack-deploy/secrets/forge_jacob.token")
    helper = ('!f(){ echo username=jacob; echo "password=$(cat ' + token_file + ')"; }; f')
    if not os.path.isdir(os.path.join(MIRROR, ".git")):
        subprocess.run(["git", "-c", "credential.helper=", "-c",
                        f"credential.{FORGE_HOST}.helper={helper}",
                        "clone", "-q", "--depth", "1", url, MIRROR], check=True)
        subprocess.run(["git", "-C", MIRROR, "config", "credential.helper", ""], check=True)
        subprocess.run(["git", "-C", MIRROR, "config",
                        f"credential.{FORGE_HOST}.helper", helper], check=True)
    r = subprocess.run(["git", "-C", MIRROR, "pull", "-q", "--ff-only"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("mirror pull failed:", (r.stderr or "")[-200:])
    return os.path.join(MIRROR, "events.jsonl")


def events(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


# ------------------------------------------------------------------- cards
def card(e):
    t = e.get("type")
    if t not in PUBLIC:
        return None
    base = {"seq": e.get("seq"), "ts": str(e.get("ts_utc", ""))[:16].replace("T", " ")}

    if t == "llm_trace":
        m = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', e.get("raw_head", "") or "")
        if not m:
            return None                       # only the reasoning field, never raw output
        try:
            body = json.loads('"' + m.group(1) + '"')
        except Exception:                                      # noqa: BLE001
            body = m.group(1)
        return {**base, "kind": "think", "title": "Agent reasoning", "body": body,
                "meta": f"model {e.get('model', '?')}"}
    if t == "prereg":
        pred = e.get("predicted") or {}
        meta = " · ".join(filter(None, [
            e.get("filename", ""),
            json.dumps(e.get("variant_params", {}), separators=(",", "=")),
            f"objective {e.get('objective', 'sortino_ratio')}",
            f"parent {e['parent']}" if e.get("parent") else "",
            (f"predicts train {_num(pred.get('train'))} / valid {_num(pred.get('valid'))}"
             if pred else "")]))
        card = {**base, "kind": "prereg", "title": f"Pre-registered {e.get('id', '')}",
                "body": e.get("motivation", ""), "meta": meta}
        if e.get("sweep_of"):
            card["sweep_of"] = e["sweep_of"]
            card["variant_line"] = (f"{str(e.get('id', '')).rsplit('.', 1)[-1]}: "
                                    f"{json.dumps(e.get('variant_params', {}), separators=(',', '='))}"
                                    + (f" \u00b7 predicts train {_num(pred.get('train'))} / valid "
                                       f"{_num(pred.get('valid'))}" if pred else ""))
        return card
    if t == "verdict":
        v = str(e.get("verdict", ""))
        kind = "adopt" if v.startswith("ADOPT") else "reject" if v.startswith("REJECT") else "insuff"
        bits = []
        if e.get("delta"):
            bits.append(f"delta ({e.get('objective', 'sortino')}): {_pair(e['delta'])}")
        if e.get("dd_delta"):
            bits.append(f"drawdown: {_pair(e['dd_delta'])}")
        if e.get("zones"):
            bits.append("zones: " + " · ".join(f"{k} {vv}" for k, vv in e["zones"].items()))
        if e.get("robustness"):
            bits.append("cost stress: " + _pair(e["robustness"], 2))
        if e.get("calibration_err"):
            bits.append("prediction error: " + _pair(e["calibration_err"]))
        nc = e.get("null_calibration") or {}
        if nc:
            bits.append(f"null calibration: {nc.get('status')} (FDR est {nc.get('fdr_estimate')})")
        if e.get("flags"):
            bits.append("flags: " + ", ".join(e["flags"]))
        return {**base, "kind": kind, "title": f"{v} — {e.get('id', '')}",
                "body": "\n".join(bits),
                "meta": (f"iteration {e['iteration_n']} of family {e.get('family_root')}"
                         if e.get("iteration_n") else "")}
    if t == "driver_cycle_start":
        return {**base, "kind": "cycle", "title": "Cycle started — thinking…", "body": "",
                "meta": f"{e.get('model')} / {e.get('effort')}" if e.get("model") else ""}
    if t == "driver_run_end":
        return {**base, "kind": "cycle", "title": f"Run ended — {e.get('cycles', '?')} cycle(s)",
                "body": "", "meta": ""}
    if t == "driver_rest":
        return {**base, "kind": "rest", "title": "Agent chose to rest",
                "body": e.get("reasoning", ""), "meta": ""}
    if t == "operator_stop":
        return {**base, "kind": "rest", "title": "Rested at the operator's request",
                "body": f"{e.get('cycles_done')} cycle(s) completed; nothing was interrupted.",
                "meta": ""}
    if t in ("stop_request", "stop_armed", "driver_held", "resume_applied"):
        titles = {"stop_request": "Operator: finish the current hypothesis, then rest",
                  "stop_armed": "Stop armed by root", "driver_held": "Run held (stop armed)",
                  "resume_applied": "Research resumed"}
        return {**base, "kind": "op", "title": titles[t], "body": "", "meta": ""}
    if t in ("family_note", "rule_audit_summary"):
        return {**base, "kind": "note",
                "title": ("Family note: " + str(e.get("family_root", "")) if t == "family_note"
                          else "Rule audit: " + str(e.get("strategy", ""))),
                "body": e.get("learning") or json.dumps(e.get("verdicts", {}), indent=1),
                "meta": ""}
    if t == "candidate_written":
        return {**base, "kind": "sys", "title": "Agent wrote a candidate",
                "body": e.get("summary", ""),
                "meta": f"{e.get('candidate', '')} · flags {', '.join(e.get('flags') or [])}"}
    if t == "candidate_admitted":
        return {**base, "kind": "adopt", "title": "Candidate admitted by root",
                "body": e.get("summary", ""), "meta": f"{e.get('candidate', '')} · every gate passed"}
    if t == "candidate_rejected":
        return {**base, "kind": "reject", "title": f"Candidate refused at gate: {e.get('stage')}",
                "body": e.get("detail", ""), "meta": e.get("candidate", "")}
    if t == "birth_check":
        return {**base, "kind": "sys", "title": "Birth check " + ("PASS" if e.get("pass") else "FAIL"),
                "body": (f"inert {e.get('inert_ok')} · deterministic {e.get('deterministic')} · "
                         f"effect {e.get('effect')} · causal {e.get('causal', 'n/a')}"
                         + ("\n" + e["diagnosis"] if e.get("diagnosis") else "")),
                "meta": e.get("candidate", "")}
    if t == "family_created":
        return {**base, "kind": "adopt", "title": f"New strategy family: {e.get('root')}",
                "body": f"Authored from scratch; adjudicated against {e.get('benchmark')}.",
                "meta": ""}
    if t == "adoption_report":
        return {**base, "kind": "adopt", "title": f"Adoption dossier written: {e.get('id')}",
                "body": "For human promotion review. Diffs and sealed-data numbers stay private.",
                "meta": f"family {e.get('family_root')}"}
    if t == "proxy_refused":
        return {**base, "kind": "warn", "title": "Engine proxy refused a request",
                "body": e.get("why", ""), "meta": f"{e.get('method', '')} {e.get('path', '')}"}
    if t == "request_unverified":
        return {**base, "kind": "warn", "title": "Request ignored: not from the operator",
                "body": f"{e.get('request_type')} written by {e.get('writer')}", "meta": ""}
    if t == "tripwire_stop":
        return {**base, "kind": "warn", "title": "Watchdog tripwire: driver stopped",
                "body": "; ".join(e.get("reasons") or []), "meta": ""}
    if t == "tripwire_reset":
        return {**base, "kind": "op", "title": "Tripwire reset by the operator", "body": "", "meta": ""}
    if t == "mining_null_result":
        return {**base, "kind": "note", "title": "Mining-null measured",
                "body": (f"{e.get('adoptions')} of {e.get('seeds_run')} pure-noise rules were "
                         f"adopted ({100 * float(e.get('false_discovery_rate') or 0):.0f}%). "
                         f"Every real adoption is read against this."),
                "meta": f"root {e.get('root', 'funnel')}"}
    if t == "discovery_rate":
        a = e.get("all_time") or {}
        return {**base, "kind": "note", "title": f"Discovery rate \u2014 block {e.get('block')}",
                "body": (f"this block: zone hits {100*float(e.get('block_zone_rate',0)):.0f}%, adopts "
                         f"{100*float(e.get('block_adopt_rate',0)):.0f}%; all-time zone {100*float(a.get('zone_rate',0)):.0f}%, "
                         f"adopt {100*float(a.get('adopt_rate',0)):.0f}%, reject {100*float(a.get('reject_rate',0)):.0f}%"),
                "meta": f"{e.get('trials')} trials"}
    if t == "discovery_spike":
        return {**base, "kind": "warn", "title": "Discovery-rate spike detected",
                "body": (f"{e.get('zone_hits')}/{e.get('n')} zone hits vs a {100*float(e.get('baseline_rate',0)):.0f}% baseline "
                         f"(p={e.get('p_value')}). A fresh mining-null run is scheduled to tell genuine "
                         f"improvement from a funnel that loosened."), "meta": ""}
    if t == "budget_wind_down":
        return {**base, "kind": "warn", "title": "Run wound down on a usage limit — not a failure",
                "body": scrub(e.get("reason", "")), "meta": scrub(e.get("note", ""))}
    if t == "brain_changed":
        to = e.get("to") or {}
        return {**base, "kind": "op", "title": "Brain switched by the operator",
                "body": f"{to.get('model')} / {to.get('effort')}", "meta": ""}
    if t in ("adr", "harness_fix", "harness_incident", "policy_update"):
        return {**base, "kind": "sys", "title": f"{t.replace('_', ' ')} {e.get('id', '')}",
                "body": e.get("change") or e.get("fix") or e.get("note") or "",
                "meta": (e.get("reason") or e.get("defect") or "")[:240]}
    if t == "graveyard_repetition_blocked":
        return {**base, "kind": "warn", "title": "Duplicate hypothesis blocked",
                "body": "The same variant was already registered; the record refuses repeats.",
                "meta": e.get("id", "")}
    if t in ("candidate_superseded", "name_allocated"):
        return {**base, "kind": "sys", "title": t.replace("_", " "),
                "body": e.get("note", ""), "meta": ""}
    if t in ("holdout_audit", "holdout_refused", "shadow_forward_run"):
        return {**base, "kind": "note", "title": t.replace("_", " "),
                "body": ("PASS" if e.get("pass") else "FAIL") if t == "holdout_audit"
                else e.get("note") or e.get("reason") or "", "meta": e.get("family", "")}
    return None


def collapse_sweeps(cards):
    """One card per dose sweep. A `propose` with `variants` registers N
    hypotheses (<id>.v1..vN) that share one motivation; each is a complete
    record in the journal, but showing the same paragraph N times reads as a
    bug (2026-09-02). Prereg cards of the same sweep merge into one card even
    when engine-run cards sit between them (each variant backtests as it is
    registered); those run counts fold into the merged card."""
    out = []
    for c in cards:
        sid = c.get("sweep_of")
        if c.get("kind") == "prereg" and not sid:
            m = re.match(r"^(.+)\.v\d+$", str(c.get("title", "")).replace("Pre-registered ", ""))
            sid = m.group(1) if m else None
            if sid:
                c["sweep_of"] = sid
                if not c.get("variant_line"):
                    c["variant_line"] = c.get("meta", "")
        if c.get("kind") == "prereg" and sid:
            # look back past trailing run cards for the open sweep card
            k = len(out) - 1
            runs = 0
            while k >= 0 and out[k].get("kind") == "runs":
                runs += int(re.sub(r"\D", "", str(out[k].get("meta", "0"))) or 0)
                k -= 1
            if k >= 0 and out[k].get("kind") == "prereg" and out[k].get("sweep_of") == sid:
                head = out[k]
                del out[k + 1:]                         # fold the run cards
                head.setdefault("variants", [head.get("variant_line", "")])
                head["variants"].append(c.get("variant_line", ""))
                head["runs_folded"] = head.get("runs_folded", 0) + runs
                n = len(head["variants"])
                head["title"] = f"Pre-registered {sid} \u2014 dose sweep, {n} variants"
                head["meta"] = "\n".join(head["variants"]) + (
                    f"\n\u2699 {head['runs_folded']} engine runs so far" if head["runs_folded"] else "")
                head["seq"] = f"{head.get('seq_first', head.get('seq'))}\u2013{c.get('seq')}"
                continue
            c["seq_first"] = c.get("seq")
        out.append(c)
    return out


# ------------------------------------------------------------------- stats
def stats(evs):
    c = {"events": 0, "backtests": 0, "verdicts": 0, "adopt": 0, "reject": 0, "insuff": 0,
         "prereg": 0, "refused": 0, "unverified": 0, "families": set(), "null": None,
         "last": "", "integrity": 0}
    for e in evs:
        c["events"] += 1
        t = e.get("type")
        if t == "backtest":
            c["backtests"] += 1
        elif t == "verdict":
            c["verdicts"] += 1
            v = str(e.get("verdict", ""))
            c["adopt" if v.startswith("ADOPT") else "reject" if v.startswith("REJECT") else "insuff"] += 1
            if e.get("family_root"):
                c["families"].add(e["family_root"])
        elif t == "prereg":
            c["prereg"] += 1
        elif t == "candidate_rejected":
            c["refused"] += 1
        elif t in ("proxy_refused", "request_unverified"):
            c["unverified"] += 1
        elif t == "mining_null_result":
            c["null"] = e
        c["last"] = str(e.get("ts_utc", ""))[:16].replace("T", " ")
    c["families"] = len(c["families"])
    return c


# -------------------------------------------------------------------- page
CSS = """
*{box-sizing:border-box}body{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 'Segoe UI',system-ui,sans-serif}
#top{padding:22px 28px;border-bottom:1px solid #21262d;display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}
#top h1{margin:0;font-size:22px}#top h1 span{color:#60a5fa}#top .sub{color:#8b98a9}
#wrap{display:grid;grid-template-columns:1fr 320px;gap:0}
#feed{padding:18px 28px;max-width:960px}#side{border-left:1px solid #21262d;padding:18px 20px;position:sticky;top:0;height:100vh;overflow:auto}
h3{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8b98a9;margin:18px 0 8px}
.krow{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid #161b22;font-size:13.5px}.kk{color:#8b98a9}.kv{text-align:right}
.card{background:#161b22;border:1px solid #21262d;border-left:4px solid #30363d;border-radius:10px;padding:12px 14px;margin:0 0 12px}
.hd{display:flex;justify-content:space-between;gap:12px;font-weight:600}.sq{color:#5b6b85;font-size:12px;font-weight:400;white-space:nowrap}
.bd{white-space:pre-wrap;margin-top:6px;color:#c9d1d9}.mt{color:#8b98a9;font-size:12.5px;margin-top:6px}
.think{border-left-color:#8b5cf6}.prereg{border-left-color:#3b82f6}.adopt{border-left-color:#22c55e}.reject{border-left-color:#ef4444}.insuff{border-left-color:#f59e0b}
.rest{border-left-color:#64748b}.op{border-left-color:#06b6d4}.warn{border-left-color:#f97316}.sys{border-left-color:#475569}.note{border-left-color:#a3e635}.cycle{border-left-color:#1f2937}
.notice{background:#0f1a2a;border:1px solid #1e3a8a;color:#93c5fd;border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:13.5px}
a{color:#60a5fa}@media(max-width:900px){#wrap{grid-template-columns:1fr}#side{position:static;height:auto;border-left:0;border-top:1px solid #21262d}}
"""


def render_page(cards, st):
    esc = lambda s: html.escape(scrub(s))          # noqa: E731
    null = st["null"]
    null_txt = (f"{null.get('adoptions')}/{null.get('seeds_run')} noise rules adopted "
                f"({100 * float(null.get('false_discovery_rate') or 0):.0f}%)") if null else "not yet measured"
    rows = [("journal events", f"{st['events']:,}"), ("backtests run", f"{st['backtests']:,}"),
            ("hypotheses pre-registered", st["prereg"]), ("verdicts", st["verdicts"]),
            ("adopt candidates", st["adopt"]), ("rejects", st["reject"]),
            ("insufficient evidence", st["insuff"]), ("rule families", st["families"]),
            ("candidates refused at a gate", st["refused"]),
            ("boundary probes refused", st["unverified"]), ("mining-null rate", null_txt),
            ("last journal entry (UTC)", st["last"])]
    side = "".join(f'<div class=krow><span class=kk>{esc(k)}</span><span class=kv>{esc(v)}</span></div>' for k, v in rows)
    feed = "".join(
        f'<div class="card {c["kind"]}"><div class=hd><span>{esc(c["title"])}</span>'
        f'<span class=sq>#{c["seq"]} {esc(c["ts"])}</span></div>'
        + (f'<div class=bd>{esc(c["body"])}</div>' if c.get("body") else "")
        + (f'<div class=mt>{esc(c["meta"])}</div>' if c.get("meta") else "") + "</div>"
        for c in cards)
    gen = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EdgeStack research lab — read-only</title><style>{CSS}</style></head><body>
<div id=top><h1>Edge<span>Stack</span> research lab</h1><span class=sub>an autonomous research agent, watched through its own hash-chained journal · read-only replica, regenerated {gen}</span>
<span class=sub><a href="https://jpennin5.github.io/edgestack/">live trading dashboard</a> · <a href="https://github.com/jpennin5/edgestack">repository</a></span></div>
<div id=wrap><div id=feed>
<div class=notice>What you are watching: the agent reads the operator's strategies, pre-registers a hypothesis with a prediction, and a deterministic pipeline it cannot touch adjudicates it on two windows with cost stress and a measured noise baseline. Root-owned gates decide what code enters the engine; a sealed holdout it can never see waits for promotion time; a watchdog stops it if the record's integrity is ever in question. Nothing here is interactive by design: no request from this page reaches the lab, and no model call is made on the reader's behalf.</div>
{feed}</div>
<div id=side><h3>Lab record</h3>{side}
<h3>Containment (all root-owned)</h3><div class=krow><span class=kk>engine</span><span class=kv>unprivileged uid, loopback only</span></div>
<div class=krow><span class=kk>code entering the engine</span><span class=kv>static gate + birth checks</span></div>
<div class=krow><span class=kk>agent ↔ engine</span><span class=kv>scoped proxy, sealed holdout</span></div>
<div class=krow><span class=kk>journal</span><span class=kv>hash chain, writer-stamped, mirrored</span></div>
<div class=krow><span class=kk>adoption</span><span class=kv>null-calibrated FDR, human promotion</span></div>
<div class=krow><span class=kk>operator quota</span><span class=kv>wind-down governor</span></div>
<h3>Not shown, on purpose</h3><div style="color:#8b98a9;font-size:13px">Strategy code and diffs, sealed-holdout and forward-audit numbers, the operator's account usage, and the operator's own conversations with the agent.</div>
</div></div></body></html>"""


def publish(html_text):
    import publish_url
    tok = publish_url.github_token()
    if not tok:
        print("no GitHub token in credential store")
        return 1
    api = f"https://api.github.com/repos/{publish_url.REPO}/contents/{PAGES_PATH}"
    status, cur = publish_url.api("GET", api + f"?ref={publish_url.BRANCH}", tok)
    body = {"message": "lab page refresh", "branch": publish_url.BRANCH,
            "content": base64.b64encode(html_text.encode()).decode()}
    if status == 200 and cur.get("sha"):
        body["sha"] = cur["sha"]
    status, out = publish_url.api("PUT", api, tok, body)
    if status == 409:
        # lost a compare-and-swap to the 15-minute publisher loop: re-read the
        # current sha and try once more (2026-09-02)
        status, cur = publish_url.api("GET", api + f"?ref={publish_url.BRANCH}", tok)
        if status == 200 and cur.get("sha"):
            body["sha"] = cur["sha"]
            status, out = publish_url.api("PUT", api, tok, body)
    if status in (200, 201):
        print("published https://jpennin5.github.io/edgestack/lab/")
        return 0
    print("publish failed:", status, str(out)[:200])
    return 1


def main():
    path = sync_mirror()
    evs = list(events(path))
    st = stats(evs)
    idx = private_index(evs)
    kept, dropped = [], 0
    for e in evs:
        c = card(e)
        if not c:
            continue
        if is_private(e, c, idx):
            dropped += 1
            continue
        kept.append(c)
    cards = collapse_sweeps(kept)[-FEED_CARDS:][::-1]
    page = render_page(cards, st)
    for rx, _ in SCRUB:                                   # belt and braces
        assert not rx.search(page), f"redaction failed: {rx.pattern}"
    if idx["rx"]:                                         # nothing private may be named
        hit = idx["rx"].search(page)
        assert not hit, f"private name leaked into the public page: {hit.group(0)}"
    os.makedirs(os.path.dirname(OUT_LOCAL), exist_ok=True)
    with open(OUT_LOCAL, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"rendered {len(cards)} cards from {st['events']} events "
          f"({dropped} withheld as private) -> {OUT_LOCAL}")
    if "--publish" in sys.argv:
        return publish(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

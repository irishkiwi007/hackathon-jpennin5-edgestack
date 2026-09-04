"""Session scheduler - keeps the agent live and trading unattended.

The hackathon requires the agent to be live from Mon Aug 31 09:30 ET and to trade unattended for
five sessions. Two jobs run per session, at the times the research actually supports:

  09:35 ET  EXIT pass. Close anything that has completed its 3-session hold.
  15:45 ET  ENTRY pass. Yahoo's live feed makes today's bar available, so the signal is computed
            from today's price and volume and traded at today's close - the +1.365% entry rather
            than the +1.205% next-open entry. 15:45 is the compromise: late enough that ~89% of
            the session's volume is in (so the volume estimate is sound), early enough to get a
            spread filled before the close.

Anything that throws is caught, logged and retried next tick. A crashed scheduler on day one is
the single worst outcome available, so nothing here is allowed to raise.

Usage
    python agent/scheduler.py                # run until stopped
    python agent/scheduler.py --once entry   # run one pass now and exit
    python agent/scheduler.py --once exit
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "..", "journal", "scheduler.log")

EXIT_AT = (9, 31)   # core overnight position sells at the open
ENTRY_AT = (15, 45)


def now_et() -> datetime.datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                    # noqa: BLE001
        return datetime.datetime.now()


def log(msg: str) -> None:
    line = f"[{now_et():%Y-%m-%d %H:%M:%S ET}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _stamp_in_window(stamp: str, hh: int, mm: int) -> bool:
    """A decision record's timestamp (ISO, any zone) falls within 25 minutes
    after the pass target in ET."""
    try:
        t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        from zoneinfo import ZoneInfo
        t = t.astimezone(ZoneInfo("America/New_York"))
        start = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return start <= t <= start + datetime.timedelta(minutes=25)
    except Exception:                                    # noqa: BLE001
        return False


def run_pass(kind: str) -> None:
    args = [sys.executable, os.path.join(HERE, "run_agent.py")]
    if kind == "exit":
        args.append("--manage")
    log(f"--- {kind} pass starting ---")
    try:
        attempt = 0
        while True:
            attempt += 1
            res = subprocess.run(args, capture_output=True, text=True, timeout=900)
            for line in (res.stdout or "").splitlines():
                log(f"  {line}")
            if res.returncode != 0:
                for line in (res.stderr or "").splitlines()[-15:]:
                    log(f"  !! {line}")
                log(f"--- {kind} pass exited {res.returncode} (attempt {attempt}) ---")
                # A transient broker failure at 15:45 must not cost the day: retry
                # while there is still time before the 15:50 MOC cutoff (2026-09-02).
                if kind == "entry" and attempt < 3 and now_et().strftime("%H:%M:%S") < "15:49:15":
                    log("retrying the entry pass in 40s, still ahead of the MOC cutoff")
                    time.sleep(40)
                    continue
            else:
                log(f"--- {kind} pass complete ---")
            break
        if kind == "entry":
            # the audit trail commits itself: journal artifacts -> git -> GitHub
            try:
                r = subprocess.run([sys.executable,
                                    os.path.join(HERE, "..", "host", "commit_journal.py")],
                                   capture_output=True, text=True, timeout=180)
                log(f"journal commit: {(r.stdout or r.stderr).strip()[:120]}")
            except Exception as exc:                   # noqa: BLE001
                log(f"journal commit failed: {exc}")
    except subprocess.TimeoutExpired:
        log(f"!! {kind} pass timed out after 900s")
    except Exception as exc:                             # noqa: BLE001
        log(f"!! {kind} pass crashed: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", choices=["entry", "exit"], help="run one pass now and exit")
    args = ap.parse_args()

    if args.once:
        run_pass(args.once)
        return 0

    log("scheduler up; exit pass {:02d}:{:02d} ET, entry pass {:02d}:{:02d} ET".format(
        *EXIT_AT, *ENTRY_AT))
    # 2026-09-04: the host was down 11:18-22:07 ET on 2026-09-03 and the entry
    # pass never ran; nothing said so. If this process starts on a weekday
    # after a pass window has closed and the day's journal has no record of
    # that pass, say it here in plain words (the dashboard shows it too).
    try:
        n0 = now_et()
        if n0.weekday() < 5:
            import json as _json
            recs = []
            try:
                with open(os.path.join(HERE, "..", "journal", "decisions.jsonl"), encoding="utf-8") as fh:
                    recs = [_json.loads(l) for l in fh if l.strip()]
            except OSError:
                pass
            today = n0.date().isoformat()
            stamps = [str(r.get("timestamp", "")) for r in recs if r.get("session_date") == today]
            for kind, (hh, mm) in (("exit", EXIT_AT), ("entry", ENTRY_AT)):
                closed = n0.time() > datetime.time(hh, mm + 10)
                ran = any(_stamp_in_window(s, hh, mm) for s in stamps)
                if closed and not ran:
                    log(f"!! MISSED the {kind} pass today ({today}): the host was not running at "
                        f"{hh:02d}:{mm:02d} ET and the window has closed - no orders were placed")
    except Exception as exc:                             # noqa: BLE001
        log(f"missed-pass check failed: {exc}")
    done: set[tuple[str, str]] = set()
    while True:
        try:
            n = now_et()
            day = n.date().isoformat()
            if n.weekday() < 5:
                for kind, (hh, mm) in (("exit", EXIT_AT), ("entry", ENTRY_AT)):
                    target = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    # fire once per day, within a 10-minute window after the target
                    if (kind, day) not in done and target <= n < target + datetime.timedelta(
                            minutes=10):
                        done.add((kind, day))
                        run_pass(kind)
            # forget old marks so the set cannot grow without bound
            done = {(k, d) for (k, d) in done
                    if d >= (n.date() - datetime.timedelta(days=3)).isoformat()}
        except Exception as exc:                         # noqa: BLE001
            log(f"!! scheduler loop error (continuing): {exc}")
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())

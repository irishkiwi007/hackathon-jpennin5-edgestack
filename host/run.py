"""Supervisor for the EdgeStack host processes (this machine is the host).

    python host/run.py mcp        # Alpaca MCP server  (port 8000, via uvx, pinned 2.3.0)
    python host/run.py scheduler  # session scheduler  (agent entries/exits)
    python host/run.py dashboard  # live dashboard     (port 8787)
    python host/run.py live       # Live Manager loop (deployments, kill switches)
    python host/run.py tunnel     # cloudflared quick tunnel -> public URL (self-healing)

Each mode: loads .env, then keeps its process alive forever — restart on exit, with
backoff. Port-owning modes first CHECK the port and idle if something already serves it
(ensure-running semantics). The tunnel mode additionally WATCHES its public URL: quick
tunnels can die at the edge while cloudflared retry-loops forever (observed 2026-08-30),
so three failed probes recycle the process for a fresh URL, and journal/live_url.txt is
always kept pointing at the current one. Logs to journal/<mode>.supervisor.log.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
JOURNAL = os.path.join(ROOT, "journal")
os.makedirs(JOURNAL, exist_ok=True)


def load_env() -> None:
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def port_up(port: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), 2)
        s.close()
        return True
    except OSError:
        return False


MODES = {
    "mcp": {
        "cmd": ["uvx", "--python", "3.11", "--with", "fastmcp==3.4.7",
                "alpaca-mcp-server==2.3.0",
                "--transport", "streamable-http", "--host", "127.0.0.1",
                "--port", "8000"],
        "port": 8000,
        "env": {"ALPACA_TOOLSETS":
                "account,trading,assets,options-data,stock-data"},
    },
    "scheduler": {
        "cmd": [sys.executable, os.path.join(ROOT, "agent", "scheduler.py")],
        "port": None,
    },
    "dashboard": {
        "cmd": [sys.executable, os.path.join(ROOT, "agent", "dashboard.py")],
        "port": 8787,
    },
    "live": {
        "cmd": [sys.executable, os.path.join(ROOT, "agent", "live_manager.py")],
        "port": None,
    },
    "tunnel": {
        "cmd": [os.path.join(HERE, "bin", "cloudflared.exe"), "tunnel",
                "--url", "http://127.0.0.1:8787", "--no-autoupdate"],
        "port": None,
    },
}


def _watch_tunnel(proc, log_path, log, start_offset=0):
    """One cloudflared lifecycle: publish its URL, probe it every 60s, recycle on death."""
    import urllib.request
    url = None
    fails = 0
    url_deadline = time.time() + 120
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    while True:
        if proc.poll() is not None:
            return proc.returncode
        if url is None:
            try:
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    fh.seek(start_offset)          # only THIS run's output; old runs
                    text = fh.read()               # contain dead URLs
                found = pattern.findall(text)
                if found:
                    url = found[-1]
                    with open(os.path.join(JOURNAL, "live_url.txt"), "w",
                              encoding="utf-8") as fh:
                        fh.write(url + "\n")
                    log("tunnel URL published: " + url)
                    try:
                        import publish_url as _pub
                        rc_pub = _pub.publish()
                        log(f"stable-page publish rc={rc_pub} "
                            "(https://jpennin5.github.io/edgestack/)")
                    except Exception as exc:           # noqa: BLE001
                        log(f"stable-page publish failed: {exc}")
                elif time.time() > url_deadline:
                    log("no URL within 120s; recycling cloudflared")
                    proc.kill()
                    return -1
            except OSError:
                pass
            time.sleep(5)
            continue
        time.sleep(60)
        ok = False
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=20) as resp:
                ok = resp.status < 500
        except Exception:                              # noqa: BLE001
            ok = False
        if ok:
            fails = 0
        else:
            fails += 1
            log(f"tunnel probe failed ({fails}/3): {url}")
            if fails >= 3:
                log("tunnel URL dead; recycling cloudflared for a fresh one")
                proc.kill()
                return -2


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        print(f"usage: run.py [{'|'.join(MODES)}]")
        return 1
    mode = sys.argv[1]
    spec = MODES[mode]
    load_env()
    env = dict(os.environ)
    env.update(spec.get("env") or {})
    log_path = os.path.join(JOURNAL, f"{mode}.supervisor.log")
    backoff = 5

    def log(msg: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {msg}\n")

    log(f"supervisor up for '{mode}'")
    while True:
        if spec["port"] and port_up(spec["port"]):
            time.sleep(30)                 # someone already serves it — just watch
            backoff = 5
            continue
        log(f"starting: {' '.join(spec['cmd'])}")
        try:
            offset = os.path.getsize(log_path) if os.path.exists(log_path) else 0
            with open(log_path, "a", encoding="utf-8") as out:
                proc = subprocess.Popen(spec["cmd"], cwd=ROOT, env=env,
                                        stdout=out, stderr=out)
                if mode == "tunnel":
                    rc = _watch_tunnel(proc, log_path, log, offset)
                else:
                    rc = proc.wait()
            log(f"exited rc={rc}; restarting in {backoff}s")
        except FileNotFoundError as exc:
            log(f"command missing: {exc}; retry in 300s")
            time.sleep(300)
            continue
        except Exception as exc:           # noqa: BLE001
            log(f"supervisor error: {exc}")
        time.sleep(backoff)
        backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    raise SystemExit(main())

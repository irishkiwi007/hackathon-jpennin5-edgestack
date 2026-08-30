"""Supervisor for the EdgeStack host processes (this machine is the host).

    python host/run.py mcp        # Alpaca MCP server  (port 8000, via uvx, pinned 2.3.0)
    python host/run.py scheduler  # session scheduler  (agent entries/exits)
    python host/run.py dashboard  # live dashboard     (port 8787)
    python host/run.py tunnel     # cloudflared quick tunnel -> public URL

Each mode: loads .env, then keeps its process alive forever — restart on exit, with
backoff. Port-owning modes first CHECK the port and idle if something already serves it
(ensure-running semantics: a second supervisor instance never double-binds). Registered
with Windows Task Scheduler at logon by host/install_tasks.py; logs to journal/.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
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
        "cmd": ["uvx", "--python", "3.11", "alpaca-mcp-server==2.3.0",
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
    "tunnel": {
        "cmd": ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8787",
                "--no-autoupdate"],
        "port": None,
    },
}


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
            with open(log_path, "a", encoding="utf-8") as out:
                proc = subprocess.Popen(spec["cmd"], cwd=ROOT, env=env,
                                        stdout=out, stderr=out)
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

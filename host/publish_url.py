"""Publish the current live-dashboard URL to a STABLE address.

Problem: quick-tunnel hostnames change on every recycle, but the submission form wants one
URL that keeps working. Solution: https://jpennin5.github.io/edgestack/ is a tiny branded
page on the gh-pages branch that redirects to the CURRENT tunnel URL. The tunnel supervisor
calls this script whenever the URL changes; it upserts index.html through the GitHub
Contents API using the token already stored in Windows Credential Manager (read via
ctypes — no git, no subprocess, token never leaves memory).

    python host/publish_url.py            # publish journal/live_url.txt
    python host/publish_url.py --check    # print what is currently published
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "jpennin5/edgestack"
BRANCH = "gh-pages"
API = f"https://api.github.com/repos/{REPO}/contents/index.html"


# ---------------------------------------------------------------- credential read
class _CRED(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
                ("Comment", wt.LPWSTR), ("LastWritten", ctypes.c_byte * 8),
                ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def github_token() -> str | None:
    adv = ctypes.windll.advapi32
    p = ctypes.POINTER(_CRED)()
    for target in ("git:https://github.com", "git:https://x-access-token@github.com"):
        if adv.CredReadW(target, 1, 0, ctypes.byref(p)):
            n = p.contents.CredentialBlobSize
            raw = ctypes.string_at(p.contents.CredentialBlob, n)
            adv.CredFree(p)
            try:
                return raw.decode("utf-16-le")
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="replace")
    return None


# ---------------------------------------------------------------- page template
def page(url: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>EdgeStack</title>
<meta http-equiv="refresh" content="2;url={url}">
<style>body{{background:#0b0f14;color:#e5e7eb;font:17px/1.6 'Segoe UI',system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#121826;border:1px solid #1f2937;border-radius:16px;padding:44px 52px;
max-width:560px;text-align:center}}
h1{{font-size:34px}}h1 span{{color:#60a5fa}}
p{{color:#8b98a9;margin-top:14px}}a{{color:#60a5fa}}</style>
<script>setTimeout(function(){{location.href={json.dumps(url)}}},1500)</script></head>
<body><div class="card"><h1>Edge<span>Stack</span></h1>
<p>Connecting you to the live dashboard&hellip;</p>
<p><a href="{url}">continue</a> &middot;
<a href="https://github.com/{REPO}">repository</a></p>
<p style="font-size:13px">Every rule survived an attempt to kill it.</p>
</div></body></html>"""


def api(method: str, url: str, token: str, body: dict | None = None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body else None)
    req.add_header("Authorization", f"token {token}")
    req.add_header("User-Agent", "edgestack")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def publish() -> int:
    live = os.path.join(ROOT, "journal", "live_url.txt")
    try:
        url = open(live, encoding="utf-8").read().strip()
    except OSError:
        print("no live_url.txt")
        return 1
    if not url.startswith("https://"):
        print("bad url:", url)
        return 1
    token = github_token()
    if not token:
        print("no GitHub token in credential store")
        return 1

    content = base64.b64encode(page(url).encode()).decode()
    status, cur = api("GET", API + f"?ref={BRANCH}", token)
    body = {"message": f"live URL -> {url}", "content": content, "branch": BRANCH}
    if status == 200 and cur.get("sha"):
        # skip if unchanged (avoid commit spam)
        try:
            existing = base64.b64decode(cur.get("content", "")).decode()
            if url in existing:
                print("already current:", url)
                return 0
        except Exception:                              # noqa: BLE001
            pass
        body["sha"] = cur["sha"]
    status, out = api("PUT", API, token, body)
    if status in (200, 201):
        print("published", url, "-> https://jpennin5.github.io/edgestack/")
        return 0
    print("publish failed:", status, str(out)[:200])
    return 1


if __name__ == "__main__":
    if "--check" in sys.argv:
        t = github_token()
        s, cur = api("GET", API + f"?ref={BRANCH}", t)
        if s == 200:
            html = base64.b64decode(cur.get("content", "")).decode()
            import re
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", html)
            print("published target:", m.group(0) if m else "?")
        else:
            print("no page yet:", s)
        raise SystemExit(0)
    raise SystemExit(publish())

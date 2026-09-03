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
    """Three tabs on one stable address: LIVE (the tunnel, embedded, with a
    direct link kept for anyone whose browser blocks frames), RESEARCH (the
    /lab/ replica, read-only, regenerated from the agent's journal mirror) and
    BACKTEST (the tunnel's own Backtest tab). The tunnel URL is still the only thing that
    changes between publishes, so --check keeps working."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EdgeStack</title>
<style>*{{box-sizing:border-box}}body{{background:#0b0f14;color:#e5e7eb;margin:0;
font:15px/1.5 'Segoe UI',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}}
#hd{{display:flex;align-items:center;gap:22px;padding:12px 22px;border-bottom:1px solid #1f2937;background:#0d1219}}
#hd h1{{margin:0;font-size:22px}}#hd h1 span{{color:#60a5fa}}#hd .tag{{color:#8b98a9;font-size:13px}}
#tabs{{display:flex;gap:6px;margin-left:auto}}
#tabs button{{background:#121826;border:1px solid #1f2937;color:#c9d1d9;padding:8px 16px;border-radius:9px;font-size:14px;cursor:pointer}}
#tabs button.on{{background:#1d4ed8;border-color:#1d4ed8;color:#fff}}
#links{{font-size:13px;color:#8b98a9;display:flex;align-items:center}}#links a{{color:#60a5fa;margin-left:12px}}
#okey{{margin-left:14px;background:#0d1219;border:1px solid #1f2937;color:#e5e7eb;border-radius:6px;padding:5px 8px;width:130px;font:12px Consolas,monospace}}
.pane{{flex:1;display:none}}.pane.on{{display:block}}
iframe{{width:100%;height:100%;border:0;background:#0b0f14}}</style></head>
<body><div id=hd><h1>Edge<span>Stack</span></h1><span class=tag>Evidence opens the door to opportunity.</span>
<div id=tabs><button id=t-live class=on>Live</button><button id=t-lab>Research</button><button id=t-backtest>Backtest</button></div>
<span id=links><a href="{url}" target=_blank>open dashboard</a><a href="https://github.com/{REPO}">repository</a>
<input id=okey type=password placeholder="operator key" title="Only the operator has one. Stored in this browser on this stable address, so it survives the tunnel changing hostname; handed to the dashboard in the URL fragment, which never leaves the browser." autocomplete=off></span></div>
<div id=p-live class="pane on"><iframe src="{url}/?embed=1#live" title="EdgeStack live dashboard"></iframe></div>
<div id=p-lab class=pane><iframe src="https://jpennin5.github.io/edgestack/lab/" title="EdgeStack research lab (read-only)"></iframe></div>
<div id=p-backtest class=pane><iframe src="{url}/?embed=1#backtest" title="EdgeStack backtests"></iframe></div>
<script>
function show(t){{for(const k of ['live','lab','backtest']){{document.getElementById('t-'+k).classList.toggle('on',k===t);
document.getElementById('p-'+k).classList.toggle('on',k===t)}};try{{history.replaceState(null,'','#'+t)}}catch(e){{}}}}
document.getElementById('t-live').onclick=()=>show('live');document.getElementById('t-lab').onclick=()=>show('lab');
document.getElementById('t-backtest').onclick=()=>show('backtest');
if(location.hash==='#lab')show('lab');if(location.hash==='#backtest')show('backtest');
const okey=document.getElementById('okey');try{{okey.value=localStorage.getItem('opkey')||''}}catch(e){{}}
function frames(){{const k=okey.value.trim();const s=t=>"{url}/?embed=1#"+t+(k?'&key='+encodeURIComponent(k):'');
document.querySelector('#p-live iframe').src=s('live');document.querySelector('#p-backtest iframe').src=s('backtest')}}
okey.onchange=()=>{{try{{localStorage.setItem('opkey',okey.value.trim())}}catch(e){{}}frames()}};
if(okey.value)frames();
/* On the operator's own machine the dashboard is listening on loopback and will hand this
   page its key (to this origin only, and only to a local browser). Anywhere else the fetch
   just fails and the field stays empty. */
(async()=>{{if(okey.value)return;try{{const r=await fetch('http://127.0.0.1:8787/api/operator-key',{{mode:'cors',credentials:'omit'}});
if(!r.ok)return;const j=await r.json();if(j&&j.key){{okey.value=j.key;try{{localStorage.setItem('opkey',j.key)}}catch(e){{}}frames()}}}}catch(e){{}}}})();
</script></body></html>"""


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
            if existing == page(url):                   # same URL AND same template
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

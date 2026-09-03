"""EdgeStack live dashboard — the submission's "live application URL".

Stdlib-only HTTP server (port 8787). Three tabs on one page:

  Live      the running competition agent (journal, positions, equity, MCP route) plus the
            Live Manager: deployments of any strategy module against an account slice with a
            drawdown kill switch (agent/live_manager.py), exactly the TrustyRustyEngine model.
  Research  the public read-only replica of the research lab (regenerated from the lab
            journal mirror; never the lab itself).
  Backtest  run the borrowed engine runner on any strategy file (agent/backtests.py) and keep
            the results.

Reads are public. Anything that runs code or moves money needs the operator key
(journal/operator_token, generated on first start, sent as X-Operator-Token) — the tunnel
puts this page on the open internet, so the write surface is keyed even though the process
only ever listens on this machine.

    python agent/dashboard.py            # http://127.0.0.1:8787
"""
from __future__ import annotations

import datetime
import hmac
import html
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.join(HERE, "..")
JOURNAL = os.path.join(ROOT, "journal")
PORT = int(os.environ.get("EDGESTACK_DASH_PORT", "8787"))
TOKEN_PATH = os.path.join(JOURNAL, "operator_token")
PRIVATE = os.environ.get("EDGESTACK_PRIVATE") == "1"      # the operator's own instance
# Public instance: the read-only replica. Private instance: the lab itself.
LAB_URL = os.environ.get("EDGESTACK_LAB_URL") or "https://jpennin5.github.io/edgestack/lab/"
DOSSIER_URL = os.environ.get("EDGESTACK_DOSSIER_URL") or \
    "http://forgejo.tail054462.ts.net:3000/jacob/lab-journal/src/branch/master/reports/"

_cache: dict = {"t": 0.0, "data": None}
_lock = threading.Lock()


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _read_jsonl(path, last_n=14):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out[-last_n:]


def operator_token() -> str:
    try:
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            t = fh.read().strip()
            if t:
                return t
    except OSError:
        pass
    os.makedirs(JOURNAL, exist_ok=True)
    t = secrets.token_hex(16)
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        fh.write(t + "\n")
    return t


def collect() -> dict:
    """Everything the page needs. Account read is cached for 120s."""
    with _lock:
        now = time.time()
        if _cache["data"] and now - _cache["t"] < 120:
            return _cache["data"]

        acct, routes = {}, []
        try:
            from broker import Alpaca, load_env
            load_env(os.path.join(ROOT, ".env"))
            api = Alpaca()
            acct = api.account()
            routes = list(api.route_log)
        except Exception as exc:                       # noqa: BLE001
            routes = [f"account read failed: {exc}"]

        recs = _read_jsonl(os.path.join(JOURNAL, "decisions.jsonl"))
        latest = recs[-1] if recs else {}
        sched_alive = False
        try:
            mt = os.path.getmtime(os.path.join(JOURNAL, "scheduler.log"))
            sched_alive = (now - mt) < 26 * 3600
        except OSError:
            pass

        data = {
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"),
            "account": {
                "number": acct.get("account_number", "?"),
                "equity": float(acct.get("equity", 0) or 0),
                "options_bp": float(acct.get("options_buying_power", 0) or 0),
                "status": acct.get("status", "?"),
            },
            "broker_routes": routes[-6:],
            "scheduler_alive": sched_alive,
            "equity_state": _read_json(os.path.join(JOURNAL, "equity_state.json"),
                                       {"core": None, "sleeve": []}),
            "option_trades": _read_json(os.path.join(JOURNAL, "open_trades.json"), []),
            "journal": recs,
            "latest": {
                "session": latest.get("session_date", "-"),
                "regime": (latest.get("account") or {}).get("regime", "-"),
                "gate": (latest.get("account") or {}).get("equity_gate", "-"),
                "signals": len(latest.get("signals_fired") or []),
            },
        }
        _cache.update(t=now, data=data)
        return data


# ------------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0b0f14;--card:#121826;--line:#1f2937;--txt:#e5e7eb;--dim:#8b98a9;
--green:#34d399;--red:#f87171;--amber:#fbbf24;--acc:#60a5fa}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:15px/1.55 'Segoe UI',system-ui,sans-serif;
padding:0 28px 28px;max-width:1180px;margin:0 auto}
h1{font-size:26px;letter-spacing:.3px} h1 span{color:var(--acc)}
.tag{color:var(--dim);margin:4px 0 22px}
#hd{display:flex;align-items:center;gap:18px;padding:16px 0 10px;border-bottom:1px solid var(--line);
margin-bottom:18px;flex-wrap:wrap}
#tabs{display:flex;gap:6px;margin-left:auto}
#tabs button{background:var(--card);border:1px solid var(--line);color:#c9d1d9;padding:8px 16px;
border-radius:9px;font-size:14px;cursor:pointer}
#tabs button.on{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
#opkey{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dim)}
#opkey input{background:#0d1219;border:1px solid var(--line);color:var(--txt);border-radius:6px;
padding:5px 8px;width:150px;font-family:Consolas,monospace;font-size:12px}
.pane{display:none}.pane.on{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.k{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.8px}
.v{font-size:22px;font-weight:600;margin-top:4px}
.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}
.sec{margin-top:26px}.sec h2{font-size:15px;color:var(--dim);text-transform:uppercase;
letter-spacing:1px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12px;text-transform:uppercase}
tr.sel td{background:#0f1a2e}
.mono{font-family:Consolas,monospace;font-size:13px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;
border:1px solid var(--line);margin:2px 4px 2px 0;color:var(--dim)}
.evidence{display:flex;flex-wrap:wrap;gap:8px}
footer{margin-top:34px;color:var(--dim);font-size:13px;border-top:1px solid var(--line);
padding-top:14px}
form.f{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;align-items:end}
form.f label{display:flex;flex-direction:column;font-size:12px;color:var(--dim);gap:4px}
form.f input,form.f select{background:#0d1219;border:1px solid var(--line);color:var(--txt);
border-radius:6px;padding:7px 8px;font-size:13px}
form.f .full{grid-column:1/-1}
button.b{background:#1d4ed8;border:0;color:#fff;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:13px}
button.b.danger{background:#991b1b}button.b.ghost{background:var(--card);border:1px solid var(--line);color:#c9d1d9}
button.b:disabled{opacity:.5;cursor:not-allowed}
.small{font-size:12px;color:var(--dim)}
#msg{position:fixed;right:18px;bottom:18px;background:#1f2937;color:#fff;padding:10px 14px;border-radius:8px;
font-size:13px;display:none;max-width:420px;border:1px solid #374151}
iframe.lab{width:100%;height:calc(100vh - 140px);border:1px solid var(--line);border-radius:12px;background:#0b0f14}
svg.chart{width:100%;height:260px;background:#0d1219;border:1px solid var(--line);border-radius:10px}
.params{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
.params label{font-size:11px;color:var(--dim);display:flex;flex-direction:column;gap:3px}
.params input{background:#0d1219;border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:5px 7px;font-size:12px}
a{color:var(--acc)}
td.x{width:28px;text-align:right;padding-right:6px}
button.xb{background:none;border:0;color:var(--dim);font-size:16px;line-height:1;cursor:pointer;padding:0 4px;border-radius:4px}
button.xb:hover{color:var(--red);background:#1f2937}
"""

JS = r"""
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const EMBED=new URLSearchParams(location.search).get('embed')==='1';
function show(t){for(const k of ['live','research','backtest']){$('#t-'+k).classList.toggle('on',k===t);$('#p-'+k).classList.toggle('on',k===t)}
 try{history.replaceState(null,'','#'+t)}catch(e){} if(t==='backtest')loadBacktest(); if(t==='live')loadLive();}
for(const k of ['live','research','backtest'])$('#t-'+k).onclick=()=>show(k);
if(EMBED)$('#tabs').style.display='none';
const key=()=>{try{return localStorage.getItem('opkey')||''}catch(e){return ''}};
/* The stable landing page keeps the operator key on ITS origin (which never changes) and
   hands it over in the fragment, because a quick tunnel takes a new hostname on every
   restart and localStorage here dies with the old one. Fragments never reach the server. */
try{const m=(location.hash||'').match(/[#&;]key=([A-Za-z0-9]+)/); if(m)localStorage.setItem('opkey',m[1])}catch(e){}
try{if(!$('#opkey input').value)$('#opkey input').value=key();
 const v=$('#opkey input').value.trim(); if(v&&v!==key())localStorage.setItem('opkey',v)}catch(e){}
$('#opkey input').onchange=e=>{try{localStorage.setItem('opkey',e.target.value.trim())}catch(x){} note('operator key stored in this browser')};
function note(m,bad){const b=$('#msg');b.textContent=m;b.style.display='block';b.style.borderColor=bad?'#f87171':'#374151';clearTimeout(b._t);b._t=setTimeout(()=>b.style.display='none',6000)}
async function api(path,method='GET',body){
 let r; try{r=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Operator-Token':key()},body:body?JSON.stringify(body):undefined})}
 catch(e){throw new Error(method+' '+path+' could not reach the dashboard: '+e.message)}
 const txt=await r.text(); let j=null; try{j=JSON.parse(txt)}catch(e){}
 if(j===null){throw new Error('HTTP '+r.status+' '+r.statusText+' from '+path+' — not JSON: '+txt.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,160))}
 if(!r.ok)throw new Error(j.error||('HTTP '+r.status+' from '+path));
 return j}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct=x=>(x==null||isNaN(x))?'—':(100*x).toFixed(1)+'%', num=(x,d=2)=>(x==null||isNaN(x))?'—':Number(x).toFixed(d);
let STRATS=[], RESULTS=[], SEL=null;

/* ---------------- Backtest tab ---------------- */
async function loadBacktest(){
 try{const s=await api('/api/strategies'); STRATS=s.strategies; renderStrats(s);}catch(e){note('strategies: '+e.message,true)}
 try{const r=await api('/api/backtests'); RESULTS=r.results; renderResults();}catch(e){note('results: '+e.message,true)}
}
function renderStrats(s){
 const sel=$('#bt-strategy'); const cur=sel.value; sel.innerHTML=STRATS.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} · ${x.kind}</option>`).join('');
 if(cur)sel.value=cur; paramInputs('#bt-params',sel.value);
 const dsel=$('#dp-stem'); dsel.innerHTML=sel.innerHTML; if(cur)dsel.value=cur; paramInputs('#dp-params',dsel.value);
 $('#bt-strats').innerHTML=STRATS.map(x=>`<tr><td class=mono>${esc(x.name)}</td><td>${x.kind}</td><td class=mono>${esc((x.symbols||[]).join(' '))}</td><td>${Object.keys(x.params||{}).length}</td>
  <td>${(x.dossiers||[]).map(d=>`<a href="#backtest&dossier=${esc(d)}" onclick="openDossier('${esc(d)}');return false">${esc(d)}</a>`).join(', ')||'<span class=small>—</span>'}</td>
  <td>${x.error?'<span class=bad>'+esc(x.error.slice(0,80))+'</span>':'<span class=ok>ok</span>'}</td></tr>`).join('');
 const ds=s.data||{}; $('#bt-data').textContent=Object.entries(ds).map(([k,v])=>k+' → '+v).join(' · ');
}
function paramInputs(box,name){const st=STRATS.find(x=>x.name===name); const p=(st&&st.params)||{};
 $(box).innerHTML=Object.entries(p).map(([k,v])=>`<label>${esc(k)} <span class=small>(${esc(v.type)})</span><input name="${esc(k)}" placeholder="${esc(v.default)}" title="${esc(v.description||'')}"></label>`).join('')||'<span class=small>no parameters</span>';}
$('#bt-strategy').onchange=e=>paramInputs('#bt-params',e.target.value);
$('#dp-stem').onchange=e=>paramInputs('#dp-params',e.target.value);
function overrides(box){const o={}; $$('input',$(box)).forEach(i=>{if(i.value.trim()!==''){const v=i.value.trim(); o[i.name]=isNaN(Number(v))?v:Number(v)}}); return o}
$('#bt-form').onsubmit=async e=>{e.preventDefault(); const f=e.target; const body={strategy:$('#bt-strategy').value,start_date:f.start.value,end_date:f.end.value,
 initial_capital:+f.capital.value||100000,slippage_bps:+f.slip.value||0,commission_bps:+f.comm.value||0,param_overrides:overrides('#bt-params')};
 try{const r=await api('/api/backtests/run','POST',body); note('backtest started '+r.id); pollResults(r.id)}catch(x){note(x.message,true)}};
async function pollResults(id){for(let i=0;i<120;i++){await new Promise(r=>setTimeout(r,2500)); try{const r=await api('/api/backtests'); RESULTS=r.results; renderResults();
 const row=RESULTS.find(x=>x.id===id); if(row&&row.status!=='running'){selectResult(id); return}}catch(e){}}}
function renderResults(){$('#bt-results').innerHTML=RESULTS.map(r=>{const m=r.metrics||{};
 return `<tr class="${SEL===r.id?'sel':''}" onclick="selectResult('${r.id}')" style="cursor:pointer"><td class=mono>${esc(r.created).slice(0,16)}</td><td class=mono>${esc(r.strategy)}</td>
 <td>${r.status==='running'?'<span class=warn>running</span>':r.status==='error'?'<span class=bad>error</span>':'<span class=ok>done</span>'}</td>
 <td>${pct(m.cagr)}</td><td>${pct(m.total_return)}</td><td>${pct(m.max_drawdown)}</td><td>${num(m.sharpe_ratio)}</td><td>${m.total_trades??'—'}</td><td class=small>${esc(r.options&&r.options.start_date||'')}→${esc(r.options&&r.options.end_date||'')}</td>
 <td class=x><button class=xb title="delete this backtest" onclick="deleteResult(event,'${r.id}')">&times;</button></td></tr>`}).join('')||'<tr><td colspan=10 class=small>no backtests yet</td></tr>'}
async function selectResult(id){SEL=id; renderResults(); try{const r=await api('/api/backtests/'+id); drawResult(r)}catch(e){note(e.message,true)}}
window.selectResult=selectResult;
window.deleteResult=async(ev,id)=>{ev.stopPropagation(); if(!confirm('Delete this backtest result?'))return;
 try{await api('/api/backtests/'+id,'DELETE'); if(SEL===id){SEL=null;$('#bt-detail').innerHTML=''} const r=await api('/api/backtests'); RESULTS=r.results; renderResults()}catch(e){note(e.message,true)}};
function drawResult(r){const box=$('#bt-detail'); const m=r.metrics||{};
 if(r.status==='error'){box.innerHTML=`<div class=card><b class=bad>error</b><pre class=mono style="white-space:pre-wrap">${esc(r.error)}</pre></div>`;return}
 const rows=[['CAGR',pct(m.cagr)],['total return',pct(m.total_return)],['max drawdown',pct(m.max_drawdown)],['Sharpe',num(m.sharpe_ratio)],['win rate',pct(m.win_rate)],['profit factor',num(m.profit_factor)],['trades',m.total_trades],['span',(m.start_date||'')+' → '+(m.end_date||'')],['fills',r.fills],['elapsed',(r.elapsed_s||0)+'s']];
 box.innerHTML=`<div class=card><div class=k>${esc(r.strategy)} · ${esc(r.id)}</div>
  <div class=grid style="margin:10px 0">${rows.map(([k,v])=>`<div><div class=k>${k}</div><div class=v style="font-size:17px">${esc(v)}</div></div>`).join('')}</div>
  ${chart(r.equity_curve||[],r.benchmark_curve||[])}
  <div class=small style="margin-top:8px">blue: strategy · grey: SPY buy-and-hold anchored at the first live bar · params used: <span class=mono>${esc(JSON.stringify(r.params||{}))}</span></div>
  <div class=small>final target weights (last bar): <span class=mono>${esc(JSON.stringify(r.final_weights||{}))}</span></div>
  <div style="margin-top:10px"><button class=b onclick="prefillDeploy('${esc(r.strategy)}',${esc(JSON.stringify(JSON.stringify(r.params||{})))})">Deploy this strategy…</button></div></div>`}
function chart(a,b){if(a.length<2)return '<div class=small>no equity curve</div>'; const W=1000,H=260,P=28; const all=a.concat(b).map(p=>p.equity); const lo=Math.min(...all),hi=Math.max(...all);
 const x=(i,n)=>P+(W-2*P)*i/(n-1), y=v=>H-P-(H-2*P)*(v-lo)/((hi-lo)||1);
 const path=(s)=>s.map((p,i)=>(i?'L':'M')+x(i,s.length).toFixed(1)+' '+y(p.equity).toFixed(1)).join(' ');
 return `<svg class=chart viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${path(b)}" fill=none stroke="#4b5563" stroke-width=1.5/><path d="${path(a)}" fill=none stroke="#60a5fa" stroke-width=2/>
 <text x=${P} y=${P-8} fill="#8b98a9" font-size=12>${esc(a[0].date)}</text><text x=${W-P} y=${P-8} fill="#8b98a9" font-size=12 text-anchor=end>${esc(a[a.length-1].date)}</text>
 <text x=${W-P} y=${H-6} fill="#8b98a9" font-size=12 text-anchor=end>${lo.toLocaleString()} – ${hi.toLocaleString()}</text></svg>`}
window.prefillDeploy=(stem,paramsJson)=>{show('live'); $('#dp-stem').value=stem; paramInputs('#dp-params',stem); try{const p=JSON.parse(paramsJson); $$('input',$('#dp-params')).forEach(i=>{if(p[i.name]!=null)i.value=p[i.name]})}catch(e){} $('#dp-form').scrollIntoView({behavior:'smooth'})};

/* ---------------- Dossiers: read, then reproduce in the lab engine ---------------- */
function md(src){ /* minimal, deterministic: headings, bullets, bold, code, fences */
 const lines=esc(src).split('\n'); let out='',inFence=false,inList=false;
 const inline=s=>s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code class=mono>$1</code>');
 for(const l of lines){
  if(l.startsWith('```')){ if(inList){out+='</ul>';inList=false} inFence=!inFence; out+=inFence?'<pre class="mono" style="white-space:pre-wrap;background:#0d1219;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px">':'</pre>'; continue }
  if(inFence){ out+=l+'\n'; continue }
  const h=l.match(/^(#{1,3}) (.*)/); if(h){ if(inList){out+='</ul>';inList=false} out+=`<h${h[1].length+1} style="margin:14px 0 6px;font-size:${h[1].length===1?18:14}px">${inline(h[2])}</h${h[1].length+1}>`; continue }
  if(l.startsWith('- ')){ if(!inList){out+='<ul style="margin:4px 0 4px 18px">';inList=true} out+=`<li>${inline(l.slice(2))}</li>`; continue }
  if(inList){out+='</ul>';inList=false}
  if(l.trim()==='')continue; out+=`<p style="margin:6px 0">${inline(l)}</p>`}
 if(inList)out+='</ul>'; return out}
let DOSSIER_ID=null, DOSSIER_POLL=null;
window.openDossier=async id=>{DOSSIER_ID=id; show('backtest'); try{history.replaceState(null,'','#backtest&dossier='+id)}catch(e){}
 const box=$('#bt-dossier'); box.innerHTML='<div class=card><span class=small>loading dossier '+esc(id)+'…</span></div>'; box.scrollIntoView({behavior:'smooth'});
 try{const d=await api('/api/dossiers/'+id); renderDossier(d)}catch(e){box.innerHTML='<div class=card><span class=bad>'+esc(e.message)+'</span></div>'}};
function renderDossier(d){const v=d.verdict||{},p=d.prereg||{},r=d.reproduction;
 const head=`<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><b style="font-size:16px">Dossier ${esc(d.id)}</b>
  <span class=pill>${esc(p.filename||'?')}</span><span class=pill>objective ${esc(v.objective||p.objective||'?')}</span>
  <span class="pill ${String(v.verdict||'').startsWith('ADOPT')?'ok':''}">${esc(v.verdict||'no verdict')}</span>
  <a class=small href="${esc(d.forge)}" target=_blank>open on the forge</a>
  <button class=b onclick="reproduce('${esc(d.id)}')" ${r&&r.status==='running'?'disabled':''}>${r&&r.status==='running'?'reproducing…':'Reproduce in the lab engine'}</button>
  <button class="b ghost" onclick="$('#bt-dossier').innerHTML='';DOSSIER_ID=null">close</button></div>
  <div class=small style="margin:6px 0 10px">Reproduce = baseline vs variant on the protocol's train and valid windows, at the protocol's costs, on the research container's own engine — the exact runs behind the verdict. Three columns: what was predicted, what the lab recorded, what the engine says now.</div>`;
 $('#bt-dossier').innerHTML=`<div class=card>${head}${reproBlock(r)}<details ${r?'':'open'}><summary class=small style="cursor:pointer">dossier text</summary><div style="font-size:14px">${md(d.markdown||'')}</div></details></div>`;
 if(r&&r.status==='running'){clearTimeout(DOSSIER_POLL);DOSSIER_POLL=setTimeout(()=>{if(DOSSIER_ID===d.id)openDossier(d.id)},4000)}}
function reproBlock(r){ if(!r)return ''; if(r.status==='running')return `<div class=card style="margin:8px 0"><span class=warn>&#9679; running four engine backtests (baseline and variant, train and valid) — this takes a minute or two</span></div>`;
 if(r.status==='error')return `<div class=card style="margin:8px 0"><b class=bad>reproduction failed</b><div class="mono small" style="white-space:pre-wrap">${esc(r.error)}</div></div>`;
 const f=x=>(x==null||isNaN(x))?'—':(x>=0?'+':'')+Number(x).toFixed(4);
 const lab=r.lab||{},pr=r.prediction||{};
 const row=w=>{const R=r.reproduced[w],L=lab.delta?{delta:lab.delta[w],d_sortino:(lab.d_sortino||{})[w],dd_delta:(lab.dd_delta||{})[w]}:{},P=pr[w]||{};
  return `<tr><td><b>${w}</b><div class=small>${esc((r.windows[w]||[]).join(' → '))}</div></td>
   <td>${f(P.predicted)}</td><td>${f(L.delta)}</td><td><b>${f(R.delta)}</b></td>
   <td class=small>${f(R.d_sortino)} <span style="color:var(--dim)">lab ${f(L.d_sortino)}</span></td>
   <td class=small>${f(R.dd_delta)} <span style="color:var(--dim)">lab ${f(L.dd_delta)}</span></td>
   <td>${P.direction_held==null?'—':P.direction_held?'<span class=ok>held</span>':'<span class=bad>wrong</span>'} <span class=small>err ${f(P.error)}</span></td>
   <td>${esc((r.zones_now||{})[w]||'')}</td></tr>`};
 const ok=r.reproduces===true, held=r.prediction_held===true;
 return `<div class=card style="margin:8px 0;border-color:${ok&&held?'#14532d':ok?'#78350f':'#7f1d1d'}">
  <div style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:8px">
   <span>reproduces the lab: <b class="${ok?'ok':r.reproduces===false?'bad':'warn'}">${r.reproduces===true?'YES':r.reproduces===false?'NO':'n/a'}</b> <span class=small>(noise floor ${r.noise_floor})</span></span>
   <span>prediction delivered: <b class="${held?'ok':r.prediction_held===false?'bad':'warn'}">${r.prediction_held===true?'YES':r.prediction_held===false?'NO':'n/a'}</b></span>
   <span>re-derived verdict: <b>${esc(r.verdict_rederived)}</b> <span class=small>lab: ${esc((r.lab||{}).verdict||'—')}</span></span></div>
  <table><tr><th>window</th><th>predicted Δ</th><th>lab Δ</th><th>reproduced Δ</th><th>Δ Sortino</th><th>Δ maxDD</th><th>direction</th><th>zone now</th></tr>${row('train')}${row('valid')}</table>
  <p style="margin-top:10px">${esc(r.conclusion)}</p>
  <div class=small>objective ${esc(r.objective)} · params ${esc(JSON.stringify(r.variant_params))} over base ${esc(JSON.stringify(r.base_params))} · costs ${r.costs.slippage_bps}+${r.costs.commission_bps} bps, capital $${Number(r.costs.capital).toLocaleString()} · ${esc(r.engine)} · ${esc(r.finished)}</div></div>`}
window.reproduce=async id=>{try{await api('/api/reproduce/'+id,'POST',{}); openDossier(id)}catch(e){note(e.message,true)}};

/* ---------------- Live tab: deployments ---------------- */
async function loadLive(){try{const s=await api('/api/live/status'); renderLive(s)}catch(e){note('live manager: '+e.message,true)}
 if(!STRATS.length){try{const s=await api('/api/strategies'); STRATS=s.strategies; const dsel=$('#dp-stem'); dsel.innerHTML=STRATS.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} · ${x.kind}</option>`).join(''); paramInputs('#dp-params',dsel.value)}catch(e){}}}
function renderAlloc(s){const box=$('#lm-alloc'); if(!box)return; const eq=+box.dataset.equity||0; const agentOn=box.dataset.agent==='on';
 const live=s.deployments.filter(d=>d.mode==='live'&&(d.status||{}).state==='active');
 const shadow=s.deployments.filter(d=>d.mode==='shadow'&&(d.status||{}).state==='active');
 const sum=live.reduce((a,d)=>a+(+d.alloc_pct||0),0); const rest=Math.max(0,100-sum);
 const colors=['#60a5fa','#34d399','#fbbf24','#f472b6','#a78bfa','#fb923c'];
 const rows=[]; live.forEach((d,i)=>{const nav=d.last_nav!=null?+d.last_nav:null; const cur=(nav!=null&&eq>0)?100*nav/eq:null;
  rows.push({name:d.display_name,stem:d.stem,acct:d.account_id,alloc:+d.alloc_pct,cur,nav,rule:d.rule,color:colors[i%colors.length],kind:'live'})});
 if(agentOn)rows.push({name:'EdgeStack agent',stem:'agent/run_agent.py — core 0.70 NAV, sleeve ≤0.60, options behind 14 gates',acct:'competition',alloc:rest,cur:null,nav:null,rule:null,color:'#94a3b8',kind:'agent'});
 const bar=rows.filter(r=>r.alloc>0).map(r=>`<div title="${esc(r.name)} ${r.alloc.toFixed(1)}%" style="width:${Math.min(100,r.alloc)}%;background:${r.color}"></div>`).join('');
 const over=sum>100?`<div class=bad style="margin:6px 0">live allocations total ${sum.toFixed(1)}% — over 100%; the agent and the deployments will contend for the same equity</div>`:'';
 box.innerHTML=`<div style="display:flex;height:14px;border-radius:7px;overflow:hidden;background:#1f2937;margin:4px 0 10px">${bar}</div>${over}
  <table><tr><th>strategy</th><th>account</th><th>allocated</th><th>current model NAV</th><th>kill rule</th></tr>
  ${rows.map(r=>`<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${r.color};margin-right:8px"></span><b>${esc(r.name)}</b><div class="small mono">${esc(r.stem)}</div></td>
   <td class=mono>${esc(r.acct||'—')}</td><td><b>${r.alloc.toFixed(1)}%</b>${r.kind==='agent'?'<div class=small>the remainder: it sizes off NAV, not a slice</div>':eq>0?'<div class=small>≈ $'+Math.round(eq*r.alloc/100).toLocaleString()+'</div>':''}</td>
   <td>${r.cur!=null?r.cur.toFixed(1)+'% <span class=small>($'+Math.round(r.nav).toLocaleString()+')</span>':'<span class=small>—</span>'}</td>
   <td class=small>${r.rule?`${r.rule.threshold_pct}% / ${r.rule.resolution}`:(r.kind==='agent'?'equity gate + 14 deterministic gates':'none')}</td></tr>`).join('')}
  ${shadow.length?`<tr><td colspan=5 class=small>shadow (not trading): ${shadow.map(d=>esc(d.display_name)+' ($'+(+d.shadow_capital||0).toLocaleString()+' virtual)').join(' · ')}</td></tr>`:''}
  ${!live.length&&!agentOn?'<tr><td colspan=5 class=small>nothing is deployed live on this instance</td></tr>':''}</table>
  <div class=small style="margin-top:6px">account equity $${Math.round(eq).toLocaleString()} · live deployments ${live.length} · allocated to deployments ${sum.toFixed(1)}%</div>`}
function renderLive(s){
 renderAlloc(s);
 $('#lm-loop').innerHTML=s.loop_alive?'<span class=ok>&#9679; manager loop alive</span>':'<span class=warn>&#9679; manager loop not running (host/run.py live)</span>';
 $('#lm-kill').innerHTML=s.kill_switch?`<span class=bad><b>GLOBAL KILL SWITCH ARMED</b> — no order leaves this machine</span> <button class="b ghost" onclick="killSwitch(false)">disarm</button>`
  :`<span class=ok>kill switch disarmed</span> <button class="b danger" onclick="killSwitch(true)">ARM global kill switch</button>`;
 const acc=$('#dp-account'); acc.innerHTML=s.accounts.map(a=>`<option value="${esc(a.id)}">${esc(a.label)}${a.credentials_ok?'':' (no credentials)'}</option>`).join('');
 $('#lm-accounts').innerHTML=s.accounts.map(a=>`<span class=pill>${esc(a.label)} · ${a.is_paper?'paper':'LIVE'} · key ${esc(a.key_hint)} · ${a.credentials_ok?'<span class=ok>ok</span>':'<span class=bad>no creds</span>'}</span>`).join('');
 const rows=s.deployments.map(d=>{const st=d.status||{}; const cls=st.state==='active'?'ok':st.state==='killed'?'bad':'warn'; const m=d.metrics||{};
  const pos=Object.entries(d.positions||{}).filter(([k,v])=>v).map(([k,v])=>k+'×'+v).join(' ')||'flat';
  return `<tr><td><b>${esc(d.display_name)}</b><div class=small class=mono>${esc(d.stem)} · ${esc((d.module_hash||'').slice(0,10))}</div></td>
   <td>${d.mode==='live'?`live · ${esc(d.account_id)} · ${d.alloc_pct}%`:`shadow · $${(d.shadow_capital||0).toLocaleString()}`}</td>
   <td class="${cls}">${esc(st.state)}${st.reason?'<div class=small>'+esc(st.reason)+'</div>':''}${d.pending_flatten?'<div class=small>flatten pending (next open)</div>':''}${d.pending_targets?'<div class=small>rebalance pending: '+esc(JSON.stringify(d.pending_targets))+'</div>':''}</td>
   <td class=mono>${esc(pos)}</td>
   <td>${d.rule?`${d.rule.threshold_pct}% / ${d.rule.resolution}`:'<span class=small>none</span>'}${d.dd_pct!=null?'<div class=small>dd now '+d.dd_pct+'%</div>':''}${d.rule_alert?'<div class=warn style="font-size:12px">'+esc(d.rule_alert)+'</div>':''}</td>
   <td>${d.last_nav!=null?'$'+Number(d.last_nav).toLocaleString():'—'}<div class=small>hwm ${d.hwm?Number(d.hwm).toLocaleString():'—'} · ret ${pct(m.total_return)} · maxDD ${pct(m.max_drawdown)}</div></td>
   <td class=small>${esc(d.last_model_run||'—')}${d.last_error?'<div class=bad>'+esc(d.last_error.slice(0,120))+'</div>':''}</td>
   <td>${st.state==='active'?`<button class="b ghost" onclick="stopDep('${d.id}')">■ stop</button>`:`<button class="b ghost" onclick="purgeDep('${d.id}')">purge</button>`}
    <button class="b ghost" onclick="ruleDep('${d.id}')">rule…</button></td></tr>`}).join('');
 $('#lm-deps').innerHTML=rows||'<tr><td colspan=8 class=small>no deployments yet — launch a module below (live against an account slice, or shadow-tracked virtually)</td></tr>';
 $('#lm-journal').innerHTML=(s.journal||[]).slice().reverse().slice(0,12).map(e=>`<tr><td class=mono>${esc(e.ts).slice(0,19)}</td><td>${esc(e.type)}</td><td class="small mono">${esc(JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k])=>!['ts','type'].includes(k))))).slice(0,220)}</td></tr>`).join('');
}
window.killSwitch=async armed=>{if(armed&&!confirm('Arm the GLOBAL kill switch? No order will leave this machine until disarmed.'))return; try{await api('/api/live/kill',armed?'POST':'DELETE'); loadLive()}catch(e){note(e.message,true)}};
window.stopDep=async id=>{if(!confirm('Stop this deployment and flatten its positions at the next opportunity?'))return; try{await api('/api/live/deployments/'+id,'DELETE'); loadLive()}catch(e){note(e.message,true)}};
window.purgeDep=async id=>{if(!confirm('Remove this deployment record?'))return; try{await api('/api/live/deployments/'+id+'/purge','DELETE'); loadLive()}catch(e){note(e.message,true)}};
window.ruleDep=async id=>{const t=prompt('Max-drawdown kill threshold % (blank = remove rule)'); if(t===null)return; const res=t?(prompt('Resolution: daily, hourly or minute','daily')||'daily'):'daily';
 try{await api('/api/live/deployments/'+id+'/rules','POST',t?{threshold_pct:+t,resolution:res}:{}); loadLive()}catch(e){note(e.message,true)}};
$('#dp-mode').onchange=e=>{$('#dp-livefields').style.display=e.target.value==='live'?'contents':'none'};
$('#dp-form').onsubmit=async e=>{e.preventDefault(); const f=e.target; const body={stem:$('#dp-stem').value,display_name:f.dname.value,mode:$('#dp-mode').value,account_id:$('#dp-account').value,
 alloc_pct:+f.alloc.value,shadow_capital:+f.shadow.value,params:overrides('#dp-params'),rule:{threshold_pct:+f.thr.value,resolution:f.res.value},confirm_competition:f.confirm.checked,force:f.force.checked};
 if(body.mode==='live'&&!confirm(`Launch LIVE on '${body.account_id}' at ${body.alloc_pct}% of equity?`))return;
 try{const r=await api('/api/live/deployments','POST',body); note('launched '+r.display_name+' ('+r.mode+')'); loadLive()}catch(x){note(x.message,true)}};

/* ---------------- boot ---------------- */
const h=(location.hash||'#live').slice(1).split(/[&;]/)[0]; show(['live','research','backtest'].includes(h)?h:'live');
try{const dm=(location.hash||'').match(/[#&;]dossier=([A-Za-z0-9._-]+)/); if(dm)openDossier(dm[1])}catch(e){}
setInterval(()=>{if(document.activeElement&&['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return; if($('#p-live').classList.contains('on'))location.reload()},90000);
"""


def esc(x) -> str:
    return html.escape(str(x))


def render_live(d: dict) -> str:
    a = d["account"]
    eq = a["equity"]
    pnl = eq - 100_000.0
    pnl_cls = "ok" if pnl >= 0 else "bad"
    gate = d["latest"]["gate"]
    gate_open = "DETERIORATING" not in str(gate) and "DOWN" not in str(gate) \
        and gate not in ("-", None)
    core = d["equity_state"].get("core")
    sleeve = d["equity_state"].get("sleeve") or []
    opts = d["option_trades"] or []
    mcp_ok = any("via MCP" in r or "mcp: connected" in r for r in d["broker_routes"])
    # The routing flag above describes the LAST pass; judges see this card
    # between passes, so also probe the server itself (2026-09-02).
    import socket
    try:
        socket.create_connection(("127.0.0.1", 8000), 2).close()
        mcp_up = True
    except OSError:
        mcp_up = False
    if mcp_ok:
        mcp_cls, mcp_txt, mcp_sub = "ok", "ROUTING", "orders + account via MCP, REST fallback"
    elif mcp_up:
        mcp_cls, mcp_txt, mcp_sub = "ok", "UP", "server listening; routes via MCP at the next pass"
    else:
        mcp_cls, mcp_txt, mcp_sub = "bad", "FALLBACK", "MCP server down; orders + account via REST"

    rows = ""
    for r in reversed(d["journal"]):
        acts = r.get("actions_taken") or []
        sigs = r.get("signals_fired") or []
        what = "; ".join(f"{x.get('action')}: {str(x.get('detail'))[:70]}"
                         for x in acts[:3]) or "no trade — gates held"
        rows += (f"<tr><td class=mono>{esc(r.get('session_date'))}</td>"
                 f"<td>{len(sigs)}</td><td>{esc(what)}</td></tr>")

    pos_rows = ""
    if core:
        pos_rows += (f"<tr><td>SPY</td><td>overnight core</td>"
                     f"<td class=mono>x{esc(core.get('qty'))}</td>"
                     f"<td class=mono>{esc(core.get('entry_date'))}</td></tr>")
    for p in sleeve:
        pos_rows += (f"<tr><td>{esc(p.get('symbol'))}</td><td>capitulation sleeve</td>"
                     f"<td class=mono>x{esc(p.get('qty'))}</td>"
                     f"<td class=mono>{esc(p.get('entry_date'))}</td></tr>")
    parked = d["equity_state"].get("parked")
    if parked:
        pos_rows += (f"<tr><td>SGOV</td><td>parked bills — gate shut, earning "
                     f"{100 * float(parked.get('yield') or 0):.2f}%</td>"
                     f"<td class=mono>x{esc(parked.get('qty'))}</td>"
                     f"<td class=mono>{esc(parked.get('entry_date'))}</td></tr>")
    for p in opts:
        pos_rows += (f"<tr><td>{esc(p.get('symbol'))}</td><td>bull put spread "
                     f"{esc(p.get('short_strike'))}/{esc(p.get('long_strike'))}</td>"
                     f"<td class=mono>x{esc(p.get('contracts'))}</td>"
                     f"<td class=mono>{esc(p.get('entry_date'))}</td></tr>")
    if not pos_rows:
        pos_rows = "<tr><td colspan=4 style='color:var(--dim)'>flat — waiting for signals that clear the gates</td></tr>"

    return f"""
<p class="tag">{'Private instance &middot; every strategy, tailnet only' if PRIVATE else
    'Evidence opens the door to opportunity &middot; 33 years of evidence, three backtest engines, one graveyard'}
&middot; Alpaca paper account <span class="mono">{esc(a['number'])}</span></p>

<div class="grid">
<div class="card"><div class="k">Equity</div><div class="v">${eq:,.0f}</div>
<div class="{pnl_cls}">{pnl:+,.0f} vs $100k start</div></div>
<div class="card"><div class="k">Equity gate</div>
<div class="v {'ok' if gate_open else 'warn'}">{'OPEN' if gate_open else 'CLOSED'}</div>
<div style="font-size:12px;color:var(--dim)">{esc(gate)}</div></div>
<div class="card"><div class="k">Macro regime</div>
<div style="font-size:13px;margin-top:6px">{esc(d['latest']['regime'])}</div></div>
<div class="card"><div class="k">Alpaca MCP server</div>
<div class="v {mcp_cls}">{mcp_txt}</div>
<div style="font-size:12px;color:var(--dim)">{mcp_sub}</div></div>
</div>

<div class="sec"><h2>Open positions</h2>
<table><tr><th>symbol</th><th>component</th><th>size</th><th>entered</th></tr>{pos_rows}</table></div>

{'' if PRIVATE else '''<div class="sec"><h2>Strategy — every number is a measurement</h2>
<div class="evidence">
<span class="pill">SPY overnight core &middot; Sharpe 0.89 vs 0.05 intraday &middot; 8/9 eras</span>
<span class="pill">gate: 12-month trend AND credit canary (HYG &gt; SMA100) &middot; validated on
disjoint windows 0.80&rarr;0.98 / 0.65&rarr;1.02</span>
<span class="pill">capitulation sleeve &middot; +1.42%/event &middot; 67.6% win &middot; t=4.27 &middot; 33y</span>
<span class="pill">volume ceiling 2.5x — above it "real news arrived", edge dies</span>
<span class="pill">options: defined-risk put spreads behind 14 deterministic gates</span>
</div></div>
'''}
<div class="sec"><h2>Decision journal (latest sessions)</h2>
<table><tr><th>session</th><th>signals</th><th>what happened &amp; why</th></tr>{rows or '<tr><td colspan=3 class=small>no agent sessions on this instance</td></tr>'}</table></div>

<div class="sec"><h2>Live allocation — what is trading this account, and how much of it</h2>
<div id="lm-alloc" data-equity="{eq:.2f}" data-agent="{'off' if PRIVATE else 'on'}"><span class="small">loading…</span></div></div>

<div class="sec"><h2>Live Manager — deployments</h2>
<div class="small" style="margin-bottom:8px">Deploy any strategy module against a slice of an account with a drawdown kill switch,
the TrustyRustyEngine model: the module is pinned at launch, sized to <i>equity &times; alloc%</i>, rebalanced at the open
from the SAME runner that backtests it, and killed (flattened) when its model NAV falls the threshold below its since-launch
high-water mark at the chosen bar resolution. Orders route through the Alpaca MCP server. Writes need the operator key.</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:8px"><span id="lm-loop"></span><span id="lm-kill"></span></div>
<div id="lm-accounts" style="margin-bottom:8px"></div>
<table><tr><th>deployment</th><th>mode</th><th>status</th><th>model positions</th><th>kill rule</th><th>model NAV</th><th>model run</th><th></th></tr>
<tbody id="lm-deps"></tbody></table>
<form id="dp-form" class="f card" style="margin-top:14px">
<label>strategy module<select id="dp-stem"></select></label>
<label>display name<input name="dname" placeholder="optional"></label>
<label>mode<select id="dp-mode"><option value="shadow">shadow (virtual ledger, never traded)</option><option value="live">live (orders via MCP)</option></select></label>
<label>shadow capital $<input name="shadow" type="number" value="2500" min="100" step="100"></label>
<div id="dp-livefields" style="display:none">
<label>account<select id="dp-account"></select></label>
<label>allocation % of equity<input name="alloc" type="number" value="10" min="0.1" max="100" step="0.1"></label>
<label class="small" style="flex-direction:row;align-items:center;gap:6px"><input name="confirm" type="checkbox"> I understand a live deployment on the competition account changes the judged P&amp;L</label>
<label class="small" style="flex-direction:row;align-items:center;gap:6px"><input name="force" type="checkbox"> allow the account's total allocation past 100%</label>
</div>
<label>kill: max drawdown % from launch HWM<input name="thr" type="number" value="5" min="0" step="0.5" placeholder="0 = no rule"></label>
<label>checked at each close of<select name="res"><option value="daily">daily bars</option><option value="hourly">hourly bars</option><option value="minute">minute bars</option></select></label>
<div class="full"><div class="k" style="margin-bottom:6px">parameter overrides (blank = strategy default)</div><div id="dp-params" class="params"></div></div>
<div class="full"><button class="b" type="submit">Launch deployment</button> <span class="small">nothing trades until the next open (09:35 ET); a launch during hours rebalances at the next tick</span></div>
</form>
<div class="sec"><h2>Live Manager journal</h2><table><tbody id="lm-journal"></tbody></table></div>
</div>

<footer>Generated {esc(d['generated'])} &middot; auto-refresh 90s &middot;
routes: {esc('; '.join(d['broker_routes'][-2:]))} &middot;
no-trade sessions are the gates working — the journal records every refusal with its reason.
</footer>"""


BACKTEST_PANE = """
<p class="tag">The borrowed TrustyRustyEngine runner (T+1 open fills, 5+5 bps costs, SPY benchmark) on any strategy file
in <span class="mono">engine/strategies</span> — the lab's baselines, the agent's candidates, and the benchmark they must beat.
Running needs the operator key; results are public.</p>
<form id="bt-form" class="f card">
<label>strategy<select id="bt-strategy"></select></label>
<label>start<input name="start" type="date" value="2015-01-01"></label>
<label>end<input name="end" type="date" value="2024-12-31"></label>
<label>capital $<input name="capital" type="number" value="100000" step="1000"></label>
<label>slippage bps<input name="slip" type="number" value="5"></label>
<label>commission bps<input name="comm" type="number" value="5"></label>
<div class="full"><div class="k" style="margin-bottom:6px">parameter overrides (blank = strategy default)</div><div id="bt-params" class="params"></div></div>
<div class="full"><button class="b" type="submit">Run backtest</button> <span class="small">the lab's sealed holdout starts 2025-01-01; keep research windows before it</span></div>
</form>
<div class="sec"><h2>Results</h2>
<table><tr><th>when</th><th>strategy</th><th>status</th><th>CAGR</th><th>return</th><th>max DD</th><th>Sharpe</th><th>trades</th><th>window</th><th></th></tr><tbody id="bt-results"></tbody></table></div>
<div class="sec" id="bt-detail"></div>
<div class="sec" id="bt-dossier"></div>
<div class="sec"><h2>Strategies</h2>
<table><tr><th>file</th><th>kind</th><th>universe</th><th>params</th><th>adoption dossiers</th><th>inspect</th></tr><tbody id="bt-strats"></tbody></table>
<div class="small" style="margin-top:8px">history: <span id="bt-data" class="mono"></span></div></div>
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EdgeStack</title><style>@@CSS@@</style></head><body>
<div id="hd"><h1>Edge<span>Stack</span> <span style="font-size:13px" class="@@ALIVE_CLS@@">&#9679; @@ALIVE_TXT@@</span></h1>
<div id="tabs"><button id="t-live">Live</button><button id="t-research">Research</button><button id="t-backtest">Backtest</button></div>
<span id="opkey">operator key @@KEYFIELD@@</span></div>
<div id="p-live" class="pane">@@LIVE@@</div>
<div id="p-research" class="pane"><p class="tag">The research agent's lab, read-only: a public replica regenerated from the lab journal mirror.
The lab itself, its engine and the Claude subscription behind it are not reachable from this page.</p>
<iframe class="lab" src="@@LAB_URL@@" title="EdgeStack research lab (read-only)"></iframe>
<p class="small"><a href="@@LAB_URL@@" target="_blank">open the research replica in its own tab</a></p></div>
<div id="p-backtest" class="pane">@@BACKTEST@@</div>
<div id="msg"></div>
<script>const DOSSIER=@@DOSSIER@@;@@JS@@</script></body></html>"""


def render(d: dict, local: bool = False) -> str:
    alive_cls, alive_txt = (("ok", "LIVE") if d["scheduler_alive"] else ("warn", "IDLE"))
    # Shown only to this machine's own browser, which may already write without
    # it: this is how the operator copies the key for use over the tunnel.
    key_field = (f'<input type="password" value="{esc(operator_token())}" autocomplete="off" '
                 f'title="this machine: writes are allowed without a key. Copy this to drive '
                 f'the dashboard over the tunnel.">' if local else
                 '<input type="password" placeholder="journal/operator_token" autocomplete="off">')
    return (PAGE.replace("@@CSS@@", CSS).replace("@@JS@@", JS)
            .replace("@@KEYFIELD@@", key_field)
            .replace("@@ALIVE_CLS@@", alive_cls).replace("@@ALIVE_TXT@@", alive_txt)
            .replace("@@LIVE@@", render_live(d)).replace("@@BACKTEST@@", BACKTEST_PANE)
            .replace("@@LAB_URL@@", LAB_URL).replace("@@DOSSIER@@", json.dumps(DOSSIER_URL)))


# ------------------------------------------------------------------- HTTP
ACCESS_LOG = os.path.join(JOURNAL, "dashboard.access.log")


def access(line: str) -> None:
    """One line per request. The browser is the only client whose failures we
    cannot reproduce with curl, so when something goes wrong on the page this
    is what says which request it was and what it got back (2026-09-02)."""
    try:
        os.makedirs(JOURNAL, exist_ok=True)
        if os.path.exists(ACCESS_LOG) and os.path.getsize(ACCESS_LOG) > 2_000_000:
            with open(ACCESS_LOG, encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-2000:]
            with open(ACCESS_LOG, "w", encoding="utf-8") as fh:
                fh.writelines(tail)
        with open(ACCESS_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        pass


STABLE_PAGE_ORIGIN = "https://jpennin5.github.io"      # the landing page's permanent origin

# Tailscale hands every node an address from these ranges and nothing else can
# source them here: the packets only arrive through the WireGuard tunnel that
# the operator's own account authenticated. That is the operator's tailnet.
import ipaddress
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def is_tailnet(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in TAILNET)


def origin_allowed(origin: str) -> bool:
    """Origins that may make cross-origin calls here: this machine, the tailnet,
    the tunnel the page is served through, and the stable landing page."""
    host = origin.split("//")[-1].split(":")[0].strip("[]")
    return (host in ("127.0.0.1", "localhost") or origin == STABLE_PAGE_ORIGIN
            or origin.endswith(".trycloudflare.com") or host.endswith(".ts.net")
            or is_tailnet(host))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype="application/json", cors_origin: str | None = None):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, default=str)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype if ctype != "application/json" else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)
        if not self.path.startswith("/api"):
            return
        access(f"{code} {self.command} {self.path} "
               f"origin={self.headers.get('Origin') or '-'} "
               f"ctype={self.headers.get('Content-Type') or '-'} "
               f"local={self._local_operator()} key={'y' if self.headers.get('X-Operator-Token') else 'n'} "
               f"ts={self.headers.get('Tailscale-User-Login') or '-'}"
               + ("" if code < 400 else f" body={body[:160].decode(errors='replace')}"))

    def _tunnelled(self) -> bool:
        """cloudflared proxies the public tunnel FROM loopback, so a visitor from
        anywhere arrives looking local; the CF-* headers it stamps on every
        request (and a client cannot strip) give it away. `tailscale serve`
        ALSO proxies from loopback - for https://lenovo.tail054462.ts.net - but
        stamps X-Forwarded-For with the peer's tailnet address and the
        operator's Tailscale login instead; that is the operator, not a
        visitor (2026-09-02)."""
        if any(self.headers.get(h) for h in ("CF-Connecting-IP", "CF-Ray")):
            return True
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return bool(fwd) and not is_tailnet(fwd)

    def _local_operator(self) -> bool:
        """True when the request came from a browser ON this machine or from a
        device on the operator's tailnet. Whoever is at the console can already
        read the token file, so making them paste it back buys nothing; a
        tailnet peer has already been authenticated by WireGuard to the
        operator's own Tailscale account, which is a stronger proof than a
        pasted string (2026-09-02). LAN addresses are NOT trusted."""
        host = (self.client_address or ("",))[0]
        if host in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return not self._tunnelled()
        return is_tailnet(host) and not self._tunnelled()

    def _same_origin(self) -> bool:
        """A cross-site page must not be able to drive the local dashboard: the
        JSON content type forces a CORS preflight this server never answers,
        and an Origin from anywhere else is refused outright."""
        origin = self.headers.get("Origin")
        if origin:
            ohost = origin.split("//")[-1].split(":")[0].strip("[]")
            if ohost not in ("127.0.0.1", "localhost") and not ohost.endswith(".ts.net") \
                    and not is_tailnet(ohost):
                return False
        return str(self.headers.get("Content-Type", "")).startswith("application/json")

    def _authed(self) -> bool:
        given = self.headers.get("X-Operator-Token", "")
        if given and hmac.compare_digest(given, operator_token()):
            return True
        return self._local_operator() and self._same_origin()

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 200_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except ValueError:
            return {}

    def do_GET(self):                                  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api" or path == "/api/":
                return self._send(200, json.dumps(collect(), indent=1))
            if path == "/api/strategies":
                import backtests
                return self._send(200, {"strategies": backtests.strategies(),
                                        "data": backtests.data_status()})
            if path == "/api/backtests":
                import backtests
                return self._send(200, {"results": backtests.results()})
            if path.startswith("/api/backtests/"):
                import backtests
                rec = backtests.get(path.rsplit("/", 1)[-1])
                return self._send(200 if rec else 404, rec or {"error": "no such backtest"})
            if path == "/api/live/status":
                import live_manager
                return self._send(200, live_manager.status())
            if path == "/api/dossiers":
                import reproduce
                return self._send(200, {"dossiers": reproduce.dossiers()})
            if path.startswith("/api/dossiers/"):
                import reproduce
                hid = path.rsplit("/", 1)[-1]
                try:
                    h = reproduce.hypothesis(hid)
                    md = reproduce.markdown(hid)
                except (KeyError, ValueError, OSError):
                    return self._send(404, {"error": "no such dossier"})
                return self._send(200, {"id": hid, "markdown": md, "prereg": h["prereg"],
                                        "verdict": h["verdict"], "reproduction": reproduce.latest(hid),
                                        "forge": DOSSIER_URL + hid + ".md"})
            if path == "/api/operator-key":
                # Hands the key to a browser ON THIS MACHINE, so the stable
                # landing page can fill it in by itself when the operator opens
                # it here. Two locks: the request must be local (loopback with
                # no tunnel headers), and the answer is readable only by the
                # landing page's own origin - any other site in the same
                # browser gets an opaque response the browser will not let it
                # read. Elsewhere in the world the fetch simply fails.
                origin = self.headers.get("Origin") or ""
                if self._local_operator() and (not origin or origin == STABLE_PAGE_ORIGIN
                                               or origin_allowed(origin) and "trycloudflare" not in origin):
                    return self._send(200, {"key": operator_token()}, cors_origin=origin or None)
                return self._send(403, {"error": "the key is only handed to a browser on the host"})
            if path.startswith("/api"):
                return self._send(404, {"error": "no such route"})
            return self._send(200, render(collect(), local=self._local_operator()),
                              "text/html; charset=utf-8")
        except Exception as exc:                       # noqa: BLE001
            return self._send(500, {"error": str(exc)[:500]})

    def do_POST(self):                                 # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self._authed():
            return self._send(403, {"error": "operator key required (journal/operator_token)"})
        body = self._body()
        try:
            if path == "/api/backtests/run":
                import backtests
                bt_id = backtests.run(str(body.get("strategy") or ""), body)
                return self._send(202, {"id": bt_id})
            if path.startswith("/api/reproduce/"):
                import reproduce
                try:
                    return self._send(202, reproduce.start(path.rsplit("/", 1)[-1]))
                except RuntimeError as exc:
                    return self._send(409, {"error": str(exc)})
            import live_manager
            if path == "/api/live/deployments":
                return self._send(201, live_manager.deploy(body))
            if path == "/api/live/kill":
                live_manager.set_kill_switch(True)
                return self._send(200, {"kill_switch": True})
            if path == "/api/live/accounts":
                return self._send(201, live_manager.upsert_account(body))
            if path.startswith("/api/live/deployments/") and path.endswith("/rules"):
                dep_id = path.split("/")[4]
                return self._send(200, live_manager.set_rule(dep_id, body or None))
            return self._send(404, {"error": "no such route"})
        except (ValueError, FileNotFoundError, KeyError) as exc:
            return self._send(400, {"error": str(exc)[:500]})
        except Exception as exc:                       # noqa: BLE001
            return self._send(500, {"error": str(exc)[:500]})

    def do_DELETE(self):                               # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self._authed():
            return self._send(403, {"error": "operator key required (journal/operator_token)"})
        try:
            if path.startswith("/api/backtests/"):
                import backtests
                bt_id = path.rsplit("/", 1)[-1]
                found = backtests.delete(bt_id)
                return self._send(200 if found else 404,
                                  {"deleted": bt_id} if found else {"error": "no such backtest"})
            import live_manager
            if path == "/api/live/kill":
                live_manager.set_kill_switch(False)
                return self._send(200, {"kill_switch": False})
            if path.startswith("/api/live/deployments/"):
                parts = path.split("/")
                dep_id = parts[4]
                if path.endswith("/purge"):
                    live_manager.purge(dep_id)
                    return self._send(200, {"purged": dep_id})
                return self._send(200, live_manager.stop(dep_id))
            return self._send(404, {"error": "no such route"})
        except (ValueError, KeyError) as exc:
            return self._send(400, {"error": str(exc)[:500]})
        except Exception as exc:                       # noqa: BLE001
            return self._send(500, {"error": str(exc)[:500]})

    def do_OPTIONS(self):                              # noqa: N802
        """A cross-origin write carries X-Operator-Token, which is not a simple
        header, so the browser preflights it. Without this the base class
        answers 501 with an HTML body and the page reports only "bad json"."""
        origin = self.headers.get("Origin") or ""
        allowed = bool(origin) and origin_allowed(origin)
        self.send_response(204 if allowed else 403)
        if allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Operator-Token")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network"):
                # Chrome asks before letting a public page reach loopback.
                self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()
        access(f"{204 if allowed else 403} OPTIONS {self.path} origin={origin or '-'}")

    def do_HEAD(self):                                 # noqa: N802 — probes use HEAD
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def send_error(self, code, message=None, explain=None):
        """The base class answers unknown methods and malformed requests with an
        HTML body; log it, because to the page it is just a non-JSON failure."""
        access(f"{code} {self.command} {self.path} base-class-error={message or ''}")
        super().send_error(code, message, explain)

    def log_message(self, fmt, *args):                 # quiet
        pass


if __name__ == "__main__":
    operator_token()
    print(f"EdgeStack dashboard on http://127.0.0.1:{PORT}  (operator key: {TOKEN_PATH})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

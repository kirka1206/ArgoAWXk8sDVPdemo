#!/usr/bin/env python3
import base64
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


GITEA_URL = os.environ["GITEA_URL"].rstrip("/")
GITEA_OWNER = os.environ.get("GITEA_OWNER", "practicum")
GITEA_REPO = os.environ.get("GITEA_REPO", "practicum-demo")
GITEA_BRANCH = os.environ.get("GITEA_BRANCH", "main")
GITEA_USER = os.environ["GITEA_USER"]
GITEA_PASSWORD = os.environ["GITEA_PASSWORD"]
STATUS_ROOT = "gitops/self-service/practicum/status"
ACTION_ROOT = "gitops/self-service/practicum/actions"
ADMIN_EMAIL = "victor.melnikov.practicum@demo.local"
ADMIN_NAME = "victor-melnikov-practicum"
ADMIN_GROUP = "practicum-vm-operators"


def basic_auth():
    token = base64.b64encode(f"{GITEA_USER}:{GITEA_PASSWORD}".encode()).decode()
    return f"Basic {token}"


def gitea(method, endpoint, payload=None):
    url = f"{GITEA_URL}/api/v1/repos/{GITEA_OWNER}/{GITEA_REPO}{endpoint}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": basic_auth(), "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(exc.read().decode()) from exc


def get_file(path):
    return gitea("GET", f"/contents/{urllib.parse.quote(path, safe='/')}?ref={GITEA_BRANCH}")


def get_text(path, default=""):
    item = get_file(path)
    return base64.b64decode(item["content"]).decode() if item else default


def list_dir(path):
    result = gitea("GET", f"/contents/{urllib.parse.quote(path, safe='/')}?ref={GITEA_BRANCH}")
    return result if isinstance(result, list) else []


def put_text(path, content, message):
    existing = get_file(path)
    payload = {
        "branch": GITEA_BRANCH,
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    method = "POST"
    if existing:
        method = "PUT"
        payload["sha"] = existing["sha"]
    return gitea(method, f"/contents/{urllib.parse.quote(path, safe='/')}", payload)


def decode_jwt(headers):
    authorization = headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return {}
    parts = authorization.split(" ", 1)[1].split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode())
    except Exception:
        return {}


def groups(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def current_admin(headers):
    claims = decode_jwt(headers)
    email = (headers.get("X-Auth-Request-Email") or claims.get("email", "")).strip().lower()
    asserted = set(groups(headers.get("X-Auth-Request-Groups")) or groups(claims.get("groups")))
    if email != ADMIN_EMAIL or ADMIN_GROUP not in asserted:
        raise PermissionError("Доступ разрешён только Victor Melnikov")
    return {"name": ADMIN_NAME, "email": email, "groups": sorted(asserted)}


def slug(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", str(value).lower())).strip("-")[:63]


def send(handler, status, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else (
        payload.encode() if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False).encode()
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def environments():
    result = []
    for item in list_dir(STATUS_ROOT):
        if item.get("type") != "file" or not item["name"].endswith(".json"):
            continue
        status = json.loads(get_text(item["path"], "{}") or "{}")
        environment = status.get("environmentId", "")
        if environment.startswith("practicum-env-"):
            result.append(status)
    return sorted(result, key=lambda value: value.get("updatedAt", ""), reverse=True)


def create_action(admin, payload):
    environment = slug(payload.get("environment"))
    action = payload.get("action")
    reason = str(payload.get("reason") or "").strip()
    if action not in {
        "delete-environment", "delete-vm", "start-vm", "stop-vm", "restart-vm",
    }:
        raise ValueError("Недоступное действие")
    if not reason:
        raise ValueError("Укажите причину действия")
    status = json.loads(get_text(f"{STATUS_ROOT}/{environment}.json", "{}") or "{}")
    if not status or not environment.startswith("practicum-env-"):
        raise ValueError("Tenant-стенд не найден")
    if status.get("lastAction", {}).get("status") == "Running":
        raise ValueError("Предыдущее действие ещё выполняется")
    if action != "delete-environment" and not status.get("virtualMachine"):
        raise ValueError("В стенде нет виртуальной машины")
    suffix = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:6]
    action_id = f"{environment}-{action}-{suffix}"[:63]
    requested = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = {
        "apiVersion": "demo.practicum/v1",
        "kind": "EnvironmentAction",
        "metadata": {"name": action_id},
        "spec": {
            "environment": environment,
            "action": action,
            "actor": admin["name"],
            "actorEmail": admin["email"],
            "reason": reason,
            "requestedAt": requested,
        },
    }
    put_text(
        f"{ACTION_ROOT}/{action_id}.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        f"Admin request {action} for {environment}: {reason}",
    )
    return {"actionId": action_id, "environmentId": environment}


HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Practicum VM Administration</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:#172434;font:14px system-ui,sans-serif}.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}
aside{background:#fff;border-right:1px solid #dce3ea;padding:20px 14px;position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:800;padding:2px 8px 24px}.logo{display:grid;place-items:center;width:36px;height:36px;border-radius:8px;background:#1677e8;color:#fff}
nav button{width:100%;display:flex;gap:10px;border:0;background:transparent;color:#52677d;padding:11px 12px;border-radius:6px;text-align:left;font:inherit}nav button.active{background:#eaf3ff;color:#0969d7;font-weight:750;border-left:3px solid #1677e8}.shell{min-width:0}.top{height:66px;background:#fff;border-bottom:1px solid #dce3ea;display:flex;justify-content:space-between;align-items:center;padding:0 28px}.avatar{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#eaf3ff;color:#0969d7;font-weight:800}.logout{color:#536a80;text-decoration:none;margin-left:12px}
main{padding:26px;min-width:0}.heading{display:flex;justify-content:space-between;align-items:end;margin-bottom:18px}h1{font-size:27px;margin:0 0 5px}.muted{color:#6b7f92}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:18px}.kpi,.panel{min-width:0;background:#fff;border:1px solid #dce3ea;border-radius:8px;box-shadow:0 1px 2px #142b4410}.kpi{padding:16px}.kpi b{font-size:28px;display:block;margin-top:12px}.toolbar{display:flex;flex-wrap:wrap;gap:10px;padding:14px}.toolbar input,.toolbar select,.dialog textarea{min-width:0;border:1px solid #b8c5d1;border-radius:6px;padding:9px;font:inherit}.toolbar input{flex:1 1 220px}.table-wrap{overflow:auto;max-width:100%}table{width:100%;border-collapse:collapse}th,td{padding:12px 14px;border-top:1px solid #e7ecf1;text-align:left;white-space:nowrap}th{color:#6b7f92;font-size:12px}.badge{padding:4px 8px;border-radius:12px;background:#eaf3ff;color:#0969d7;font-weight:750;font-size:12px}.badge.Ready{background:#e5f7f1;color:#08785a}.badge.Error,.badge.ActionFailed{background:#fde9e9;color:#ad2929}.menu button,.secondary{border:1px solid #b8c5d1;background:#fff;border-radius:6px;padding:7px 10px}.danger{background:#c93535;color:#fff;border:0;border-radius:6px;padding:9px 14px}.modal{position:fixed;inset:0;background:#10203388;display:none;place-items:center;padding:20px}.modal.open{display:grid}.dialog{background:#fff;border-radius:8px;padding:22px;width:min(540px,100%)}.dialog textarea{width:100%;min-height:90px}.warning{background:#fff4e4;border-left:3px solid #d98b15;padding:12px;margin:14px 0}.actions{display:flex;justify-content:flex-end;gap:10px}.mono{font-family:ui-monospace,monospace}
@media(max-width:900px){.app{grid-template-columns:1fr}aside{position:static;height:auto}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.top{padding:0 16px}main{padding:18px}.toolbar select{flex:1 1 150px}}
</style></head><body><div class="app"><aside><div class="brand"><span class="logo">P</span>Practicum Admin</div><nav><button class="active">▦ Обзор</button><button>▣ Стенды</button><button>▤ Виртуальные машины</button><button>↻ Операции</button><button>⌕ Аудит</button></nav></aside>
<div class="shell"><header class="top"><div>Practicum › <b>Управление стендами</b></div><div><span class="avatar">V</span> <span id="user">Victor</span><a href="/logout" class="logout">Выйти</a></div></header><main>
<div class="heading"><div><h1>Стенды пользователей</h1><div class="muted">GitOps-управление tenant environments в practicum-tks</div></div><button class="secondary" onclick="load()">↻ Обновить</button></div>
<div class="kpis"><div class="kpi">Активные стенды<b id="active">0</b></div><div class="kpi">Работающие VM<b id="running">0</b></div><div class="kpi">Queued<b id="queued">0</b></div><div class="kpi">Ошибки<b id="errors">0</b></div><div class="kpi">Истекают в течение часа<b id="expiring">0</b></div></div>
<section class="panel"><div class="toolbar"><input id="search" placeholder="Поиск по Environment ID или владельцу"><select id="status"><option value="">Все статусы</option><option>Ready</option><option>Queued</option><option>Error</option><option>Cleaned</option></select><select id="vm"><option value="">Все стенды</option><option value="yes">С VM</option><option value="no">Без VM</option></select></div>
<div class="table-wrap"><table><thead><tr><th>Environment</th><th>Владелец</th><th>Профиль</th><th>Статус</th><th>TTL</th><th>VM / IP</th><th>AWX</th><th>Действия</th></tr></thead><tbody id="rows"></tbody></table></div></section>
</main></div></div><div id="modal" class="modal"><div class="dialog"><h2 id="title"></h2><p class="mono" id="environment"></p><div class="warning" id="warning"></div><label>Причина<textarea id="reason" placeholder="Обязательное обоснование"></textarea></label><div class="actions"><button class="secondary" onclick="closeModal()">Отмена</button><button id="confirm" class="danger">Подтвердить</button></div></div></div>
<script>
const $=id=>document.getElementById(id);let data=[],pending=null;async function api(path,opts={}){const r=await fetch(path,{headers:{"Content-Type":"application/json"},...opts});const p=await r.json();if(!r.ok)throw Error(p.error||"Ошибка");return p}
function metrics(){const now=Date.now();$("active").textContent=data.filter(x=>x.state!=="Cleaned").length;$("running").textContent=data.filter(x=>x.virtualMachine?.phase==="Running").length;$("queued").textContent=data.filter(x=>x.state==="Queued").length;$("errors").textContent=data.filter(x=>["Error","Rejected","ActionFailed"].includes(x.state)).length;$("expiring").textContent=data.filter(x=>{const t=Date.parse(x.expiresAt);return t>now&&t-now<3600000}).length}
function buttons(x){if(x.state==="Cleaned")return"-";const vm=x.virtualMachine;return `<span class="menu">${vm?`<button onclick="ask('${x.environmentId}','start-vm')">▶</button><button onclick="ask('${x.environmentId}','stop-vm')">■</button><button onclick="ask('${x.environmentId}','restart-vm')">↻</button><button onclick="ask('${x.environmentId}','delete-vm')">Удалить VM</button>`:""}<button onclick="ask('${x.environmentId}','delete-environment')">Удалить стенд</button></span>`}
function render(){const q=$("search").value.toLowerCase(),st=$("status").value,v=$("vm").value;const rows=data.filter(x=>(x.environmentId+" "+x.owner).toLowerCase().includes(q)&&(!st||x.state===st)&&(!v||(v==="yes")===!!x.virtualMachine));$("rows").innerHTML=rows.map(x=>`<tr><td class="mono">${x.environmentId}</td><td>${x.owner||"-"}</td><td>${x.profile||"-"}</td><td><span class="badge ${x.state}">${x.state}</span></td><td>${x.expiresAt||"-"}</td><td>${x.virtualMachine?`${x.virtualMachine.phase} / ${x.virtualMachine.ip||"-"}`:"-"}</td><td>${x.awxJob||"-"} / ${x.awxStatus||"-"}</td><td>${buttons(x)}</td></tr>`).join("")}
async function load(){data=await api("/api/environments");metrics();render()}function ask(env,action){pending={environment:env,action};$("title").textContent=action.replace("-"," ");$("environment").textContent=env;$("warning").textContent=action.startsWith("delete")?"Удаление выполняется через Git и Argo CD prune. Диск восстановить нельзя.":"Операция будет записана в Git и выполнена DVP.";$("reason").value="";$("modal").classList.add("open")}function closeModal(){$("modal").classList.remove("open");pending=null}
$("confirm").onclick=async()=>{const reason=$("reason").value.trim();if(!reason)return alert("Укажите причину");await api("/api/actions",{method:"POST",body:JSON.stringify({...pending,reason})});closeModal();setTimeout(load,2000)};["search","status","vm"].forEach(id=>$(id).oninput=render);async function init(){const me=await api("/api/me");$("user").textContent=me.email;await load();setInterval(load,5000)}init().catch(e=>alert(e.message));
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def do_GET(self):
        try:
            if self.path == "/healthz":
                return send(self, 200, {"status": "ok"})
            if self.path == "/":
                return send(self, 200, HTML, "text/html; charset=utf-8")
            admin = current_admin(self.headers)
            if self.path == "/api/me":
                return send(self, 200, admin)
            if self.path == "/api/environments":
                return send(self, 200, environments())
            return send(self, 404, {"error": "Not found"})
        except PermissionError as exc:
            return send(self, 403, {"error": str(exc)})
        except Exception as exc:
            return send(self, 500, {"error": str(exc)})

    def do_POST(self):
        try:
            if self.path != "/api/actions":
                return send(self, 404, {"error": "Not found"})
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            return send(self, 201, create_action(current_admin(self.headers), payload))
        except PermissionError as exc:
            return send(self, 403, {"error": str(exc)})
        except ValueError as exc:
            return send(self, 400, {"error": str(exc)})
        except Exception as exc:
            return send(self, 500, {"error": str(exc)})


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

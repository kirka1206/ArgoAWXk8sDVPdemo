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
NAMESPACE = os.environ.get("NAMESPACE", "practicum-tks")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "d8case.ru")
REQUEST_ROOT = "gitops/self-service/practicum/requests"
STATUS_ROOT = "gitops/self-service/practicum/status"
ACTION_ROOT = "gitops/self-service/practicum/actions"

PROFILES = {
    "app-only": {
        "title": "Контейнерное приложение",
        "description": "Один nginx Deployment, Service и Ingress. Для smoke-тестов UI/API без виртуальной машины.",
        "groups": {"practicum-payments-devs", "practicum-analytics-devs", "practicum-qa-devs"},
        "ttl": ["2h", "4h", "8h"],
        "vm": None,
    },
    "app-with-vm": {
        "title": "Приложение + Linux VM",
        "description": "Контейнерное приложение и минимальная DVP VM из активного golden image с автоматическим AWX post-config.",
        "groups": {"practicum-payments-devs", "practicum-qa-devs"},
        "ttl": ["2h", "4h", "8h"],
        "vm": {"cpu": "1 core / 5%", "memory": "512Mi", "disk": "768Mi"},
    },
    "app-with-postgres-vm": {
        "title": "Приложение + PostgreSQL VM",
        "description": "Приложение и минимальная DVP VM, для которой AWX устанавливает выбранную версию PostgreSQL и проверяет настройку.",
        "groups": {"practicum-analytics-devs", "practicum-qa-devs"},
        "ttl": ["4h", "8h", "24h"],
        "vm": {"cpu": "1 core / 5%", "memory": "512Mi", "disk": "768Mi"},
        "postgresVersions": ["16", "17", "18"],
    },
}

PURPOSES = {
    "feature": {
        "title": "Разработка функции",
        "description": "Стенд для разработки и проверки новой функциональности. Выбор влияет на Environment ID и аудит, но не меняет ресурсы выбранного профиля.",
    },
    "bugfix": {
        "title": "Проверка исправления",
        "description": "Изолированный стенд для воспроизведения дефекта и проверки исправления. Ресурсы определяет профиль стенда.",
    },
    "demo": {
        "title": "Демонстрация",
        "description": "Временный стенд для показа сценария или презентации. Назначение сохраняется в Git и отображается в истории.",
    },
    "loadtest": {
        "title": "Нагрузочный тест",
        "description": "Стенд с пометкой для нагрузочных проверок. Текущая демо-версия не увеличивает ресурсы автоматически: их по-прежнему задаёт профиль.",
    },
}

APPROVED_USERS = {
    "alice.koroleva.practicum@demo.local": {
        "name": "alice-koroleva-practicum",
        "groups": {"practicum-payments-devs"},
    },
    "boris.smirnov.practicum@demo.local": {
        "name": "boris-smirnov-practicum",
        "groups": {"practicum-analytics-devs"},
    },
    "marina.volkova.practicum@demo.local": {
        "name": "marina-volkova-practicum",
        "groups": {"practicum-qa-devs"},
    },
}


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


def current_user(headers):
    claims = decode_jwt(headers)
    email = (headers.get("X-Auth-Request-Email") or claims.get("email", "")).strip().lower()
    identity = APPROVED_USERS.get(email)
    if not identity:
        raise PermissionError("Пользователь не разрешён для practicum self-service")
    asserted_groups = set(groups(headers.get("X-Auth-Request-Groups")) or groups(claims.get("groups")))
    effective_groups = sorted(asserted_groups.intersection(identity["groups"]))
    if not effective_groups:
        raise PermissionError("Dex не передал разрешённую группу пользователя")
    return {"name": identity["name"], "email": email, "groups": effective_groups}


def slug(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", str(value).lower())).strip("-")


def commit_sha(result):
    if not isinstance(result, dict):
        return None
    commit = result.get("commit") or {}
    return commit.get("sha") or commit.get("id") or result.get("sha")


def send(handler, status, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else (
        payload.encode() if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode()
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def create_request(user, payload):
    profile = payload.get("profile")
    ttl = payload.get("ttl")
    purpose = slug(payload.get("purpose", "demo"))
    if purpose not in PURPOSES:
        raise ValueError("Неизвестное назначение")
    if profile not in PROFILES:
        raise ValueError("Неизвестный профиль")
    if ttl not in PROFILES[profile]["ttl"]:
        raise ValueError("TTL недоступен для выбранного профиля")
    if not set(user["groups"]).intersection(PROFILES[profile]["groups"]):
        raise PermissionError("Группа пользователя не имеет доступа к профилю")
    postgres_version = payload.get("postgresVersion")
    allowed_postgres_versions = PROFILES[profile].get("postgresVersions", [])
    if allowed_postgres_versions and postgres_version not in allowed_postgres_versions:
        raise ValueError("Недоступная версия PostgreSQL")
    owner = user["name"]
    suffix = hashlib.sha256(f"{owner}-{time.time_ns()}".encode()).hexdigest()[:6]
    short_owner = owner.replace("-practicum", "").split("-")[0]
    environment = f"practicum-env-{short_owner}-{purpose}-{suffix}"[:63]
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = {
        "apiVersion": "demo.practicum/v1",
        "kind": "EnvironmentRequest",
        "metadata": {"name": environment},
        "spec": {
            "owner": owner,
            "email": user["email"],
            "groups": user["groups"],
            "profile": profile,
            "purpose": purpose,
            "ttl": ttl,
            "createdAt": created,
        },
    }
    if postgres_version:
        document["spec"]["postgresql"] = {"version": postgres_version}
    result = put_text(
        f"{REQUEST_ROOT}/{environment}.yaml",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        f"Request practicum environment {environment}",
    )
    return {
        "environmentId": environment,
        "namespace": NAMESPACE,
        "profile": profile,
        "postgresVersion": postgres_version,
        "ttl": ttl,
        "gitCommit": commit_sha(result),
        "status": "Submitted",
    }


def environments_for(user, include_cleaned=False):
    result = []
    for item in list_dir(STATUS_ROOT):
        if item.get("type") != "file" or not item["name"].endswith(".json"):
            continue
        status = json.loads(get_text(item["path"], "{}") or "{}")
        if status.get("owner") != user["name"]:
            continue
        if not include_cleaned and status.get("state") == "Cleaned":
            continue
        result.append(status)
    return sorted(result, key=lambda value: value.get("updatedAt", ""), reverse=True)


def create_action(user, payload):
    environment = slug(payload.get("environment"))
    action = payload.get("action")
    if action not in {"delete-vm", "delete-environment"}:
        raise ValueError("Недоступное действие")
    status = json.loads(get_text(f"{STATUS_ROOT}/{environment}.json", "{}") or "{}")
    if not status:
        raise ValueError("Стенд не найден")
    if status.get("owner") != user["name"]:
        raise PermissionError("Нельзя управлять чужим стендом")
    if status.get("lastAction", {}).get("status") == "Running":
        raise ValueError("Предыдущее действие ещё выполняется")
    if action == "delete-vm" and not status.get("virtualMachine"):
        raise ValueError("В стенде нет виртуальной машины")
    action_id = f"{environment}-{action}-{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:6]}"[:63]
    requested = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = {
        "apiVersion": "demo.practicum/v1",
        "kind": "EnvironmentAction",
        "metadata": {"name": action_id},
        "spec": {
            "environment": environment,
            "action": action,
            "actor": user["name"],
            "actorEmail": user["email"],
            "reason": "owner-request",
            "requestedAt": requested,
        },
    }
    result = put_text(
        f"{ACTION_ROOT}/{action_id}.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        f"Request {action} for {environment}",
    )
    return {"actionId": action_id, "environmentId": environment, "gitCommit": commit_sha(result)}


HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Practicum Self-Service</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:#172434;font:14px system-ui,sans-serif}.app{min-height:100vh;display:grid;grid-template-columns:230px 1fr}
aside{background:#fff;border-right:1px solid #dce3ea;padding:20px 14px;position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:800;padding:2px 8px 24px}.logo{display:grid;place-items:center;width:36px;height:36px;border-radius:8px;background:#1677e8;color:#fff}
nav button{width:100%;display:flex;align-items:center;gap:10px;border:0;background:transparent;color:#52677d;padding:11px 12px;border-radius:6px;text-align:left;font:inherit;cursor:pointer}nav button.active{background:#eaf3ff;color:#0969d7;font-weight:750;border-left:3px solid #1677e8}
.shell{min-width:0}.top{height:66px;background:#fff;border-bottom:1px solid #dce3ea;display:flex;align-items:center;justify-content:space-between;padding:0 28px}.crumb{color:#61758a}.user{display:flex;align-items:center;gap:10px}.avatar{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#eaf3ff;color:#0969d7;font-weight:800}.logout{color:#536a80;text-decoration:none}
main{padding:26px;max-width:1400px}.view{display:none}.view.active{display:block}.heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:20px}h1{font-size:27px;margin:0 0 6px}h2{font-size:18px;margin:0}.muted{color:#6b7f92}.panel,.card{background:#fff;border:1px solid #dce3ea;border-radius:8px;box-shadow:0 1px 2px #142b4410}.panel{padding:20px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
label{display:grid;gap:7px;font-weight:650;margin-bottom:16px}select,button{min-height:40px;border-radius:6px;font:inherit}select{border:1px solid #b8c5d1;background:white;padding:8px}.primary{border:0;background:#1677e8;color:white;font-weight:750;padding:0 16px}.danger{border:0;background:#c93535;color:white;font-weight:750;padding:0 16px}.secondary{border:1px solid #b8c5d1;background:#fff;color:#263b50;padding:0 14px}
.profile{border-left:3px solid #1677e8;background:#f2f7fd;padding:12px;margin:-4px 0 16px;line-height:1.45}.purpose-help{border-left:3px solid #8ca4bc;background:#f7f9fb;padding:10px 12px;margin:-5px 0 16px;line-height:1.45;color:#52677d}.card{overflow:hidden}.card-head{padding:16px;border-bottom:1px solid #e7ecf1;display:flex;justify-content:space-between;gap:12px}.card-body{padding:16px;display:grid;gap:12px}.card-foot{background:#f7f9fb;padding:12px 16px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.title{font-weight:800;font-size:16px}.badge{display:inline-flex;padding:4px 8px;border-radius:12px;background:#eaf3ff;color:#0969d7;font-size:12px;font-weight:750}.badge.ready{background:#e5f7f1;color:#08785a}.badge.work{background:#fff3da;color:#9a6200}.badge.error{background:#fde9e9;color:#ad2929}.kv{display:grid;grid-template-columns:135px minmax(0,1fr);gap:7px 10px}.kv span:nth-child(odd){color:#718497}.kv b{font-weight:650;overflow-wrap:anywhere}.operation{border-left:3px solid #d98b15;background:#fff8e9;padding:10px 12px;line-height:1.45}.operation.ready{border-color:#15966f;background:#edf9f5}.mono{font-family:ui-monospace,monospace;overflow-wrap:anywhere}.status{white-space:pre-wrap;line-height:1.5}.progress{height:4px;background:#e6ebf0;overflow:hidden}.progress span{display:block;width:35%;height:100%;background:#1677e8;animation:move 1.5s infinite}@keyframes move{from{transform:translateX(-110%)}to{transform:translateX(330%)}}
.modal{position:fixed;inset:0;background:#10203388;display:none;place-items:center;padding:20px;z-index:10}.modal.open{display:grid}.dialog{width:min(520px,100%);background:#fff;border-radius:8px;padding:22px}.warning{background:#fff4e4;border-left:3px solid #d98b15;padding:12px;margin:16px 0}.actions{display:flex;justify-content:flex-end;gap:10px}.empty{padding:42px;text-align:center;color:#718497}
@media(max-width:760px){.app{grid-template-columns:1fr}aside{height:auto;position:static;border-right:0;border-bottom:1px solid #dce3ea}.brand{padding-bottom:10px}nav{display:flex;overflow:auto}nav button{white-space:nowrap}.top{padding:0 16px}.user span:not(.avatar){display:none}main{padding:18px}.heading{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}}
</style></head><body>
<div class="app"><aside><div class="brand"><span class="logo">P</span>Practicum</div><nav>
<button data-view="new" class="active">＋ Новый стенд</button><button data-view="mine">▣ Мои стенды</button><button data-view="history">≡ История</button></nav></aside>
<div class="shell"><header class="top"><div class="crumb">Self-Service › <b id="crumb">Новый стенд</b></div><div class="user"><span class="avatar" id="initial">U</span><span id="user"></span><a class="logout" href="/logout">Выйти</a></div></header>
<main><section id="new" class="view active"><div class="heading"><div><h1>Новый стенд</h1><div class="muted">Заказ ресурсов через GitOps</div></div></div><div class="panel">
<form id="form"><label>Профиль стенда<select id="profile"></select></label><div id="details" class="profile"></div>
<label id="postgresVersionField" hidden>Версия PostgreSQL<select id="postgresVersion"></select></label>
<label>Назначение<select id="purpose"></select></label><div id="purposeDetails" class="purpose-help"></div>
<label>Время жизни<select id="ttl"></select></label><button id="submit" class="primary">Отправить заявку</button></form></div>
<div class="panel" style="margin-top:16px"><h2>Результат</h2><div id="progress" class="progress" hidden><span></span></div><p id="activity" class="muted">После отправки здесь появится ход выполнения.</p><div id="result" class="status"></div></div></section>
<section id="mine" class="view"><div class="heading"><div><h1>Мои стенды</h1><div class="muted">Все активные стенды текущего пользователя из GitOps status</div></div><button id="refreshEnvs" class="secondary" onclick="loadEnvs(true)">↻ Обновить</button></div><div id="envRefreshState" class="muted" style="margin:-10px 0 14px"></div><div id="envs" class="grid"></div></section>
<section id="history" class="view"><div class="heading"><div><h1>История</h1><div class="muted">Очищенные стенды и последние операции</div></div></div><div id="historyList" class="grid"></div></section></main></div></div>
<div id="modal" class="modal"><div class="dialog"><h2 id="modalTitle"></h2><p id="modalText"></p><div class="warning" id="modalWarning"></div><div class="actions"><button class="secondary" onclick="closeModal()">Отмена</button><button class="danger" id="confirmAction">Подтвердить</button></div></div></div>
<script>
let profiles=[],purposes=[],last=null,pollTimer=null,listPollTimer=null,pendingAction=null;const $=id=>document.getElementById(id);
async function api(path,opts={}){const r=await fetch(path,{cache:"no-store",headers:{"Content-Type":"application/json"},...opts});const p=await r.json();if(!r.ok)throw Error(p.error||"Ошибка");return p}
function profile(){return profiles.find(p=>p.name===$("profile").value)}
function renderProfile(){const p=profile();$("details").innerHTML=`<b>${p.title}</b><br>${p.description}<br><br><b>Ресурсы:</b> приложение 1 replica, 25m CPU / 32Mi RAM${p.vm?`, VM ${p.vm.cpu}, RAM ${p.vm.memory}, диск ${p.vm.disk}`:"; VM не создаётся"}.<br><b>Namespace:</b> practicum-tks`;$("ttl").innerHTML=p.ttl.map(v=>`<option>${v}</option>`).join("");const versions=p.postgresVersions||[];$("postgresVersionField").hidden=!versions.length;$("postgresVersion").innerHTML=versions.map(v=>`<option value="${v}">PostgreSQL ${v}</option>`).join("")}
function renderPurpose(){const p=purposes.find(p=>p.name===$("purpose").value);$("purposeDetails").innerHTML=`<b>${p.title}</b><br>${p.description}`}
function working(s){return !["Ready","Rejected","Error","Cleaned","ActionFailed"].includes(s.state)}
function render(s){$("progress").hidden=!working(s);$("activity").textContent=working(s)?"Система выполняет GitOps-операцию. Статус обновляется каждые 5 секунд.":s.state==="Ready"?"Стенд готов.":"Операция завершена.";$("result").textContent=`Environment ID: ${s.environmentId}
Namespace: ${s.namespace}
Технический статус: ${s.state||s.status}
Причина: ${s.reason||"-"}
Владелец: ${s.owner||"-"}
Профиль: ${s.profile||"-"}
Версия PostgreSQL: ${s.postgresVersion||"не требуется"}
TTL до: ${s.expiresAt||"-"}
Git commit: ${s.gitCommit||"-"}
Argo CD: ${s.argoCD?.sync||"-"} / ${s.argoCD?.health||"-"}
Приложение: ${s.application?.name||"-"}, ready ${s.application?.readyReplicas??"-"}/${s.application?.replicas??"-"}
URL: ${s.application?.url||"-"}
VM: ${s.virtualMachine?.name||"не требуется"}
VM phase/IP: ${s.virtualMachine?.phase||"-"} / ${s.virtualMachine?.ip||"-"}
VM: ${s.virtualMachine?`${s.virtualMachine.cpu}, RAM ${s.virtualMachine.memory}, disk ${s.virtualMachine.disk}, image ${s.virtualMachine.image}`:"-"}
Логин VM: ${s.virtualMachine?.access?.username||"-"} (${s.virtualMachine?.access?.authentication||"-"})
SSH: ${s.virtualMachine?.access?.command||"-"}
AWX job/status: ${s.awxJob||"-"} / ${s.awxStatus||"-"}`;}
async function poll(){if(!last)return;try{const s=await api(`/api/status/${last}`);render(s);if(!working(s)){$("submit").disabled=false;loadEnvs();return}}catch(e){$("activity").textContent=`Ошибка связи: ${e.message}. Повтор через 5 секунд.`}pollTimer=setTimeout(poll,5000)}
function badge(s){const c=s==="Ready"?"ready":s==="Cleaned"?"":s.includes("Error")||s==="Rejected"?"error":"work";return`<span class="badge ${c}">${s}</span>`}
function operationText(s){const names={ActionRequested:"Запрос операции записан в Git. Контроллер ожидает обработку.",VMDeleting:"VM и диск удалены из desired state. Argo CD выполняет prune.",DeletionRequested:"Запрос удаления принят и записан в Git.",Deleting:"Ресурсы удалены из desired state. Argo CD выполняет prune.",VMStarting:"DVP запускает виртуальную машину.",VMStopping:"DVP останавливает виртуальную машину.",VMRestarting:"DVP выполняет перезапуск виртуальной машины.",Provisioning:"Argo CD создаёт ресурсы, затем AWX настраивает ОС.",Queued:"Заявка ожидает свободной ёмкости."};if(names[s.state])return names[s.state];if(s.lastAction?.status==="Running")return`Выполняется ${s.lastAction.action}. Статус проверяется каждые 5 секунд.`;if(s.lastAction?.status==="Completed")return`Последняя операция ${s.lastAction.action} завершена.`;return""}
function card(s,history=false){const vm=s.virtualMachine,app=s.application||{},op=operationText(s);return `<article class="card"><div class="card-head"><div><div class="title">${s.environmentId}</div><div class="muted">Namespace: ${s.namespace||"practicum-tks"}</div></div>${badge(s.state)}</div><div class="card-body"><div class="kv"><span>Владелец</span><b>${s.owner||"-"}</b><span>Профиль</span><b>${s.profile||"-"}</b><span>PostgreSQL</span><b>${s.postgresVersion||"не требуется"}</b><span>TTL до</span><b>${s.expiresAt||"-"}</b><span>Приложение</span><b>${app.name||"-"}, ready ${app.readyReplicas??"-"}/${app.replicas??"-"}</b><span>URL</span><b>${app.url?`<a href="${app.url}" target="_blank">${app.url}</a>`:"-"}</b><span>VM</span><b>${vm?.name||"не требуется"}</b><span>VM IP</span><b>${vm?.ip||"-"}</b><span>Характеристики VM</span><b>${vm?`${vm.cpu}, RAM ${vm.memory}, disk ${vm.disk}, image ${vm.image}`:"-"}</b><span>Логин VM</span><b>${vm?.access?.username||"-"}${vm?.access?.authentication?` (${vm.access.authentication})`:""}</b><span>SSH</span><b class="mono">${vm?.access?.command||"-"}</b><span>AWX</span><b>${s.awxJob||"-"} / ${s.awxStatus||"-"}</b><span>Git commit</span><b class="mono">${s.gitCommit||"-"}</b></div>${op?`<div class="operation ${s.lastAction?.status==="Completed"?"ready":""}"><b>Ход операции</b><br>${op}${s.reason?`<br>Причина: ${s.reason}`:""}</div>`:""}</div>${history?"":`<div class="card-foot">${vm?`<button class="secondary" onclick="ask('${s.environmentId}','delete-vm')">Удалить VM</button>`:"<span></span>"}<button class="danger" onclick="ask('${s.environmentId}','delete-environment')">Удалить стенд</button></div>`}</article>`}
async function loadEnvs(manual=false){clearTimeout(listPollTimer);const button=$("refreshEnvs");if(button)button.disabled=true;$("envRefreshState").textContent=manual?"Обновляем данные из Git...":"Загружаем стенды...";try{const [active,history]=await Promise.all([api(`/api/environments?t=${Date.now()}`),api(`/api/environments?history=1&t=${Date.now()}`)]);$("envs").innerHTML=active.length?active.map(s=>card(s)).join(""):`<div class="panel empty">Активных стендов нет</div>`;const cleaned=history.filter(s=>s.state==="Cleaned");$("historyList").innerHTML=cleaned.length?cleaned.map(s=>card(s,true)).join(""):`<div class="panel empty">История пока пуста</div>`;$("envRefreshState").textContent=`Показано стендов: ${active.length}. Обновлено ${new Date().toLocaleTimeString("ru-RU")}.`;if(active.some(working))listPollTimer=setTimeout(()=>loadEnvs(false),5000)}catch(e){$("envRefreshState").textContent=`Не удалось обновить: ${e.message}`}finally{if(button)button.disabled=false}}
function ask(env,action){pendingAction={environment:env,action};$("modalTitle").textContent=action==="delete-vm"?"Удалить виртуальную машину?":"Удалить стенд?";$("modalText").textContent=env;$("modalWarning").textContent=action==="delete-vm"?"VM и VirtualDisk будут необратимо удалены. Приложение сохранится.":"Deployment, Service, Ingress, VM и диск будут удалены через Argo CD prune.";$("modal").classList.add("open")}
function closeModal(){$("modal").classList.remove("open");pendingAction=null}
$("confirmAction").onclick=async()=>{const a=pendingAction;closeModal();try{await api("/api/actions",{method:"POST",body:JSON.stringify(a)});last=a.environment;show("mine");$("envRefreshState").textContent="Операция записана в Git. Ожидаем controller и Argo CD...";loadEnvs(false)}catch(e){$("envRefreshState").textContent=`Не удалось создать операцию: ${e.message}`}}
function show(id){document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===id));document.querySelectorAll("nav button").forEach(v=>v.classList.toggle("active",v.dataset.view===id));$("crumb").textContent={new:"Новый стенд",mine:"Мои стенды",history:"История"}[id];if(id!=="new")loadEnvs()}
async function init(){const me=await api("/api/me");profiles=me.profiles;purposes=me.purposes;$("user").textContent=me.email||me.name;$("initial").textContent=(me.name||"U")[0].toUpperCase();$("profile").innerHTML=profiles.map(p=>`<option value="${p.name}">${p.title}</option>`).join("");$("purpose").innerHTML=purposes.map(p=>`<option value="${p.name}">${p.title}</option>`).join("");document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>show(b.dataset.view));$("profile").onchange=renderProfile;$("purpose").onchange=renderPurpose;renderProfile();renderPurpose();loadEnvs()}
$("form").onsubmit=async e=>{e.preventDefault();clearTimeout(pollTimer);$("submit").disabled=true;$("progress").hidden=false;$("activity").textContent="Создаём EnvironmentRequest в Git...";const p=profile();try{const r=await api("/api/requests",{method:"POST",body:JSON.stringify({profile:$("profile").value,purpose:$("purpose").value,ttl:$("ttl").value,postgresVersion:p.postgresVersions?.length?$("postgresVersion").value:null})});last=r.environmentId;render(r);poll()}catch(err){$("submit").disabled=false;$("progress").hidden=true;$("activity").textContent=err.message}};
init().catch(e=>{$("result").textContent=e.message});
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
            user = current_user(self.headers)
            if self.path == "/api/me":
                allowed = [
                    {"name": name, **{key: value for key, value in profile.items() if key != "groups"}}
                    for name, profile in PROFILES.items()
                    if set(user["groups"]).intersection(profile["groups"])
                ]
                purposes = [
                    {"name": name, **purpose}
                    for name, purpose in PURPOSES.items()
                ]
                return send(self, 200, {
                    **user,
                    "profiles": allowed,
                    "purposes": purposes,
                    "namespace": NAMESPACE,
                })
            if self.path.startswith("/api/environments"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                include_cleaned = query.get("history") == ["1"]
                return send(self, 200, environments_for(user, include_cleaned))
            if self.path.startswith("/api/status/"):
                environment = slug(urllib.parse.unquote(self.path.rsplit("/", 1)[1]))
                status = get_text(f"{STATUS_ROOT}/{environment}.json")
                return send(self, 200, json.loads(status) if status else {
                    "environmentId": environment, "namespace": NAMESPACE, "state": "Submitted"
                })
            return send(self, 404, {"error": "Not found"})
        except Exception as exc:
            return send(self, 500, {"error": str(exc)})

    def do_POST(self):
        try:
            if self.path not in {"/api/requests", "/api/actions"}:
                return send(self, 404, {"error": "Not found"})
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            user = current_user(self.headers)
            if self.path == "/api/actions":
                return send(self, 201, create_action(user, payload))
            return send(self, 201, create_request(user, payload))
        except PermissionError as exc:
            return send(self, 403, {"error": str(exc)})
        except ValueError as exc:
            return send(self, 400, {"error": str(exc)})
        except Exception as exc:
            return send(self, 500, {"error": str(exc)})


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

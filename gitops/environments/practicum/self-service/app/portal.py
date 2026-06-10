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
    handler.end_headers()
    handler.wfile.write(body)


def create_request(user, payload):
    profile = payload.get("profile")
    ttl = payload.get("ttl")
    purpose = slug(payload.get("purpose", "demo"))
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


HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Practicum Self-Service</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#18232b;font:15px system-ui,sans-serif}
header{background:#173f35;color:white;padding:24px max(24px,calc((100% - 1080px)/2));display:flex;align-items:center;justify-content:space-between;gap:20px}
header h1{font-size:28px;margin:0 0 6px}header p{margin:0;color:#d5e6df}
.logout{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 16px;border:1px solid #92b8aa;border-radius:6px;color:white;text-decoration:none;font-weight:700;white-space:nowrap}
.logout:hover,.logout:focus-visible{background:#28594c;outline:2px solid white;outline-offset:2px}
main{max-width:1080px;margin:0 auto;padding:24px;display:grid;grid-template-columns:380px 1fr;gap:20px}
section{background:white;border:1px solid #d6dde2;border-radius:8px;padding:20px}h2{font-size:18px;margin:0 0 18px}
label{display:grid;gap:7px;font-weight:650;margin-bottom:16px}select,button{min-height:42px;border-radius:6px;font:inherit}
select{border:1px solid #aebac3;background:white;padding:8px}button{border:0;background:#176b54;color:white;font-weight:750;cursor:pointer}
button:disabled{background:#80938d;cursor:wait}
.profile{border-left:4px solid #3c8c74;background:#f5faf8;padding:12px;margin:-4px 0 16px;line-height:1.45}
.status-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.state{display:inline-flex;align-items:center;gap:9px;font-size:18px;font-weight:800}
.state-dot{width:11px;height:11px;border-radius:50%;background:#74818a;flex:none}
.state.working .state-dot{background:#c17b17;animation:pulse 1.4s ease-in-out infinite}
.state.ready .state-dot{background:#16805d}.state.failed .state-dot{background:#b33232}
.progress{height:5px;background:#e3e8eb;overflow:hidden;margin:0 0 16px}
.progress span{display:block;width:36%;height:100%;background:#c17b17;animation:progress 1.6s ease-in-out infinite}
.progress[hidden]{display:none}.activity{margin:0 0 16px;font-weight:650;line-height:1.45}
.status{white-space:pre-wrap;line-height:1.5}.muted{color:#65737d}.error{color:#a12828}
.poll-meta{font-size:13px;color:#65737d;text-align:right}
@keyframes pulse{50%{opacity:.35;transform:scale(.8)}}@keyframes progress{0%{transform:translateX(-110%)}100%{transform:translateX(320%)}}
dl{display:grid;grid-template-columns:170px 1fr;gap:8px;margin:0}dt{color:#65737d}dd{margin:0;font-weight:600}
@media(max-width:760px){header{align-items:flex-start}main{grid-template-columns:1fr}.logout{min-width:88px}.status-head{align-items:flex-start;flex-direction:column}.poll-meta{text-align:left}}
</style></head><body>
<header><div><h1>Practicum Self-Service</h1><p>Заказ временных стендов через единый GitOps-процесс</p></div><a class="logout" href="/logout">Выйти</a></header>
<main><section><h2>Новая заявка</h2><div id="user" class="muted"></div>
<form id="form"><label>Профиль стенда<select id="profile"></select></label><div id="details" class="profile"></div>
<label id="postgresVersionField" hidden>Версия PostgreSQL<select id="postgresVersion"></select></label>
<label>Назначение<select id="purpose"><option value="feature">Разработка функции</option><option value="bugfix">Проверка исправления</option><option value="demo">Демонстрация</option><option value="loadtest">Нагрузочный тест</option></select></label>
<label>Время жизни<select id="ttl"></select></label><button id="submit">Отправить заявку</button></form></section>
<section><h2>Результат</h2><div class="status-head"><div id="state" class="state"><span class="state-dot"></span><span>Ожидание</span></div><div id="pollMeta" class="poll-meta"></div></div>
<div id="progress" class="progress" hidden><span></span></div><p id="activity" class="activity muted">После отправки здесь появятся текущий этап, Git commit, Argo CD, ресурсы, AWX job и TTL.</p>
<div id="result" class="status muted"></div></section></main>
<script>
let profiles=[],last=null,pollCount=0,startedAt=null,pollTimer=null;const $=id=>document.getElementById(id);
async function api(path,opts={}){const r=await fetch(path,{headers:{"Content-Type":"application/json"},...opts});const p=await r.json();if(!r.ok)throw Error(p.error||"Ошибка");return p}
function profile(){return profiles.find(p=>p.name===$("profile").value)}
function renderProfile(){const p=profile();$("details").innerHTML=`<b>${p.title}</b><br>${p.description}<br><br><b>Ресурсы:</b> приложение 1 replica, 25m CPU / 32Mi RAM${p.vm?`, VM ${p.vm.cpu}, RAM ${p.vm.memory}, диск ${p.vm.disk}`:"; VM не создаётся"}.<br><b>Namespace:</b> practicum-tks`;$("ttl").innerHTML=p.ttl.map(v=>`<option>${v}</option>`).join("");const versions=p.postgresVersions||[];$("postgresVersionField").hidden=!versions.length;$("postgresVersion").innerHTML=versions.map(v=>`<option value="${v}">PostgreSQL ${v}</option>`).join("")}
function viewState(s){const state=s.state||s.status||"Submitted";if(["Rejected","Error"].includes(state))return{label:"Ошибка",kind:"failed",working:false};if(state==="Ready")return{label:"Готово",kind:"ready",working:false};if(state==="Cleaned")return{label:"Удалено по TTL",kind:"ready",working:false};if(state==="Expired")return{label:"Срок истёк",kind:"ready",working:false};if(state==="Queued")return{label:"В очереди",kind:"working",working:true};return{label:"В работе",kind:"working",working:true}}
function activity(s){const state=s.state||s.status||"Submitted";if(state==="Submitted")return"Заявка записана в Git. Ожидаем, когда request controller начнёт обработку.";if(state==="Queued")return"Заявка проверена и ждёт свободной квоты платформы.";if(["Rejected","Error"].includes(state))return s.reason?`Обработка остановлена: ${s.reason}`:"Обработка остановлена. Проверьте причину ниже.";if(state==="Ready")return"Стенд готов к использованию. Все обязательные проверки завершены.";if(state==="Cleaned")return"Время жизни завершилось, ресурсы заявки удалены через GitOps.";if(state==="Expired")return"Время жизни завершилось. Выполняется GitOps-очистка ресурсов.";if(state==="Provisioning"){if(!s.application)return"Argo CD применяет манифесты приложения и инфраструктуры.";if((s.application.readyReplicas??0)<(s.application.replicas??1))return"Kubernetes запускает контейнерное приложение.";if(!s.virtualMachine&&s.profile!=="app-only")return"Приложение запущено. DVP создаёт диск и виртуальную машину.";if(!s.virtualMachine)return"Приложение запущено. Завершаются проверки готовности стенда.";if(s.virtualMachine.phase!=="Running")return`DVP создаёт и запускает виртуальную машину. Текущая фаза: ${s.virtualMachine.phase||"ожидание"}.`;if(!s.virtualMachine.guestReady)return"Виртуальная машина запущена. Ожидаем готовность гостевой ОС и qemu-guest-agent.";if(!s.awxJob)return"Гостевая ОС готова. Request controller запускает AWX post-configuration.";if(["failed","error","canceled"].includes(s.awxStatus))return`AWX job ${s.awxJob} завершился со статусом ${s.awxStatus}. Controller проверяет возможность повторного запуска.`;if(s.awxStatus!=="successful")return`AWX выполняет настройку и проверку ОС. Job ${s.awxJob}, статус ${s.awxStatus||"pending"}.`;return"AWX завершил работу успешно. Controller выполняет итоговую проверку стенда."}return"Система обрабатывает заявку."}
function render(s){const v=viewState(s);$("state").className=`state ${v.kind}`;$("state").querySelector("span:last-child").textContent=v.label;$("progress").hidden=!v.working;$("activity").className=`activity ${v.kind==="failed"?"error":"muted"}`;$("activity").textContent=activity(s);const elapsed=startedAt?Math.max(0,Math.floor((Date.now()-startedAt)/1000)):0;$("pollMeta").textContent=v.working?`Проверка каждые 5 секунд · ${pollCount} · прошло ${elapsed} сек.`:`Обновлено ${new Date().toLocaleTimeString("ru-RU")}`;$("result").className=`status ${v.kind==="failed"?"error":""}`;$("result").textContent=`Environment ID: ${s.environmentId}
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
async function poll(){if(!last)return;pollCount++;try{const s=await api(`/api/status/${last}`);render(s);if(["Ready","Rejected","Error","Cleaned"].includes(s.state)){$("submit").disabled=false;return}}catch(e){$("state").className="state failed";$("state").querySelector("span:last-child").textContent="Ошибка связи";$("activity").className="activity error";$("activity").textContent=`Не удалось получить статус: ${e.message}. Повторим через 5 секунд.`}pollTimer=setTimeout(poll,5000)}
async function init(){const me=await api("/api/me");profiles=me.profiles;$("user").textContent=`${me.email||me.name} · ${me.groups.join(", ")}`;$("profile").innerHTML=profiles.map(p=>`<option value="${p.name}">${p.title}</option>`).join("");if(!profiles.length){$("form").hidden=true;$("result").textContent="Для групп пользователя нет доступных профилей.";return}$("profile").onchange=renderProfile;renderProfile()}
$("form").onsubmit=async e=>{e.preventDefault();clearTimeout(pollTimer);$("submit").disabled=true;$("state").className="state working";$("state").querySelector("span:last-child").textContent="Отправка";$("progress").hidden=false;$("activity").className="activity muted";$("activity").textContent="Создаём EnvironmentRequest в Git...";$("result").textContent="";$("pollMeta").textContent="";const p=profile();try{const r=await api("/api/requests",{method:"POST",body:JSON.stringify({profile:$("profile").value,purpose:$("purpose").value,ttl:$("ttl").value,postgresVersion:p.postgresVersions?.length?$("postgresVersion").value:null})});last=r.environmentId;pollCount=0;startedAt=Date.now();render(r);poll()}catch(err){$("submit").disabled=false;$("progress").hidden=true;$("state").className="state failed";$("state").querySelector("span:last-child").textContent="Ошибка";$("activity").className="activity error";$("activity").textContent="Заявку не удалось отправить.";$("result").className="status error";$("result").textContent=err.message}};
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
                return send(self, 200, {**user, "profiles": allowed, "namespace": NAMESPACE})
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
            if self.path != "/api/requests":
                return send(self, 404, {"error": "Not found"})
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            return send(self, 201, create_request(current_user(self.headers), payload))
        except PermissionError as exc:
            return send(self, 403, {"error": str(exc)})
        except ValueError as exc:
            return send(self, 400, {"error": str(exc)})
        except Exception as exc:
            return send(self, 500, {"error": str(exc)})


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

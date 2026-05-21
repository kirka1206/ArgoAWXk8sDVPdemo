#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


GITEA_URL = os.environ.get("GITEA_URL", "http://gitea.gitea.svc.cluster.local:3000").rstrip("/")
GITEA_OWNER = os.environ.get("GITEA_OWNER", "codex")
GITEA_REPO = os.environ.get("GITEA_REPO", "demo")
GITEA_BRANCH = os.environ.get("GITEA_BRANCH", "main")
GITEA_USER = os.environ.get("GITEA_USER", "codex")
GITEA_PASSWORD = os.environ.get("GITEA_PASSWORD", "")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "example.local")
INGRESS_CLASS = os.environ.get("INGRESS_CLASS", "nginx")
STORAGE_CLASS = os.environ.get("STORAGE_CLASS", "k8nfs")
K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
K8S_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

PROFILES = {
    "app-only": {
        "title": "App only",
        "description": "Лёгкий стенд только с контейнерным приложением. Подходит для проверки UI/API, демо nginx и быстрых smoke-тестов без VM.",
        "resources": ["Namespace", "ResourceQuota", "LimitRange", "RBAC", "Deployment demo-app", "Service", "Ingress"],
        "groups": ["payments-devs", "analytics-devs", "qa-devs"],
        "ttl": ["2h", "4h", "8h"],
        "vm": False,
        "postgres": False,
        "quota": {"cpu": "1", "memory": "1Gi", "pods": "8"},
        "app": {"replicas": 1, "requests": "50m CPU / 64Mi RAM", "limits": "200m CPU / 256Mi RAM"},
    },
    "app-with-vm": {
        "title": "App + DVP VM",
        "description": "Контейнерное приложение и минимальная DVP VM из утверждённого ClusterVirtualImage. Подходит для проверки связки Kubernetes + VM + AWX post-config.",
        "resources": ["Namespace", "ResourceQuota", "LimitRange", "RBAC", "Deployment demo-app", "Service", "Ingress", "VirtualDisk 256Mi", "VirtualMachine 1 core / 5% / 512Mi"],
        "groups": ["payments-devs", "qa-devs"],
        "ttl": ["2h", "4h", "8h"],
        "vm": True,
        "postgres": False,
        "quota": {"cpu": "2", "memory": "2Gi", "pods": "12"},
        "app": {"replicas": 1, "requests": "50m CPU / 64Mi RAM", "limits": "200m CPU / 256Mi RAM"},
        "vmSpec": {"cpu": "1 core", "coreFraction": "5%", "memory": "512Mi", "disk": "256Mi", "imageKind": "ClusterVirtualImage"},
    },
    "app-with-postgres-vm": {
        "title": "App + PostgreSQL VM",
        "description": "Контейнерное приложение и минимальная DVP VM как цель для настройки PostgreSQL через AWX. Подходит для демо post-configuration и validation.",
        "resources": ["Namespace", "ResourceQuota", "LimitRange", "RBAC", "Deployment demo-app", "Service", "Ingress", "VirtualDisk 256Mi", "VirtualMachine 1 core / 5% / 512Mi", "AWX-ready PostgreSQL post-config target"],
        "groups": ["analytics-devs", "qa-devs"],
        "ttl": ["4h", "8h", "24h"],
        "vm": True,
        "postgres": True,
        "quota": {"cpu": "2", "memory": "3Gi", "pods": "16"},
        "app": {"replicas": 1, "requests": "50m CPU / 64Mi RAM", "limits": "200m CPU / 256Mi RAM"},
        "vmSpec": {"cpu": "1 core", "coreFraction": "5%", "memory": "512Mi", "disk": "256Mi", "imageKind": "ClusterVirtualImage"},
    },
}

APP_IMAGES = ["nginx:1.27", "nginx:1.26"]
VM_IMAGES = ["alpine-base-3-23-v1"]
PURPOSES = {
    "feature": "Разработка или проверка новой функциональности в изолированном namespace.",
    "bugfix": "Воспроизведение и проверка исправления дефекта без влияния на общие окружения.",
    "loadtest": "Короткий нагрузочный или ресурсный тест в рамках квот выбранного профиля.",
    "demo": "Демонстрационный стенд для показа заказчику, команде или архитектурной аудитории.",
}


def slug(value, default="env"):
    value = (value or default).lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return (value or default)[:40]


def decode_jwt_payload(headers):
    authorization = headers.get("Authorization") or ""
    if not authorization.startswith("Bearer "):
        return {}
    parts = authorization.split(" ", 1)[1].split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def normalize_groups(value):
    if isinstance(value, list):
        return [str(group).strip() for group in value if str(group).strip()]
    return [group.strip() for group in str(value or "").replace(";", ",").split(",") if group.strip()]


def user_from_headers(headers):
    jwt_payload = decode_jwt_payload(headers)
    email = headers.get("X-Auth-Request-Email") or headers.get("X-Forwarded-Email") or ""
    email = email or jwt_payload.get("email", "")
    user = headers.get("X-Auth-Request-User") or headers.get("X-Forwarded-User") or email or "demo-user"
    user = jwt_payload.get("preferred_username") or jwt_payload.get("name") or user
    groups = headers.get("X-Auth-Request-Groups") or headers.get("X-Forwarded-Groups") or ""
    group_list = normalize_groups(groups) or normalize_groups(jwt_payload.get("groups"))
    if not group_list and os.environ.get("DEMO_AUTH_GROUPS"):
        group_list = normalize_groups(os.environ["DEMO_AUTH_GROUPS"])
    return {
        "user": slug(user.split("@")[0], "developer"),
        "email": email,
        "groups": group_list,
    }


def allowed_profiles(groups):
    if not groups:
        return []
    return [
        {"name": name, **profile}
        for name, profile in PROFILES.items()
        if sorted(set(groups).intersection(profile["groups"]))
    ]


def profile_summary(profile, ttl, app_image, vm_image=None):
    spec = PROFILES[profile]
    summary = {
        "name": profile,
        "title": spec["title"],
        "description": spec["description"],
        "ttl": ttl,
        "quota": spec["quota"],
        "resources": spec["resources"],
        "app": {"image": app_image, **spec["app"]},
        "vm": None,
        "awx": "Не требуется для app-only профиля.",
    }
    if spec["vm"]:
        summary["vm"] = {"nameSuffix": "-vm", "image": vm_image, **spec["vmSpec"]}
        summary["awx"] = "После создания VM можно запустить AWX post-configuration/validation."
    return summary


def response(handler, status, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def static(handler, content_type, body):
    data = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def gitea_request(method, path, payload=None):
    url = f"{GITEA_URL}/api/v1/repos/{GITEA_OWNER}/{GITEA_REPO}{path}"
    body = None
    headers = {"Content-Type": "application/json"}
    token = base64.b64encode(f"{GITEA_USER}:{GITEA_PASSWORD}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Gitea API {method} {path} failed: {exc.code} {detail}") from exc


def get_file(path):
    quoted = urllib.parse.quote(path)
    try:
        return gitea_request("GET", f"/contents/{quoted}?ref={GITEA_BRANCH}")
    except RuntimeError as exc:
        if "404" in str(exc):
            return None
        raise


def put_file(path, content, message):
    existing = get_file(path)
    payload = {
        "branch": GITEA_BRANCH,
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]
        return gitea_request("PUT", f"/contents/{urllib.parse.quote(path)}", payload)
    return gitea_request("POST", f"/contents/{urllib.parse.quote(path)}", payload)


def get_text_file(path, default=""):
    existing = get_file(path)
    if not existing:
        return default
    return base64.b64decode(existing["content"]).decode("utf-8")


def render_request(name, user, profile, purpose, ttl, app_image, vm_image):
    vm_block = ""
    if PROFILES[profile]["vm"]:
        vm_block = f"""  vm:
    image: {vm_image}
    imageKind: ClusterVirtualImage
"""
    groups_yaml = "".join([f"    - {g}\n" for g in user["groups"]])
    return f"""apiVersion: demo.platform/v1
kind: EnvironmentRequest
metadata:
  name: {name}
spec:
  owner: {user["user"]}
  email: {user["email"] or "unknown@example.local"}
  groups:
{groups_yaml}  profile: {profile}
  purpose: {purpose}
  ttl: {ttl}
  access:
    exposeIngress: true
    sshToVm: false
  software:
    appImage: {app_image}
{vm_block}"""


def render_namespace(name, user, profile, ttl, purpose):
    return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {name}
  labels:
    self-service.demo/request: {name}
    self-service.demo/owner: {user["user"]}
    self-service.demo/profile: {profile}
    self-service.demo/purpose: {purpose}
  annotations:
    self-service.demo/ttl: {ttl}
    argocd.argoproj.io/sync-wave: "0"
"""


def render_quota(name, profile):
    q = PROFILES[profile]["quota"]
    return f"""apiVersion: v1
kind: ResourceQuota
metadata:
  name: {name}-quota
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  hard:
    requests.cpu: "{q["cpu"]}"
    requests.memory: {q["memory"]}
    pods: "{q["pods"]}"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: {name}-defaults
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 50m
        memory: 64Mi
      default:
        cpu: 200m
        memory: 256Mi
"""


def render_rbac(name):
    return f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: developer
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer-read
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
rules:
  - apiGroups: ["", "apps", "networking.k8s.io", "virtualization.deckhouse.io"]
    resources: ["pods", "services", "deployments", "ingresses", "virtualmachines", "virtualdisks"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-read
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
subjects:
  - kind: ServiceAccount
    name: developer
    namespace: {name}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: developer-read
"""


def render_app(name, app_image):
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
  namespace: {name}
  labels:
    app: demo-app
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-app
  template:
    metadata:
      labels:
        app: demo-app
    spec:
      containers:
        - name: nginx
          image: {app_image}
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: demo-app
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  selector:
    app: demo-app
  ports:
    - name: http
      port: 80
      targetPort: 80
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: demo-app
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  ingressClassName: {INGRESS_CLASS}
  rules:
    - host: {name}.{BASE_DOMAIN}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: demo-app
                port:
                  name: http
"""


def render_vm(name, vm_image, postgres=False):
    packages = "        - openssh\n        - python3\n        - sudo\n        - qemu-guest-agent\n"
    if postgres:
        packages += "        - postgresql15\n"
    return f"""apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualDisk
metadata:
  name: {name}-vm-root
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  dataSource:
    type: ObjectRef
    objectRef:
      kind: ClusterVirtualImage
      name: {vm_image}
  persistentVolumeClaim:
    size: 256Mi
    storageClassName: {STORAGE_CLASS}
---
apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualMachine
metadata:
  name: {name}-vm
  namespace: {name}
  labels:
    self-service.demo/request: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  virtualMachineClassName: generic
  runPolicy: AlwaysOn
  osType: Generic
  bootloader: BIOS
  cpu:
    cores: 1
    coreFraction: 5%
  memory:
    size: 512Mi
  blockDeviceRefs:
    - kind: VirtualDisk
      name: {name}-vm-root
  provisioning:
    type: UserData
    userData: |
      #cloud-config
      hostname: {name}-vm
      users:
        - name: ansible
          lock_passwd: false
          passwd: $1$demoans$ZvqsQCamGDBaHD6nqXyqT/
          sudo: ALL=(ALL) NOPASSWD:ALL
          shell: /bin/sh
      ssh_pwauth: true
      package_update: false
      packages:
{packages}      runcmd:
        - rc-update add sshd default || true
        - service sshd start || true
        - rc-update add qemu-guest-agent default || true
        - service qemu-guest-agent start || true
"""


def render_access(name, user, profile):
    vm_line = f"- VM: `{name}-vm`, IP смотрите через портал или `kubectl get vm -n {name}`.\n" if PROFILES[profile]["vm"] else ""
    return f"""# Access for {name}

- Owner: `{user["user"]}`
- Namespace: `{name}`
- Application URL: `http://{name}.{BASE_DOMAIN}`
{vm_line}- TTL: see namespace annotation `self-service.demo/ttl`.

Credentials are issued through the approved platform flow. Demo manifests use safe placeholder values only.
"""


def render_kustomization(profile):
    resources = ["namespace.yaml", "quota.yaml", "rbac.yaml", "app.yaml", "access-secret.example.yaml"]
    if PROFILES[profile]["vm"]:
        resources.insert(4, "vm.yaml")
    return "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n" + "".join(
        [f"  - {item}\n" for item in resources]
    )


def render_access_secret(name):
    return f"""apiVersion: v1
kind: Secret
metadata:
  name: {name}-access
  namespace: {name}
  annotations:
    argocd.argoproj.io/sync-wave: "4"
type: Opaque
stringData:
  README: "Replace with External Secrets or approved credential delivery in production."
"""


def ensure_generated_root(name):
    path = "gitops/self-service/generated/kustomization.yaml"
    current = get_text_file(path, "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n")
    line = f"  - {name}\n"
    if line not in current:
        if not current.endswith("\n"):
            current += "\n"
        current += line
        put_file(path, current, f"Register self-service environment {name}")


def create_environment(user, payload):
    profile = payload.get("profile")
    purpose = payload.get("purpose")
    ttl = payload.get("ttl")
    app_image = payload.get("appImage")
    vm_image = payload.get("vmImage", VM_IMAGES[0])
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    if purpose not in PURPOSES:
        raise ValueError("Unknown purpose")
    if ttl not in PROFILES[profile]["ttl"]:
        raise ValueError("TTL is not allowed for this profile")
    if app_image not in APP_IMAGES:
        raise ValueError("Application image is not allowed")
    if PROFILES[profile]["vm"] and vm_image not in VM_IMAGES:
        raise ValueError("VM image is not allowed")
    if not set(user["groups"]).intersection(PROFILES[profile]["groups"]):
        raise PermissionError("Your groups are not allowed to use this profile")

    suffix = hashlib.sha1(f"{user['user']}-{purpose}-{time.time_ns()}".encode()).hexdigest()[:4]
    name = slug(f"dev-{user['user']}-{purpose}-{suffix}", "dev-env")
    base = f"gitops/self-service/generated/{name}"
    message = f"Create self-service environment {name}"
    files = {
        f"gitops/self-service/requests/{name}.yaml": render_request(name, user, profile, purpose, ttl, app_image, vm_image),
        f"{base}/namespace.yaml": render_namespace(name, user, profile, ttl, purpose),
        f"{base}/quota.yaml": render_quota(name, profile),
        f"{base}/rbac.yaml": render_rbac(name),
        f"{base}/app.yaml": render_app(name, app_image),
        f"{base}/access-secret.example.yaml": render_access_secret(name),
        f"{base}/ACCESS.md": render_access(name, user, profile),
        f"{base}/kustomization.yaml": render_kustomization(profile),
    }
    if PROFILES[profile]["vm"]:
        files[f"{base}/vm.yaml"] = render_vm(name, vm_image, PROFILES[profile]["postgres"])

    for path, content in files.items():
        put_file(path, content, message)
    ensure_generated_root(name)
    return {
        "name": name,
        "namespace": name,
        "profile": profile,
        "purpose": purpose,
        "purposeDescription": PURPOSES[purpose],
        "ttl": ttl,
        "url": f"http://{name}.{BASE_DOMAIN}",
        "git": {
            "request": f"gitops/self-service/requests/{name}.yaml",
            "generated": f"gitops/self-service/generated/{name}/",
        },
        "summary": profile_summary(profile, ttl, app_image, vm_image),
    }


def k8s_get(path):
    if not os.path.exists(K8S_TOKEN_PATH):
        return None
    with open(K8S_TOKEN_PATH, "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()
    ctx = ssl.create_default_context(cafile=K8S_CA_PATH)
    req = urllib.request.Request(
        f"https://kubernetes.default.svc{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        raise


def environment_status(name):
    ns = k8s_get(f"/api/v1/namespaces/{name}")
    deployment = k8s_get(f"/apis/apps/v1/namespaces/{name}/deployments/demo-app")
    service = k8s_get(f"/api/v1/namespaces/{name}/services/demo-app")
    ingress = k8s_get(f"/apis/networking.k8s.io/v1/namespaces/{name}/ingresses/demo-app")
    vd = k8s_get(f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{name}/virtualdisks/{name}-vm-root")
    vm = k8s_get(f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{name}/virtualmachines/{name}-vm")
    ns_meta = ns.get("metadata", {}) if ns else {}
    deploy_status = deployment.get("status", {}) if deployment else {}
    deploy_spec = deployment.get("spec", {}) if deployment else {}
    vm_status = vm.get("status", {}) if vm else {}
    vm_spec = vm.get("spec", {}) if vm else {}
    return {
        "namespace": {"name": name, "phase": ns.get("status", {}).get("phase") if ns else "Pending", "ttl": ns_meta.get("annotations", {}).get("self-service.demo/ttl"), "owner": ns_meta.get("labels", {}).get("self-service.demo/owner"), "profile": ns_meta.get("labels", {}).get("self-service.demo/profile")},
        "app": {"name": "demo-app", "replicas": deploy_spec.get("replicas", 0), "availableReplicas": deploy_status.get("availableReplicas", 0), "readyReplicas": deploy_status.get("readyReplicas", 0)},
        "service": {"name": "demo-app", "clusterIP": service.get("spec", {}).get("clusterIP") if service else None, "port": service.get("spec", {}).get("ports", [{}])[0].get("port") if service else None},
        "ingress": ingress.get("spec", {}).get("rules", [{}])[0].get("host") if ingress else None,
        "virtualDisk": {"name": f"{name}-vm-root", "phase": vd.get("status", {}).get("phase") if vd else None, "capacity": vd.get("status", {}).get("capacity") if vd else None},
        "vm": {"name": f"{name}-vm", "phase": vm_status.get("phase"), "ip": vm_status.get("ipAddress"), "node": vm_status.get("node"), "cpu": vm_spec.get("cpu", {}), "memory": vm_spec.get("memory", {}).get("size")},
    }


HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-service стенды</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <main>
    <section class="top">
      <div>
        <p class="eyebrow">GitOps Self-Service</p>
        <h1>Создание тестового стенда</h1>
      </div>
      <div id="user" class="user"></div>
    </section>
    <section class="layout">
      <form id="requestForm">
        <label>Профиль стенда<select id="profile"></select></label>
        <div id="profileDetails" class="hint"></div>
        <label>Назначение<select id="purpose"></select></label>
        <div id="purposeDetails" class="hint"></div>
        <label>TTL<select id="ttl"></select></label>
        <label>Образ приложения<select id="appImage"></select></label>
        <label id="vmImageWrap">Образ VM<select id="vmImage"></select></label>
        <button type="submit">Создать стенд</button>
      </form>
      <aside>
        <h2>Что произойдёт</h2>
        <ol>
          <li>Портал создаст request и generated manifests в Gitea.</li>
          <li>Argo CD синхронизирует namespace, app, ingress и VM.</li>
          <li>AWX сможет выполнить post-configuration для VM-профилей.</li>
        </ol>
      </aside>
    </section>
    <section id="result" class="result"></section>
  </main>
  <script src="/app.js"></script>
</body>
</html>
"""

CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172026; background: #f4f6f8; }
main { max-width: 1120px; margin: 0 auto; padding: 36px 20px; }
.top { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.eyebrow { margin: 0 0 8px; color: #28705f; font-weight: 700; text-transform: uppercase; font-size: 12px; letter-spacing: .08em; }
h1 { margin: 0; font-size: 36px; letter-spacing: 0; }
h2 { margin-top: 0; font-size: 20px; }
.user { padding: 10px 12px; background: #fff; border: 1px solid #d9e0e6; border-radius: 8px; min-width: 260px; font-size: 14px; }
.layout { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(280px, .7fr); gap: 20px; align-items: start; }
form, aside, .result { background: #fff; border: 1px solid #d9e0e6; border-radius: 8px; padding: 20px; }
label { display: grid; gap: 8px; margin-bottom: 16px; font-weight: 650; }
select { width: 100%; min-height: 42px; border: 1px solid #b9c5cf; border-radius: 6px; padding: 8px 10px; font: inherit; background: #fff; }
button { min-height: 44px; border: 0; border-radius: 6px; background: #1f6feb; color: #fff; padding: 0 18px; font-weight: 750; cursor: pointer; }
button:disabled { background: #8795a1; cursor: progress; }
.hint { margin: -8px 0 16px; padding: 12px; border: 1px solid #d9e0e6; border-radius: 6px; background: #f8fafb; color: #34424d; font-size: 14px; line-height: 1.45; }
.hint strong { display: block; margin-bottom: 6px; color: #172026; }
.hint ul { margin: 8px 0 0; padding-left: 18px; }
ol { padding-left: 22px; }
li { margin: 10px 0; }
.result { margin-top: 20px; white-space: pre-wrap; }
.ok { border-color: #71b58f; }
.err { border-color: #d96b6b; }
@media (max-width: 800px) { .top, .layout { grid-template-columns: 1fr; display: grid; } h1 { font-size: 30px; } }
"""

JS = """
let me = null;
let profiles = [];
const el = (id) => document.getElementById(id);
const purposeDescriptions = {
  feature: "Разработка или проверка новой функциональности в изолированном namespace.",
  bugfix: "Воспроизведение и проверка исправления дефекта без влияния на общие окружения.",
  loadtest: "Короткий нагрузочный или ресурсный тест в рамках квот выбранного профиля.",
  demo: "Демонстрационный стенд для показа заказчику, команде или архитектурной аудитории.",
};

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "request failed");
  return payload;
}

function fill(select, values, labelKey) {
  select.innerHTML = values.map((item) => {
    const value = typeof item === "string" ? item : item.name;
    const label = typeof item === "string" ? item : item[labelKey || "title"];
    return `<option value="${value}">${label}</option>`;
  }).join("");
}

function currentProfile() {
  return profiles.find((profile) => profile.name === el("profile").value);
}

function renderProfileDetails(profile) {
  if (!profile) {
    el("profileDetails").textContent = "";
    return;
  }
  const resources = (profile.resources || []).map((resource) => `<li>${resource}</li>`).join("");
  const vm = profile.vmSpec
    ? `<br><strong>VM:</strong> ${profile.vmSpec.cpu}, coreFraction ${profile.vmSpec.coreFraction}, RAM ${profile.vmSpec.memory}, disk ${profile.vmSpec.disk}, image ${profile.vmSpec.imageKind}.`
    : "";
  el("profileDetails").innerHTML = `<strong>${profile.title}</strong>${profile.description}<br><strong>Квоты:</strong> CPU ${profile.quota.cpu}, RAM ${profile.quota.memory}, pods ${profile.quota.pods}.<br><strong>Приложение:</strong> 1 replica, requests ${profile.app.requests}, limits ${profile.app.limits}.${vm}<br><strong>Будет создано:</strong><ul>${resources}</ul>`;
}

function renderPurposeDetails() {
  const purpose = el("purpose").value;
  el("purposeDetails").innerHTML = `<strong>${purpose}</strong>${purposeDescriptions[purpose] || ""}`;
}

function formatCreated(created) {
  const summary = created.summary;
  const vm = summary.vm
    ? `\\nVM: будет создана ${created.namespace}-vm (${summary.vm.cpu}, coreFraction ${summary.vm.coreFraction}, RAM ${summary.vm.memory}, disk ${summary.vm.disk}, image ${summary.vm.image})`
    : "\\nVM: не создаётся для выбранного профиля";
  return `Заявка создана: ${created.name}
Namespace: ${created.namespace}
Профиль: ${summary.title} (${created.profile})
Назначение: ${created.purpose} - ${created.purposeDescription}
TTL: ${created.ttl}
Квоты namespace: CPU ${summary.quota.cpu}, RAM ${summary.quota.memory}, pods ${summary.quota.pods}
Приложение: demo-app, image ${summary.app.image}, replicas ${summary.app.replicas}, requests ${summary.app.requests}, limits ${summary.app.limits}${vm}
Git request: ${created.git.request}
Generated manifests: ${created.git.generated}
URL приложения: ${created.url}

Ожидаю Argo CD sync...`;
}

function formatStatus(created, status) {
  const ns = status.namespace || {};
  const app = status.app || {};
  const svc = status.service || {};
  const disk = status.virtualDisk || {};
  const vm = status.vm || {};
  const vmLine = vm.phase
    ? `\\nVM: ${vm.name}, phase ${vm.phase}, IP ${vm.ip || "-"}, node ${vm.node || "-"}, CPU ${vm.cpu?.cores || "-"} core / ${vm.cpu?.coreFraction || "-"}, RAM ${vm.memory || "-"}\\nVirtualDisk: ${disk.name}, phase ${disk.phase || "-"}, capacity ${disk.capacity || "-"}`
    : "\\nVM: не создаётся для выбранного профиля";
  return `Заявка создана: ${created.name}
Namespace: ${ns.name} (${ns.phase || "Pending"})
Owner: ${ns.owner || me.user}
Профиль: ${created.summary.title} (${created.profile})
Назначение: ${created.purpose}
TTL: ${ns.ttl || created.ttl}
Квоты namespace: CPU ${created.summary.quota.cpu}, RAM ${created.summary.quota.memory}, pods ${created.summary.quota.pods}
Deployment: demo-app, replicas ${app.availableReplicas || 0}/${app.replicas || 0} available
Service: ${svc.name || "demo-app"}, ClusterIP ${svc.clusterIP || "-"}, port ${svc.port || "-"}
Ingress: ${status.ingress || "-"}${vmLine}
Git request: ${created.git.request}
Generated manifests: ${created.git.generated}
URL приложения: ${created.url}`;
}

function syncProfile() {
  const profile = currentProfile();
  if (!profile) {
    el("ttl").innerHTML = "";
    el("vmImageWrap").style.display = "none";
    el("result").className = "result err";
    el("result").textContent = "Для пользователя не найдено доступных профилей. Проверьте группы Dex и claims, переданные в портал.";
    return;
  }
  fill(el("ttl"), profile.ttl);
  renderProfileDetails(profile);
  el("vmImageWrap").style.display = profile.vm ? "grid" : "none";
  if (!el("result").textContent) el("result").className = "result";
}

async function init() {
  me = await api("/api/me");
  profiles = await api("/api/profiles");
  el("user").textContent = `${me.user} / ${me.email || "no-email"} / ${me.groups.join(", ") || "no-groups"}`;
  if (!profiles.length) {
    fill(el("purpose"), Object.keys(purposeDescriptions));
    fill(el("appImage"), ["nginx:1.27", "nginx:1.26"]);
    fill(el("vmImage"), ["alpine-base-3-23-v1"]);
    renderPurposeDetails();
    syncProfile();
    return;
  }
  fill(el("profile"), profiles, "title");
  fill(el("purpose"), Object.keys(purposeDescriptions));
  fill(el("appImage"), ["nginx:1.27", "nginx:1.26"]);
  fill(el("vmImage"), ["alpine-base-3-23-v1"]);
  renderPurposeDetails();
  syncProfile();
}

el("profile").addEventListener("change", syncProfile);
el("purpose").addEventListener("change", renderPurposeDetails);
el("requestForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  el("result").className = "result";
  el("result").textContent = "Создаю GitOps-заявку...";
  try {
    const created = await api("/api/request", {
      method: "POST",
      body: JSON.stringify({
        profile: el("profile").value,
        purpose: el("purpose").value,
        ttl: el("ttl").value,
        appImage: el("appImage").value,
        vmImage: el("vmImage").value,
      }),
    });
    el("result").className = "result ok";
    el("result").textContent = formatCreated(created);
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      const status = await api(`/api/status/${created.name}`);
      el("result").textContent = formatStatus(created, status);
      if (((status.vm?.phase === "Running" || status.vm?.phase === null) && (status.app?.availableReplicas || 0) > 0) || tries > 60) clearInterval(timer);
    }, 5000);
  } catch (error) {
    el("result").className = "result err";
    el("result").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

init().catch((error) => {
  el("result").className = "result err";
  el("result").textContent = error.message;
});
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            return static(self, "text/html", HTML)
        if self.path == "/styles.css":
            return static(self, "text/css", CSS)
        if self.path == "/app.js":
            return static(self, "application/javascript", JS)
        if self.path == "/api/me":
            return response(self, 200, user_from_headers(self.headers))
        if self.path == "/api/profiles":
            user = user_from_headers(self.headers)
            return response(self, 200, allowed_profiles(user["groups"]))
        if self.path.startswith("/api/status/"):
            name = slug(self.path.rsplit("/", 1)[-1])
            return response(self, 200, environment_status(name))
        response(self, 404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/request":
            return response(self, 404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            created = create_environment(user_from_headers(self.headers), payload)
            response(self, 201, created)
        except PermissionError as exc:
            response(self, 403, {"error": str(exc)})
        except ValueError as exc:
            response(self, 400, {"error": str(exc)})
        except Exception as exc:
            response(self, 500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

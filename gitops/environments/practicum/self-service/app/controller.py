#!/usr/bin/env python3
import base64
import datetime as dt
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


GITEA_URL = os.environ["GITEA_URL"].rstrip("/")
GITEA_OWNER = os.environ.get("GITEA_OWNER", "practicum")
GITEA_REPO = os.environ.get("GITEA_REPO", "practicum-demo")
GITEA_BRANCH = os.environ.get("GITEA_BRANCH", "main")
GITEA_USER = os.environ["GITEA_USER"]
GITEA_PASSWORD = os.environ["GITEA_PASSWORD"]
AWX_URL = os.environ["AWX_URL"].rstrip("/")
AWX_TOKEN = os.environ["AWX_TOKEN"]
AWX_SSH_PUBLIC_KEY = os.environ["AWX_SSH_PUBLIC_KEY"].strip()
NAMESPACE = os.environ.get("NAMESPACE", "practicum-tks")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "d8case.ru")
STORAGE_CLASS = os.environ.get("STORAGE_CLASS", "replicated")
VM_CLASS = os.environ.get("VM_CLASS", "generic")
REQUEST_ROOT = "gitops/self-service/practicum/requests"
ARCHIVE_ROOT = "gitops/self-service/practicum/archive"
STATUS_ROOT = "gitops/self-service/practicum/status"
GENERATED_ROOT = "gitops/environments/practicum/self-service/generated"
GENERATED_KUSTOMIZATION = f"{GENERATED_ROOT}/kustomization.yaml"
K8S_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
K8S_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

PROFILES = {
    "app-only": {"vm": False, "postgres": False, "ttl": {"2h", "4h", "8h"}},
    "app-with-vm": {"vm": True, "postgres": False, "ttl": {"2h", "4h", "8h"}},
    "app-with-postgres-vm": {"vm": True, "postgres": True, "ttl": {"4h", "8h", "24h"}},
}
OWNERS = {
    "alice-koroleva-practicum": {
        "email": "alice.koroleva.practicum@demo.local",
        "groups": {"practicum-payments-devs"},
        "profiles": {"app-only", "app-with-vm"},
    },
    "boris-smirnov-practicum": {
        "email": "boris.smirnov.practicum@demo.local",
        "groups": {"practicum-analytics-devs"},
        "profiles": {"app-only", "app-with-postgres-vm"},
    },
    "marina-volkova-practicum": {
        "email": "marina.volkova.practicum@demo.local",
        "groups": {"practicum-qa-devs"},
        "profiles": set(PROFILES),
    },
}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(value):
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def ttl_delta(value):
    match = re.fullmatch(r"(\d+)h", str(value))
    if not match:
        raise ValueError("TTL must use the <hours>h format")
    return dt.timedelta(hours=int(match.group(1)))


def slug(value):
    value = re.sub(r"[^a-z0-9-]+", "-", str(value).lower())
    return re.sub(r"-+", "-", value).strip("-")[:63]


def basic_auth():
    token = base64.b64encode(f"{GITEA_USER}:{GITEA_PASSWORD}".encode()).decode()
    return f"Basic {token}"


def request_json(method, url, payload=None, headers=None, timeout=20, context=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        raw = response.read()
        return json.loads(raw.decode()) if raw else {}


def gitea(method, endpoint, payload=None):
    url = f"{GITEA_URL}/api/v1/repos/{GITEA_OWNER}/{GITEA_REPO}{endpoint}"
    try:
        return request_json(method, url, payload, {"Authorization": basic_auth()})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        if exc.code == 404:
            return None
        raise RuntimeError(f"Gitea {method} {endpoint}: {exc.code} {detail}") from exc


def content_path(path):
    return urllib.parse.quote(path, safe="/")


def get_file(path):
    return gitea("GET", f"/contents/{content_path(path)}?ref={GITEA_BRANCH}")


def get_text(path, default=""):
    item = get_file(path)
    if not item:
        return default
    return base64.b64decode(item["content"]).decode()


def put_text(path, content, message):
    existing = get_file(path)
    if existing and base64.b64decode(existing["content"]).decode() == content:
        return existing
    payload = {
        "branch": GITEA_BRANCH,
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if existing:
        payload["sha"] = existing["sha"]
        return gitea("PUT", f"/contents/{content_path(path)}", payload)
    return gitea("POST", f"/contents/{content_path(path)}", payload)


def delete_file(path, message):
    existing = get_file(path)
    if existing:
        gitea("DELETE", f"/contents/{content_path(path)}", {
            "branch": GITEA_BRANCH,
            "message": message,
            "sha": existing["sha"],
        })


def list_dir(path):
    result = gitea("GET", f"/contents/{content_path(path)}?ref={GITEA_BRANCH}")
    return result if isinstance(result, list) else []


def load_json(path, default=None):
    text = get_text(path)
    return json.loads(text) if text else default


def write_status(environment, state, **fields):
    payload = {
        "environmentId": environment,
        "namespace": NAMESPACE,
        "state": state,
        **fields,
    }
    path = f"{STATUS_ROOT}/{environment}.json"
    existing = load_json(path, {}) or {}
    comparable = {key: value for key, value in existing.items() if key != "updatedAt"}
    if comparable == payload:
        return existing
    payload["updatedAt"] = iso(utcnow())
    put_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        f"Update self-service status {environment}: {state}",
    )
    return payload


def root_environments():
    text = get_text(
        GENERATED_KUSTOMIZATION,
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources: []\n",
    )
    return [
        line.split("-", 1)[1].strip()
        for line in text.splitlines()
        if re.fullmatch(r"\s*-\s+practicum-env-[a-z0-9-]+", line)
    ]


def write_root(environments, message):
    unique = sorted(set(environments))
    resources = "resources: []\n" if not unique else "resources:\n" + "".join(f"  - {name}\n" for name in unique)
    content = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n" + resources
    put_text(GENERATED_KUSTOMIZATION, content, message)


def active_image():
    text = get_text("gitops/environments/practicum/golden-images/catalog.yaml")
    match = re.search(r"^\s*activeGoldenImage:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError("activeGoldenImage is not configured")
    return match.group(1)


def validate_request(document):
    if document.get("kind") != "EnvironmentRequest":
        raise ValueError("kind must be EnvironmentRequest")
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    owner = spec.get("owner")
    profile = spec.get("profile")
    ttl = spec.get("ttl")
    purpose = slug(spec.get("purpose", "demo"))
    if owner not in OWNERS:
        raise ValueError("owner is not approved")
    if profile not in PROFILES or profile not in OWNERS[owner]["profiles"]:
        raise ValueError("profile is not allowed for owner")
    if ttl not in PROFILES[profile]["ttl"]:
        raise ValueError("TTL is not allowed for profile")
    requested_groups = set(spec.get("groups") or [])
    if requested_groups and not requested_groups.issubset(OWNERS[owner]["groups"]):
        raise ValueError("request contains unauthorized groups")
    created_at = parse_time(spec.get("createdAt")) if spec.get("createdAt") else utcnow()
    environment = slug(metadata.get("name"))
    if not environment.startswith("practicum-env-"):
        raise ValueError("environment ID must start with practicum-env-")
    expires_at = created_at + ttl_delta(ttl)
    return {
        "environment": environment,
        "owner": owner,
        "email": OWNERS[owner]["email"],
        "groups": sorted(OWNERS[owner]["groups"]),
        "profile": profile,
        "purpose": purpose,
        "ttl": ttl,
        "createdAt": iso(created_at),
        "expiresAt": iso(expires_at),
        "vm": PROFILES[profile]["vm"],
        "postgres": PROFILES[profile]["postgres"],
    }


def object_metadata(kind, name, request):
    expires_label = request["expiresAt"].replace("-", "").replace(":", "")
    return f"""apiVersion: {kind[0]}
kind: {kind[1]}
metadata:
  name: {name}
  namespace: {NAMESPACE}
  annotations:
    demo.deckhouse.io/description: "4 practicum"
    demo.practicum/expires-at: "{request['expiresAt']}"
  labels:
    app.kubernetes.io/part-of: practicum-demo
    demo.practicum/environment: {request['environment']}
    demo.practicum/owner: {request['owner']}
    demo.practicum/expires-at: {expires_label}
"""


def render_resources(request):
    env = request["environment"]
    image = active_image()
    metadata = object_metadata(("apps/v1", "Deployment"), env, request)
    documents = [f"""{metadata}spec:
  replicas: 1
  selector:
    matchLabels:
      app: {env}
  template:
    metadata:
      labels:
        app: {env}
        demo.practicum/environment: {env}
    spec:
      containers:
        - name: nginx
          image: nginx:1.27
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 25m
              memory: 32Mi
            limits:
              cpu: 100m
              memory: 128Mi
"""]
    metadata = object_metadata(("v1", "Service"), env, request)
    documents.append(f"""{metadata}spec:
  selector:
    app: {env}
  ports:
    - name: http
      port: 80
      targetPort: 80
""")
    metadata = object_metadata(("networking.k8s.io/v1", "Ingress"), env, request)
    documents.append(f"""{metadata}spec:
  ingressClassName: nginx
  rules:
    - host: {env}.{BASE_DOMAIN}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {env}
                port:
                  name: http
""")
    if request["vm"]:
        metadata = object_metadata(("virtualization.deckhouse.io/v1alpha2", "VirtualDisk"), f"{env}-root", request)
        documents.append(f"""{metadata}spec:
  dataSource:
    type: ObjectRef
    objectRef:
      kind: VirtualImage
      name: {image}
  persistentVolumeClaim:
    size: 768Mi
    storageClassName: {STORAGE_CLASS}
""")
        packages = "qemu-guest-agent curl jq" + (" postgresql15" if request["postgres"] else "")
        metadata = object_metadata(("virtualization.deckhouse.io/v1alpha2", "VirtualMachine"), f"{env}-vm", request)
        documents.append(f"""{metadata}spec:
  virtualMachineClassName: {VM_CLASS}
  runPolicy: AlwaysOnUnlessStoppedManually
  osType: Generic
  bootloader: BIOS
  cpu:
    cores: 1
    coreFraction: 5%
  memory:
    size: 512Mi
  blockDeviceRefs:
    - kind: VirtualDisk
      name: {env}-root
  provisioning:
    type: UserData
    userData: |
      #cloud-config
      hostname: {env}-vm
      users:
        - name: ansible
          lock_passwd: true
          sudo: ALL=(ALL) NOPASSWD:ALL
          shell: /bin/sh
          ssh_authorized_keys:
            - {AWX_SSH_PUBLIC_KEY}
      ssh_pwauth: false
      package_update: false
      packages:
        - openssh
        - python3
        - sudo
      runcmd:
        - apk add --no-cache {packages}
        - rc-update add sshd default || true
        - service sshd start || true
""")
    return "---\n".join(documents)


def create_generated(request):
    env = request["environment"]
    base = f"{GENERATED_ROOT}/{env}"
    put_text(f"{base}/resources.yaml", render_resources(request), f"Generate self-service environment {env}")
    put_text(
        f"{base}/kustomization.yaml",
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - resources.yaml\n",
        f"Finalize self-service environment {env}",
    )
    environments = root_environments()
    if env not in environments:
        environments.append(env)
        return write_root(environments, f"Activate self-service environment {env}")
    return None


def k8s_get(path):
    with open(K8S_TOKEN, encoding="utf-8") as token_file:
        token = token_file.read().strip()
    context = ssl.create_default_context(cafile=K8S_CA)
    try:
        return request_json(
            "GET",
            f"https://kubernetes.default.svc{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
            context=context,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def cluster_status(request):
    env = request["environment"]
    deployment = k8s_get(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{env}")
    ingress = k8s_get(f"/apis/networking.k8s.io/v1/namespaces/{NAMESPACE}/ingresses/{env}")
    vm = None
    disk = None
    if request["vm"]:
        disk = k8s_get(
            f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}/virtualdisks/{env}-root"
        )
        vm = k8s_get(
            f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}/virtualmachines/{env}-vm"
        )
    application = k8s_get(
        f"/apis/argoproj.io/v1alpha1/namespaces/{NAMESPACE}/applications/practicum-demo"
    )
    app_status = (application or {}).get("status", {})
    deployment_status = (deployment or {}).get("status", {})
    vm_status = (vm or {}).get("status", {})
    vm_conditions = {
        condition.get("type"): condition.get("status")
        for condition in vm_status.get("conditions", [])
    }
    disk_source = ((disk or {}).get("spec", {}).get("dataSource", {}).get("objectRef", {}))
    return {
        "argoCD": {
            "sync": (app_status.get("sync") or {}).get("status", "Unknown"),
            "health": (app_status.get("health") or {}).get("status", "Unknown"),
        },
        "application": {
            "name": env,
            "replicas": (deployment or {}).get("spec", {}).get("replicas", 1),
            "readyReplicas": deployment_status.get("readyReplicas", 0),
            "url": f"https://{env}.{BASE_DOMAIN}",
            "ingressReady": bool(ingress),
        },
        "virtualMachine": None if not request["vm"] else {
            "name": f"{env}-vm",
            "phase": vm_status.get("phase", "Pending"),
            "ip": vm_status.get("ipAddress"),
            "agentReady": vm_conditions.get("AgentReady") == "True",
            "cpu": "1 core, 5%",
            "memory": "512Mi",
            "disk": "768Mi",
            "image": disk_source.get("name"),
        },
    }


def awx(method, endpoint, payload=None):
    return request_json(
        method,
        f"{AWX_URL}/api/v2{endpoint}",
        payload,
        {"Authorization": f"Bearer {AWX_TOKEN}"},
    )


def launch_awx(request, host):
    templates = awx("GET", "/job_templates/?name=Practicum%20Environment%20Post-Config")
    template_id = templates["results"][0]["id"]
    result = awx("POST", f"/job_templates/{template_id}/launch/", {
        "extra_vars": {
            "target_host": host,
            "target_name": request["environment"],
            "install_postgresql": request["postgres"],
        }
    })
    return result["job"]


def delete_generated(request, request_path):
    env = request["environment"]
    write_status(env, "Expired", owner=request["owner"], expiresAt=request["expiresAt"])
    environments = [name for name in root_environments() if name != env]
    write_root(environments, f"Expire self-service environment {env}")
    for filename in ("resources.yaml", "kustomization.yaml"):
        delete_file(f"{GENERATED_ROOT}/{env}/{filename}", f"Remove expired environment {env}")
    original = get_text(request_path)
    put_text(f"{ARCHIVE_ROOT}/{env}.yaml", original, f"Archive expired request {env}")
    delete_file(request_path, f"Remove expired request {env}")
    write_status(env, "Cleaned", owner=request["owner"], expiresAt=request["expiresAt"])


def reconcile_existing(request, request_path):
    env = request["environment"]
    if utcnow() >= parse_time(request["expiresAt"]):
        delete_generated(request, request_path)
        return
    current = load_json(f"{STATUS_ROOT}/{env}.json", {}) or {}
    runtime = cluster_status(request)
    awx_job = current.get("awxJob")
    awx_status = current.get("awxStatus")
    vm = runtime["virtualMachine"]
    if (
        request["vm"]
        and vm
        and vm.get("phase") == "Running"
        and vm.get("ip")
        and vm.get("agentReady")
        and not awx_job
    ):
        awx_job = launch_awx(request, vm["ip"])
        awx_status = "pending"
    elif awx_job and awx_status not in {"successful", "failed", "error", "canceled"}:
        job = awx("GET", f"/jobs/{awx_job}/")
        awx_status = job["status"]
    app_ready = runtime["application"]["readyReplicas"] >= runtime["application"]["replicas"]
    vm_ready = not request["vm"] or (vm and vm.get("phase") == "Running")
    awx_ready = not request["vm"] or awx_status == "successful"
    state = "Ready" if app_ready and vm_ready and awx_ready else "Provisioning"
    write_status(
        env,
        state,
        owner=request["owner"],
        profile=request["profile"],
        purpose=request["purpose"],
        createdAt=request["createdAt"],
        expiresAt=request["expiresAt"],
        gitCommit=current.get("gitCommit"),
        awxJob=awx_job,
        awxStatus=awx_status,
        **runtime,
    )


def request_files():
    return [
        item
        for item in list_dir(REQUEST_ROOT)
        if item.get("type") == "file" and item["name"].endswith((".yaml", ".json"))
    ]


def reconcile():
    files = request_files()
    active = root_environments()
    active_vm = 0
    for environment in active:
        status = load_json(f"{STATUS_ROOT}/{environment}.json", {}) or {}
        if (status.get("virtualMachine") or {}).get("name"):
            active_vm += 1
    for item in sorted(files, key=lambda value: value["name"]):
        path = item["path"]
        try:
            document = json.loads(get_text(path))
            request = validate_request(document)
            env = request["environment"]
            if env in active:
                reconcile_existing(request, path)
                continue
            if utcnow() >= parse_time(request["expiresAt"]):
                delete_generated(request, path)
                continue
            if len(active) >= 3 or (request["vm"] and active_vm >= 2):
                write_status(
                    env,
                    "Queued",
                    owner=request["owner"],
                    profile=request["profile"],
                    reason="capacity-limit",
                    activeEnvironments=len(active),
                    activeVirtualMachines=active_vm,
                    expiresAt=request["expiresAt"],
                )
                continue
            result = create_generated(request)
            active.append(env)
            active_vm += 1 if request["vm"] else 0
            write_status(
                env,
                "Provisioning",
                owner=request["owner"],
                profile=request["profile"],
                createdAt=request["createdAt"],
                expiresAt=request["expiresAt"],
                gitCommit=(result or {}).get("commit", {}).get("sha") if isinstance(result, dict) else None,
            )
        except Exception as exc:
            environment = slug(item["name"].rsplit(".", 1)[0])
            state = "Error" if environment in active else "Rejected"
            write_status(environment, state, reason=str(exc))


if __name__ == "__main__":
    while True:
        try:
            reconcile()
        except Exception as exc:
            print(f"reconcile failed: {exc}", flush=True)
        time.sleep(20)

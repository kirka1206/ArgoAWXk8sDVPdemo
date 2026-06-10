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
NAMESPACE = os.environ.get("NAMESPACE", "practicum-tks")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "d8case.ru")
STORAGE_CLASS = os.environ.get("STORAGE_CLASS", "replicated")
VM_CLASS = os.environ.get("VM_CLASS", "generic")
MAX_ACTIVE_ENVIRONMENTS = int(os.environ.get("MAX_ACTIVE_ENVIRONMENTS", "3"))
MAX_ACTIVE_VMS = int(os.environ.get("MAX_ACTIVE_VMS", "2"))
REQUEST_ROOT = "gitops/self-service/practicum/requests"
ARCHIVE_ROOT = "gitops/self-service/practicum/archive"
STATUS_ROOT = "gitops/self-service/practicum/status"
ACTION_ROOT = "gitops/self-service/practicum/actions"
ACTION_ARCHIVE_ROOT = "gitops/self-service/practicum/actions-archive"
GENERATED_ROOT = "gitops/environments/practicum/self-service/generated"
GENERATED_KUSTOMIZATION = f"{GENERATED_ROOT}/kustomization.yaml"
K8S_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
K8S_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

PROFILES = {
    "app-only": {"vm": False, "postgres": False, "ttl": {"2h", "4h", "8h"}},
    "app-with-vm": {"vm": True, "postgres": False, "ttl": {"2h", "4h", "8h"}},
    "app-with-postgres-vm": {
        "vm": True,
        "postgres": True,
        "postgresVersions": {"16", "17", "18"},
        "ttl": {"4h", "8h", "24h"},
    },
}
SSH_USERNAME = "ansible"
SSH_IDENTITY_FILE = "local/practicum-ssh/id_ed25519"
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


def atomic_commit(message, writes=None, deletes=None):
    writes = writes or {}
    deletes = deletes or []
    operations = []
    for path, content in writes.items():
        existing = get_file(path)
        operation = {
            "operation": "update" if existing else "create",
            "path": path,
            "content": base64.b64encode(content.encode()).decode(),
        }
        if existing:
            operation["sha"] = existing["sha"]
        operations.append(operation)
    for path in deletes:
        existing = get_file(path)
        if not existing:
            continue
        operations.append({
            "operation": "delete",
            "path": path,
            "sha": existing["sha"],
        })
    if not operations:
        return latest_commit(GENERATED_KUSTOMIZATION)
    result = gitea("POST", "/contents", {
        "branch": GITEA_BRANCH,
        "message": message,
        "files": operations,
    })
    return commit_sha(result)


def list_dir(path):
    result = gitea("GET", f"/contents/{content_path(path)}?ref={GITEA_BRANCH}")
    return result if isinstance(result, list) else []


def load_json(path, default=None):
    text = get_text(path)
    return json.loads(text) if text else default


def latest_commit(path):
    commits = gitea(
        "GET",
        f"/commits?sha={urllib.parse.quote(GITEA_BRANCH)}"
        f"&path={content_path(path)}&limit=1",
    )
    if not commits:
        return None
    return commits[0].get("sha")


def commit_sha(result):
    if not isinstance(result, dict):
        return None
    commit = result.get("commit") or {}
    return commit.get("sha") or commit.get("id") or result.get("sha")


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
    return put_text(GENERATED_KUSTOMIZATION, content, message)


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
    postgres_version = (spec.get("postgresql") or {}).get("version")
    if PROFILES[profile]["postgres"]:
        # Requests created before version selection was introduced used the
        # newest package available in Alpine 3.23, which is PostgreSQL 18.
        postgres_version = str(postgres_version or "18")
        if postgres_version not in PROFILES[profile]["postgresVersions"]:
            raise ValueError("PostgreSQL version must be one of: 16, 17, 18")
    elif postgres_version:
        raise ValueError("PostgreSQL version is allowed only for the PostgreSQL profile")
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
        "postgresVersion": postgres_version,
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
    type: UserDataRef
    userDataRef:
      kind: Secret
      name: practicum-golden-builder-cloud-init
""")
    return "---\n".join(documents)


def generated_kustomization(include_operation=False):
    resources = ["resources.yaml"]
    if include_operation:
        resources.append("operation.yaml")
    return (
        "apiVersion: kustomize.config.k8s.io/v1beta1\n"
        "kind: Kustomization\nresources:\n"
        + "".join(f"  - {name}\n" for name in resources)
    )


def create_generated(request):
    env = request["environment"]
    base = f"{GENERATED_ROOT}/{env}"
    put_text(f"{base}/resources.yaml", render_resources(request), f"Generate self-service environment {env}")
    put_text(
        f"{base}/kustomization.yaml",
        generated_kustomization(),
        f"Finalize self-service environment {env}",
    )
    environments = root_environments()
    if env not in environments:
        environments.append(env)
        return write_root(environments, f"Activate self-service environment {env}")
    return None


def action_files():
    return [
        item for item in list_dir(ACTION_ROOT)
        if item.get("type") == "file" and item["name"].endswith(".json")
    ]


def load_request_for_environment(environment):
    path = f"{REQUEST_ROOT}/{environment}.yaml"
    text = get_text(path)
    if not text:
        return None, path, None
    return validate_request(json.loads(text)), path, text


def action_status(
    environment, action, state, status, reason=None, root_updates=None, **extra
):
    current = load_json(f"{STATUS_ROOT}/{environment}.json", {}) or {}
    current.pop("updatedAt", None)
    current.update(root_updates or {})
    current["state"] = state
    current["reason"] = reason
    current["lastAction"] = {
        "id": action["id"],
        "action": action["action"],
        "actor": action["actor"],
        "reason": action.get("reason"),
        "requestedAt": action["requestedAt"],
        "gitCommit": action.get("gitCommit"),
        "status": status,
        **extra,
    }
    return write_status(
        environment,
        current.pop("state"),
        **{
            key: value for key, value in current.items()
            if key not in {"environmentId", "namespace"}
        },
    )


def archive_action(action_path, action, outcome):
    archived = {**action, "outcome": outcome, "completedAt": iso(utcnow())}
    atomic_commit(
        f"Archive environment action {action['id']}: {outcome}",
        writes={
            f"{ACTION_ARCHIVE_ROOT}/{action['id']}.json":
                json.dumps(archived, ensure_ascii=False, indent=2) + "\n",
        },
        deletes=[action_path],
    )


def operation_manifest(action):
    operation = {
        "start-vm": "Start",
        "stop-vm": "Stop",
        "restart-vm": "Restart",
    }[action["action"]]
    name = f"{action['environment']}-{operation.lower()}-{action['id'][-6:]}"[:63]
    return name, f"""apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualMachineOperation
metadata:
  name: {name}
  namespace: {NAMESPACE}
  annotations:
    demo.deckhouse.io/description: "4 practicum"
  labels:
    app.kubernetes.io/part-of: practicum-demo
    demo.practicum/environment: {action['environment']}
    demo.practicum/action: {action['id']}
spec:
  type: {operation}
  virtualMachineName: {action['environment']}-vm
"""


def reconcile_action(item):
    action_path = item["path"]
    action = json.loads(get_text(action_path))
    action_id = slug((action.get("metadata") or {}).get("name"))
    spec = action.get("spec") or {}
    environment = slug(spec.get("environment"))
    action_type = spec.get("action")
    actor = spec.get("actor")
    reason = str(spec.get("reason") or "").strip()
    requested_at = spec.get("requestedAt") or iso(utcnow())
    if action.get("kind") != "EnvironmentAction":
        raise ValueError("kind must be EnvironmentAction")
    if action_type not in {
        "delete-environment", "delete-vm", "start-vm", "stop-vm", "restart-vm",
    }:
        raise ValueError("unsupported environment action")
    if actor not in {*OWNERS, "victor-melnikov-practicum"}:
        raise ValueError("actor is not approved")
    if actor == "victor-melnikov-practicum" and not reason:
        raise ValueError("administrator reason is required")
    request, request_path, request_text = load_request_for_environment(environment)
    current = load_json(f"{STATUS_ROOT}/{environment}.json", {}) or {}
    if not request:
        if action_type == "delete-environment" and current.get("state") == "Deleting":
            deployment = k8s_get(
                f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{environment}"
            )
            vm = k8s_get(
                f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
                f"/virtualmachines/{environment}-vm"
            )
            disk = k8s_get(
                f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
                f"/virtualdisks/{environment}-root"
            )
            if not deployment and not vm and not disk:
                normalized = {
                    "id": action_id, "environment": environment,
                    "action": action_type, "actor": actor, "reason": reason,
                    "requestedAt": requested_at, "gitCommit": latest_commit(action_path),
                }
                archive_action(action_path, normalized, "Completed")
                action_status(environment, normalized, "Cleaned", "Completed")
            return
        if action_type.startswith("delete") and current.get("state") == "Cleaned":
            archive_action(action_path, {
                "id": action_id, "environment": environment, "action": action_type,
                "actor": actor, "reason": reason, "requestedAt": requested_at,
            }, "NoOp")
            return
        raise ValueError("environment does not exist")
    if actor != "victor-melnikov-practicum" and request["owner"] != actor:
        raise PermissionError("actor does not own this environment")
    normalized = {
        "id": action_id,
        "environment": environment,
        "action": action_type,
        "actor": actor,
        "reason": reason,
        "requestedAt": requested_at,
        "gitCommit": latest_commit(action_path),
    }
    base = f"{GENERATED_ROOT}/{environment}"
    if action_type == "delete-environment":
        awx_job = current.get("awxJob")
        if awx_job and current.get("awxStatus") not in {
            "successful", "failed", "error", "canceled",
        }:
            try:
                awx("POST", f"/jobs/{awx_job}/cancel/", {})
            except urllib.error.HTTPError as exc:
                if exc.code not in {400, 405}:
                    raise
        deployment = k8s_get(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{environment}")
        vm = k8s_get(
            f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
            f"/virtualmachines/{environment}-vm"
        )
        if environment not in root_environments() and not deployment and not vm:
            archive_action(action_path, normalized, "Completed")
            action_status(environment, normalized, "Cleaned", "Completed")
            return
        if environment in root_environments():
            environments = [name for name in root_environments() if name != environment]
            resources = "resources: []\n" if not environments else (
                "resources:\n" + "".join(f"  - {name}\n" for name in sorted(environments))
            )
            archived_request = json.loads(request_text)
            archived_request["metadata"]["annotations"] = {
                "demo.practicum/deleted-by": actor,
                "demo.practicum/delete-reason": reason or "owner-request",
            }
            atomic_commit(
                f"Request deletion of environment {environment}",
                writes={
                    GENERATED_KUSTOMIZATION:
                        "apiVersion: kustomize.config.k8s.io/v1beta1\n"
                        f"kind: Kustomization\n{resources}",
                    f"{ARCHIVE_ROOT}/{environment}.yaml":
                        json.dumps(archived_request, ensure_ascii=False, indent=2) + "\n",
                },
                deletes=[
                    f"{base}/resources.yaml",
                    f"{base}/kustomization.yaml",
                    f"{base}/operation.yaml",
                    request_path,
                ],
            )
        action_status(environment, normalized, "Deleting", "Running")
        return
    if action_type == "delete-vm":
        vm = k8s_get(
            f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
            f"/virtualmachines/{environment}-vm"
        )
        disk = k8s_get(
            f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
            f"/virtualdisks/{environment}-root"
        )
        if not vm and not disk and not request["vm"]:
            archive_action(action_path, normalized, "Completed")
            action_status(
                environment,
                normalized,
                "Ready",
                "Completed",
                root_updates={
                    "profile": "app-only",
                    "postgresVersion": None,
                    "virtualMachine": None,
                    "awxJob": None,
                    "awxStatus": None,
                },
            )
            return
        if request["vm"]:
            document = json.loads(request_text)
            document["spec"]["profile"] = "app-only"
            document["spec"].pop("postgresql", None)
            app_request = validate_request(document)
            atomic_commit(
                f"Remove VM from environment {environment}",
                writes={
                    request_path: json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    f"{base}/resources.yaml": render_resources(app_request),
                    f"{base}/kustomization.yaml": generated_kustomization(),
                },
                deletes=[f"{base}/operation.yaml"],
            )
        action_status(environment, normalized, "VMDeleting", "Running")
        return
    if not request["vm"]:
        raise ValueError("environment has no virtual machine")
    operation_name, manifest = operation_manifest(normalized)
    operation = k8s_get(
        f"/apis/virtualization.deckhouse.io/v1alpha2/namespaces/{NAMESPACE}"
        f"/virtualmachineoperations/{operation_name}"
    )
    phase = (operation or {}).get("status", {}).get("phase")
    if phase == "Completed":
        atomic_commit(
            f"Complete VM operation {action_id}",
            writes={f"{base}/kustomization.yaml": generated_kustomization()},
            deletes=[f"{base}/operation.yaml"],
        )
        archive_action(action_path, normalized, "Completed")
        action_status(environment, normalized, "Ready", "Completed")
        return
    if phase in {"Failed", "Error"}:
        archive_action(action_path, normalized, "Failed")
        action_status(
            environment, normalized, "ActionFailed", "Failed",
            reason=f"VirtualMachineOperation {operation_name} failed",
        )
        return
    if not get_text(f"{base}/operation.yaml"):
        atomic_commit(
            f"Start VM operation {action_id}",
            writes={
                f"{base}/operation.yaml": manifest,
                f"{base}/kustomization.yaml": generated_kustomization(True),
            },
        )
    states = {
        "start-vm": "VMStarting",
        "stop-vm": "VMStopping",
        "restart-vm": "VMRestarting",
    }
    action_status(
        environment, normalized, states[action_type], "Running",
        operation=operation_name,
    )


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
    running_condition = next(
        (
            condition
            for condition in vm_status.get("conditions", [])
            if condition.get("type") == "Running" and condition.get("status") == "True"
        ),
        {},
    )
    running_since = running_condition.get("lastTransitionTime")
    running_long_enough = bool(
        running_since and utcnow() - parse_time(running_since) >= dt.timedelta(seconds=90)
    )
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
            "url": f"http://{env}.{BASE_DOMAIN}",
            "ingressReady": bool(ingress),
        },
        "virtualMachine": None if not request["vm"] else {
            "name": f"{env}-vm",
            "phase": vm_status.get("phase", "Pending"),
            "ip": vm_status.get("ipAddress"),
            "agentReady": vm_conditions.get("AgentReady") == "True",
            "guestReady": vm_conditions.get("AgentReady") == "True" or running_long_enough,
            "cpu": "1 core, 5%",
            "memory": "512Mi",
            "disk": "768Mi",
            "image": disk_source.get("name"),
            "access": {
                "username": SSH_USERNAME,
                "authentication": "SSH key",
                "identityFile": SSH_IDENTITY_FILE,
                "command": (
                    f"d8 v ssh {SSH_USERNAME}@{env}-vm "
                    f"--namespace {NAMESPACE} "
                    f"--identity-file {SSH_IDENTITY_FILE} --local-ssh"
                ),
            },
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
            "postgresql_version": request["postgresVersion"],
            "postgresql_package": (
                f"postgresql{request['postgresVersion']}"
                if request["postgres"] else ""
            ),
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
    awx_attempts = current.get("awxAttempts", 0)
    vm = runtime["virtualMachine"]
    retry_awx = awx_status in {"failed", "error", "canceled"} and awx_attempts < 3
    if (
        request["vm"]
        and vm
        and vm.get("phase") == "Running"
        and vm.get("ip")
        and vm.get("guestReady")
        and (not awx_job or retry_awx)
    ):
        awx_job = launch_awx(request, vm["ip"])
        awx_status = "pending"
        awx_attempts += 1
    elif awx_job and awx_status not in {"successful", "failed", "error", "canceled"}:
        job = awx("GET", f"/jobs/{awx_job}/")
        awx_status = job["status"]
    app_ready = runtime["application"]["readyReplicas"] >= runtime["application"]["replicas"]
    vm_ready = not request["vm"] or (vm and vm.get("phase") == "Running")
    awx_ready = not request["vm"] or awx_status == "successful"
    awx_failed = (
        request["vm"]
        and awx_status in {"failed", "error", "canceled"}
        and awx_attempts >= 3
    )
    state = "Error" if awx_failed else (
        "Ready" if app_ready and vm_ready and awx_ready else "Provisioning"
    )
    reason = (
        f"AWX post-configuration failed after {awx_attempts} attempts; "
        f"last job: {awx_job}, status: {awx_status}"
        if awx_failed else None
    )
    write_status(
        env,
        state,
        owner=request["owner"],
        profile=request["profile"],
        postgresVersion=request["postgresVersion"],
        purpose=request["purpose"],
        createdAt=request["createdAt"],
        expiresAt=request["expiresAt"],
        gitCommit=current.get("gitCommit") or latest_commit(request_path),
        awxJob=awx_job,
        awxStatus=awx_status,
        awxAttempts=awx_attempts,
        reason=reason,
        **runtime,
    )


def request_files():
    return [
        item
        for item in list_dir(REQUEST_ROOT)
        if item.get("type") == "file" and item["name"].endswith((".yaml", ".json"))
    ]


def reconcile():
    actions = sorted(action_files(), key=lambda value: value["name"])
    action_environments = set()
    for item in actions:
        try:
            raw_action = json.loads(get_text(item["path"], "{}") or "{}")
            action_environments.add(slug((raw_action.get("spec") or {}).get("environment")))
            reconcile_action(item)
        except Exception as exc:
            action = json.loads(get_text(item["path"], "{}") or "{}")
            spec = action.get("spec") or {}
            fallback_environment = item["name"].rsplit(".", 1)[0]
            environment = slug(spec.get("environment") or fallback_environment)
            existing = load_json(f"{STATUS_ROOT}/{environment}.json", {}) or {}
            existing.pop("updatedAt", None)
            write_status(
                environment,
                "ActionFailed",
                **{
                    key: value for key, value in existing.items()
                    if key not in {"environmentId", "namespace", "state", "reason"}
                },
                reason=str(exc),
            )
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
            if env in action_environments:
                continue
            if env in active:
                reconcile_existing(request, path)
                continue
            if utcnow() >= parse_time(request["expiresAt"]):
                delete_generated(request, path)
                continue
            if (
                len(active) >= MAX_ACTIVE_ENVIRONMENTS
                or (request["vm"] and active_vm >= MAX_ACTIVE_VMS)
            ):
                write_status(
                    env,
                    "Queued",
                    owner=request["owner"],
                    profile=request["profile"],
                    postgresVersion=request["postgresVersion"],
                    reason="capacity-limit",
                    activeEnvironments=len(active),
                    activeVirtualMachines=active_vm,
                    maxActiveEnvironments=MAX_ACTIVE_ENVIRONMENTS,
                    maxActiveVirtualMachines=MAX_ACTIVE_VMS,
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
                postgresVersion=request["postgresVersion"],
                createdAt=request["createdAt"],
                expiresAt=request["expiresAt"],
                gitCommit=commit_sha(result) or latest_commit(path),
            )
        except Exception as exc:
            environment = slug(item["name"].rsplit(".", 1)[0])
            state = "Error" if environment in active else "Rejected"
            existing = load_json(f"{STATUS_ROOT}/{environment}.json", {}) or {}
            preserved = {
                key: value
                for key, value in existing.items()
                if key not in {"environmentId", "namespace", "state", "reason", "updatedAt"}
            }
            write_status(environment, state, reason=str(exc), **preserved)


if __name__ == "__main__":
    while True:
        try:
            reconcile()
        except Exception as exc:
            print(f"reconcile failed: {exc}", flush=True)
        time.sleep(20)

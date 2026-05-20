#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

KUBECTL="${KUBECTL:-kubectl}"
GIT="${GIT:-git}"
CURL="${CURL:-curl}"
JQ="${JQ:-jq}"

GITEA_USER="${GITEA_USER:-codex}"
GITEA_PASSWORD="${GITEA_PASSWORD:-codex123}"
GITEA_EMAIL="${GITEA_EMAIL:-codex@example.local}"
GITEA_REPO="${GITEA_REPO:-demo}"
GITEA_LOCAL_PORT="${GITEA_LOCAL_PORT:-3001}"
ARGOCD_LOCAL_PORT="${ARGOCD_LOCAL_PORT:-3000}"
AWX_LOCAL_PORT="${AWX_LOCAL_PORT:-3002}"

AWX_NAME="${AWX_NAME:-awx-demo}"
AWX_OPERATOR_REF="${AWX_OPERATOR_REF:-2.19.1}"
AWX_VERSION="${AWX_VERSION:-24.6.1}"
AWX_EE_IMAGE="${AWX_EE_IMAGE:-quay.io/ansible/awx-ee:${AWX_VERSION}}"

log() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

wait_deploy() {
  local namespace="$1"
  local deploy="$2"
  local timeout="${3:-300s}"
  "$KUBECTL" -n "$namespace" rollout status "deployment/${deploy}" "--timeout=${timeout}"
}

start_port_forward() {
  local name="$1"
  local namespace="$2"
  local service="$3"
  local mapping="$4"
  local log_file="${ROOT_DIR}/.run/${name}.log"
  local pid_file="${ROOT_DIR}/.run/${name}.pid"

  mkdir -p "${ROOT_DIR}/.run"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
    return 0
  fi

  nohup "$KUBECTL" -n "$namespace" port-forward "svc/${service}" "$mapping" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
}

api() {
  local method="$1"
  local url="$2"
  local body="${3:-}"
  if [[ -n "$body" ]]; then
    "$CURL" -fsS -X "$method" -u "${AWX_ADMIN_USER}:${AWX_ADMIN_PASSWORD}" \
      -H 'Content-Type: application/json' -d "$body" "$url"
  else
    "$CURL" -fsS -X "$method" -u "${AWX_ADMIN_USER}:${AWX_ADMIN_PASSWORD}" \
      -H 'Content-Type: application/json' "$url"
  fi
}

upsert_first_id() {
  local list_url="$1"
  local create_url="$2"
  local jq_filter="$3"
  local body="$4"
  local existing

  existing="$(api GET "$list_url" | "$JQ" -r "$jq_filter")"
  if [[ -n "$existing" && "$existing" != "null" ]]; then
    echo "$existing"
  else
    api POST "$create_url" "$body" | "$JQ" -r '.id'
  fi
}

need "$KUBECTL"
need "$GIT"
need "$CURL"
need "$JQ"

log "Checking Kubernetes context"
"$KUBECTL" config current-context
"$KUBECTL" get nodes

log "Installing Argo CD"
"$KUBECTL" create namespace argocd --dry-run=client -o yaml | "$KUBECTL" apply -f -
"$KUBECTL" apply --server-side --force-conflicts -n argocd -f "${ROOT_DIR}/manifests/argocd/install.yaml"

log "Installing Gitea"
"$KUBECTL" apply -f "${ROOT_DIR}/manifests/gitea/gitea.yaml"
wait_deploy gitea gitea 300s
start_port_forward gitea gitea gitea-http "${GITEA_LOCAL_PORT}:3000"
sleep 3

log "Creating Gitea user and repository"
GITEA_POD="$("$KUBECTL" -n gitea get pod -l app=gitea -o jsonpath='{.items[0].metadata.name}')"
"$KUBECTL" -n gitea exec "$GITEA_POD" -- gitea admin user create \
  --username "$GITEA_USER" \
  --password "$GITEA_PASSWORD" \
  --email "$GITEA_EMAIL" \
  --admin \
  --must-change-password=false >/dev/null 2>&1 || true

"$CURL" -fsS -u "${GITEA_USER}:${GITEA_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"${GITEA_REPO}\",\"private\":false,\"auto_init\":false}" \
  "http://localhost:${GITEA_LOCAL_PORT}/api/v1/user/repos" >/dev/null 2>&1 || true

log "Pushing this project into local Gitea"
if [[ ! -d "${ROOT_DIR}/.git" ]]; then
  "$GIT" -C "$ROOT_DIR" init -b main
fi
"$GIT" -C "$ROOT_DIR" config user.email "${GIT_AUTHOR_EMAIL:-codex@example.local}"
"$GIT" -C "$ROOT_DIR" config user.name "${GIT_AUTHOR_NAME:-Codex}"
"$GIT" -C "$ROOT_DIR" add .
"$GIT" -C "$ROOT_DIR" commit -m 'Bootstrap Argo AWX Kubernetes demo' >/dev/null 2>&1 || true
"$GIT" -C "$ROOT_DIR" remote remove local-gitea >/dev/null 2>&1 || true
"$GIT" -C "$ROOT_DIR" remote add local-gitea "http://${GITEA_USER}:${GITEA_PASSWORD}@localhost:${GITEA_LOCAL_PORT}/${GITEA_USER}/${GITEA_REPO}.git"
"$GIT" -C "$ROOT_DIR" push -u local-gitea main

log "Applying Argo CD Application"
wait_deploy argocd argocd-redis 300s || {
  "$KUBECTL" -n argocd set image deployment/argocd-redis redis=redis:8.2.3-alpine
  wait_deploy argocd argocd-redis 300s
}
wait_deploy argocd argocd-repo-server 300s
wait_deploy argocd argocd-server 300s
"$KUBECTL" wait -n argocd --for=condition=Ready pod/argocd-application-controller-0 --timeout=300s
"$KUBECTL" apply -f "${ROOT_DIR}/manifests/argocd/application-demo.yaml"
"$KUBECTL" -n argocd annotate application ansible-os-pods argocd.argoproj.io/refresh=hard --overwrite >/dev/null

log "Waiting for Argo CD to deploy demo OS pods"
for _ in $(seq 1 90); do
  sync="$("$KUBECTL" -n argocd get application ansible-os-pods -o jsonpath='{.status.sync.status}' 2>/dev/null || true)"
  health="$("$KUBECTL" -n argocd get application ansible-os-pods -o jsonpath='{.status.health.status}' 2>/dev/null || true)"
  [[ "$sync" == "Synced" && "$health" == "Healthy" ]] && break
  sleep 3
done
"$KUBECTL" -n demo-os wait --for=condition=Ready pod -l app.kubernetes.io/part-of=ansible-argo-demo --timeout=300s

log "Installing AWX Operator"
"$KUBECTL" apply -k "github.com/ansible/awx-operator/config/default?ref=${AWX_OPERATOR_REF}"
"$KUBECTL" -n awx set image deployment/awx-operator-controller-manager kube-rbac-proxy=quay.io/brancz/kube-rbac-proxy:v0.15.0 >/dev/null 2>&1 || true
wait_deploy awx awx-operator-controller-manager 300s

log "Installing AWX"
"$KUBECTL" apply -f "${ROOT_DIR}/manifests/awx/awx.yaml"
"$KUBECTL" apply -f "${ROOT_DIR}/manifests/awx/projects-pvc.yaml"
for deploy in "${AWX_NAME}-web" "${AWX_NAME}-task"; do
  for _ in $(seq 1 120); do
    "$KUBECTL" -n awx get "deployment/${deploy}" >/dev/null 2>&1 && break
    sleep 2
  done
done
wait_deploy awx "${AWX_NAME}-web" 600s
wait_deploy awx "${AWX_NAME}-task" 600s
start_port_forward awx awx "${AWX_NAME}-service" "${AWX_LOCAL_PORT}:80"
start_port_forward argocd argocd argocd-server "${ARGOCD_LOCAL_PORT}:80"
sleep 5

AWX_ADMIN_USER=admin
AWX_ADMIN_PASSWORD="$("$KUBECTL" -n awx get secret "${AWX_NAME}-admin-password" -o jsonpath='{.data.password}' | base64 -d)"
AWX_URL="http://localhost:${AWX_LOCAL_PORT}"

log "Configuring AWX inventory, project, credentials and job template"
ORG_ID="$(api GET "${AWX_URL}/api/v2/organizations/" | "$JQ" -r '.results[0].id')"
INV_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/inventories/?name=Demo%20OS%20pods" \
  "${AWX_URL}/api/v2/inventories/" \
  '.results[0].id // empty' \
  "{\"name\":\"Demo OS pods\",\"organization\":${ORG_ID},\"variables\":\"ansible_user: ansible\\nansible_password: ansible123\\nansible_become: true\\nansible_become_method: sudo\\nansible_ssh_common_args: \\\"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\\\"\\n\"}")"
GROUP_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/groups/?name=linux_pods" \
  "${AWX_URL}/api/v2/groups/" \
  '.results[0].id // empty' \
  "{\"name\":\"linux_pods\",\"inventory\":${INV_ID}}")"

for host in ol-node-1.demo-os.svc.cluster.local ol-node-2.demo-os.svc.cluster.local; do
  HOST_ID="$(upsert_first_id \
    "${AWX_URL}/api/v2/hosts/?name=${host}" \
    "${AWX_URL}/api/v2/hosts/" \
    '.results[0].id // empty' \
    "{\"name\":\"${host}\",\"inventory\":${INV_ID},\"variables\":\"ansible_host: ${host}\\n\"}")"
  api POST "${AWX_URL}/api/v2/groups/${GROUP_ID}/hosts/" "{\"id\":${HOST_ID}}" >/dev/null 2>&1 || true
done

MACHINE_CT_ID="$(api GET "${AWX_URL}/api/v2/credential_types/?name=Machine" | "$JQ" -r '.results[0].id')"
CRED_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/credentials/?name=demo-pod-ssh" \
  "${AWX_URL}/api/v2/credentials/" \
  '.results[0].id // empty' \
  "{\"name\":\"demo-pod-ssh\",\"organization\":${ORG_ID},\"credential_type\":${MACHINE_CT_ID},\"inputs\":{\"username\":\"ansible\",\"password\":\"ansible123\",\"become_method\":\"sudo\"}}")"
PROJECT_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/projects/?name=Gitea%20demo%20repo" \
  "${AWX_URL}/api/v2/projects/" \
  '.results[0].id // empty' \
  "{\"name\":\"Gitea demo repo\",\"organization\":${ORG_ID},\"scm_type\":\"git\",\"scm_url\":\"http://gitea-http.gitea.svc.cluster.local:3000/${GITEA_USER}/${GITEA_REPO}.git\",\"scm_branch\":\"main\",\"scm_update_on_launch\":true}")"
EE_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/execution_environments/?name=AWX%20EE%20${AWX_VERSION}" \
  "${AWX_URL}/api/v2/execution_environments/" \
  '.results[0].id // empty' \
  "{\"name\":\"AWX EE ${AWX_VERSION}\",\"organization\":${ORG_ID},\"image\":\"${AWX_EE_IMAGE}\",\"pull\":\"missing\"}")"

UPDATE_ID="$(api POST "${AWX_URL}/api/v2/projects/${PROJECT_ID}/update/" | "$JQ" -r '.id')"
for _ in $(seq 1 90); do
  status="$(api GET "${AWX_URL}/api/v2/project_updates/${UPDATE_ID}/" | "$JQ" -r '.status')"
  [[ "$status" == "successful" ]] && break
  [[ "$status" == "failed" || "$status" == "error" ]] && {
    echo "AWX project update failed" >&2
    exit 1
  }
  sleep 2
done

JT_ID="$(upsert_first_id \
  "${AWX_URL}/api/v2/job_templates/?name=Configure%20OS%20pods" \
  "${AWX_URL}/api/v2/job_templates/" \
  '.results[0].id // empty' \
  "{\"name\":\"Configure OS pods\",\"job_type\":\"run\",\"inventory\":${INV_ID},\"project\":${PROJECT_ID},\"playbook\":\"awx/os-demo-playbook.yml\",\"execution_environment\":${EE_ID},\"become_enabled\":true}")"
api POST "${AWX_URL}/api/v2/job_templates/${JT_ID}/credentials/" "{\"id\":${CRED_ID}}" >/dev/null 2>&1 || true

log "Done"
cat <<EOF
Gitea:  http://localhost:${GITEA_LOCAL_PORT} (${GITEA_USER}/${GITEA_PASSWORD})
ArgoCD: http://localhost:${ARGOCD_LOCAL_PORT} (admin/$("$KUBECTL" -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d))
AWX:    http://localhost:${AWX_LOCAL_PORT} (${AWX_ADMIN_USER}/${AWX_ADMIN_PASSWORD})

AWX job template: Configure OS pods
To run the Ansible demo:
  ./scripts/run-demo-job.sh
EOF

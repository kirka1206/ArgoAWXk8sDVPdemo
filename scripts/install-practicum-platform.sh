#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-practicum-tks}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-practicum-tks-api.d8case.ru}"
GITEA_USER="${GITEA_USER:-practicum}"
GITEA_EMAIL="${GITEA_EMAIL:-practicum@demo.local}"
GITEA_REPO="${GITEA_REPO:-practicum-demo}"
ARGOCD_USER="${ARGOCD_USER:-practicum-admin}"
ARGOCD_VERSION="${ARGOCD_VERSION:-v3.4.2}"

log() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

current_context="$(kubectl config current-context)"
if [[ "$current_context" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to continue: expected context ${EXPECTED_CONTEXT}, got ${current_context}" >&2
  exit 1
fi

kubectl get namespace "$NAMESPACE" >/dev/null

log "Applying default container resources 4 practicum"
kubectl apply -f "${ROOT_DIR}/manifests/practicum/resource-defaults.yaml"

log "Installing Gitea resources 4 practicum"
kubectl apply -f "${ROOT_DIR}/manifests/practicum/gitea.yaml"
kubectl rollout status -n "$NAMESPACE" deployment/practicum-gitea --timeout=600s

if ! kubectl get secret -n "$NAMESPACE" practicum-gitea-admin-credentials >/dev/null 2>&1; then
  gitea_password="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  kubectl create secret generic practicum-gitea-admin-credentials \
    -n "$NAMESPACE" \
    --from-literal=username="$GITEA_USER" \
    --from-literal=password="$gitea_password" \
    --from-literal=email="$GITEA_EMAIL" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
kubectl annotate secret -n "$NAMESPACE" practicum-gitea-admin-credentials \
  demo.deckhouse.io/description="4 practicum" --overwrite

gitea_password="$(kubectl get secret -n "$NAMESPACE" practicum-gitea-admin-credentials -o jsonpath='{.data.password}' | base64 -d)"
if ! kubectl exec -n "$NAMESPACE" deployment/practicum-gitea -- \
  gitea admin user list --admin 2>/dev/null | awk '{print $2}' | grep -qx "$GITEA_USER"; then
  kubectl exec -n "$NAMESPACE" deployment/practicum-gitea -- \
    gitea admin user create \
      --username "$GITEA_USER" \
      --password "$gitea_password" \
      --email "$GITEA_EMAIL" \
      --admin \
      --must-change-password=false
fi

log "Creating Gitea repository ${GITEA_USER}/${GITEA_REPO}"
kubectl port-forward -n "$NAMESPACE" service/practicum-gitea-http 33001:3000 >/tmp/practicum-gitea-port-forward.log 2>&1 &
port_forward_pid=$!
trap 'kill "$port_forward_pid" >/dev/null 2>&1 || true' EXIT
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:33001/api/healthz >/dev/null 2>&1 && break
  sleep 1
done
repo_status="$(curl -sS -o /tmp/practicum-gitea-repo-response.json -w '%{http_code}' \
  -u "${GITEA_USER}:${gitea_password}" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"${GITEA_REPO}\",\"description\":\"4 practicum\",\"private\":false,\"auto_init\":false}" \
  http://127.0.0.1:33001/api/v1/user/repos)"
if [[ "$repo_status" != "201" && "$repo_status" != "409" ]]; then
  cat /tmp/practicum-gitea-repo-response.json >&2
  exit 1
fi
kill "$port_forward_pid" >/dev/null 2>&1 || true
trap - EXIT

log "Installing Argo CD ${ARGOCD_VERSION} CRDs"
kubectl apply --server-side --force-conflicts \
  -k "https://github.com/argoproj/argo-cd/manifests/crds?ref=${ARGOCD_VERSION}"

log "Installing namespace-scoped Argo CD 4 practicum"
kubectl apply -k "${ROOT_DIR}/manifests/practicum/argocd"
for deployment in \
  argocd-applicationset-controller \
  argocd-dex-server \
  argocd-notifications-controller \
  argocd-redis \
  argocd-repo-server \
  argocd-server; do
  kubectl rollout status -n "$NAMESPACE" "deployment/${deployment}" --timeout=600s
done
kubectl rollout status -n "$NAMESPACE" statefulset/argocd-application-controller --timeout=600s

if ! kubectl get secret -n "$NAMESPACE" practicum-argocd-admin-credentials >/dev/null 2>&1; then
  argocd_password="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  kubectl create secret generic practicum-argocd-admin-credentials \
    -n "$NAMESPACE" \
    --from-literal=username="$ARGOCD_USER" \
    --from-literal=password="$argocd_password" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
kubectl annotate secret -n "$NAMESPACE" practicum-argocd-admin-credentials \
  demo.deckhouse.io/description="4 practicum" --overwrite

argocd_password="$(kubectl get secret -n "$NAMESPACE" practicum-argocd-admin-credentials -o jsonpath='{.data.password}' | base64 -d)"
argocd_hash="$(htpasswd -bnBC 10 "" "$argocd_password" | tr -d ':\n')"
argocd_mtime="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl patch secret -n "$NAMESPACE" argocd-secret --type merge \
  -p "$(jq -n --arg hash "$argocd_hash" --arg mtime "$argocd_mtime" \
    '{"stringData":{"accounts.practicum-admin.password":$hash,"accounts.practicum-admin.passwordMtime":$mtime}}')"

log "Installing AWX Operator 2.19.1 4 practicum"
kubectl apply -k "${ROOT_DIR}/manifests/practicum/awx-operator"
kubectl rollout status -n "$NAMESPACE" deployment/awx-operator-controller-manager --timeout=600s

log "Installing AWX instance practicum-awx"
kubectl apply -f "${ROOT_DIR}/manifests/practicum/awx.yaml"
for deployment in practicum-awx-web practicum-awx-task; do
  for _ in $(seq 1 180); do
    kubectl get -n "$NAMESPACE" "deployment/${deployment}" >/dev/null 2>&1 && break
    sleep 5
  done
  kubectl wait -n "$NAMESPACE" \
    --for=condition=available "deployment/${deployment}" \
    --timeout=1200s
done
kubectl annotate secret -n "$NAMESPACE" practicum-awx-admin-password \
  demo.deckhouse.io/description="4 practicum" --overwrite

log "Publishing practicum ingresses"
kubectl apply -f "${ROOT_DIR}/manifests/practicum/ingresses.yaml"

log "Installation summary"
kubectl get pods,pvc,ingress -n "$NAMESPACE" -o wide
printf '\nCredentials are stored in Kubernetes Secrets:\n'
printf '  Gitea: kubectl -n %s get secret practicum-gitea-admin-credentials\n' "$NAMESPACE"
printf '  Argo CD: kubectl -n %s get secret practicum-argocd-admin-credentials\n' "$NAMESPACE"
printf '  AWX: kubectl -n %s get secret practicum-awx-admin-password\n' "$NAMESPACE"

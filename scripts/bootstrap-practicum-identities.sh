#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-practicum-tks-api.d8case.ru}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-${ROOT_DIR}/local/practicum-demo-users.env}"

if [[ "$(kubectl config current-context)" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to continue: expected context ${EXPECTED_CONTEXT}" >&2
  exit 1
fi

mkdir -p "$(dirname "$CREDENTIALS_FILE")"
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  umask 077
  cat >"$CREDENTIALS_FILE" <<EOF
ALICE_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)
BORIS_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)
MARINA_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)
VICTOR_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)
GITEA_PORTAL_BOT_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)
EOF
fi

if ! grep -q '^GITEA_PORTAL_BOT_PASSWORD=' "$CREDENTIALS_FILE"; then
  printf 'GITEA_PORTAL_BOT_PASSWORD=%s\n' \
    "$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)" >>"$CREDENTIALS_FILE"
fi

# shellcheck disable=SC1090
source "$CREDENTIALS_FILE"

apply_user() {
  local name="$1"
  local email="$2"
  local password="$3"
  local hash
  hash="$(htpasswd -bnBC 10 "" "$password" | tr -d ':\n')"
  kubectl apply -f - <<EOF
apiVersion: deckhouse.io/v1
kind: User
metadata:
  name: ${name}
  annotations:
    demo.deckhouse.io/description: "4 practicum"
spec:
  email: ${email}
  password: '${hash}'
EOF
}

apply_user alice-koroleva-practicum alice.koroleva.practicum@demo.local "$ALICE_PASSWORD"
apply_user boris-smirnov-practicum boris.smirnov.practicum@demo.local "$BORIS_PASSWORD"
apply_user marina-volkova-practicum marina.volkova.practicum@demo.local "$MARINA_PASSWORD"
apply_user victor-melnikov-practicum victor.melnikov.practicum@demo.local "$VICTOR_PASSWORD"

kubectl apply -f "${ROOT_DIR}/manifests/practicum/identities-rbac.yaml"

if ! kubectl exec -n practicum-tks deployment/practicum-gitea -- \
  gitea admin user list | awk 'NR > 1 {print $2}' | grep -qx practicum-portal-bot; then
  kubectl exec -n practicum-tks deployment/practicum-gitea -- \
    gitea admin user create \
      --username practicum-portal-bot \
      --password "$GITEA_PORTAL_BOT_PASSWORD" \
      --email practicum.portal.bot@demo.local \
      --must-change-password=false
fi

gitea_admin_user="$(kubectl get secret -n practicum-tks \
  practicum-gitea-admin-credentials -o jsonpath='{.data.username}' | base64 -d)"
gitea_admin_password="$(kubectl get secret -n practicum-tks \
  practicum-gitea-admin-credentials -o jsonpath='{.data.password}' | base64 -d)"
kubectl port-forward -n practicum-tks service/practicum-gitea-http \
  33003:3000 >/tmp/practicum-gitea-identity-port-forward.log 2>&1 &
port_forward_pid=$!
trap 'kill "$port_forward_pid" >/dev/null 2>&1 || true' EXIT
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:33003/api/healthz >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -X PUT \
  -u "${gitea_admin_user}:${gitea_admin_password}" \
  -H 'Content-Type: application/json' \
  -d '{"permission":"write"}' \
  http://127.0.0.1:33003/api/v1/repos/practicum/practicum-demo/collaborators/practicum-portal-bot
kill "$port_forward_pid" >/dev/null 2>&1 || true
trap - EXIT

echo "Credentials saved to ${CREDENTIALS_FILE}"
echo "Users and practicum DVP RBAC are ready."

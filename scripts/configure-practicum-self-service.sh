#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-practicum-tks}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-practicum-tks-api.d8case.ru}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-${ROOT_DIR}/local/practicum-demo-users.env}"
SSH_PUBLIC_KEY_FILE="${SSH_PUBLIC_KEY_FILE:-${ROOT_DIR}/local/practicum-ssh/id_ed25519.pub}"

if [[ "$(kubectl config current-context)" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to continue: expected context ${EXPECTED_CONTEXT}" >&2
  exit 1
fi

if [[ ! -f "$CREDENTIALS_FILE" || ! -f "$SSH_PUBLIC_KEY_FILE" ]]; then
  echo "Local practicum credentials or SSH public key are missing" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CREDENTIALS_FILE"

kubectl create secret generic practicum-self-service-runtime \
  -n "$NAMESPACE" \
  --from-literal=giteaUsername=practicum-portal-bot \
  --from-literal=giteaPassword="$GITEA_PORTAL_BOT_PASSWORD" \
  --from-file=sshPublicKey="$SSH_PUBLIC_KEY_FILE" \
  --dry-run=client -o yaml |
  kubectl annotate --local -f - demo.deckhouse.io/description="4 practicum" -o yaml |
  kubectl apply -f -

echo "Practicum self-service runtime Secret is ready."

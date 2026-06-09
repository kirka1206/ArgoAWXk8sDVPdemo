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
  echo "Practicum local credentials or SSH public key are missing" >&2
  exit 1
fi

if ! grep -q '^GOLDEN_BUILDER_PASSWORD=' "$CREDENTIALS_FILE"; then
  printf 'GOLDEN_BUILDER_PASSWORD=%s\n' \
    "$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)" >>"$CREDENTIALS_FILE"
fi
# shellcheck disable=SC1090
source "$CREDENTIALS_FILE"

if openssl passwd -6 test >/dev/null 2>&1; then
  password_hash="$(openssl passwd -6 "$GOLDEN_BUILDER_PASSWORD")"
elif python3 -c 'import crypt' >/dev/null 2>&1; then
  password_hash="$(
    GOLDEN_BUILDER_PASSWORD="$GOLDEN_BUILDER_PASSWORD" python3 - <<'PY'
import crypt
import os

print(crypt.crypt(os.environ["GOLDEN_BUILDER_PASSWORD"], crypt.mksalt(crypt.METHOD_SHA512)))
PY
  )"
else
  echo "Cannot create a SHA-512 password hash: install compatible OpenSSL or Python crypt" >&2
  exit 1
fi
ssh_public_key="$(cat "$SSH_PUBLIC_KEY_FILE")"
cloud_init="$(cat <<EOF
#cloud-config
hostname: practicum-golden-builder-vm
users:
  - name: ansible
    lock_passwd: false
    passwd: '${password_hash}'
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/sh
    ssh_authorized_keys:
      - ${ssh_public_key}
ssh_pwauth: true
package_update: false
packages:
  - openssh
  - python3
  - sudo
runcmd:
  - rc-update add sshd default || true
  - service sshd start || true
EOF
)"

kubectl create secret generic practicum-golden-builder-cloud-init \
  -n "$NAMESPACE" \
  --from-literal=userData="$cloud_init" \
  --dry-run=client -o yaml |
  kubectl annotate --local -f - demo.deckhouse.io/description="4 practicum" -o yaml |
  kubectl apply -f -

echo "Golden builder cloud-init Secret is ready."

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KUBECTL="${KUBECTL:-kubectl}"

"${ROOT_DIR}/scripts/stop-port-forward.sh" || true

"$KUBECTL" delete application -n argocd ansible-os-pods --ignore-not-found
"$KUBECTL" delete namespace demo-os awx gitea argocd --ignore-not-found

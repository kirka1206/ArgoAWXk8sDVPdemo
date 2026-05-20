#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

KUBECTL="${KUBECTL:-kubectl}"
CONTEXT="${CONTEXT:-codex-api.d8.kir.lab}"

GITEA_HOST="${GITEA_HOST:-gitea-awx.d8.kir.lab}"
ARGOCD_HOST="${ARGOCD_HOST:-argocd-awx.d8.kir.lab}"
AWX_HOST="${AWX_HOST:-awx-demo.d8.kir.lab}"

GITEA_LOCAL_PORT="${GITEA_LOCAL_PORT:-3101}"
ARGOCD_LOCAL_PORT="${ARGOCD_LOCAL_PORT:-3100}"
AWX_LOCAL_PORT="${AWX_LOCAL_PORT:-3102}"

export KUBECTL
export GITEA_LOCAL_PORT
export ARGOCD_LOCAL_PORT
export AWX_LOCAL_PORT

log() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

current_context="$("$KUBECTL" config current-context)"
if [[ "$current_context" != "$CONTEXT" ]]; then
  log "Switching kubectl context from ${current_context} to ${CONTEXT}"
  "$KUBECTL" config use-context "$CONTEXT"
fi

log "Deploying the base demo stack into DKP"
"${ROOT_DIR}/scripts/bootstrap.sh"

log "Applying DKP ingress resources"
"$KUBECTL" -n argocd patch configmap argocd-cmd-params-cm \
  --type merge \
  -p '{"data":{"server.insecure":"true"}}'
"$KUBECTL" -n argocd rollout restart deployment/argocd-server
"$KUBECTL" -n argocd rollout status deployment/argocd-server --timeout=300s

"$KUBECTL" -n gitea set env deployment/gitea \
  GITEA__server__ROOT_URL="http://${GITEA_HOST}/" \
  GITEA__server__SSH_DOMAIN="${GITEA_HOST}"
"$KUBECTL" -n gitea rollout status deployment/gitea --timeout=300s

"$KUBECTL" apply -f "${ROOT_DIR}/manifests/dkp/ingresses.yaml"

log "DKP deployment summary"
cat <<EOF
Gitea:  http://${GITEA_HOST}
ArgoCD: http://${ARGOCD_HOST}
AWX:    http://${AWX_HOST}

Local fallback port-forwards:
Gitea:  http://localhost:${GITEA_LOCAL_PORT}
ArgoCD: http://localhost:${ARGOCD_LOCAL_PORT}
AWX:    http://localhost:${AWX_LOCAL_PORT}
EOF


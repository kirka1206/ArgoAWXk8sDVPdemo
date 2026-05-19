#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KUBECTL="${KUBECTL:-kubectl}"

mkdir -p "${ROOT_DIR}/.run"

start_pf() {
  local name="$1"
  local namespace="$2"
  local service="$3"
  local mapping="$4"
  local pid_file="${ROOT_DIR}/.run/${name}.pid"
  local log_file="${ROOT_DIR}/.run/${name}.log"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
    echo "${name} already running with pid $(cat "$pid_file")"
    return
  fi
  nohup "$KUBECTL" -n "$namespace" port-forward "svc/${service}" "$mapping" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "${name}: ${mapping}"
}

start_pf gitea gitea gitea-http 3001:3000
start_pf argocd argocd argocd-server 3000:80
start_pf awx awx awx-demo-service 3002:80

#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
CURL="${CURL:-curl}"
JQ="${JQ:-jq}"
AWX_LOCAL_PORT="${AWX_LOCAL_PORT:-3002}"
AWX_NAME="${AWX_NAME:-awx-demo}"
AWX_URL="http://localhost:${AWX_LOCAL_PORT}"

AWX_ADMIN_USER=admin
AWX_ADMIN_PASSWORD="$("$KUBECTL" -n awx get secret "${AWX_NAME}-admin-password" -o jsonpath='{.data.password}' | base64 -d)"

api() {
  local method="$1"
  local url="$2"
  "$CURL" -fsS -X "$method" -u "${AWX_ADMIN_USER}:${AWX_ADMIN_PASSWORD}" \
    -H 'Content-Type: application/json' "$url"
}

jt_id="$(api GET "${AWX_URL}/api/v2/job_templates/?name=Configure%20OS%20pods" | "$JQ" -r '.results[0].id')"
job_id="$(api POST "${AWX_URL}/api/v2/job_templates/${jt_id}/launch/" | "$JQ" -r '.job')"

echo "Launched AWX job ${job_id}"
for _ in $(seq 1 120); do
  status="$(api GET "${AWX_URL}/api/v2/jobs/${job_id}/" | "$JQ" -r '.status')"
  echo "job_status=${status}"
  case "$status" in
    successful|failed|error|canceled) break ;;
  esac
  sleep 3
done

api GET "${AWX_URL}/api/v2/jobs/${job_id}/stdout/?format=txt" | tail -120

echo
echo "Marker files inside Argo-managed pods:"
"$KUBECTL" exec -n demo-os deploy/ol-node-1 -- cat /etc/ansible-managed-by-awx
"$KUBECTL" exec -n demo-os deploy/ol-node-2 -- cat /etc/ansible-managed-by-awx

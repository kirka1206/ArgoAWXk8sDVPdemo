#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-practicum-tks}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-practicum-tks-api.d8case.ru}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-${ROOT_DIR}/local/practicum-demo-users.env}"
SSH_KEY_FILE="${SSH_KEY_FILE:-${ROOT_DIR}/local/practicum-ssh/id_ed25519}"
AWX_PORT="${AWX_PORT:-33002}"

if [[ "$(kubectl config current-context)" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to continue: expected context ${EXPECTED_CONTEXT}" >&2
  exit 1
fi

if [[ ! -f "$CREDENTIALS_FILE" || ! -f "$SSH_KEY_FILE" ]]; then
  echo "Run bootstrap-practicum-identities.sh and create the practicum SSH key first" >&2
  exit 1
fi

if ! grep -q '^AWX_AUTOMATION_PASSWORD=' "$CREDENTIALS_FILE"; then
  printf 'AWX_AUTOMATION_PASSWORD=%s\n' \
    "$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)" >>"$CREDENTIALS_FILE"
fi
# shellcheck disable=SC1090
source "$CREDENTIALS_FILE"

admin_user="$(kubectl get awx practicum-awx -n "$NAMESPACE" -o jsonpath='{.status.adminUser}')"
admin_password="$(kubectl get secret practicum-awx-admin-password -n "$NAMESPACE" \
  -o jsonpath='{.data.password}' | base64 -d)"

kubectl port-forward -n "$NAMESPACE" service/practicum-awx-service \
  "${AWX_PORT}:80" >/tmp/practicum-awx-config-port-forward.log 2>&1 &
port_forward_pid=$!
trap 'kill "$port_forward_pid" >/dev/null 2>&1 || true' EXIT
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${AWX_PORT}/api/v2/ping/" >/dev/null 2>&1 && break
  sleep 1
done

api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -fsS -u "${admin_user}:${admin_password}" \
      -X "$method" -H 'Content-Type: application/json' -d "$data" \
      "http://127.0.0.1:${AWX_PORT}${path}"
  else
    curl -fsS -u "${admin_user}:${admin_password}" \
      -X "$method" "http://127.0.0.1:${AWX_PORT}${path}"
  fi
}

lookup_id() {
  local endpoint="$1"
  local name="$2"
  api GET "/api/v2/${endpoint}/?name=$(jq -rn --arg value "$name" '$value|@uri')" |
    jq -r '.results[0].id // empty'
}

ensure_named() {
  local endpoint="$1"
  local name="$2"
  local payload="$3"
  local id
  id="$(lookup_id "$endpoint" "$name")"
  if [[ -z "$id" ]]; then
    id="$(api POST "/api/v2/${endpoint}/" "$payload" | jq -r '.id')"
  else
    api PATCH "/api/v2/${endpoint}/${id}/" "$payload" >/dev/null
  fi
  printf '%s' "$id"
}

organization_id="$(lookup_id organizations Default)"
ee_id="$(lookup_id execution_environments 'AWX EE (24.6.1)')"

automation_user_id="$(api GET '/api/v2/users/?username=practicum-automation' | jq -r '.results[0].id // empty')"
user_payload="$(jq -cn \
  --arg password "$AWX_AUTOMATION_PASSWORD" \
  '{username:"practicum-automation",email:"practicum.automation@demo.local",
    first_name:"4",last_name:"practicum",password:$password,
    is_superuser:false,is_system_auditor:false}')"
if [[ -z "$automation_user_id" ]]; then
  automation_user_id="$(api POST '/api/v2/users/' "$user_payload" | jq -r '.id')"
else
  api PATCH "/api/v2/users/${automation_user_id}/" "$user_payload" >/dev/null
fi

project_payload="$(jq -cn \
  --argjson organization "$organization_id" \
  '{name:"Practicum GitOps Demo",description:"4 practicum",organization:$organization,
    scm_type:"git",
    scm_url:"http://practicum-gitea-http.practicum-tks.svc.cluster.local:3000/practicum/practicum-demo.git",
    scm_branch:"main",scm_update_on_launch:true,scm_clean:true}')"
project_id="$(ensure_named projects 'Practicum GitOps Demo' "$project_payload")"
project_update_id="$(api POST "/api/v2/projects/${project_id}/update/" '{}' | jq -r '.id')"
for _ in $(seq 1 120); do
  project_status="$(api GET "/api/v2/project_updates/${project_update_id}/" | jq -r '.status')"
  [[ "$project_status" == successful ]] && break
  [[ "$project_status" == failed || "$project_status" == error || "$project_status" == canceled ]] &&
    { echo "AWX project update failed: ${project_status}" >&2; exit 1; }
  sleep 2
done

inventory_payload="$(jq -cn --argjson organization "$organization_id" \
  '{name:"Practicum DVP VMs",description:"4 practicum",organization:$organization}')"
inventory_id="$(ensure_named inventories 'Practicum DVP VMs' "$inventory_payload")"

ssh_key="$(cat "$SSH_KEY_FILE")"
credential_payload="$(jq -cn \
  --argjson organization "$organization_id" \
  --arg ssh_key "$ssh_key" \
  '{name:"practicum-dvp-ssh",description:"4 practicum",organization:$organization,
    credential_type:1,inputs:{username:"ansible",ssh_key_data:$ssh_key}}')"
credential_id="$(ensure_named credentials practicum-dvp-ssh "$credential_payload")"

builder_ip="$(kubectl get vm practicum-golden-builder-vm -n "$NAMESPACE" \
  -o jsonpath='{.status.ipAddress}')"
host_variables="$(jq -cn --arg host "$builder_ip" \
  '{ansible_host:$host,ansible_user:"ansible",
    ansible_ssh_common_args:"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"}')"
host_payload="$(jq -cn \
  --argjson inventory "$inventory_id" \
  --arg variables "$host_variables" \
  '{name:"practicum-golden-builder-vm",description:"4 practicum",
    inventory:$inventory,variables:$variables,enabled:true}')"
host_id="$(ensure_named hosts practicum-golden-builder-vm "$host_payload")"
group_payload="$(jq -cn --argjson inventory "$inventory_id" \
  '{name:"golden_builder",description:"4 practicum",inventory:$inventory}')"
group_id="$(ensure_named groups golden_builder "$group_payload")"
api POST "/api/v2/groups/${group_id}/hosts/" "$(jq -cn --argjson id "$host_id" '{id:$id}')" >/dev/null

ensure_job_template() {
  local name="$1"
  local playbook="$2"
  local ask_limit="${3:-false}"
  local payload id
  payload="$(jq -cn \
    --arg name "$name" \
    --arg playbook "$playbook" \
    --argjson inventory "$inventory_id" \
    --argjson project "$project_id" \
    --argjson ee "$ee_id" \
    --argjson ask_limit "$ask_limit" \
    '{name:$name,description:"4 practicum",job_type:"run",inventory:$inventory,
      project:$project,playbook:$playbook,execution_environment:$ee,
      ask_limit_on_launch:$ask_limit,become_enabled:false,verbosity:0}')"
  id="$(ensure_named job_templates "$name" "$payload")"
  api POST "/api/v2/job_templates/${id}/credentials/" \
    "$(jq -cn --argjson id "$credential_id" '{id:$id}')" >/dev/null
  printf '%s' "$id"
}

prepare_id="$(ensure_job_template 'Practicum Prepare Golden Image' \
  'gitops/awx/playbooks/prepare-golden-image.yml')"
validate_id="$(ensure_job_template 'Practicum Validate Golden Image' \
  'gitops/awx/playbooks/validate-golden-image.yml')"
shutdown_id="$(ensure_job_template 'Practicum Shutdown Golden Builder' \
  'gitops/awx/playbooks/shutdown-golden-image.yml')"
post_config_id="$(ensure_job_template 'Practicum Environment Post-Config' \
  'gitops/awx/playbooks/practicum-environment-post-config.yml' true)"

workflow_payload="$(jq -cn --argjson organization "$organization_id" \
  '{name:"Practicum Golden Image Build",description:"4 practicum",
    organization:$organization,ask_variables_on_launch:false}')"
workflow_id="$(ensure_named workflow_job_templates 'Practicum Golden Image Build' "$workflow_payload")"

ensure_node() {
  local identifier="$1"
  local template_id="$2"
  local node_id payload
  node_id="$(api GET "/api/v2/workflow_job_templates/${workflow_id}/workflow_nodes/?identifier=${identifier}" |
    jq -r '.results[0].id // empty')"
  if [[ -z "$node_id" ]]; then
    payload="$(jq -cn --arg identifier "$identifier" --argjson template "$template_id" \
      '{identifier:$identifier,unified_job_template:$template}')"
    node_id="$(api POST "/api/v2/workflow_job_templates/${workflow_id}/workflow_nodes/" \
      "$payload" | jq -r '.id')"
  fi
  printf '%s' "$node_id"
}

prepare_node="$(ensure_node prepare "$prepare_id")"
validate_node="$(ensure_node validate "$validate_id")"
shutdown_node="$(ensure_node shutdown "$shutdown_id")"
api POST "/api/v2/workflow_job_template_nodes/${prepare_node}/success_nodes/" \
  "$(jq -cn --argjson id "$validate_node" '{id:$id}')" >/dev/null
api POST "/api/v2/workflow_job_template_nodes/${validate_node}/success_nodes/" \
  "$(jq -cn --argjson id "$shutdown_node" '{id:$id}')" >/dev/null

workflow_json="$(api GET "/api/v2/workflow_job_templates/${workflow_id}/")"
execute_role_id="$(printf '%s' "$workflow_json" | jq -r '.summary_fields.object_roles.execute_role.id')"
api POST "/api/v2/roles/${execute_role_id}/users/" \
  "$(jq -cn --argjson id "$automation_user_id" '{id:$id}')" >/dev/null
post_config_json="$(api GET "/api/v2/job_templates/${post_config_id}/")"
post_execute_role_id="$(printf '%s' "$post_config_json" | jq -r '.summary_fields.object_roles.execute_role.id')"
api POST "/api/v2/roles/${post_execute_role_id}/users/" \
  "$(jq -cn --argjson id "$automation_user_id" '{id:$id}')" >/dev/null

if ! kubectl get secret practicum-awx-automation-token -n "$NAMESPACE" >/dev/null 2>&1; then
  token="$(api POST "/api/v2/users/${automation_user_id}/personal_tokens/" \
    '{"description":"4 practicum request controller","scope":"write"}' | jq -r '.token')"
  kubectl create secret generic practicum-awx-automation-token \
    -n "$NAMESPACE" \
    --from-literal=token="$token" \
    --from-literal=username=practicum-automation \
    --dry-run=client -o yaml |
    kubectl annotate --local -f - demo.deckhouse.io/description="4 practicum" -o yaml |
    kubectl apply -f -
fi

kill "$port_forward_pid" >/dev/null 2>&1 || true
trap - EXIT
echo "AWX practicum automation objects are ready."

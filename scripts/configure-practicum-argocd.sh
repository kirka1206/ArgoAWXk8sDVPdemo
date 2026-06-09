#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-practicum-tks}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-practicum-tks-api.d8case.ru}"

if [[ "$(kubectl config current-context)" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to continue: expected context ${EXPECTED_CONTEXT}" >&2
  exit 1
fi

for _ in $(seq 1 30); do
  token="$(kubectl get secret -n "$NAMESPACE" \
    argocd-practicum-manager-token -o jsonpath='{.data.token}' 2>/dev/null || true)"
  ca_data="$(kubectl get secret -n "$NAMESPACE" \
    argocd-practicum-manager-token -o jsonpath='{.data.ca\.crt}' 2>/dev/null || true)"
  [[ -n "$token" && -n "$ca_data" ]] && break
  sleep 1
done

if [[ -z "${token:-}" || -z "${ca_data:-}" ]]; then
  echo "Argo CD service account token was not populated" >&2
  exit 1
fi

token="$(printf '%s' "$token" | base64 -d)"
config="$(jq -cn --arg token "$token" --arg ca "$ca_data" \
  '{bearerToken:$token,tlsClientConfig:{insecure:false,caData:$ca}}')"

kubectl create secret generic argocd-practicum-cluster \
  -n "$NAMESPACE" \
  --from-literal=name=practicum-local \
  --from-literal=server=https://kubernetes.default.svc \
  --from-literal=namespaces="$NAMESPACE" \
  --from-literal=clusterResources=false \
  --from-literal=config="$config" \
  --dry-run=client -o yaml |
  kubectl label --local -f - \
    argocd.argoproj.io/secret-type=cluster \
    demo.deckhouse.io/description="4 practicum" \
    -o yaml |
  kubectl apply -f -

kubectl annotate application -n "$NAMESPACE" practicum-demo \
  argocd.argoproj.io/refresh=hard --overwrite

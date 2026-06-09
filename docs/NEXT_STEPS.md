# Next Steps

## Immediate

1. Create DNS records for `gitea-practicum.d8case.ru`, `argocd-practicum.d8case.ru` and `awx-practicum.d8case.ru` pointing to `192.168.2.31`; use local `/etc/hosts` entries until then.
2. Push the demo repository into `practicum/practicum-demo` on the new Gitea.
3. Register the new Gitea repository in Argo CD and create the target Application only after target-specific domain, StorageClass, DVP class and namespace values are adapted.
4. Configure AWX Project, Inventory, credentials and Job Templates for the new Gitea and target resources.
5. Decide whether to carry current generated self-service environments to the new stand or clean `gitops/self-service/requests/` and `gitops/self-service/generated/` before migration.
6. After bootstrap validation, ask the cluster administrator to replace the temporary `SuperAdmin` rule with least-privilege permissions.

## Architecture Improvements

1. Remove the need to edit two files for app scale and VM resize.
   - Preferred direction: convert `demo-platform` to Helm or another templating approach where `values.yaml` is the only admin-facing input.
   - Alternative: use Kustomize patches/replacements and make the scenario explicitly edit only one live source file.
2. Keep architecture decisions synchronized in `README.md` and `README.ru.md`.
3. Parameterize currently hardcoded stand-specific values:
   - base domain in manifests and generated self-service artifacts;
   - StorageClass `k8nfs`;
   - VM class `generic`;
   - Gitea owner/repo and Argo CD repoURL.
4. Consider adding repeatable scripts for AWX VM objects:
   - create/update DVP VM inventory;
   - create/update VM bootstrap job template;
   - run bootstrap and validation jobs.
5. Convert the self-service portal backend from direct commits to branch/PR workflow.
6. Add policy validation for `EnvironmentRequest` before merge.
7. Add AWX launch automation after VM profile creation.

## Self-Service Scenario Draft

Goal: demonstrate developer-facing self-service without bypassing GitOps governance.

Status: catalog, generated examples, portal backend and scenario documentation are live. Current generated environments include `dev-alice-koroleva-demo-c3aa`, `dev-alice-koroleva-feature-f72b` and `dev-alice-koroleva-feature-8c3e`; Argo CD is `Synced/Healthy`, app resources are available, `ClusterVirtualImage` is `Ready`, and VM profiles run minimal DVP VMs.

Proposed flow:

1. Developer opens `self-service-ui/index.html`.
2. Developer selects an approved profile and TTL.
3. UI generates an `EnvironmentRequest`.
4. Request is committed to Git and reviewed.
5. Platform automation renders manifests into `gitops/self-service/generated/<request>/`.
6. Argo CD applies namespace, quota, RBAC, app, ingress and optional DVP VM.
7. AWX performs post-configuration for profiles with VM.
8. Developer receives namespace, endpoint and credential retrieval instructions.

## Golden Image Scenario Draft

Goal: demonstrate production-like golden image management in DVP.

Status: initial manifests, playbooks and scenario documentation were added. The live demo talk plan is in `scenarios/08-golden-image-management.md`. First-phase live validation passed: source image import is `Ready`, builder VM exists and is intentionally stopped in `Manual` mode. Full AWX customization and golden image publication are still pending.

Proposed flow:

1. Admin defines an external source image URL in Git.
2. Argo CD creates a DVP `VirtualImage` from that URL.
3. Argo CD creates a builder `VirtualDisk` and temporary `golden-builder-vm`.
4. AWX customizes the builder VM:
   - installs packages;
   - changes configuration files;
   - enables `qemu-guest-agent`;
   - cleans machine-id, SSH host keys, logs and caches;
   - runs validation.
5. A new versioned `VirtualImage` or `ClusterVirtualImage` is published.
6. Workload VM manifests switch from `golden-v1` to `golden-v2` through Git.
7. Rollback is done by Git revert.

Design decision to make:

- Whether to implement full image baking in the current cluster or first model it as a documented GitOps flow with DVP manifests and AWX playbooks.

## Useful Checks

```bash
kubectl get application -n argocd
kubectl get vi,vd,vm -n demo-prod -o wide
kubectl get deploy demo-app -n demo-prod
kubectl get ns customer-a
kubectl get ns | grep '^dev-'
```

For AWX API work:

```bash
AWX_URL=http://awx-demo.d8.kir.lab
AWX_PASS="$(kubectl -n awx get secret awx-demo-admin-password -o jsonpath='{.data.password}' | base64 -d)"
```

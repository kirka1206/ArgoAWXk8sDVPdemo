# Next Steps

## Immediate

1. Decide whether to revert scenario 02 scale back to `2` replicas or keep `demo-app` at `4` replicas for the next demo.
2. Document AWX UI steps for creating `DVP VMs`, `postgres-vm`, `dvp-vm-ssh` and `Bootstrap DVP VM` in Russian docs.
3. Continue scenario 08 live validation: start `golden-builder-vm`, run AWX customization and validation, then decide whether to publish `alpine-golden-3-23-v1`.
4. Manually check scenario 10 in a browser after adding `10.77.77.208 selfservice-awx.d8.kir.lab` to `/etc/hosts`.

## Architecture Improvements

1. Remove the need to edit two files for app scale and VM resize.
   - Preferred direction: convert `demo-platform` to Helm or another templating approach where `values.yaml` is the only admin-facing input.
   - Alternative: use Kustomize patches/replacements and make the scenario explicitly edit only one live source file.
2. Keep architecture decisions synchronized in `README.md` and `README.ru.md`.
3. Consider adding repeatable scripts for AWX VM objects:
   - create/update DVP VM inventory;
   - create/update VM bootstrap job template;
   - run bootstrap and validation jobs.
4. Convert the self-service portal backend from direct commits to branch/PR workflow.
5. Add policy validation for `EnvironmentRequest` before merge.
6. Add AWX launch automation after VM profile creation.

## Self-Service Scenario Draft

Goal: demonstrate developer-facing self-service without bypassing GitOps governance.

Status: initial catalog, request, generated example, static web UI and scenario documentation were added. Live validation passed in DKP/DVP for `dev-alice-001`: Argo CD is `Synced/Healthy`, app is available, `ClusterVirtualImage` is `Ready`, VM is `Running`.

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
```

For AWX API work:

```bash
AWX_URL=http://awx-demo.d8.kir.lab
AWX_PASS="$(kubectl -n awx get secret awx-demo-admin-password -o jsonpath='{.data.password}' | base64 -d)"
```

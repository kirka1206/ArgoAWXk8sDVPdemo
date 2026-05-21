# Current Status

Updated: 2026-05-21 10:59 MSK

## Repository Rule

Before starting new work in this repository, read this file and `docs/NEXT_STEPS.md` first. Keep architectural decisions in both `README.md` and `README.ru.md`. Update this file after meaningful changes.

## Repository

- Local path: `/Users/kir/code/ArgoAWXk8sDVPdemo`
- GitHub: `git@github.com:kirka1206/ArgoAWXk8sDVPdemo.git`
- DKP Gitea: `http://gitea-awx.d8.kir.lab/codex/demo.git`
- Current branch: `main`

## Cluster

- Kubernetes context: `codex-api.d8.kir.lab`
- DKP/DVP cluster: `d8.kir.lab`
- Ingress address: `10.77.77.208`
- Master node `dmaster` is schedulable; the control-plane `NoSchedule` taint was removed for demo capacity.

## UI Endpoints

- Gitea: `http://gitea-awx.d8.kir.lab`
- Argo CD: `http://argocd-awx.d8.kir.lab`
- AWX: `http://awx-demo.d8.kir.lab`
- Self-service portal: `https://selfservice-awx.d8.kir.lab`

## Argo CD Applications

- `ansible-os-pods`: synced and healthy during last check.
- `demo-platform`: synced and healthy during last check.

## DVP Resources

Namespace: `demo-prod`

- `VirtualImage/demo-alpine-cloud`: `Ready`
- `VirtualDisk/postgres-vm-root`: `Ready`, `256Mi`
- `VirtualMachine/postgres-vm`: `Running`, `1` core, `coreFraction: 5%`, `512Mi`, IP `10.77.111.5`
- `qemu-guest-agent`: installed and started by AWX bootstrap; DVP reported `AgentReady=True` during last check.
- Golden image source import:
  - `VirtualImage/alpine-base-3-23-v1`: `Ready`, imported from URL in Git.
  - `ClusterVirtualImage/alpine-base-3-23-v1`: `Ready`, imported from URL in Git and used by self-service tenant VMs.
  - `VirtualDisk/golden-builder-root`: `WaitForFirstConsumer` with `k8nfs`; expected while `golden-builder-vm` is stopped.
  - `VirtualMachine/golden-builder-vm`: `Stopped`, `runPolicy: Manual`, minimal resources, IP lease `10.77.111.6`.

## Kubernetes Demo Resources

- `demo-prod/demo-app`: scaled to `4` replicas during scenario 02.
- `customer-a`: tenant namespace exists with quota, limit range, RBAC and starter workload.
- `dev-alice-001`: self-service example namespace exists; `demo-app` is available, ingress host is `dev-alice-001.example.local`, `dev-alice-001-vm` is `Running` with `1` core, `coreFraction: 5%`, `512Mi`, IP `10.77.111.7`.
- `dev-alice-koroleva-demo-7266`: created through the self-service portal backend test; app-only profile is available with ingress `dev-alice-koroleva-demo-7266.d8.kir.lab`.
- `self-service-portal`: portal namespace exists; `self-service-portal` and `self-service-portal-dex-authenticator` deployments are `1/1`; certificate `self-service-portal` is `Ready`; portal and DexAuthenticator ingresses expose ports `80,443`.
- `demo-os`: contains pod-only AWX/Argo demo nodes `ol-node-1` and `ol-node-2`.

## Dex Demo Users

- `alice-koroleva`, `alice.koroleva@demo.local`, group `payments-devs`
- `boris-smirnov`, `boris.smirnov@demo.local`, group `analytics-devs`
- `marina-volkova`, `marina.volkova@demo.local`, group `qa-devs`

Passwords are stored locally in `local/self-service-demo-users.md` and are not committed to Git.

## AWX State

Existing useful objects:

- Project: `Gitea demo repo`
- Job Template: `Configure OS pods`
- Inventory: `Demo OS pods`
- Job Template: `Bootstrap DVP VM`
- Inventory: `DVP VMs`
- Host: `postgres-vm`, `ansible_host: 10.77.111.5`
- Credential: `dvp-vm-ssh`

Recent AWX result:

- `Bootstrap DVP VM` succeeded after playbook fixes for Alpine/OpenRC.

## Important Implementation Notes

- `demo-platform` currently uses plain YAML/Kustomize. Some scenarios require changing both `values.yaml` and the actual manifest because `values.yaml` is not yet wired into templating.
- For scenario 02 scale, both `gitops/environments/prod/values.yaml` and `gitops/environments/prod/demo-app.yaml` must be kept aligned.
- For scenario 04 VM resize, both `gitops/environments/prod/values.yaml` and `gitops/environments/prod/dvp-postgres-vm.yaml` must be kept aligned.
- Argo CD in the cluster reads from Gitea, not GitHub. For live demos, push to `dkp-gitea` as well as `origin`.
- Avoid force-push to Gitea unless explicitly approved. Gitea may contain UI commits from live demos.

## Recent Fixes

- Added real minimal DVP VM manifest.
- Added `demo-platform` Application.
- Refreshed Russian documentation.
- Added AWX VM bootstrap inventory/template and validated SSH from AWX to VM.
- Added `qemu-guest-agent` installation and service startup for Alpine/OpenRC VM bootstrap.
- Added `docs/STATUS.md` and `docs/NEXT_STEPS.md` as lightweight repo context files.
- Documented the context-maintenance rule in both README files.
- Added golden image management scenario artifacts:
  - source `VirtualImage` imported from an external URL in Git;
  - builder `VirtualDisk` and manual `golden-builder-vm`;
  - AWX playbooks `prepare-golden-image.yml` and `validate-golden-image.yml`;
  - scenario `scenarios/08-golden-image-management.md`.
- Added a live demo talk plan to `scenarios/08-golden-image-management.md` and a short golden image talk track to `docs/demo-talk-track.ru.md`.
- Added self-service environment request scenario artifacts:
  - approved profiles under `gitops/self-service/catalog/`;
  - example request `gitops/self-service/requests/dev-alice-001.yaml`;
  - generated example `gitops/self-service/generated/dev-alice-001/`;
  - static web UI under `self-service-ui/`;
  - scenario `scenarios/09-self-service-environment-request.md`;
  - documentation `docs/self-service.ru.md`.
- Fixed self-service DVP image handling by adding approved `ClusterVirtualImage/alpine-base-3-23-v1`.
- Changed the self-service VM example to `runPolicy: AlwaysOn` with minimal resources and cloud-init installation of `qemu-guest-agent`.
- Added Dex-protected self-service portal:
  - `gitops/self-service/portal/` with backend, Deployment, Service, Ingress, DexAuthenticator and RBAC;
  - `docs/self-service-portal.ru.md`;
  - `scenarios/10-self-service-portal.md`;
  - three live Dex demo users and groups;
  - live Kubernetes Secret `self-service-portal-gitea` for Gitea API access.
- Portal backend direct-header test passed and created `dev-alice-koroleva-demo-7266`; Gitea commits were pulled back locally and pushed to GitHub.
- Fixed portal browser login 403 caused by DexAuthenticator CSRF cookie loss on callback:
  - added `cert-manager.io/Certificate` for `selfservice-awx.d8.kir.lab`;
  - enabled TLS on portal ingress;
  - set `applicationIngressCertificateSecretName` on `DexAuthenticator`;
  - changed portal URL documentation from HTTP to HTTPS.

## Pending Validation

- Golden image scenario 08 first phase is live-validated: source image import is `Ready`, builder VM exists in `Manual`/`Stopped`.
- Full golden image customization is not yet executed. Next validation requires starting `golden-builder-vm`, adding it to AWX inventory as `golden_builder`, running `prepare-golden-image.yml`, then `validate-golden-image.yml`.
- Self-service scenario 09 first live validation passed: Argo CD `demo-platform` is `Synced/Healthy`, app resources are ready, `ClusterVirtualImage` is `Ready`, `VirtualDisk/dev-alice-001-vm-root` is `Ready`, `VirtualMachine/dev-alice-001-vm` is `Running`.
- Self-service portal scenario 10 infrastructure is live-validated: Argo CD `demo-platform` is `Synced/Healthy`, certificate is `Ready`, DexAuthenticator redirects unauthenticated HTTPS traffic to `/dex-authenticator/sign_in`, portal pod is ready, backend can create an app-only environment in Gitea. Logs show successful browser authentication for `alice.koroleva@demo.local` after the TLS fix.

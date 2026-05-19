# Use cases and demo scenario

## Use cases

### 1. GitOps delivery of compute resources

An engineer changes Kubernetes manifests in Git. Argo CD detects the change and reconciles the cluster. In this demo, the resources are two Linux pods. In a DVP/KubeVirt environment, the same role can be played by `VirtualMachine` and related CRDs.

Value: the desired infrastructure state is reviewable, versioned and recoverable.

### 2. OS configuration after resource delivery

After Argo CD creates the workloads, AWX runs an Ansible job against them over SSH. The playbook writes a marker file and installs a package.

Value: Kubernetes object lifecycle and guest OS lifecycle are separated but connected.

### 3. Audit trail across two control planes

Gitea contains the source code for both Kubernetes state and Ansible automation. Argo CD shows the sync status for cluster resources. AWX shows job execution history and per-host results.

Value: operators can explain what changed, where it changed and which tool performed the action.

### 4. DVP/KubeVirt implementation rehearsal

The demo can be used before a DVP/KubeVirt implementation to explain the operating model without requiring a full virtualization platform on a laptop.

Value: stakeholders see the workflow first, then replace demo pods with real VM CRDs in the target environment.

## Demonstration scenario

### Setup

1. Start with a clean Docker Desktop Kubernetes cluster.
2. Run:

   ```bash
   ./scripts/bootstrap.sh
   ```

3. Open:

   - Gitea: `http://localhost:3001`
   - Argo CD: `http://localhost:3000`
   - AWX: `http://localhost:3002`

### Part 1. Show Git as the source of truth

1. Open Gitea.
2. Open repository `codex/demo`.
3. Show:

   - `gitops/demo-manifests/os-nodes.yaml`
   - `awx/os-demo-playbook.yml`

Talking point: one repository contains both declarative Kubernetes state and Ansible automation code.

### Part 2. Show Argo CD managing Kubernetes state

1. Open Argo CD.
2. Open application `ansible-os-pods`.
3. Show `Synced` and `Healthy`.
4. In terminal, run:

   ```bash
   kubectl get pods,svc -n demo-os
   ```

Talking point: Argo CD created and keeps the Linux pods and Services aligned with Git.

### Part 3. Show AWX managing OS state

1. Open AWX.
2. Open job template `Configure OS pods`.
3. Launch the job or run:

   ```bash
   ./scripts/run-demo-job.sh
   ```

4. Show the job output:

   - facts gathered from both hosts;
   - marker file written;
   - package installation task completed;
   - recap with `failed=0`.

Talking point: AWX does not create the Kubernetes objects here. It configures the OS/userspace of workloads that Argo CD delivered.

### Part 4. Verify inside the pods

Run:

```bash
kubectl exec -n demo-os deploy/ol-node-1 -- cat /etc/ansible-managed-by-awx
kubectl exec -n demo-os deploy/ol-node-2 -- cat /etc/ansible-managed-by-awx
```

Expected result:

```text
managed_by=AWX
deployed_by=Argo CD
host=...
kernel=...
```

### Part 5. Explain the DVP/KubeVirt mapping

Replace the demo objects mentally:

| Demo object | DVP/KubeVirt equivalent |
| --- | --- |
| Linux pod Deployment | `VirtualMachine` |
| Container image/bootstrap | `VirtualImage`, cloud-init or Sysprep |
| Kubernetes Service for SSH | VM publishing Service or platform access method |
| AWX SSH target | Guest OS IP/DNS |

Closing message: Argo CD owns declared platform resources; AWX owns guest OS configuration workflows.


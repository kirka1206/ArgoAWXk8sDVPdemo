# AWX Post-Configuration

This directory contains examples for VM post-configuration after Argo CD applies Kubernetes or DVP resources.

Do not store real AWX tokens in Git. Copy `secrets/awx-token.example.yaml`, replace the dummy values outside the repository, and apply the real Secret through your secure delivery process.

Example flow:

```bash
kubectl apply -f gitops/awx/secrets/awx-token.example.yaml
kubectl apply -f gitops/awx/hooks/awx-postsync-job.yaml
```

Before production use, replace:

- `https://awx.example.local`
- `demo-token-replace-me`
- `replace-with-template-id`

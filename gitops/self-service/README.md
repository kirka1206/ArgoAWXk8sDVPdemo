# Self-Service Environments

This directory models controlled self-service provisioning.

Developers do not edit raw Kubernetes or DVP manifests directly. They create an `EnvironmentRequest` that selects one approved profile from `catalog/`.

Flow:

1. Developer creates a request in `requests/`.
2. Platform automation validates the request against `catalog/`.
3. Platform automation renders manifests into `generated/<request-name>/`.
4. Argo CD applies generated manifests.
5. AWX performs post-configuration and validation when the selected profile requires it.
6. The developer receives namespace, endpoints and credential retrieval instructions.

The static web UI in `self-service-ui/` helps generate the same request YAML. It is not a replacement for GitOps.

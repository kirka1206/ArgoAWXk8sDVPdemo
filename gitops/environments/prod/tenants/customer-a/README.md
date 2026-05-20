# customer-a Tenant

This directory demonstrates self-service tenant provisioning through Git.

Adding the directory to the environment repository models a platform-team approved onboarding flow:

- namespace is created from Git;
- quota and limit range are applied from Git;
- RBAC is standardized;
- a starter workload is deployed;
- an optional VM manifest is kept as an adaptable DVP example.

Before applying `vm.yaml`, replace the placeholder API with the actual DVP CRD schema used in the target cluster.

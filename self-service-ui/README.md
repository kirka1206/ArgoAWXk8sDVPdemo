# Self-Service Web UI

Static one-page helper for scenario 09.

It does not create Kubernetes or DVP resources directly. It generates an `EnvironmentRequest` YAML and Git commands. The request must still go through Git, review/merge, Argo CD sync and optional AWX post-configuration.

Open locally:

```bash
open self-service-ui/index.html
```

Or serve it from any static web server.

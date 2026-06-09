# Practicum Environment Requests

Place one JSON-formatted YAML document per request in this directory. JSON is
valid YAML and lets the in-cluster controller validate requests without adding
runtime parser dependencies.

The portal writes the same document automatically. Developers do not commit
generated Kubernetes or DVP resources.

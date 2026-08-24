# Kubernetes sidecar

`voicemd-sidecar.yaml` demonstrates a same-pod loopback sidecar. Replace image names and deliver the contract through the organization's normal immutable configuration process.

For production, add:

- startup validation against the expected spec/version;
- resource requests/limits;
- network policy;
- immutable ConfigMap or signed artifact deployment;
- contract hash/version telemetry;
- last-known-good or fail-closed behavior.

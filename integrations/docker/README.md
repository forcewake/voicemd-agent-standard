# Docker sidecar

From the repository root:

```bash
docker compose -f integrations/docker/compose.yaml up --build
curl http://127.0.0.1:8765/health
```

The Compose example publishes only on loopback. The reference server has no authentication; do not expose it publicly without a hardened gateway and approved source registry.

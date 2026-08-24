# Docker sidecar

The base image is pinned by multi-platform manifest digest. During a deliberate
dependency update, resolve the current `python:3.12-slim` digest from the Docker
registry, review the upstream image change, update the digest, and rerun the Docker
build-and-health smoke gate. A successful smoke test does not by itself prove that
two image builds are byte-identical. The image build is not claimed to be hermetic
or byte-reproducible: Python runtime dependencies remain range-constrained and are
resolved from external package indexes.

From the repository root:

```bash
docker compose -f integrations/docker/compose.yaml up --build
curl http://127.0.0.1:8765/health
```

The Compose example publishes only on loopback. The reference server has no authentication; do not expose it publicly without a hardened gateway and approved source registry.

The root `.dockerignore` is an allowlist. Only Python package sources and the metadata needed by `pip` enter the Docker build context; repository contracts, release artifacts, local environment files, and Git metadata are excluded.
The `src` allowlist names only Python modules and the three packaged resource
locations; it does not re-allow arbitrary descendants. Final deny rules after
all negations exclude case-insensitive `.env` and `.env.*` files/directories,
all other hidden paths, bytecode, caches, and egg-info at every depth. Keep
those deny rules last: Docker applies the last matching rule.

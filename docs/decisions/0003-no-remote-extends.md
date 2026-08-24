# ADR 0003: Reject implicit remote `extends` in the core implementation

Status: Accepted  
Date: 2026-08-24

## Context

Remote composition is convenient for organization-wide brand rules but creates mutable supply-chain behavior, availability failures, and hidden production changes.

## Decision

The core reference implementation resolves only local filesystem paths. Remote resolution is an extension that requires immutable pinning, integrity checks, explicit trust configuration, cache policy, and failure semantics.

## Consequences

- Reproducible builds and simpler threat model.
- Shared contracts must be vendored, packaged, or distributed through controlled build tooling.

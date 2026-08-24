# ADR 0004: Voice contracts have communication-only authority

Status: Accepted  
Date: 2026-08-24

## Context

A project instruction file can become an accidental authority-escalation channel. “Personality” prompts often mix style, permissions, safety, identity, and tool rules.

## Decision

VOICE.md may influence only observable communication behavior. It cannot grant tools, change facts, alter permissions, bypass safety, request hidden reasoning, mutate exact quotations, or override required schemas.

## Consequences

- Clear separation from AGENTS.md, safety policy, and tool manifests.
- Harness/application adapters must enforce the boundary even when the file violates it.
- Some teams will need separate `PERSONA.md`, `SAFETY.md`, or capability configuration rather than overloading VOICE.md.

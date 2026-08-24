# ADR 0001: Use Agent Skill progressive disclosure as the default harness adapter

Status: Accepted  
Date: 2026-08-24

## Context

Coding agents frequently perform machine-output tasks for which a communication contract is irrelevant. Always loading a large VOICE.md consumes context and can accidentally influence code or structured output.

## Decision

Use a small harness-native bootstrap plus an on-demand `voice-contract` Agent Skill where the harness supports skills. The skill activates for human-facing natural language and reads/compiles the nearest contract.

## Consequences

- Lower context cost for ordinary coding work.
- Better activation boundary.
- Compatibility depends on skill discovery and trigger quality.
- Harnesses without skills use rules/imports or application injection.

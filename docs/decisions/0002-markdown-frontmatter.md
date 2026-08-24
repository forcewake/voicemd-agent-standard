# ADR 0002: Keep Markdown as the canonical source with optional YAML frontmatter

Status: Accepted  
Date: 2026-08-24

## Context

Pure prose is easy to author but hard to merge and test. Pure JSON/YAML is machine-friendly but poor for examples, contrasts, and narrative guidance.

## Decision

Use UTF-8 Markdown with optional YAML frontmatter. Plain Markdown is valid L0. Structured levels use frontmatter for deterministic selection and testing while retaining Markdown for nuanced guidance.

## Consequences

- Easy manual adoption.
- Schema applies only to frontmatter.
- Free-form body remains a prompt-injection/trust consideration.
- Implementations need both a YAML parser and Markdown-preserving behavior for full support.

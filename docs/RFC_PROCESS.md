# RFC process

Use an RFC for:

- a new core field;
- changed discovery or merge semantics;
- changed authority or activation behavior;
- new required conformance behavior;
- a breaking schema change;
- a standardized provider envelope;
- governance changes.

## Template

Create `rfcs/NNNN-short-name.md` with:

```md
# RFC NNNN: Title

Status: Draft
Authors:
Created:
Target format version:

## Summary
## Motivation
## Non-goals
## Detailed design
## Security and authority impact
## Compatibility
## Alternatives
## Migration
## Test and conformance plan
## Unresolved questions
```

## Lifecycle

1. **Draft:** author gathers implementation feedback.
2. **Review:** maintainers open a defined review period.
3. **Accepted:** semantics are approved but may await implementation.
4. **Implemented:** schema, reference code, docs, tests, and migration are merged.
5. **Rejected or withdrawn:** rationale remains in the repository.
6. **Superseded:** a newer RFC replaces it.

No RFC is complete without a conformance/test plan.

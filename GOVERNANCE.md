# Governance

VoiceMD begins as a maintainer-led independent draft. The goal is a transparent, vendor-neutral specification rather than control by a model provider, agency, or single commercial product.

## Roles

- **Maintainers** merge changes, publish drafts, and manage releases.
- **Editors** maintain normative text and schemas.
- **Implementers** maintain reference implementations and conformance tools.
- **Contributors** submit issues, examples, tests, and proposals.

## Decision process

1. Non-breaking clarifications may be merged through normal review.
2. New fields or semantic changes require an RFC under `docs/RFC_PROCESS.md`.
3. Breaking changes require a new format version and migration notes.
4. Security fixes may be embargoed until a patched release is available.
5. Vendor-specific convenience must not weaken provider neutrality or the authority boundary.

## Future steering group

Before a 1.0 release, governance should move to at least three independent maintainers from different organizations. No organization should control more than half of voting seats.

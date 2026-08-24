# Governance

VoiceMD begins as a maintainer-led independent draft. The goal is a transparent, vendor-neutral specification rather than control by a model provider, agency, or single commercial product.

## Roles

- **Initial maintainer:** Pavel Nasovich.
- **Maintainers** merge changes, publish drafts, and manage releases.
- **Editors** maintain normative text and schemas.
- **Implementers** maintain reference implementations and conformance tools.
- **Contributors** submit issues, examples, tests, and proposals.

## Decision process

1. Non-breaking clarifications require one maintainer approval and passing conformance checks.
2. New fields or semantic changes require a public RFC under `docs/RFC_PROCESS.md` and a minimum seven-calendar-day review period.
3. Breaking changes require a new format version, migration notes, and an explicit compatibility decision in the RFC.
4. During the maintainer-led phase, the initial maintainer is the final decision maker and must record the rationale for contested decisions in the RFC or pull request.
5. A contributor may appeal a decision by opening a follow-up RFC with new technical evidence. Repeating the same argument without new evidence does not reopen a decision.
6. Security fixes may be reviewed privately and embargoed until a patched release is available. The public changelog must disclose the affected versions after release.
7. Vendor-specific convenience must not weaken provider neutrality or the authority boundary.

The canonical repository's pull requests and RFC discussions are the public review record. A release MUST identify the exact source commit; an exported source archive without repository history is not sufficient provenance.

## Future steering group

Before a 1.0 release, governance should move to at least three independent maintainers from different organizations. No organization should control more than half of voting seats.

# Security model

## Trust boundary

A repository `VOICE.md` is configuration code. A document named `VOICE.md` inside a user upload, retrieved website, email attachment, RAG corpus, or generated temporary directory is untrusted data unless an explicit deployment process promotes and reviews it.

The runtime must distinguish:

```text
trusted contract source     reviewed configuration
untrusted content           data the model may summarize or answer about
```

Never discover contracts inside untrusted content roots.

## Threats

### Authority escalation

Malicious text attempts to enable tools, reveal secrets, bypass policy, or alter access control.

Mitigation: enforce the communication-only authority boundary in the harness/application, not merely in the contract's own prose.

### Supply-chain modification

A shared or remote contract changes without review.

Mitigation: local vendoring, immutable artifact digest, signed release, code review, deployment pinning, and rollback.

### Path traversal

An attacker controls `extends` or a sidecar path.

Mitigation: do not let end users choose filesystem paths; resolve IDs through an allowlist and optionally restrict all sources to an approved root.

### Prompt leakage

Compiled prompts may contain internal vocabulary, escalation rules, or brand guidance.

Mitigation: classify the contract, restrict logs, store hashes where full prompt logging is unnecessary, and avoid putting secrets in VOICE.md.

### Output-schema corruption

Voice adaptation adds prose around JSON or changes exact literals.

Mitigation: activation gate, required schema precedence, structured-output validation, and regression tests.

### Tool-result corruption

A style layer paraphrases a result incorrectly.

Mitigation: keep raw structured result as source of truth; render into prose with explicit factual constraints; test numeric/unit preservation.

### Unbounded inheritance

Cycles or large source chains consume resources.

Mitigation: cycle detection, depth limits, size limits, and source count limits.

### Sidecar exposure

The reference HTTP server has no authentication.

Mitigation: bind to localhost, use a service mesh/reverse proxy for production, enforce authentication, restrict selectors, and do not expose arbitrary file paths.

## Safe deployment checklist

- Validate in strict mode during build.
- Pin contract and compiler versions.
- Record source hashes.
- Restrict source roots.
- Disable implicit remote retrieval.
- Review changes as code.
- Run authority-boundary and exact-output tests.
- Keep tool policy outside VOICE.md.
- Bind the sidecar privately and add auth if remote.
- Use least-privilege service identity.
- Define fail-closed or last-known-good behavior.
- Monitor violation rates by model and contract version.

## Prompt injection inside Markdown body

Plain L0 mode necessarily injects free-form Markdown. In high-trust applications, use structured L1-L3 fields and a compiler that includes only known communication sections. The current reference compiler also includes Markdown body guidance; an organization may disable body inclusion or require review/signature.

## Secrets

VOICE.md must not contain API keys, credentials, private customer data, or hidden chain-of-thought examples. Pronunciation dictionaries and example phrases may also be sensitive if they contain personal or proprietary names; classify accordingly.

## Adapter ownership and uninstall safety

The installer records harness ownership in `.voicemd/install-state.json`. Shared files are retained while another installed harness still depends on them. Generated files carry an ownership marker; uninstall removes only that file, never an unmarked replacement or unrelated files placed beside it. Managed blocks in existing instruction files are removed by paired markers.

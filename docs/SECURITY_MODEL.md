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

Mitigation: do not let end users choose filesystem paths; resolve IDs through an allowlist and restrict all sources to an approved root. The reference loader resolves every explicit, discovered, and inherited source to its canonical target before checking containment. Symlinks cannot cross that boundary. `.env` and `.env.*` path components are rejected before and after resolution.

`load_contract(..., allowed_source_root=...)` and `load_voice(..., allowed_source_root=...)` set one mandatory boundary for every active source. A global contract outside that boundary is rejected; use `include_global=False` when loading a project-only contract. Without an explicit boundary, automatic discovery uses the resolved project root and global configuration directory as separate trusted roots. Operator-selected paths use `VOICE_MD_ROOT`, the nearest lexical project marker, or otherwise the selected path's resolved parent. This preserves reviewed `../shared.md` inheritance inside a project while a file or directory symlink still cannot widen the boundary to its target directory. Pass a broader explicit root only for reviewed contracts that intentionally inherit from another directory.

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

Mitigation: cycle detection, depth limits, per-file and aggregate byte limits, source count limits, YAML syntax/alias/expanded-node budgets, and bounded selected-context expansion. The reference defaults are 1 MiB per source, 4 MiB and 64 unique sources across one load, 20,000 YAML nodes after alias expansion and 100 alias references per source, and 256 selectable contexts. Every expanded mapping key and value is charged, including repeated alias occurrences. Applications can lower source/YAML limits through `load_contract` or `load_voice`; limits must be positive integers. Duplicate canonical sources in an inheritance DAG consume the aggregate byte/source budget once.

### Sidecar exposure

The reference HTTP server has no authentication.

Mitigation: bind to localhost, use a service mesh/reverse proxy for production, enforce authentication, restrict selectors, and do not expose arbitrary file paths.

### Provider transport and credential forwarding

An OpenAI-compatible endpoint can be misconfigured as plaintext HTTP or redirect a
credentialed request to another origin. The reference adapter therefore requires
HTTPS whenever a bearer token is present and never follows redirects. Without a
credential it permits HTTP only for numeric loopback addresses or `localhost`,
unless a trusted operator explicitly opts into non-loopback plaintext development
traffic. Endpoint URLs containing user information, queries, or fragments are
rejected.

## Safe deployment checklist

- Validate in strict mode during build.
- Pin contract and compiler versions.
- Record source hashes.
- Restrict source roots.
- Lower source and YAML budgets for multi-tenant or latency-sensitive services.
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

The installer records target ownership and SHA-256 hashes in
`.voicemd/install-state.json`. Shared files are retained while another installed
harness still depends on them. A marker identifies the artifact type; the recorded
hash proves which exact generated file or managed block VoiceMD owns. Reinstall
refuses to overwrite modified owned content. Uninstall preserves modified content
as `modified-retained` and relinquishes ownership.

Installer paths and every existing parent below the resolved root must not be
symlinks. All artifacts are preflighted before mutation. Writes use same-directory
temporary files plus atomic replacement, and a failed multi-file transaction
restores prior bytes and removes newly created files. These checks prevent the
known file- and directory-symlink escapes and ordinary partial installs; they are
not a substitute for excluding concurrent hostile filesystem mutation by another
process.

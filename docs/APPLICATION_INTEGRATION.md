# Application integration

## Recommended pattern

Keep base agent instructions and communication behavior separate:

```python
base = "You are the incident analysis agent. Use only approved tools."
voice = compile_voice(profile="incident_chat")
messages = [
    {"role": "system", "content": base},
    {"role": "system", "content": voice},
    {"role": "user", "content": user_input},
]
```

Some APIs distinguish system and developer roles. Put operational authority, safety, tool policy, and task instructions in the higher-priority layer. Put compiled VOICE.md guidance in the lower applicable instruction layer. Do not use VOICE.md as the only system prompt.

## Explicit activation

Use application metadata to determine whether voice applies:

```python
from voicemd import compile_voice, decide_activation, load_voice

contract = load_voice(path="VOICE.md")
decision = decide_activation(
    contract,
    request.output_kind,
    exact_output=request.exact_output,
    enabled=request.voice_enabled,
    explicit=request.voice_explicit,
    marker_text=request.trusted_voice_marker,
    profile=request.voice_profile,
    audience=request.audience,
    surface=request.surface,
    tone=request.tone,
)

if decision.apply:
    voice_prompt = compile_voice(
        contract,
        profile=request.voice_profile,
        audience=request.audience,
        surface=request.surface,
        tone=request.tone,
    )
else:
    voice_prompt = None
```

The reference decision treats `code`, `patch`, `diff`, `json`, `xml`, `yaml`, `sql`, `tool_call`, `tool_result`, `structured_data`, `exact_quote`, and `raw_data` as machine-facing. Exclusions and exact-output requirements win even when an explicit on marker is present.

## Python API

```python
from voicemd import compile_voice, lint_voice_text

prompt = compile_voice(
    path="./VOICE.md",
    profile="executive_brief",
)

issues = lint_voice_text(
    generated_text,
    path="./VOICE.md",
    profile="executive_brief",
)
```

## HTTP sidecar

Use the sidecar when the application is not written in Python or when one central service owns contract resolution.

```bash
voicemd serve --host 127.0.0.1 --port 8765 --path /contracts/VOICE.md \
  --max-workers 16 --max-body-bytes 262144 --request-timeout-seconds 30
```

The OpenAPI document is `integrations/http/openapi.yaml`.

Production hardening requires:

- authentication and authorization if exposed beyond localhost;
- TLS or private service networking;
- source pinning and an approved contract directory;
- request size and rate limits;
- bounded selectors;
- structured logs without sensitive prompt content;
- readiness tied to successful contract validation;
- last-known-good or fail-closed behavior.

The reference sidecar is deliberately small and local-first; it is not an internet-facing production gateway.

It validates the active contract before binding, revalidates it through `/health`, bounds request-body size and concurrent workers, rejects excess connections, times out slow clients, and returns generic errors. Authentication, TLS, distributed rate limiting, and multi-tenant policy remain deployment responsibilities.

## Multi-tenant applications

Do not accept an arbitrary filesystem path from the end user. Resolve a tenant/agent/profile ID through an allowlisted registry:

```text
tenant_id + agent_id + version
             |
             v
approved contract registry
             |
             v
immutable local bundle / object digest
```

Compile after policy selection, not before it. A tenant-specific voice must not change tool permissions or data access.

## Prompt placement

Recommended order:

1. platform/system safety and identity;
2. task and operational instructions;
3. tool policy and data constraints;
4. active compiled VOICE.md;
5. user content.

The exact role mapping is provider-specific, but the authority order must remain.

## Long contexts and prompt caching

A stable compiled voice prompt is a good candidate for provider prompt caching. Cache by resolved content hash, compiler version, and profile selectors. Do not cache by contract name alone.

For small models, compile compact and enforce a character budget. Remove redundant prose before reducing critical authority or epistemic rules.

## Output linting

Deterministic linting is useful for hard constraints:

- prohibited boilerplate;
- maximum length;
- ASCII-only output;
- emoji policy;
- regex-based required/forbidden patterns.

It cannot reliably score subtle qualities such as “sounds like a principal architect.” Use a model-based evaluator plus human review for those dimensions.

## Streaming

For streaming text, choose one of:

- lint the completed output and log violations;
- buffer short artifacts before display;
- run incremental checks for forbidden literals;
- prevent likely violations through stronger prompt design.

Do not retract already spoken audio merely because a non-safety style lint fails.

## Version rollout

Use staged rollout:

```text
contract draft -> offline eval -> shadow -> small cohort -> full rollout
```

Record both contract version and model version. A behavior regression may come from either.

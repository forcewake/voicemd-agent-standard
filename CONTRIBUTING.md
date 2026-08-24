# Contributing

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
voicemd validate --path templates/full/VOICE.md --strict
```

## Contribution requirements

- Preserve the authority boundary between communication behavior and agent permissions/safety.
- Add tests for semantic or compiler changes.
- Update `SPECIFICATION.md`, schema, templates, and migration notes together when a field changes.
- Use official primary documentation for harness compatibility claims.
- Do not claim native vendor support when an integration uses a generic skill, rule, import, or prompt.
- Keep local-model examples runnable without a specific paid provider where practical.

Normative changes require an RFC as described in `docs/RFC_PROCESS.md`.

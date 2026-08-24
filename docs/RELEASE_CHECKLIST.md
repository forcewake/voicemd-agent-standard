# Release checklist

- [ ] Update draft/spec/package versions consistently.
- [ ] Run `pytest`.
- [ ] Run strict validation on all structured templates.
- [ ] Regenerate compiled examples.
- [ ] Build sdist and wheel.
- [ ] Install wheel into a clean virtual environment.
- [ ] Run CLI smoke tests from the installed wheel.
- [ ] Test adapter installation and uninstall in a temporary repository.
- [ ] Recheck official harness documentation and update compatibility date.
- [ ] Recheck NVIDIA VoiceChat API constraints and model card.
- [ ] Run security regression cases.
- [ ] Review schema compatibility and migration notes.
- [ ] Update changelog.
- [ ] Create checksums for release artifacts.
- [ ] Tag the exact commit.

from pathlib import Path

from voicemd.contract import load_contract
from voicemd.linter import lint_text


def test_linter(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
lexicon:
  forbidden: [Absolutely]
formatting:
  emoji: never
response:
  max_words: 3
rules:
  - id: no-hype
    pattern: "(?i)game-changing"
    assert: must_not_match
    severity: error
    message: No hype.
---
""",
        encoding="utf-8",
    )
    contract = load_contract(paths=[path])
    issues = lint_text(contract, "Absolutely game-changing response here 😀")
    ids = {issue.rule_id for issue in issues}
    assert {"lexicon.forbidden", "formatting.emoji", "response.max_words", "no-hype"} <= ids

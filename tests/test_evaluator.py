from pathlib import Path

from voicemd.contract import load_contract
from voicemd.evaluator import run_cases


def test_inline_case(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
tests:
  - id: one
    response: "Direct answer."
    assertions:
      must_contain: [Direct]
      max_words: 3
---
""",
        encoding="utf-8",
    )
    result = run_cases(load_contract(paths=[path]))[0]
    assert result.passed


def test_supplied_empty_response_is_evaluated_not_replaced(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
tests:
  - id: empty
    response: fallback
    assertions:
      must_contain: [fallback]
---
""",
        encoding="utf-8",
    )
    contract = load_contract(paths=[path])
    result = run_cases(contract, responses={"empty": ""})[0]
    assert not result.passed
    assert "missing required phrase" in result.failures[0]

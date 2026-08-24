from pathlib import Path

import pytest

from voicemd.contract import load_contract
from voicemd.evaluator import load_responses, run_cases


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


def test_missing_response_is_not_a_vacuous_pass(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
tests:
  - id: missing
    assertions:
      must_contain: [answer]
---
""",
        encoding="utf-8",
    )
    result = run_cases(load_contract(paths=[path]))[0]
    assert result.skipped
    assert not result.passed
    assert result.failures == ["no response supplied"]


def test_response_loader_preserves_empty_string_and_rejects_duplicates(tmp_path: Path):
    responses = tmp_path / "responses.jsonl"
    responses.write_text('{"id":"one","response":""}\n', encoding="utf-8")
    assert load_responses(responses) == {"one": ""}

    responses.write_text(
        '{"id":"one","response":"first"}\n'
        '{"id":"one","response":"second"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate response id"):
        load_responses(responses)


def test_runner_rejects_unknown_or_vacuous_assertions(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Test
tests:
  - id: unknown
    response: wrong
    assertions:
      exact_text: expected
  - id: vacuous
    response: anything
    assertions:
      must_contain: []
---
''',
        encoding="utf-8",
    )
    unknown, vacuous = run_cases(load_contract(paths=[path]))
    assert not unknown.passed
    assert unknown.failures == [
        "unsupported assertions: exact_text",
        "no supported effective assertion",
    ]
    assert not vacuous.passed
    assert vacuous.failures == ["no supported effective assertion"]


def test_runner_rejects_string_instead_of_phrase_array(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Test
tests:
  - id: invalid-list
    response: a
    assertions:
      must_contain: abc
---
''',
        encoding="utf-8",
    )
    result = run_cases(load_contract(paths=[path]))[0]
    assert not result.passed
    assert "must_contain must be an array of strings" in result.failures


def test_response_loader_rejects_non_finite_json(tmp_path: Path):
    responses = tmp_path / "responses.jsonl"
    responses.write_text('{"id":"one","response":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        load_responses(responses)

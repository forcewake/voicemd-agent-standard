import json
import os
from pathlib import Path

import pytest

import evals.run_openai_compatible as eval_helpers
from evals.run_openai_compatible import (
    case_boolean,
    load_env_file,
    read_jsonl,
    request_config,
    strict_json_loads,
)
from evals.score_deterministic import assertion_failures
from evals.score_deterministic import main as deterministic_main
from evals.score_model import parse_judgment

ROOT = Path(__file__).resolve().parents[1]


def test_env_file_loads_known_syntax_without_overwriting_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / ".env"
    path.write_text(
        "AZURE_OPENAI_ENDPOINT='https://example.openai.azure.com/'\n"
        'AZURE_OPENAI_API_KEY="secret"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "already-set")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    load_env_file(path)
    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://example.openai.azure.com/"
    assert os.environ["AZURE_OPENAI_API_KEY"] == "already-set"


def test_env_file_has_a_preallocation_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / ".env"
    path.write_bytes(b"A=" + b"x" * 80)
    monkeypatch.setattr(eval_helpers, "MAX_ENV_FILE_BYTES", 32)
    with pytest.raises(ValueError, match="environment file exceeds the size limit"):
        load_env_file(path)


def test_azure_request_uses_deployment_url_and_api_key_header():
    url, headers, payload = request_config(
        provider="azure",
        endpoint="https://example.openai.azure.com/",
        api_key="secret",
        model="ignored",
        deployment="chat deployment",
        api_version="2024-10-21",
        messages=[{"role": "user", "content": "hello"}],
        temperature=None,
        reasoning_effort="medium",
    )
    assert url == (
        "https://example.openai.azure.com/openai/deployments/"
        "chat%20deployment/chat/completions?api-version=2024-10-21"
    )
    assert headers == {"api-key": "secret", "Content-Type": "application/json"}
    assert "model" not in payload
    assert payload["reasoning_effort"] == "medium"


def test_case_reader_rejects_duplicate_ids(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"same","prompt":"one"}\n{"id":"same","prompt":"two"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate case id"):
        list(read_jsonl(path))


def test_case_reader_enforces_line_file_and_record_limits_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    oversized_record = tmp_path / "oversized.jsonl"
    oversized_record.write_bytes(b'{"id":"one","prompt":"' + b"x" * 80 + b'"}\n')
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_LINE_BYTES", 64)
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_FILE_BYTES", 1024)
    with pytest.raises(ValueError, match="record exceeds the size limit"):
        list(read_jsonl(oversized_record))

    oversized_file = tmp_path / "oversized-file.jsonl"
    oversized_file.write_bytes(b'{"id":"one","prompt":"one"}\n')
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_LINE_BYTES", 1024)
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_FILE_BYTES", 16)
    with pytest.raises(ValueError, match="file exceeds the size limit"):
        list(read_jsonl(oversized_file))

    too_many_records = tmp_path / "too-many.jsonl"
    too_many_records.write_bytes(b'{"id":"one","prompt":"one"}\n{"id":"two","prompt":"two"}\n')
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_FILE_BYTES", 1024)
    monkeypatch.setattr(eval_helpers, "MAX_JSONL_RECORDS", 1)
    with pytest.raises(ValueError, match="record count exceeds the limit"):
        list(read_jsonl(too_many_records))


def test_case_controls_require_real_booleans():
    assert case_boolean({"id": "case"}, "voice_enabled", True)
    with pytest.raises(TypeError, match="must be a boolean"):
        case_boolean({"id": "case", "voice_enabled": "false"}, "voice_enabled", True)


def test_deterministic_eval_assertions_cover_exact_json_and_text():
    assert not assertion_failures(
        {"assertions": {"json_equals": {"status": "ok"}}}, '{"status":"ok"}'
    )
    assert assertion_failures({"assertions": {"json_equals": {"status": "ok"}}}, "```json\n{}\n```")
    assert not assertion_failures({"assertions": {"exact_text": "verbatim"}}, "verbatim")
    assert assertion_failures({"assertions": {"exact_text": "verbatim"}}, "Verbatim")
    assert not assertion_failures(
        {"assertions": {"must_contain_any": [["no data loss", "no data has been lost"]]}},
        "No data has been lost.",
    )
    assert not assertion_failures({"assertions": {"max_words": 0}}, "")


def test_model_judgment_requires_exact_dimensions_and_bounded_scores():
    text = json.dumps(
        {
            "scores": {"authority": 5, "specificity": 4},
            "critical_failures": [],
            "rationale": "The response preserves authority and is concrete.",
        }
    )
    result = parse_judgment(text, ["authority", "specificity"])
    assert result["scores"] == {"authority": 5, "specificity": 4}
    with pytest.raises(ValueError, match="every rubric dimension"):
        parse_judgment(text, ["authority", "specificity", "format"])
    with pytest.raises(ValueError, match="exactly scores"):
        parse_judgment(
            json.dumps({**json.loads(text), "unexpected": True}),
            ["authority", "specificity"],
        )


def test_eval_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="non-finite"):
        strict_json_loads('{"value": NaN}')
    assert assertion_failures(
        {"assertions": {"json_equals": {"value": None}}},
        '{"value": NaN}',
    ) == ["response is not exactly one valid JSON value"]


def test_deterministic_scorer_rejects_empty_or_partial_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"id":"one","prompt":"one","assertions":{"must_contain":["one"]}}\n'
        '{"id":"two","prompt":"two","assertions":{"must_contain":["two"]}}\n',
        encoding="utf-8",
    )
    results = tmp_path / "results.jsonl"
    results.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["score_deterministic.py", "--cases", str(cases), "--results", str(results)],
    )
    with pytest.raises(ValueError, match="contains no evaluation cases"):
        deterministic_main()

    results.write_text(
        '{"id":"one","prompt":"one","response":"one"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing result IDs"):
        deterministic_main()


def test_checked_in_a2_azure_evidence_remains_complete_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
):
    cases = ROOT / "evals" / "prompts.jsonl"
    evidence = ROOT / "evals" / "evidence" / "0.1.0a2-azure-results.jsonl"
    records = list(read_jsonl(evidence))
    assert len(records) == len(list(read_jsonl(cases))) == 14
    forbidden_fields = {
        "api_key",
        "authorization",
        "azure_endpoint",
        "base_url",
        "endpoint",
    }
    assert all(not (forbidden_fields & set(record)) for record in records)
    assert {record["provider"] for record in records} == {"azure"}
    assert {record["voicemd_version"] for record in records} == {"0.1.0a2"}

    # This checked-in corpus is immutable a2 evidence, not a claim that a3
    # reproduced the same provider outputs. Validate it under its recorded
    # implementation version while current a3 voice evidence remains local.
    monkeypatch.setattr(eval_helpers, "__version__", "0.1.0a2")

    monkeypatch.setattr(
        "sys.argv",
        [
            "score_deterministic.py",
            "--voice",
            str(ROOT / "VOICE.md"),
            "--cases",
            str(cases),
            "--results",
            str(evidence),
        ],
    )
    assert deterministic_main() == 0

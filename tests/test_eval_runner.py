import json
import os
from pathlib import Path

import pytest

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
        '{"id":"same","prompt":"one"}\n'
        '{"id":"same","prompt":"two"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate case id"):
        list(read_jsonl(path))


def test_case_controls_require_real_booleans():
    assert case_boolean({"id": "case"}, "voice_enabled", True)
    with pytest.raises(TypeError, match="must be a boolean"):
        case_boolean({"id": "case", "voice_enabled": "false"}, "voice_enabled", True)


def test_deterministic_eval_assertions_cover_exact_json_and_text():
    assert not assertion_failures(
        {"assertions": {"json_equals": {"status": "ok"}}}, '{"status":"ok"}'
    )
    assert assertion_failures(
        {"assertions": {"json_equals": {"status": "ok"}}}, "```json\n{}\n```"
    )
    assert not assertion_failures(
        {"assertions": {"exact_text": "verbatim"}}, "verbatim"
    )
    assert assertion_failures(
        {"assertions": {"exact_text": "verbatim"}}, "Verbatim"
    )
    assert not assertion_failures(
        {"assertions": {"must_contain_any": [["no data loss", "no data has been lost"]]}},
        "No data has been lost.",
    )


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

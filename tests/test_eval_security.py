import argparse
import copy
import hashlib
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from evals.run_openai_compatible import (
    NoRedirectHandler,
    add_secret_argument_guards,
    call,
    candidate_messages,
    case_boolean,
    corpus_sha256,
    json_sha256,
    request_config,
    validate_endpoint_policy,
    validated_selector_kwargs,
)
from evals.run_openai_compatible import main as candidate_runner_main
from evals.score_deterministic import main as deterministic_score_main
from evals.score_model import main as model_score_main
from evals.score_model import validate_candidate_result
from voicemd import __version__, contract_sha256, decide_activation, load_voice


def _valid_candidate(
    contract: object,
    case: dict[str, object],
    cases: list[dict[str, object]],
) -> dict[str, object]:
    selectors = {"profile": None, "audience": None, "surface": None, "tone": None}
    decision = decide_activation(
        contract,
        case.get("output_kind", "chat"),
        exact_output=case_boolean(case, "exact_output", False),
        enabled=case_boolean(case, "voice_enabled", True),
        explicit=case_boolean(case, "voice_explicit", False),
        marker_text=case.get("marker_text"),
        **selectors,
    )
    messages, voice = candidate_messages(
        contract=contract,
        case=case,
        selectors=selectors,
        compact=False,
        apply_voice=decision.apply,
    )
    response = "Direct response."
    return {
        **case,
        "case_sha256": json_sha256(case),
        "corpus_sha256": corpus_sha256(cases),
        "selectors": selectors,
        "activation": {
            "apply": decision.apply,
            "mode": decision.mode,
            "reason": decision.reason,
        },
        "response": response,
        "provider": "openai-compatible",
        "model": "local-model",
        "api_version": None,
        "endpoint_sha256": "0" * 64,
        "temperature": None,
        "reasoning_effort": None,
        "compact": False,
        "voicemd_version": __version__,
        "contract_sha256": contract_sha256(contract, **selectors),
        "messages_sha256": json_sha256(messages),
        "compiled_prompt_sha256": (
            hashlib.sha256(voice.encode("utf-8")).hexdigest() if voice else None
        ),
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "finish_reason": "stop",
    }


def test_azure_requires_https_before_request_construction():
    with pytest.raises(ValueError, match="Azure OpenAI endpoints must use HTTPS"):
        request_config(
            provider="azure",
            endpoint="http://example.openai.azure.com",
            api_key="secret",
            model="ignored",
            deployment="chat",
            api_version="2024-10-21",
            messages=[{"role": "user", "content": "hello"}],
            temperature=None,
            reasoning_effort=None,
        )


def test_generic_http_is_credential_free_and_fail_closed_by_default():
    validate_endpoint_policy(
        provider="openai-compatible",
        endpoint="http://127.0.0.1:8000/v1",
        api_key="",
    )
    with pytest.raises(ValueError, match="credentials must not be sent over HTTP"):
        validate_endpoint_policy(
            provider="openai-compatible",
            endpoint="http://127.0.0.1:8000/v1",
            api_key="secret",
            allow_insecure_http=True,
        )
    with pytest.raises(ValueError, match="non-loopback HTTP requires"):
        validate_endpoint_policy(
            provider="openai-compatible",
            endpoint="http://model.internal:8000/v1",
            api_key="",
        )
    validate_endpoint_policy(
        provider="openai-compatible",
        endpoint="http://model.internal:8000/v1",
        api_key="",
        allow_insecure_http=True,
    )


def test_transport_requires_a_finite_positive_timeout_before_network():
    with pytest.raises(ValueError, match="timeout must be finite and positive"):
        call(
            provider="openai-compatible",
            endpoint="http://127.0.0.1:8000/v1",
            api_key="",
            model="local-model",
            deployment="",
            api_version="",
            messages=[{"role": "user", "content": "hello"}],
            temperature=None,
            reasoning_effort=None,
            timeout=float("nan"),
        )


def test_eval_selector_provenance_uses_portable_whitespace_set():
    selectors = {
        "profile": None,
        "audience": "\u001c",
        "surface": None,
        "tone": None,
    }
    assert validated_selector_kwargs(selectors, case_id="portable") == selectors

    selectors["audience"] = "\u0085"
    with pytest.raises(TypeError, match="selector provenance"):
        validated_selector_kwargs(selectors, case_id="portable")


@pytest.mark.parametrize(
    ("option", "environment_name"),
    [
        ("--api-key", "VOICEMD_API_KEY"),
        ("--azure-api-key", "AZURE_OPENAI_API_KEY"),
    ],
)
def test_secret_arguments_are_rejected_without_echoing_values(
    option: str,
    environment_name: str,
    capsys: pytest.CaptureFixture[str],
):
    parser = argparse.ArgumentParser()
    add_secret_argument_guards(parser)
    secret = "must-not-appear-in-output"
    with pytest.raises(SystemExit):
        parser.parse_args([option, secret])
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert environment_name in captured.err


def test_redirect_handler_never_creates_a_followup_credentialed_request():
    original = urllib.request.Request(
        "https://source.example/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
    )
    redirected = NoRedirectHandler().redirect_request(
        original,
        None,
        307,
        "Temporary Redirect",
        {},
        "https://target.example/collect",
    )
    assert redirected is None


def test_transport_rejects_redirects_instead_of_following_them():
    class RedirectHandler(BaseHTTPRequestHandler):
        final_hits = 0

        def do_POST(self):
            if self.path == "/final":
                type(self).final_hits += 1
                self.send_response(200)
                self.end_headers()
                return
            self.send_response(307)
            self.send_header("Location", "/final")
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="redirects are not allowed"):
            call(
                provider="openai-compatible",
                endpoint=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="",
                model="local-model",
                deployment="",
                api_version="",
                messages=[{"role": "user", "content": "hello"}],
                temperature=None,
                reasoning_effort=None,
                timeout=2,
            )
        assert RedirectHandler.final_hits == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_candidate_result_is_bound_to_case_corpus_messages_and_response():
    contract = load_voice(path="VOICE.md", include_global=False)
    case = {
        "id": "bound-case",
        "prompt": "Give a direct answer.",
        "assertions": {"must_contain": ["Direct"]},
    }
    cases = [case]
    item = _valid_candidate(contract, case, cases)
    validated = validate_candidate_result(
        item,
        expected_case=case,
        expected_corpus_sha256=corpus_sha256(cases),
        contract=contract,
    )
    assert validated["response"] == "Direct response."
    assert validated["result_sha256"] == json_sha256(item)

    tampered_prompt = copy.deepcopy(item)
    tampered_prompt["prompt"] = "Different prompt."
    with pytest.raises(ValueError, match="does not match corpus fields"):
        validate_candidate_result(
            tampered_prompt,
            expected_case=case,
            expected_corpus_sha256=corpus_sha256(cases),
            contract=contract,
        )

    tampered_messages = copy.deepcopy(item)
    tampered_messages["messages_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="request-message provenance mismatch"):
        validate_candidate_result(
            tampered_messages,
            expected_case=case,
            expected_corpus_sha256=corpus_sha256(cases),
            contract=contract,
        )

    tampered_response = copy.deepcopy(item)
    tampered_response["response"] = "Altered after generation."
    with pytest.raises(ValueError, match="response provenance mismatch"):
        validate_candidate_result(
            tampered_response,
            expected_case=case,
            expected_corpus_sha256=corpus_sha256(cases),
            contract=contract,
        )

    tampered_activation = copy.deepcopy(item)
    tampered_activation["activation"]["apply"] = not item["activation"]["apply"]
    with pytest.raises(ValueError, match="activation provenance mismatch"):
        validate_candidate_result(
            tampered_activation,
            expected_case=case,
            expected_corpus_sha256=corpus_sha256(cases),
            contract=contract,
        )


def test_candidate_result_requires_a_string_response():
    contract = load_voice(path="VOICE.md", include_global=False)
    case = {"id": "string-case", "prompt": "Answer."}
    item = _valid_candidate(contract, case, [case])
    item["response"] = None
    with pytest.raises(TypeError, match="missing response string"):
        validate_candidate_result(
            item,
            expected_case=case,
            expected_corpus_sha256=corpus_sha256([case]),
            contract=contract,
        )


@pytest.mark.parametrize(
    ("tamper", "expected_error"),
    [
        ("case_sha256", "case provenance mismatch"),
        ("corpus_sha256", "corpus provenance mismatch"),
        ("messages_sha256", "request-message provenance mismatch"),
        ("response", "response provenance mismatch"),
        ("activation", "activation provenance mismatch"),
    ],
)
def test_deterministic_scorer_rejects_tampered_candidate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    expected_error: str,
):
    contract = load_voice(path="VOICE.md", include_global=False)
    case = {
        "id": "deterministic-bound",
        "prompt": "Give a direct response.",
        "assertions": {"must_contain": ["Direct"]},
    }
    item = _valid_candidate(contract, case, [case])
    if tamper == "response":
        item["response"] = "Altered after generation."
    elif tamper == "activation":
        item["activation"]["apply"] = not item["activation"]["apply"]
    else:
        item[tamper] = "1" * 64

    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps(item) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "score_deterministic.py",
            "--voice",
            "VOICE.md",
            "--cases",
            str(cases),
            "--results",
            str(results),
        ],
    )

    with pytest.raises(ValueError, match=expected_error):
        deterministic_score_main()


def test_candidate_runner_records_verifiable_provenance_before_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    cases = tmp_path / "cases.jsonl"
    case = {"id": "generated", "prompt": "Give a direct response."}
    cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
    output = tmp_path / "results.jsonl"
    monkeypatch.delenv("VOICEMD_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    def fake_call(**kwargs):
        assert kwargs["api_key"] == ""
        return (
            "Direct response.",
            1,
            {
                "response_id": "mock-response",
                "provider_model": "mock-model-revision",
                "system_fingerprint": None,
                "finish_reason": "stop",
                "content_filter_results": None,
                "prompt_filter_results": None,
                "usage": None,
            },
        )

    monkeypatch.setattr("evals.run_openai_compatible.call", fake_call)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_openai_compatible.py",
            "--no-env-file",
            "--provider",
            "openai-compatible",
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--voice",
            "VOICE.md",
            "--cases",
            str(cases),
            "--output",
            str(output),
        ],
    )
    assert candidate_runner_main() == 0
    item = json.loads(output.read_text(encoding="utf-8"))
    contract = load_voice(path="VOICE.md", include_global=False)
    validated = validate_candidate_result(
        item,
        expected_case=case,
        expected_corpus_sha256=corpus_sha256([case]),
        contract=contract,
    )
    assert validated["response"] == "Direct response."


def test_model_judge_output_is_bound_to_the_exact_candidate_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = load_voice(path="VOICE.md", include_global=False)
    case = {"id": "judge-bound", "prompt": "Give a direct response."}
    item = _valid_candidate(contract, case, [case])
    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps(item) + "\n", encoding="utf-8")
    output = tmp_path / "scores.jsonl"
    monkeypatch.delenv("VOICEMD_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    dimension_ids = [
        "authority_boundary",
        "epistemic_calibration",
        "interaction_behavior",
        "audience_surface_fit",
        "voice_recognizability",
        "specificity",
        "format_and_lexicon",
    ]

    def fake_judge_call(**kwargs):
        evaluation_input = json.loads(kwargs["messages"][1]["content"])
        assert evaluation_input["prompt"] == case["prompt"]
        assert evaluation_input["response"] == item["response"]
        judgment = {
            "scores": {dimension: 5 for dimension in dimension_ids},
            "critical_failures": [],
            "rationale": "The response follows the supplied contract.",
        }
        return (
            json.dumps(judgment),
            1,
            {
                "response_id": "judge-response",
                "provider_model": "judge-revision",
                "system_fingerprint": None,
                "finish_reason": "stop",
                "content_filter_results": None,
                "prompt_filter_results": None,
                "usage": None,
            },
        )

    monkeypatch.setattr("evals.score_model.call", fake_judge_call)
    monkeypatch.setattr(
        "sys.argv",
        [
            "score_model.py",
            "--no-env-file",
            "--provider",
            "openai-compatible",
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--voice",
            "VOICE.md",
            "--cases",
            str(cases),
            "--results",
            str(results),
            "--output",
            str(output),
        ],
    )
    assert model_score_main() == 0
    score = json.loads(output.read_text(encoding="utf-8"))
    assert score["candidate_result_sha256"] == json_sha256(item)
    assert score["candidate_case_sha256"] == json_sha256(case)
    assert score["candidate_corpus_sha256"] == corpus_sha256([case])
    assert score["candidate_response_sha256"] == item["response_sha256"]


def test_model_judge_rejects_partial_corpus_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"id":"one","prompt":"one"}\n{"id":"two","prompt":"two"}\n',
        encoding="utf-8",
    )
    results = tmp_path / "results.jsonl"
    results.write_text('{"id":"one","prompt":"one"}\n', encoding="utf-8")
    output = tmp_path / "scores.jsonl"
    monkeypatch.delenv("VOICEMD_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    def unexpected_network_call(**kwargs):
        raise AssertionError("network call must not occur before corpus validation")

    monkeypatch.setattr("evals.score_model.call", unexpected_network_call)
    monkeypatch.setattr(
        "sys.argv",
        [
            "score_model.py",
            "--no-env-file",
            "--provider",
            "openai-compatible",
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--voice",
            "VOICE.md",
            "--cases",
            str(cases),
            "--results",
            str(results),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="missing result IDs: two"):
        model_score_main()
    assert not output.exists()

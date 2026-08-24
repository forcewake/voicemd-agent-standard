from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from voicemd.api import compile_voice, lint_voice_text
from voicemd.cli import main as cli_main
from voicemd.contract import ContractError, load_contract
from voicemd.linter import MAX_REGEX_INPUT_CHARS, lint_text
from voicemd.model import ResolvedVoiceContract
from voicemd.provenance import source_label
from voicemd.server import create_server
from voicemd.validator import MAX_REGEX_RULES, validate_contract


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _voice(path: Path, *, activation: str = "contextual") -> None:
    path.write_text(
        f'''---
voice_spec: "0.1"
kind: VoiceContract
name: Runtime hardening test
activation:
  mode: {activation}
  include: [chat]
  exclude: [json, code, tool_call]
identity:
  sounds_like: [direct]
---
''',
        encoding="utf-8",
    )


def _start_server(path: Path):
    server = create_server(port=0, path=path, include_global=False, quiet=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread: Thread) -> None:
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def test_sidecar_validates_before_constructing_listening_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    voice = tmp_path / "VOICE.md"
    voice.write_text("---\nname: invalid\n---\n", encoding="utf-8")
    constructed = False

    def fail_if_constructed(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("server bound before contract validation")

    monkeypatch.setattr("voicemd.server.BoundedThreadingHTTPServer", fail_if_constructed)
    with pytest.raises(ContractError):
        create_server(port=0, path=voice, include_global=False, quiet=True)
    assert not constructed


def test_compile_lint_api_and_cli_reject_invalid_selected_contract(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    voice.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Invalid selected contract
identity: {sounds_like: [direct]}
profiles:
  broken:
    overrides:
      response:
        max_words: many
---
''',
        encoding="utf-8",
    )
    contract = load_contract(paths=[voice])
    with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
        compile_voice(contract, profile="broken")
    with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
        lint_voice_text("text", contract, profile="broken")

    common = ["--path", str(voice), "--no-global", "--profile", "broken"]
    assert cli_main(["compile", *common]) == 2
    assert cli_main(["lint", *common, "--text", "text"]) == 2


def test_sidecar_rejects_ambiguous_query_and_hides_json_provenance(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    _voice(voice)
    server, thread = _start_server(voice)
    base = f"http://127.0.0.1:{server.server_port}/v1/voice/prompt"
    try:
        for query in ("compact=TRUE", "compact=true&compact=false", "unknown=value"):
            with pytest.raises(HTTPError) as error:
                urlopen(f"{base}?{query}")
            assert error.value.code == 400
            assert json.load(error.value) == {"error": "invalid_request"}

        with urlopen(f"{base}?format=json&compact=false") as response:
            wrapper = json.load(response)
        compiled = json.loads(wrapper["prompt"])
        assert str(tmp_path) not in json.dumps(compiled)
        assert "provenance" not in compiled
    finally:
        _stop_server(server, thread)


def test_sidecar_lint_body_is_strict_json_with_closed_shape(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    _voice(voice)
    server, thread = _start_server(voice)
    url = f"http://127.0.0.1:{server.server_port}/v1/voice/lint"
    try:
        for body in (b'{"text":"ok","extra":true}', b'{"text":"ok","tone":NaN}'):
            request = Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 400
            assert json.load(error.value) == {"error": "invalid_request"}
    finally:
        _stop_server(server, thread)


def test_lite_activation_casefolds_and_fails_closed():
    lite = _module(Path(__file__).parents[1] / "lite/voice_loader.py", "runtime_lite_loader")
    assert lite.should_apply(" CHAT ")
    assert lite.should_apply("SpEeCh")
    assert not lite.should_apply("custom_humanish_kind")
    assert not lite.should_apply("JSON")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_node_lite_activation_matches_python():
    loader_url = (Path(__file__).parents[1] / "lite/load-voice.mjs").resolve().as_uri()
    script = (
        f'import {{ shouldApply }} from {json.dumps(loader_url)}; '
        "console.log(JSON.stringify(["
        'shouldApply(" CHAT "), shouldApply("custom_humanish_kind"), shouldApply("JSON")'
        "]));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == [True, False, False]


def test_generic_chat_adapter_uses_activation_gate(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    _voice(voice, activation="explicit")
    adapter = _module(
        Path(__file__).parents[1] / "integrations/openai-compatible/chat_completions.py",
        "runtime_chat_completions",
    )

    inactive = adapter.compose_messages("hello", voice_path=voice)
    explicit = adapter.compose_messages("hello", voice_path=voice, voice_explicit=True)
    machine = adapter.compose_messages(
        "return JSON", voice_path=voice, output_kind="JSON", voice_explicit=True
    )
    exact = adapter.compose_messages(
        "exact", voice_path=voice, exact_output=True, voice_explicit=True
    )
    assert [item["role"] for item in inactive] == ["system", "user"]
    assert [item["role"] for item in explicit] == ["system", "system", "user"]
    assert [item["role"] for item in machine] == ["system", "user"]
    assert [item["role"] for item in exact] == ["system", "user"]


def test_provider_integrations_validate_before_disabled_or_exact_decisions(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    voice.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Invalid activation
identity: {sounds_like: [direct]}
activation:
  mode: contextual
  include: [chat]
  exclude: [CHAT]
---
''',
        encoding="utf-8",
    )
    contract = load_contract(paths=[voice])
    middleware = _module(
        Path(__file__).parents[1] / "integrations/python/middleware.py",
        "runtime_fail_closed_middleware",
    )
    adapter = _module(
        Path(__file__).parents[1] / "integrations/openai-compatible/chat_completions.py",
        "runtime_fail_closed_chat_adapter",
    )

    for context in (
        middleware.OutputContext(voice_enabled=False),
        middleware.OutputContext(exact_output=True),
    ):
        with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
            middleware.compose_system_messages("base", context, contract=contract)
    for options in ({"voice_enabled": False}, {"exact_output": True}):
        with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
            adapter.compose_messages("hello", voice_path=voice, **options)


def test_generic_chat_adapter_enforces_transport_policy():
    adapter = _module(
        Path(__file__).parents[1] / "integrations/openai-compatible/chat_completions.py",
        "runtime_chat_transport",
    )

    assert (
        adapter.validate_base_url(
            "http://127.0.0.1:8000/v1/", credentialed=False
        )
        == "http://127.0.0.1:8000/v1"
    )
    assert (
        adapter.validate_base_url("https://api.example.test/v1", credentialed=True)
        == "https://api.example.test/v1"
    )
    with pytest.raises(ValueError, match="require an HTTPS"):
        adapter.validate_base_url(
            "http://127.0.0.1:8000/v1",
            credentialed=True,
            allow_insecure_http=True,
        )
    with pytest.raises(ValueError, match="restricted to loopback"):
        adapter.validate_base_url("http://example.test/v1", credentialed=False)
    assert (
        adapter.validate_base_url(
            "http://example.test/v1",
            credentialed=False,
            allow_insecure_http=True,
        )
        == "http://example.test/v1"
    )
    for invalid in (
        "https://user:secret@example.test/v1",
        "https://example.test/v1?token=secret",
        "https://example.test/v1#fragment",
    ):
        with pytest.raises(ValueError):
            adapter.validate_base_url(invalid, credentialed=False)


def test_activation_and_sidecar_reject_empty_or_invalid_selected_contract(tmp_path: Path):
    from voicemd.activation import decide_activation

    voice = tmp_path / "VOICE.md"
    voice.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Invalid selected activation
identity: {sounds_like: [direct]}
profiles:
  broken:
    overrides:
      response:
        max_words: many
---
''',
        encoding="utf-8",
    )
    contract = load_contract(paths=[voice])
    with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
        decide_activation(contract, "chat", profile="broken")
    with pytest.raises(ContractError, match="selected VOICE.md failed validation"):
        decide_activation(contract, "chat", profile="broken", enabled=False)

    valid = tmp_path / "valid.md"
    _voice(valid)
    server, thread = _start_server(valid)
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"http://127.0.0.1:{server.server_port}/v1/voice/prompt?profile="
            )
        assert error.value.code == 400
        assert json.load(error.value) == {"error": "invalid_request"}
    finally:
        _stop_server(server, thread)


def test_linter_rejects_unsafe_regex_and_bounds_regex_input(tmp_path: Path):
    unsafe = tmp_path / "unsafe.md"
    unsafe.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Unsafe regex
identity: {sounds_like: [direct]}
rules:
  - id: unsafe
    pattern: "(a|aa)+$"
    assert: must_not_match
---
''',
        encoding="utf-8",
    )
    contract = load_contract(paths=[unsafe])
    issues = lint_text(contract, "a" * 100 + "!")
    assert any(issue.rule_id == "unsafe" and "Unsafe rule regex" in issue.message for issue in issues)

    safe = tmp_path / "safe.md"
    safe.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Bounded regex
identity: {sounds_like: [direct]}
rules:
  - id: safe
    pattern: "^forbidden"
    assert: must_not_match
---
''',
        encoding="utf-8",
    )
    issues = lint_text(load_contract(paths=[safe]), "x" * (MAX_REGEX_INPUT_CHARS + 1))
    assert any(issue.rule_id == "runtime.regex_input_limit" for issue in issues)


def test_regex_count_and_aggregate_work_are_bounded_before_matching():
    expensive_pattern = "." * 508 + "[^A]"
    excessive = ResolvedVoiceContract(
        data={
            "voice_spec": "0.1",
            "kind": "VoiceContract",
            "name": "Excessive regex rules",
            "rules": [
                {
                    "id": f"rule-{index}",
                    "pattern": expensive_pattern,
                    "assert": "must_not_match",
                }
                for index in range(MAX_REGEX_RULES + 1)
            ],
        }
    )
    validation = validate_contract(excessive)
    assert not validation.ok
    assert any("regex rule count" in error for error in validation.errors)
    assert any("aggregate regex pattern" in error for error in validation.errors)
    assert any(
        issue.rule_id == "runtime.regex_rule_limit"
        for issue in lint_text(excessive, "A" * MAX_REGEX_INPUT_CHARS)
    )

    one_expensive_rule = ResolvedVoiceContract(
        data={
            "voice_spec": "0.1",
            "kind": "VoiceContract",
            "name": "Bounded regex work",
            "rules": [
                {
                    "id": "expensive",
                    "pattern": expensive_pattern,
                    "assert": "must_not_match",
                }
            ],
        }
    )
    assert validate_contract(one_expensive_rule).ok
    assert any(
        issue.rule_id == "runtime.regex_work_limit"
        for issue in lint_text(one_expensive_rule, "A" * MAX_REGEX_INPUT_CHARS)
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_compact_compilers_preserve_non_voice_edge_whitespace():
    body = " \t\u0085Boundary body\u0085\t "
    expected_suffix = "\u0085Boundary body\u0085"
    contract_data = {
        "voice_spec": "0.1",
        "kind": "VoiceContract",
        "name": "Exact trim",
        "identity": {"sounds_like": ["Direct"]},
    }
    contract = ResolvedVoiceContract(
        data=contract_data,
        bodies=[(Path("VOICE.md"), body)],
    )
    python_output = compile_voice(contract, compact=True)
    assert python_output.endswith(expected_suffix)

    verifier_url = (
        Path(__file__).parents[1]
        / "integrations/typescript/generated/conformance-verifier.js"
    ).resolve().as_uri()
    script = (
        f'import {{ compileCompact }} from {json.dumps(verifier_url)}; '
        f"console.log(JSON.stringify(compileCompact({json.dumps(contract_data)}, "
        f"[{json.dumps(body)}])));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == python_output


def test_source_labels_never_expose_external_absolute_paths(tmp_path: Path):
    root = tmp_path / "root"
    inside = root / "VOICE.md"
    outside = tmp_path / "outside" / "VOICE.md"
    inside.parent.mkdir()
    outside.parent.mkdir()
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    assert source_label(inside, root=root) == "VOICE.md"
    external = source_label(outside, root=root)
    assert external.startswith("external:VOICE.md@sha256:")
    assert str(tmp_path) not in external


def test_nemotron_adapter_rejects_errors_timeouts_and_config_drift():
    adapter = _module(
        Path(__file__).parents[1] / "integrations/nemotron-voicechat/session_update.py",
        "runtime_nemotron_session",
    )
    with pytest.raises(RuntimeError, match="inference_timeout"):
        adapter._strict_event(
            '{"type":"error","error":{"code":"inference_timeout","message":"timeout"}}'
        )

    expected = {"audio": {"input": {}, "output": {}}, "instructions": "voice", "tools": []}
    with pytest.raises(RuntimeError, match="session.instructions"):
        adapter._verify_updated_session(
            {
                "type": "session.updated",
                "session": {"audio": expected["audio"], "instructions": "other", "tools": []},
            },
            expected,
        )

    class SlowWebSocket:
        async def recv(self):
            await asyncio.sleep(0.05)
            return '{"type":"session.created"}'

    with pytest.raises(RuntimeError, match="Timed out"):
        asyncio.run(adapter._receive_event(SlowWebSocket(), timeout_seconds=0.001))


def test_discover_json_empty_result_has_nonzero_exit(tmp_path: Path, capsys):
    assert cli_main(["discover", "--start", str(tmp_path), "--no-global", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert captured.err == ""

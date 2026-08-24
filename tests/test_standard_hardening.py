import json
from pathlib import Path

import pytest

from voicemd.compiler import CompileError, canonical_contract_json, compile_contract
from voicemd.contract import load_contract
from voicemd.discovery import discover_paths
from voicemd.evaluator import run_cases
from voicemd.frontmatter import parse_text
from voicemd.linter import lint_text
from voicemd.model import ResolvedVoiceContract
from voicemd.server import _lint_payload
from voicemd.validator import validate_contract, validate_selected_contract


def _contract(**overrides):
    data = {
        "voice_spec": "0.1",
        "kind": "VoiceContract",
        "name": "Hardening test",
        "identity": {"sounds_like": ["Direct"]},
    }
    data.update(overrides)
    return ResolvedVoiceContract(data=data)


def test_yaml_12_json_scalar_resolution_is_unambiguous():
    metadata, _ = parse_text(
        """\ufeff---
decimal: 12
negative: -2
zero: 0
fraction: 1.25
exponent: 1e3
legacy_octal: 012
underscored: 1_000
sexagesimal: 1:20
leading_plus: +1
leading_dot: .5
trailing_dot: 1.
upper_boolean: TRUE
json_boolean: true
json_null: null
legacy_null: ~
---
"""
    )
    assert metadata == {
        "decimal": 12,
        "negative": -2,
        "zero": 0,
        "fraction": 1.25,
        "exponent": 1000.0,
        "legacy_octal": "012",
        "underscored": "1_000",
        "sexagesimal": "1:20",
        "leading_plus": "+1",
        "leading_dot": ".5",
        "trailing_dot": "1.",
        "upper_boolean": "TRUE",
        "json_boolean": True,
        "json_null": None,
        "legacy_null": "~",
    }


def test_canonical_json_uses_rfc_8785_number_and_utf16_key_rules():
    contract = _contract(metadata={"n": 1.0, "z": -0.0, "\ue000": 1, "\U00010000": 2})
    assert canonical_contract_json(contract) == (
        '{"active":{"audience":null,"profile":null,"surface":null,"tone":null},'
        '"contract":{"identity":{"sounds_like":["Direct"]},"kind":"VoiceContract",'
        '"metadata":{"n":1,"z":0,"𐀀":2,"":1},"name":"Hardening test",'
        '"voice_spec":"0.1"},"markdown_bodies":[]}'
    )


@pytest.mark.parametrize("value", [2**60, "\ud800"])
def test_canonical_json_rejects_values_outside_the_voicemd_jcs_profile(value):
    with pytest.raises(CompileError, match="RFC 8785"):
        canonical_contract_json(_contract(metadata={"unsafe": value}))


def test_known_contract_fields_are_typed_and_unknown_fields_are_governed():
    wrong_type = validate_contract(_contract(response={"max_words": "ten"}))
    assert wrong_type.level == "nonconforming"
    assert any("response.max_words" in error for error in wrong_type.errors)

    permissive = validate_contract(_contract(response={"custom_behavior": "Direct"}))
    assert permissive.ok
    assert any("response.custom_behavior" in warning for warning in permissive.warnings)

    strict = validate_contract(_contract(response={"custom_behavior": "Direct"}), strict=True)
    assert not strict.ok
    assert any("x-*" in error for error in strict.errors)

    extension = validate_contract(_contract(response={"x-example-behavior": {"mode": "direct"}}))
    assert extension.ok
    assert not any("x-example-behavior" in warning for warning in extension.warnings)


def test_every_selected_context_is_revalidated_against_the_full_schema():
    contract = _contract(
        language={"default": "en", "allowed": ["en"]},
        profiles={
            "bad": {
                "overrides": {"language": {"allowed": "en"}},
            }
        },
    )
    whole = validate_contract(contract)
    assert whole.level == "nonconforming"
    assert any("profiles.bad: language.allowed" in error for error in whole.errors)

    selected = validate_selected_contract(contract, profile="bad")
    assert selected.level == "nonconforming"
    assert any("language.allowed" in error for error in selected.errors)
    with pytest.raises(CompileError, match="failed validation"):
        compile_contract(contract, profile="bad")


def test_runtime_revalidates_cross_category_selector_tuples():
    contract = _contract(
        language={"default": "en", "allowed": ["en", "ru"]},
        audiences={"russian": {"language": {"default": "ru"}}},
        surfaces={"english-only": {"language": {"allowed": ["en"]}}},
    )
    assert validate_contract(contract).ok
    selected = validate_selected_contract(
        contract,
        audience="russian",
        surface="english-only",
    )
    assert not selected.ok
    assert any("language.default" in error for error in selected.errors)
    with pytest.raises(CompileError, match="failed validation"):
        compile_contract(
            contract,
            audience="russian",
            surface="english-only",
        )


def test_selector_overlays_may_delete_inherited_fields_with_null():
    contract = _contract(
        response={"max_words": 200, "structure": "answer first"},
        profiles={"short": {"overrides": {"response": {"max_words": None}}}},
    )
    assert validate_contract(contract).ok
    selected = json.loads(compile_contract(contract, profile="short", output_format="json"))
    assert selected["contract"]["response"] == {"structure": "answer first"}


def test_filesystem_selector_overlay_preserves_null_until_selection(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Source selector deletion
identity: {sounds_like: [Direct]}
response: {opening: inherited, max_words: 200}
profiles:
  short:
    overrides:
      response:
        opening: null
        max_words: 40
---
""",
        encoding="utf-8",
    )

    contract = load_contract(paths=[path])
    assert contract.data["profiles"]["short"]["overrides"]["response"]["opening"] is None
    selected = json.loads(compile_contract(contract, profile="short", output_format="json"))
    assert selected["contract"]["response"] == {"max_words": 40}


def test_filesystem_selector_id_tombstone_survives_until_selection(tmp_path: Path):
    base = tmp_path / "base.md"
    base.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Source selector ID deletion
identity: {sounds_like: [Direct]}
rules:
  - {id: inherited, instruction: TOP_INHERITED_RULE}
audiences:
  engineer:
    rules:
      - {id: inherited, instruction: EARLIER_SELECTOR_RULE}
---
""",
        encoding="utf-8",
    )
    override = tmp_path / "override.md"
    override.write_text(
        """---
audiences:
  engineer:
    rules:
      - {id: inherited, disabled: true}
---
""",
        encoding="utf-8",
    )

    contract = load_contract(paths=[base, override])
    assert contract.data["audiences"]["engineer"]["rules"] == [
        {"id": "inherited", "disabled": True}
    ]
    prompt = compile_contract(contract, audience="engineer")
    assert "TOP_INHERITED_RULE" not in prompt
    assert "EARLIER_SELECTOR_RULE" not in prompt


def test_evaluator_skips_disabled_inline_tests():
    contract = _contract(
        tests=[
            {
                "id": "disabled",
                "disabled": True,
                "response": "wrong",
                "assertions": {"must_contain": ["missing"]},
            },
            {
                "id": "enabled",
                "response": "present",
                "assertions": {"must_contain": ["present"]},
            },
        ]
    )
    results = run_cases(contract)
    assert [result.case_id for result in results] == ["enabled"]
    assert results[0].passed


def test_full_and_compact_compilers_omit_disabled_rules():
    contract = _contract(
        rules=[
            {"id": "disabled", "instruction": "NEVER_RENDER_THIS", "disabled": True},
            {"id": "enabled", "instruction": "RENDER_THIS"},
        ]
    )
    full = compile_contract(contract)
    compact = compile_contract(contract, compact=True)
    assert "NEVER_RENDER_THIS" not in full
    assert "NEVER_RENDER_THIS" not in compact
    assert "RENDER_THIS" in full
    assert "RENDER_THIS" in compact


@pytest.mark.parametrize(
    "contract",
    [
        _contract(audiences={" ": {}}),
        _contract(profiles={"": {}}),
        _contract(
            tests=[
                {
                    "id": "empty-selector",
                    "prompt": "Answer.",
                    "profile": " ",
                    "assertions": {"max_words": 2},
                }
            ]
        ),
    ],
)
def test_selector_names_and_references_must_be_nonblank(contract):
    assert not validate_contract(contract).ok


def test_runtime_rejects_empty_selector_arguments():
    with pytest.raises(CompileError, match="non-empty string"):
        compile_contract(_contract(), profile="")


def test_selector_blank_uses_the_portable_unicode_whitespace_set():
    nel = "\u0085"
    zero_width_space = "\u200b"
    control_separator = "\u001c"
    assert not validate_contract(_contract(audiences={nel: {}})).ok

    contract = _contract(
        audiences={
            zero_width_space: {"response": {"opening": "valid"}},
            control_separator: {"response": {"opening": "also valid"}},
        }
    )
    assert validate_contract(contract).ok
    selected = json.loads(
        compile_contract(contract, audience=zero_width_space, output_format="json")
    )
    assert selected["active"]["audience"] == zero_width_space
    assert selected["contract"]["response"]["opening"] == "valid"
    selected = json.loads(
        compile_contract(contract, audience=control_separator, output_format="json")
    )
    assert selected["active"]["audience"] == control_separator
    assert _lint_payload({"text": "ok", "audience": control_separator})["audience"] == (
        control_separator
    )
    with pytest.raises(TypeError, match="non-empty string"):
        _lint_payload({"text": "ok", "audience": nel})


def test_executable_integral_json_numbers_normalize_to_safe_python_integers():
    metadata, _ = parse_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Integral JSON numbers
identity: {sounds_like: [Direct]}
response: {max_words: 1e0, max_sentences: 1.0}
runtime: {max_prompt_chars: 256e0}
tests:
  - id: one-word
    response: one
    assertions: {max_words: 1e0}
---
"""
    )
    contract = ResolvedVoiceContract(data=metadata)
    result = validate_contract(contract)
    assert result.ok
    assert result.level == "L3-testable"
    payload = json.loads(compile_contract(contract, output_format="json"))
    assert payload["contract"]["response"]["max_words"] == 1
    assert isinstance(payload["contract"]["response"]["max_words"], int)
    assert payload["contract"]["runtime"]["max_prompt_chars"] == 256
    assert run_cases(contract)[0].passed
    assert {issue.rule_id for issue in lint_text(contract, "two words. Again.")} >= {
        "response.max_words",
        "response.max_sentences",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("response", {"max_words": 9_007_199_254_740_992}),
        ("response", {"max_sentences": 9_007_199_254_740_992}),
        ("runtime", {"max_prompt_chars": 9_007_199_254_740_992}),
    ],
)
def test_executable_integer_fields_reject_values_above_safe_range(field, value):
    assert not validate_contract(_contract(**{field: value})).ok


def test_assertion_max_words_rejects_values_above_safe_range():
    contract = _contract(
        tests=[
            {
                "id": "unsafe",
                "response": "one",
                "assertions": {"max_words": 9_007_199_254_740_992},
            }
        ]
    )
    assert not validate_contract(contract).ok


def test_recursive_unknown_field_governance_covers_core_nested_shapes():
    contract = _contract(
        audiences={"reader": {"response": {"typo_response": "x"}}},
        profiles={
            "p": {
                "typo_profile": True,
                "overrides": {
                    "rules": [
                        {
                            "id": "rule",
                            "instruction": "Be direct.",
                            "typo_rule": True,
                        }
                    ]
                },
            }
        },
        tests=[
            {
                "id": "case",
                "response": "ok",
                "assertions": {"max_words": 1, "typo_assertion": True},
            }
        ],
    )
    permissive = validate_contract(contract)
    assert permissive.ok
    warnings = "\n".join(permissive.warnings)
    for field in ("typo_response", "typo_profile", "typo_rule", "typo_assertion"):
        assert field in warnings
    strict = validate_contract(contract, strict=True)
    assert not strict.ok
    errors = "\n".join(strict.errors)
    for field in ("typo_response", "typo_profile", "typo_rule", "typo_assertion"):
        assert field in errors


def test_whole_contract_validation_bounds_selectable_context_expansion():
    contract = _contract(audiences={f"audience-{index}": {} for index in range(257)})
    result = validate_contract(contract)
    assert not result.ok
    assert any("257 > 256" in error for error in result.errors)


def test_zero_word_assertion_is_valid_and_executable():
    contract = _contract(
        tests=[
            {
                "id": "empty",
                "response": "",
                "assertions": {"max_words": 0},
            }
        ]
    )
    validation = validate_contract(contract)
    assert validation.ok
    assert validation.level == "L3-testable"
    assert run_cases(contract)[0].passed


def test_regex_flags_are_portable_and_schema_checked():
    valid = validate_contract(
        _contract(
            rules=[
                {
                    "id": "case-insensitive",
                    "pattern": "forbidden",
                    "flags": ["i"],
                    "assert": "must_not_match",
                }
            ]
        )
    )
    assert valid.ok
    assert valid.level == "L3-testable"

    invalid = validate_contract(
        _contract(
            rules=[
                {
                    "id": "provider-specific",
                    "pattern": "forbidden",
                    "flags": ["g"],
                    "assert": "must_not_match",
                }
            ]
        )
    )
    assert invalid.level == "nonconforming"
    assert any("rules.0.flags" in error or "rules[0].flags" in error for error in invalid.errors)


def test_empty_override_shadows_same_directory_voice_file(tmp_path: Path):
    (tmp_path / ".voicemd-root").write_text("", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("Useful base contract.", encoding="utf-8")
    override = tmp_path / "VOICE.override.md"
    override.write_text("", encoding="utf-8")

    paths = discover_paths(tmp_path, include_global=False)
    assert paths == [override.resolve()]
    result = validate_contract(load_contract(paths=paths))
    assert result.level == "nonconforming"
    assert result.errors == ["VOICE.md is empty"]


def test_json_compilation_omits_host_paths_unless_provenance_is_requested(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: JSON paths
identity: {sounds_like: [Direct]}
---
Body.
""",
        encoding="utf-8",
    )
    contract = load_contract(paths=[path])

    portable = compile_contract(contract, output_format="json")
    assert str(tmp_path) not in portable
    assert json.loads(portable)["markdown_bodies"] == ["Body."]

    with_provenance = compile_contract(
        contract,
        output_format="json",
        include_provenance=True,
    )
    assert str(path.resolve()) in with_provenance
    assert "provenance" in json.loads(with_provenance)

import json
from pathlib import Path

import pytest

from voicemd.compiler import CompileError, compile_contract
from voicemd.contract import ContractError, load_contract
from voicemd.frontmatter import FrontmatterError, parse_text
from voicemd.merge import deep_merge
from voicemd.model import ResolvedVoiceContract
from voicemd.validator import regex_safety_error, validate_contract

PROTECTED_AUTHORITY = [
    "facts",
    "safety",
    "legal or compliance requirements",
    "permissions",
    "tool selection",
    "access to secrets",
    "hidden reasoning",
    "exact quotations",
    "required output schemas",
]


def _data(**overrides):
    data = {
        "voice_spec": "0.1",
        "kind": "VoiceContract",
        "name": "Test",
        "identity": {"sounds_like": ["Direct"]},
    }
    data.update(overrides)
    return data


def _contract(**overrides):
    return ResolvedVoiceContract(data=_data(**overrides))


def _strict_authority():
    return {
        "may_control": ["tone"],
        "must_not_control": PROTECTED_AUTHORITY,
        "precedence": "Higher-priority instructions win.",
    }


def test_frontmatter_uses_json_compatible_yaml_12_scalars():
    metadata, _ = parse_text("---\non: off\nyes_value: yes\ntruth: TRUE\ndate: 2026-08-24\n---\n")
    assert metadata == {
        "on": "off",
        "yes_value": "yes",
        "truth": True,
        "date": "2026-08-24",
    }
    json.dumps(metadata, allow_nan=False)


def test_empty_frontmatter_is_valid():
    assert parse_text("---\n---\nBody") == ({}, "Body")


@pytest.mark.parametrize(
    "frontmatter, message",
    [
        ("x: 1\nx: 2", "duplicate key"),
        ("x: .nan", "non-finite"),
        ("x: !!timestamp 2026-08-24", "unsupported YAML value"),
        ("? [a, b]\n: value", "unhashable mapping key"),
    ],
)
def test_frontmatter_rejects_ambiguous_or_non_json_values(frontmatter, message):
    with pytest.raises(FrontmatterError, match=message):
        parse_text(f"---\n{frontmatter}\n---\n")


def test_null_deletes_inherited_and_new_mapping_values():
    merged = deep_merge(
        {"language": {"default": "en", "allowed": ["en", "ru"]}},
        {"language": {"allowed": None, "match_user": None}},
    )
    assert merged == {"language": {"default": "en"}}
    assert deep_merge({}, {"language": {"allowed": None}}) == {"language": {}}


def test_conformance_levels_require_concrete_non_vacuous_evidence():
    plain = ResolvedVoiceContract(data={}, bodies=[(Path("VOICE.md"), "Direct answers.")])
    assert validate_contract(plain).level == "L0-plain"

    assert validate_contract(_contract()).level == "L1-core"
    assert validate_contract(_contract(interaction={"disagreement": "Be direct."})).level == (
        "L2-contextual"
    )

    natural_rule = _contract(rules=[{"id": "natural", "instruction": "Be direct."}])
    assert validate_contract(natural_rule).level == "L1-core"

    deterministic_rule = _contract(
        rules=[
            {
                "id": "no-hype",
                "pattern": "(?i)hype",
                "assert": "must_not_match",
            }
        ]
    )
    assert validate_contract(deterministic_rule).level == "L3-testable"

    external_test = _contract(
        activation={"mode": "contextual"},
        tests=[
            {
                "id": "external",
                "prompt": "Answer.",
                "assertions": {"must_contain": ["answer"]},
            }
        ],
    )
    external_result = validate_contract(external_test)
    assert external_result.level == "L2-contextual"
    assert any("not locally executable" in warning for warning in external_result.warnings)

    vacuous = _contract(tests=[{"id": "empty"}])
    vacuous_result = validate_contract(vacuous)
    assert vacuous_result.level == "L1-core"
    assert not vacuous_result.ok


def test_metadata_only_contract_fails_strict_validation():
    contract = ResolvedVoiceContract(
        data={
            "voice_spec": "0.1",
            "kind": "VoiceContract",
            "name": "Metadata only",
            "activation": {"mode": "contextual"},
            "authority": _strict_authority(),
        }
    )
    result = validate_contract(contract, strict=True)
    assert not result.ok
    assert any("no concrete communication guidance" in error for error in result.errors)


def test_semantic_validation_rejects_authority_overlap_and_missing_guards():
    malicious = _contract(
        activation={"mode": "contextual"},
        authority={
            "may_control": ["tone", "safety", "tool selection"],
            "must_not_control": ["tone", "facts"],
            "precedence": "Higher priority wins.",
        },
    )
    result = validate_contract(malicious, strict=True)
    assert not result.ok
    assert any("protected capabilities" in error for error in result.errors)
    assert any("both allowed and forbidden" in error for error in result.errors)
    assert any("must_not_control is missing" in error for error in result.errors)

    valid = _contract(
        activation={"mode": "contextual"},
        authority=_strict_authority(),
    )
    assert validate_contract(valid, strict=True).ok


def test_semantic_validation_rejects_overlaps_bad_references_and_duplicate_ids(
    tmp_path: Path,
):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Invalid
identity: {sounds_like: [Direct]}
activation:
  mode: contextual
  include: [chat]
  exclude: [CHAT]
  on_markers: [voice:on]
  off_markers: [VOICE:ON]
profiles:
  default:
    audience: missing
tests:
  - id: duplicate
    response: one
    profile: absent
    assertions: {max_words: 2}
  - id: duplicate
    response: two
    assertions: {max_words: 2}
rules:
  - id: repeated
    instruction: first
  - id: repeated
    instruction: second
---
""",
        encoding="utf-8",
    )
    result = validate_contract(load_contract(paths=[path]))
    assert not result.ok
    combined = "\n".join(result.errors)
    assert "include/exclude overlap" in combined
    assert "on/off marker overlap" in combined
    assert "unknown audience" in combined
    assert "unknown profile" in combined
    assert "tests: duplicate id" in combined
    assert "rules: duplicate id" in combined


@pytest.mark.parametrize(
    "pattern, expected",
    [
        ("(a+)+$", "nested quantifier"),
        ("(a|aa)+$", "alternation"),
        ("[", "invalid regex"),
        ("a" * 2049, "2048-character"),
    ],
)
def test_regex_safety_rejects_high_risk_patterns(pattern, expected):
    assert expected in (regex_safety_error(pattern) or "")


def test_regex_safety_accepts_shipped_rule_patterns():
    assert regex_safety_error("(?i)^(great|excellent|amazing|absolutely)[!,. ]") is None
    assert regex_safety_error(r"(?i)\[(laughs|sighs|pauses)\]") is None


def test_default_profile_selector_order_and_array_narrowing():
    contract = _contract(
        language={"default": "en", "allowed": ["en", "ru"], "match_user": True},
        audiences={"reader": {"response": {"opening": "audience"}}},
        surfaces={"chat": {"response": {"opening": "surface"}}},
        tones={"plain": {"response": {"opening": "tone"}}},
        profiles={
            "default": {
                "audience": "reader",
                "surface": "chat",
                "tone": "plain",
                "overrides": {
                    "response": {"opening": "profile"},
                    "language": {"allowed": ["en"], "match_user": False},
                },
            }
        },
    )
    payload = json.loads(compile_contract(contract, output_format="json"))
    assert payload["active"] == {
        "profile": "default",
        "audience": "reader",
        "surface": "chat",
        "tone": "plain",
    }
    assert payload["contract"]["response"]["opening"] == "profile"
    assert payload["contract"]["language"] == {
        "default": "en",
        "allowed": ["en"],
        "match_user": False,
    }


def test_semantic_validation_covers_effective_profile_overrides():
    contract = _contract(
        language={"default": "en", "allowed": ["en"]},
        profiles={
            "unsafe": {
                "overrides": {
                    "language": {"default": "ru", "allowed": ["en"]},
                    "authority": {"may_control": ["safety"]},
                }
            }
        },
    )
    result = validate_contract(contract)
    assert not result.ok
    combined = "\n".join(result.errors)
    assert "profiles.unsafe: language.default" in combined
    assert "profiles.unsafe: authority.may_control" in combined


def test_legacy_default_language_is_normalized_or_rejected_on_conflict():
    legacy = _contract(default_language="en")
    payload = json.loads(compile_contract(legacy, output_format="json"))
    assert "default_language" not in payload["contract"]
    assert payload["contract"]["language"]["default"] == "en"
    assert any("deprecated" in warning for warning in validate_contract(legacy).warnings)

    conflict = _contract(default_language="ru", language={"default": "en"})
    assert not validate_contract(conflict).ok


def test_json_compilation_rejects_non_finite_programmatic_values():
    contract = _contract(metadata={"score": float("nan")})
    with pytest.raises(CompileError, match="strict JSON"):
        compile_contract(contract, output_format="json")


def test_ascii_normalization_happens_before_character_budget():
    contract = ResolvedVoiceContract(
        data=_data(response={"opening": "Щ" * 1000}),
    )
    output = compile_contract(
        contract,
        output_format="nemotron-ascii",
        compact=True,
        max_chars=256,
    )
    assert output.isascii()
    assert len(output) <= 256
    assert "prompt truncated" in output


def _write_extends_chain(tmp_path: Path, hops: int) -> Path:
    paths = [tmp_path / f"level-{index}.md" for index in range(hops + 1)]
    for index in range(hops, -1, -1):
        extends = f"extends: {paths[index + 1].name}\n" if index < hops else ""
        core = (
            'voice_spec: "0.1"\nkind: VoiceContract\nname: Chain\n'
            "identity: {sounds_like: [Direct]}\n"
            if index == 0
            else ""
        )
        frontmatter = extends + core
        content = f"---\n{frontmatter}---\nlevel {index}\n" if frontmatter else f"level {index}\n"
        paths[index].write_text(content, encoding="utf-8")
    return paths[0]


def test_extends_accepts_eight_hops_and_rejects_nine(tmp_path: Path):
    eight = tmp_path / "eight"
    eight.mkdir()
    assert load_contract(paths=[_write_extends_chain(eight, 8)], max_extends_depth=8).name == (
        "Chain"
    )

    nine = tmp_path / "nine"
    nine.mkdir()
    with pytest.raises(ContractError, match="8 hops"):
        load_contract(paths=[_write_extends_chain(nine, 9)], max_extends_depth=8)


def test_extends_dag_applies_each_canonical_source_once(tmp_path: Path):
    base = tmp_path / "base.md"
    left = tmp_path / "left.md"
    right = tmp_path / "right.md"
    root = tmp_path / "VOICE.md"
    base.write_text("---\nresponse: {opening: base}\n---\nbase body", encoding="utf-8")
    left.write_text(
        "---\nextends: base.md\nresponse: {left: true}\n---\nleft body", encoding="utf-8"
    )
    right.write_text(
        "---\nextends: base.md\nresponse: {right: true}\n---\nright body",
        encoding="utf-8",
    )
    root.write_text(
        """---
extends: [left.md, right.md]
voice_spec: "0.1"
kind: VoiceContract
name: DAG
identity: {sounds_like: [Direct]}
---
root body
""",
        encoding="utf-8",
    )

    contract = load_contract(paths=[root])
    assert [source.path.name for source in contract.sources] == [
        "base.md",
        "left.md",
        "right.md",
        "VOICE.md",
    ]
    assert contract.body.count("base body") == 1
    assert contract.data["response"] == {"opening": "base", "left": True, "right": True}


@pytest.mark.parametrize("bad_depth", [-1, True, 1.5])
def test_extends_depth_must_be_non_negative_integer(tmp_path: Path, bad_depth):
    path = tmp_path / "VOICE.md"
    path.write_text("Direct.", encoding="utf-8")
    with pytest.raises(ContractError, match="non-negative integer"):
        load_contract(paths=[path], max_extends_depth=bad_depth)

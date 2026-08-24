from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from voicemd.compiler import (
    CompileError,
    canonical_contract_json,
    compile_contract,
    contract_sha256,
    resolve_context,
)
from voicemd.evaluator import run_cases
from voicemd.linter import lint_text
from voicemd.merge import deep_merge
from voicemd.model import ResolvedVoiceContract

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "conformance" / "vectors.json"
NODE_VERIFIER = (
    ROOT / "integrations" / "typescript" / "generated" / "conformance-verifier.js"
)


def _corpus() -> dict[str, Any]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _contract(data: dict[str, Any], bodies: list[str] | None = None) -> ResolvedVoiceContract:
    return ResolvedVoiceContract(
        data=copy.deepcopy(data),
        bodies=[(Path(f"body-{index}.md"), body) for index, body in enumerate(bodies or [])],
    )


def _selectors(vector: dict[str, Any]) -> dict[str, Any]:
    return dict(vector.get("selectors", {}))


def _pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    assert pointer.startswith("/"), f"invalid corpus JSON Pointer: {pointer}"
    current = document
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _set_pointer(document: dict[str, Any], pointer: str, value: Any) -> None:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    assert pointer.startswith("/") and parts
    current: dict[str, Any] = document
    for part in parts[:-1]:
        current = current[part]
        assert isinstance(current, dict)
    current[parts[-1]] = value


def _materialized_contract(vector: dict[str, Any]) -> dict[str, Any]:
    contract = copy.deepcopy(vector["contract"])
    for encoded in vector.get("encoded_values", []):
        units = encoded["utf16_code_units"]
        raw = b"".join(int(unit).to_bytes(2, "little") for unit in units)
        value = raw.decode("utf-16-le", errors="surrogatepass")
        _set_pointer(contract, encoded["pointer"], value)
    return contract


def test_corpus_metadata_and_vector_ids_are_stable_and_unique():
    corpus = _corpus()
    assert corpus["suite_version"] == "0.1.0"
    assert corpus["specification"] == "0.1"
    groups = corpus["vectors"]
    assert set(groups) == {
        "merge",
        "selection",
        "canonical",
        "compact",
        "regex",
        "assertions",
        "invalid",
    }
    ids = [vector["id"] for vectors in groups.values() for vector in vectors]
    assert len(ids) == len(set(ids))
    assert all(identifier and identifier == identifier.lower() for identifier in ids)


def test_python_reference_matches_merge_vectors():
    for vector in _corpus()["vectors"]["merge"]:
        actual = deep_merge(
            vector["base"],
            vector["override"],
            append_unique_arrays=vector["append_unique_arrays"],
        )
        assert actual == vector["expected"], vector["id"]


def test_python_reference_matches_selection_vectors():
    vectors = _corpus()["vectors"]["selection"]
    by_id = {vector["id"]: vector for vector in vectors}
    for vector in vectors:
        contract_data = vector.get("contract")
        if contract_data is None:
            contract_data = by_id[vector["contract_ref"]]["contract"]
        contract = _contract(contract_data)
        selected = resolve_context(contract, **_selectors(vector))
        compiled = json.loads(
            compile_contract(contract, output_format="json", **_selectors(vector))
        )
        assert compiled["active"] == vector["expected_active"], vector["id"]
        for pointer, expected in vector["expected_values"].items():
            found, actual = _pointer(selected, pointer)
            assert found and actual == expected, f"{vector['id']}: {pointer}"
        for pointer in vector["expected_absent"]:
            assert not _pointer(selected, pointer)[0], f"{vector['id']}: {pointer}"


def test_python_reference_matches_canonical_vectors():
    for vector in _corpus()["vectors"]["canonical"]:
        contract = _contract(vector["contract"], vector["bodies"])
        selectors = _selectors(vector)
        assert canonical_contract_json(contract, **selectors) == vector["expected_canonical"], (
            vector["id"]
        )
        assert contract_sha256(contract, **selectors) == vector["expected_sha256"], vector["id"]


def test_python_reference_matches_compact_vectors():
    for vector in _corpus()["vectors"]["compact"]:
        actual = compile_contract(
            _contract(vector["contract"], vector["bodies"]),
            compact=True,
            **_selectors(vector),
        )
        assert actual == vector["expected"], vector["id"]


def test_python_reference_matches_regex_vectors():
    for vector in _corpus()["vectors"]["regex"]:
        contract = _contract(
            {
                "voice_spec": "0.1",
                "kind": "VoiceContract",
                "name": f"Regex vector {vector['id']}",
                "identity": {"sounds_like": ["Direct"]},
                "rules": [
                    {
                        "id": vector["id"],
                        "pattern": vector["pattern"],
                        "flags": vector["flags"],
                        "assert": "must_match",
                    }
                ],
            }
        )
        issues = lint_text(contract, vector["text"])
        matched = not any(issue.rule_id == vector["id"] for issue in issues)
        assert matched is vector["expected_match"], vector["id"]


def test_python_reference_matches_assertion_vectors():
    for vector in _corpus()["vectors"]["assertions"]:
        contract = _contract(
            {
                "voice_spec": "0.1",
                "kind": "VoiceContract",
                "name": f"Assertion vector {vector['id']}",
                "identity": {"sounds_like": ["Direct"]},
                "tests": [
                    {
                        "id": vector["id"],
                        "response": vector["response"],
                        "assertions": vector["assertions"],
                    }
                ],
            }
        )
        result = run_cases(contract)[0]
        assert result.passed is vector["expected_pass"], (
            vector["id"],
            result.failures,
        )


def test_python_reference_rejects_invalid_vectors():
    for vector in _corpus()["vectors"]["invalid"]:
        contract = _contract(_materialized_contract(vector), vector.get("bodies", []))
        if vector["operation"] == "selection":
            with pytest.raises(CompileError):
                compile_contract(
                    contract,
                    output_format="json",
                    **_selectors(vector),
                )
        elif vector["operation"] == "canonical":
            with pytest.raises(CompileError):
                canonical_contract_json(contract, **_selectors(vector))
        else:  # pragma: no cover - corpus metadata test constrains known vectors.
            pytest.fail(f"unknown invalid operation in {vector['id']}")


def test_independent_node_verifier_passes_the_same_corpus():
    node = shutil.which("node")
    assert node is not None, "Node.js is required to verify the independent conformance runner"
    completed = subprocess.run(
        [node, str(NODE_VERIFIER), str(CORPUS_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    expected_total = sum(len(vectors) for vectors in _corpus()["vectors"].values())
    assert completed.stdout == (
        f"VoiceMD conformance: {expected_total}/{expected_total} passed\n"
    )


def test_independent_node_verifier_has_deterministic_failure_statuses(tmp_path: Path):
    node = shutil.which("node")
    assert node is not None, "Node.js is required to verify the independent conformance runner"

    usage = subprocess.run(
        [node, str(NODE_VERIFIER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert usage.returncode == 2
    assert usage.stdout == ""
    assert usage.stderr == "usage: conformance-verifier <conformance/vectors.json>\n"

    tampered = _corpus()
    tampered["vectors"]["merge"][0]["expected"] = None
    tampered_path = tmp_path / "tampered-vectors.json"
    tampered_path.write_text(
        json.dumps(tampered, ensure_ascii=False),
        encoding="utf-8",
    )
    failed = subprocess.run(
        [node, str(NODE_VERIFIER), str(tampered_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert failed.returncode == 1
    assert failed.stdout == ""
    assert failed.stderr.startswith("VoiceMD conformance failed:\n")
    assert "merge-null-delete-and-replace" in failed.stderr

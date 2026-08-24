from pathlib import Path

from voicemd.compiler import canonical_contract_json, contract_sha256
from voicemd.contract import load_contract


def _write_contract(path: Path, newline: str = "\n") -> None:
    content = '''---
voice_spec: "0.1"
kind: VoiceContract
name: Fingerprint test
identity:
  sounds_like: [direct]
profiles:
  default:
    overrides:
      response:
        max_words: 20
---
Body guidance.
'''
    path.write_bytes(content.replace("\n", newline).encode("utf-8"))


def test_contract_fingerprint_is_path_and_line_ending_independent(tmp_path: Path):
    first = tmp_path / "one" / "VOICE.md"
    second = tmp_path / "two" / "VOICE.md"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_contract(first, "\n")
    _write_contract(second, "\r\n")

    first_contract = load_contract(paths=[first])
    second_contract = load_contract(paths=[second])
    assert canonical_contract_json(first_contract) == canonical_contract_json(second_contract)
    assert contract_sha256(first_contract) == contract_sha256(second_contract)
    assert len(contract_sha256(first_contract)) == 64


def test_contract_fingerprint_changes_with_selected_semantics(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    _write_contract(path)
    contract = load_contract(paths=[path])
    default_hash = contract_sha256(contract)
    unselected_hash = contract_sha256(contract, profile=None, audience=None)
    assert default_hash == unselected_hash

    path.write_text(path.read_text(encoding="utf-8").replace("max_words: 20", "max_words: 21"))
    assert contract_sha256(load_contract(paths=[path])) != default_hash

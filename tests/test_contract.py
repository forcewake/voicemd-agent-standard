from pathlib import Path

from voicemd.contract import ContractError, load_contract


def test_extends_and_overlay(tmp_path: Path):
    base = tmp_path / "base.md"
    base.write_text("---\nvoice_spec: '0.1'\nkind: VoiceContract\nname: Base\nresponse:\n  max_words: 100\n---\nBase body", encoding="utf-8")
    child = tmp_path / "VOICE.md"
    child.write_text("---\nextends: ./base.md\nvoice_spec: '0.1'\nkind: VoiceContract\nname: Child\nresponse:\n  max_words: 20\n---\nChild body", encoding="utf-8")
    contract = load_contract(paths=[child])
    assert contract.name == "Child"
    assert contract.data["response"]["max_words"] == 20
    assert "Base body" in contract.body and "Child body" in contract.body


def test_extends_cycle(tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("---\nextends: second.md\n---\n", encoding="utf-8")
    second.write_text("---\nextends: first.md\n---\n", encoding="utf-8")
    try:
        load_contract(paths=[first])
    except ContractError as exc:
        assert "cycle" in str(exc)
        return
    raise AssertionError("expected cycle error")

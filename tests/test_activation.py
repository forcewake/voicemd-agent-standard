from pathlib import Path

from voicemd.activation import decide_activation
from voicemd.contract import load_contract
from voicemd.model import ResolvedVoiceContract


def _contract(tmp_path: Path, activation: str) -> ResolvedVoiceContract:
    path = tmp_path / "VOICE.md"
    path.write_text(
        f'''---
voice_spec: "0.1"
kind: VoiceContract
name: Activation test
activation:
{activation}
identity:
  sounds_like: [direct]
---
''',
        encoding="utf-8",
    )
    return load_contract(paths=[path])


def test_activation_respects_machine_and_exact_output_boundaries(tmp_path: Path):
    contract = _contract(
        tmp_path,
        "  mode: always\n  include: [chat, json]\n  exclude: [json]",
    )
    assert decide_activation(contract, "chat").apply
    assert not decide_activation(contract, "json", explicit=True).apply
    assert not decide_activation(contract, "chat", exact_output=True).apply


def test_explicit_mode_requires_selection_and_off_marker_wins(tmp_path: Path):
    contract = _contract(
        tmp_path,
        "  mode: explicit\n  on_markers: ['@voice']\n  off_markers: ['@no-voice']",
    )
    assert not decide_activation(contract, "chat").apply
    assert decide_activation(contract, "chat", explicit=True).apply
    assert decide_activation(contract, "chat", marker_text="@voice").apply
    assert not decide_activation(contract, "chat", marker_text="@voice @no-voice").apply
    assert not decide_activation(contract, "chat", marker_text="voice:office").apply


def test_off_mode_cannot_be_forced(tmp_path: Path):
    contract = _contract(tmp_path, '  mode: "off"')
    assert not decide_activation(contract, "chat", explicit=True, marker_text="@voice").apply


def test_middleware_honors_contract_activation(tmp_path: Path):
    from integrations.python.middleware import OutputContext, compose_system_messages

    contract = _contract(tmp_path, '  mode: "off"')
    messages = compose_system_messages(
        "Base authority.",
        OutputContext(output_kind="chat"),
        contract=contract,
    )
    assert messages == [{"role": "system", "content": "Base authority."}]


def test_profile_override_controls_activation_and_middleware(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Profile activation test
activation:
  mode: contextual
identity:
  sounds_like: [direct]
profiles:
  silent:
    overrides:
      activation:
        mode: off
---
''',
        encoding="utf-8",
    )
    contract = load_contract(paths=[path])
    assert decide_activation(contract, "chat").apply
    assert not decide_activation(contract, "chat", profile="silent").apply

    from integrations.python.middleware import OutputContext, compose_system_messages

    messages = compose_system_messages(
        "Base authority.",
        OutputContext(output_kind="chat", profile="silent"),
        contract=contract,
    )
    assert messages == [{"role": "system", "content": "Base authority."}]

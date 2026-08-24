from pathlib import Path

import pytest

from voicemd.ascii import to_ascii
from voicemd.compiler import CompileError, compile_contract
from voicemd.contract import load_contract


def _contract(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
identity:
  sounds_like: [Direct]
surfaces:
  spoken:
    response:
      max_words: 10
profiles:
  voice:
    surface: spoken
    overrides:
      speech:
        ascii_only: true
---
Прямо.
""",
        encoding="utf-8",
    )
    return load_contract(paths=[path])


def test_profile_compilation(tmp_path: Path):
    output = compile_contract(_contract(tmp_path), profile="voice")
    assert "max words: 10" in output


def test_ascii_compilation(tmp_path: Path):
    output = compile_contract(_contract(tmp_path), profile="voice", output_format="nemotron-ascii")
    assert output.isascii()
    assert "Pryamo" in output


def test_ascii_helper():
    assert to_ascii("Hello — мир") == "Hello - mir"


def test_profile_overrides_are_more_specific_than_surface(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
surfaces:
  spoken:
    speech:
      ascii_only: false
profiles:
  nemotron:
    surface: spoken
    overrides:
      speech:
        ascii_only: true
---
""",
        encoding="utf-8",
    )
    output = compile_contract(load_contract(paths=[path]), profile="nemotron")
    assert "ascii only: yes" in output


def test_rejects_too_small_explicit_prompt_budget(tmp_path: Path):
    with pytest.raises(CompileError, match="at least 256"):
        compile_contract(_contract(tmp_path), max_chars=100)


def test_rejects_too_small_runtime_prompt_budget(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text(
        """---
voice_spec: "0.1"
kind: VoiceContract
name: Test
runtime:
  max_prompt_chars: 100
---
""",
        encoding="utf-8",
    )
    with pytest.raises(CompileError, match="runtime.max_prompt_chars"):
        compile_contract(load_contract(paths=[path]))

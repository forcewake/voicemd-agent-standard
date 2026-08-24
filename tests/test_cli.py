from pathlib import Path

from voicemd.cli import build_parser, main
from voicemd.installer import install


def _voice(path: Path, *, tests: str = "") -> None:
    path.write_text(
        f'''---
voice_spec: "0.1"
kind: VoiceContract
name: CLI test
identity:
  sounds_like: [direct]
{tests}---
''',
        encoding="utf-8",
    )


def test_cli_test_fails_closed_on_skips(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    _voice(
        voice,
        tests="""tests:
  - id: missing
    prompt: Generate an answer.
    assertions:
      must_contain: [answer]
""",
    )
    common = ["test", "--path", str(voice), "--no-global"]
    assert main(common) == 1
    assert main([*common, "--allow-skips"]) == 0


def test_doctor_checks_owned_adapter_content(tmp_path: Path):
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    _voice(tmp_path / "VOICE.md")
    install(tmp_path, targets=["codex"], mode="auto")
    assert main(["doctor", "--start", str(tmp_path), "--no-global"]) == 0

    skill = tmp_path / ".agents/skills/voice-contract/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
    assert main(["doctor", "--start", str(tmp_path), "--no-global"]) == 1


def test_serve_parser_exposes_resource_limits():
    args = build_parser().parse_args(
        [
            "serve",
            "--max-body-bytes",
            "1024",
            "--max-workers",
            "4",
            "--request-timeout-seconds",
            "5",
        ]
    )
    assert args.max_body_bytes == 1024
    assert args.max_workers == 4
    assert args.request_timeout_seconds == 5


def test_cli_test_validates_contract_before_execution(tmp_path: Path):
    voice = tmp_path / "VOICE.md"
    _voice(
        voice,
        tests="""tests:
  - id: invalid
    response: answer
    assertions:
      must_contain: answer
""",
    )
    assert main(["test", "--path", str(voice), "--no-global"]) == 2

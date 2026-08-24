import json
import os
from pathlib import Path

import pytest

from voicemd import installer
from voicemd.installer import (
    InstallError,
    InstallWarning,
    adapter_health,
    install,
    uninstall,
)


def test_install_is_idempotent(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    first = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    install(tmp_path, targets=["codex"], mode="auto")
    second = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    assert (tmp_path / ".agents/skills/voice-contract/SKILL.md").exists()


def test_uninstall_preserves_unmanaged_text(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
    install(tmp_path, targets=["codex"], mode="auto")
    uninstall(tmp_path, targets=["codex"])
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").strip() == "# Existing"


def test_uninstall_target_does_not_remove_other_skills(tmp_path: Path):
    install(tmp_path, targets=["codex", "claude"], mode="auto")
    uninstall(tmp_path, targets=["codex"])
    assert not (tmp_path / ".agents/skills/voice-contract").exists()
    assert (tmp_path / ".claude/skills/voice-contract/SKILL.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_shared_skill_is_retained_for_remaining_harness(tmp_path: Path):
    install(tmp_path, targets=["codex", "gemini"], mode="auto")
    uninstall(tmp_path, targets=["codex"])
    assert (tmp_path / ".agents/skills/voice-contract/SKILL.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "GEMINI.md").exists()


def test_uninstall_does_not_delete_modified_unmanaged_skill(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    skill = tmp_path / ".agents/skills/voice-contract/SKILL.md"
    skill.write_text("# User-owned replacement\n", encoding="utf-8")
    uninstall(tmp_path, targets=["codex"])
    assert skill.read_text(encoding="utf-8") == "# User-owned replacement\n"


def test_uninstall_preserves_modified_generated_file_even_with_marker(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    skill = tmp_path / ".agents/skills/voice-contract/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\n<!-- user edit -->\n", encoding="utf-8")

    results = uninstall(tmp_path, targets=["codex"])

    assert skill.exists()
    assert "<!-- user edit -->" in skill.read_text(encoding="utf-8")
    assert (skill, "modified-retained") in results
    assert not (tmp_path / ".voicemd/install-state.json").exists()


def test_uninstall_preserves_modified_managed_block(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    instructions = tmp_path / "AGENTS.md"
    instructions.write_text(
        instructions.read_text(encoding="utf-8").replace("For human-facing", "User changed: for human-facing"),
        encoding="utf-8",
    )

    results = uninstall(tmp_path, targets=["codex"])

    assert instructions.exists()
    assert "User changed" in instructions.read_text(encoding="utf-8")
    assert (instructions, "modified-retained") in results


def test_install_state_tracks_owners(tmp_path: Path):
    install(tmp_path, targets=["codex", "gemini"], mode="auto")
    state = tmp_path / ".voicemd/install-state.json"
    assert state.exists()
    content = state.read_text(encoding="utf-8")
    assert '"codex"' in content
    assert '"gemini"' in content
    uninstall(tmp_path, targets=["codex"])
    content = state.read_text(encoding="utf-8")
    assert '"codex"' not in content
    assert '"gemini"' in content


def test_install_state_records_content_hashes(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    state = json.loads((tmp_path / ".voicemd/install-state.json").read_text(encoding="utf-8"))

    assert state["version"] == 2
    assert state["artifacts"][".agents/skills/voice-contract/SKILL.md"]["owners"] == [
        "codex"
    ]
    assert len(state["artifacts"][".agents/skills/voice-contract/SKILL.md"]["sha256"]) == 64
    assert len(state["artifacts"]["AGENTS.md"]["sha256"]) == 64


def test_explicit_mode_does_not_auto_activate_skill(tmp_path: Path):
    install(tmp_path, targets=["codex", "claude", "copilot", "cursor"], mode="explicit")
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".github/copilot-instructions.md").exists()
    skill = (tmp_path / ".agents/skills/voice-contract/SKILL.md").read_text(encoding="utf-8")
    claude = (tmp_path / ".claude/skills/voice-contract/SKILL.md").read_text(encoding="utf-8")
    cursor = (tmp_path / ".cursor/skills/voice-contract/SKILL.md").read_text(encoding="utf-8")
    policy = (tmp_path / ".agents/skills/voice-contract/agents/openai.yaml").read_text(
        encoding="utf-8"
    )
    assert "explicitly invokes this skill" in skill
    assert "Do not auto-activate" in skill
    assert "disable-model-invocation: true" in skill
    assert "disable-model-invocation: true" in claude
    assert "disable-model-invocation: true" in cursor
    assert "allow_implicit_invocation: false" in policy
    assert not (tmp_path / ".cursor/rules/voice-contract.mdc").exists()


def test_auto_to_explicit_removes_bootstrap_and_adds_codex_policy(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    assert (tmp_path / "AGENTS.md").exists()

    install(tmp_path, targets=["codex"], mode="explicit")

    assert not (tmp_path / "AGENTS.md").exists()
    assert "disable-model-invocation: true" in (
        tmp_path / ".agents/skills/voice-contract/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in (
        tmp_path / ".agents/skills/voice-contract/agents/openai.yaml"
    ).read_text(encoding="utf-8")


def test_always_to_explicit_removes_claude_import(tmp_path: Path):
    install(tmp_path, targets=["claude"], mode="always")
    assert "@VOICE.md" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    install(tmp_path, targets=["claude"], mode="explicit")

    assert not (tmp_path / "CLAUDE.md").exists()
    assert "disable-model-invocation: true" in (
        tmp_path / ".claude/skills/voice-contract/SKILL.md"
    ).read_text(encoding="utf-8")


def test_explicit_to_auto_removes_codex_policy(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="explicit")
    policy = tmp_path / ".agents/skills/voice-contract/agents/openai.yaml"
    assert policy.exists()

    install(tmp_path, targets=["codex"], mode="auto")

    assert not policy.exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert "disable-model-invocation" not in (
        tmp_path / ".agents/skills/voice-contract/SKILL.md"
    ).read_text(encoding="utf-8")


def test_shared_skill_rejects_explicit_and_implicit_owners_without_partial_write(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with pytest.raises(InstallError, match="Explicit owners cannot share"):
        install(tmp_path, targets=["gemini"], mode="explicit")

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_shared_agents_bootstrap_rejects_auto_always_conflict(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")

    with pytest.raises(InstallError, match="shared AGENTS.md bootstrap"):
        install(tmp_path, targets=["opencode"], mode="always")

    state = json.loads((tmp_path / ".voicemd/install-state.json").read_text(encoding="utf-8"))
    assert state["targets"] == {"codex": {"mode": "auto"}}


def test_shared_skill_allows_auto_and_always_when_bootstraps_are_separate(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    install(tmp_path, targets=["gemini"], mode="always")

    state = json.loads((tmp_path / ".voicemd/install-state.json").read_text(encoding="utf-8"))
    assert state["targets"]["codex"]["mode"] == "auto"
    assert state["targets"]["gemini"]["mode"] == "always"
    assert "disable-model-invocation" not in (
        tmp_path / ".agents/skills/voice-contract/SKILL.md"
    ).read_text(encoding="utf-8")


def test_symlinked_target_file_cannot_escape_root(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    os.symlink(outside, tmp_path / "AGENTS.md")

    with pytest.raises(InstallError, match="symlink"):
        install(tmp_path, targets=["codex"], mode="auto")

    assert outside.read_text(encoding="utf-8") == "outside\n"
    assert not (tmp_path / ".voicemd").exists()
    assert not (tmp_path / ".agents").exists()


def test_symlinked_parent_directory_cannot_escape_root(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-dir"
    outside.mkdir()
    os.symlink(outside, tmp_path / ".agents")

    with pytest.raises(InstallError, match="symlink"):
        install(tmp_path, targets=["codex"], mode="auto")

    assert list(outside.iterdir()) == []
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".voicemd").exists()


def test_preflight_error_leaves_no_partial_install(tmp_path: Path):
    unmanaged = tmp_path / ".claude/skills/voice-contract/SKILL.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("# user file\n", encoding="utf-8")

    with pytest.raises(InstallError, match="unowned file"):
        install(tmp_path, targets=["codex", "claude"], mode="auto")

    assert unmanaged.read_text(encoding="utf-8") == "# user file\n"
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".voicemd").exists()


def test_io_failure_rolls_back_created_files_and_state(tmp_path: Path, monkeypatch):
    original = installer._replace_bytes
    calls = 0

    def fail_second_write(path: Path, content: bytes, mode: int | None = None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic write failure")
        return original(path, content, mode)

    monkeypatch.setattr(installer, "_replace_bytes", fail_second_write)

    with pytest.raises(InstallError, match="rolled back"):
        install(tmp_path, targets=["codex"], mode="auto")

    assert list(tmp_path.iterdir()) == []


def test_modified_block_prevents_mode_change_without_partial_update(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    skill = tmp_path / ".agents/skills/voice-contract/SKILL.md"
    before_skill = skill.read_bytes()
    state_path = tmp_path / ".voicemd/install-state.json"
    before_state = state_path.read_bytes()
    instructions = tmp_path / "AGENTS.md"
    instructions.write_text(
        instructions.read_text(encoding="utf-8").replace("For human-facing", "Changed"),
        encoding="utf-8",
    )

    with pytest.raises(InstallError, match="modified managed block"):
        install(tmp_path, targets=["codex"], mode="explicit")

    assert skill.read_bytes() == before_skill
    assert state_path.read_bytes() == before_state
    assert "Changed" in instructions.read_text(encoding="utf-8")
    assert not (tmp_path / ".agents/skills/voice-contract/agents/openai.yaml").exists()


def test_dry_run_is_read_only(tmp_path: Path):
    results = install(tmp_path, targets=["codex"], mode="auto", dry_run=True)

    assert any(status == "created" for _, status in results)
    assert list(tmp_path.iterdir()) == []


def test_aider_install_warns_that_activation_is_manual(tmp_path: Path):
    with pytest.warns(InstallWarning, match="does not auto-discover"):
        install(tmp_path, targets=["aider"], mode="explicit")

    config = (tmp_path / ".aider.voice.yml").read_text(encoding="utf-8")
    assert "Requested mode: explicit" in config
    assert "aider --config .aider.voice.yml" in config


def test_adapter_health_checks_hashes_and_managed_blocks(tmp_path: Path):
    install(tmp_path, targets=["codex"], mode="auto")
    assert adapter_health(tmp_path)["ok"] is True

    skill = tmp_path / ".agents/skills/voice-contract/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
    report = adapter_health(tmp_path)

    assert report["ok"] is False
    assert any(
        item["path"] == ".agents/skills/voice-contract/SKILL.md"
        and item["status"] == "modified"
        for item in report["artifacts"]
    )


def test_uninstall_migrates_exact_legacy_v1_explicit_artifacts(tmp_path: Path):
    skill = tmp_path / ".cline/skills/voice-contract/SKILL.md"
    rule = tmp_path / ".clinerules/voice-contract.md"
    skill.parent.mkdir(parents=True)
    rule.parent.mkdir(parents=True)
    skill.write_text(installer._legacy_explicit_skill_text(), encoding="utf-8")
    rule.write_text(installer._rule_text(installer.LEGACY_EXPLICIT_TEXT), encoding="utf-8")
    state = tmp_path / ".voicemd/install-state.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "managed_by": "VoiceMD",
                "version": 1,
                "targets": {"cline": {"mode": "explicit"}},
            }
        ),
        encoding="utf-8",
    )

    uninstall(tmp_path, targets=["cline"])

    assert not skill.exists()
    assert not rule.exists()
    assert not state.exists()


def test_state_cannot_claim_and_delete_an_arbitrary_repository_file(tmp_path: Path):
    victim = tmp_path / "important.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    state = tmp_path / ".voicemd/install-state.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "managed_by": "VoiceMD",
                "version": 2,
                "targets": {"codex": {"mode": "auto"}},
                "artifacts": {
                    "important.txt": {
                        "kind": "generated",
                        "owners": ["codex"],
                        "sha256": installer._sha256_text("keep me\n"),
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InstallError, match="Unknown artifact"):
        uninstall(tmp_path, targets=["codex"])

    assert victim.read_text(encoding="utf-8") == "keep me\n"

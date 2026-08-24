from pathlib import Path

from voicemd.installer import install, uninstall


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


def test_explicit_mode_does_not_auto_activate_skill(tmp_path: Path):
    install(tmp_path, targets=["codex", "cursor"], mode="explicit")
    assert not (tmp_path / "AGENTS.md").exists()
    skill = (tmp_path / ".agents/skills/voice-contract/SKILL.md").read_text(encoding="utf-8")
    cursor = (tmp_path / ".cursor/rules/voice-contract.mdc").read_text(encoding="utf-8")
    assert "only when the user explicitly requests" in skill
    assert "Do not auto-activate" in skill
    assert "only when the user explicitly requests" in cursor

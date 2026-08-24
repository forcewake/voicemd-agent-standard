from pathlib import Path

from voicemd.discovery import discover_paths


def test_hierarchical_discovery(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "VOICE.md").write_text("root", encoding="utf-8")
    child = tmp_path / "services" / "api"
    child.mkdir(parents=True)
    (child / "VOICE.override.md").write_text("child", encoding="utf-8")
    paths = discover_paths(child, include_global=False)
    assert paths == [(tmp_path / "VOICE.md").resolve(), (child / "VOICE.override.md").resolve()]


def test_override_wins_same_directory(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "VOICE.md").write_text("base", encoding="utf-8")
    (tmp_path / "VOICE.override.md").write_text("override", encoding="utf-8")
    paths = discover_paths(tmp_path, include_global=False)
    assert paths == [(tmp_path / "VOICE.override.md").resolve()]


def test_voicemd_root_marker_works_without_git(tmp_path: Path):
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("root", encoding="utf-8")
    child = tmp_path / "apps" / "support"
    child.mkdir(parents=True)
    (child / "VOICE.override.md").write_text("child", encoding="utf-8")
    paths = discover_paths(child, include_global=False)
    assert paths == [(tmp_path / "VOICE.md").resolve(), (child / "VOICE.override.md").resolve()]


def test_explicit_root_environment(monkeypatch, tmp_path: Path):
    root = tmp_path / "workspace"
    child = root / "services" / "api"
    child.mkdir(parents=True)
    (root / "VOICE.md").write_text("root", encoding="utf-8")
    monkeypatch.setenv("VOICE_MD_ROOT", str(root))
    paths = discover_paths(child, include_global=False)
    assert paths == [(root / "VOICE.md").resolve()]

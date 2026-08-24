import os
import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


def _lite_module():
    path = Path(__file__).parents[1] / "lite/voice_loader.py"
    spec = spec_from_file_location("voicemd_lite", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lite_discovers_from_archive_root_and_accepts_file_start(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("root", encoding="utf-8")
    child = tmp_path / "apps" / "api"
    child.mkdir(parents=True)
    target = child / "request.txt"
    target.write_text("x", encoding="utf-8")
    (child / "VOICE.override.md").write_text("child", encoding="utf-8")
    assert lite.load_voice(target) == "root\n\nchild"


def test_lite_activation_boundary():
    lite = _lite_module()
    assert lite.should_apply("chat")
    assert not lite.should_apply("json")
    assert not lite.should_apply("chat", exact_output=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_python_node_and_shell_select_empty_override(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("base", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / "VOICE.override.md").write_text("", encoding="utf-8")
    (child / "VOICE.md").write_text("must not load", encoding="utf-8")

    assert lite.discover(child)[-1].name == "VOICE.override.md"
    assert lite.load_voice(child) == "base\n\n"
    for completed in _run_lite_clis(child):
        assert completed.returncode == 0
        assert completed.stdout == "base\n\n\n"


def _run_lite_clis(start: Path, *, env: dict[str, str] | None = None):
    repo = Path(__file__).parents[1]
    commands = [
        [sys.executable, str(repo / "lite/voice_loader.py"), str(start)],
        [str(repo / "lite/load-voice.sh"), str(start)],
    ]
    if shutil.which("node") is not None:
        commands.insert(1, ["node", str(repo / "lite/load-voice.mjs"), str(start)])
    return [
        subprocess.run(command, check=False, capture_output=True, text=True, env=env)
        for command in commands
    ]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
@pytest.mark.parametrize("escape_kind", ["file", "directory", "start"])
def test_lite_loaders_reject_symlink_escape(tmp_path: Path, escape_kind: str):
    lite = _lite_module()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".voicemd-root").write_text("root\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "VOICE.md").write_text("outside", encoding="utf-8")

    if escape_kind == "file":
        (project / "VOICE.md").symlink_to(outside / "VOICE.md")
        start = project
    elif escape_kind == "directory":
        (project / ".voice").symlink_to(outside, target_is_directory=True)
        start = project
    else:
        (project / "VOICE.md").write_text("inside", encoding="utf-8")
        (project / "linked").symlink_to(outside, target_is_directory=True)
        start = project / "linked"

    with pytest.raises(ValueError, match="outside canonical project root"):
        lite.load_voice(start)
    for completed in _run_lite_clis(start):
        assert completed.returncode == 1
        assert "outside canonical project root" in completed.stderr


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
def test_lite_loaders_allow_symlink_that_stays_inside_project(tmp_path: Path):
    lite = _lite_module()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (project / "VOICE.md").write_text("root", encoding="utf-8")
    real = project / "real"
    real.mkdir()
    (real / "VOICE.md").write_text("child", encoding="utf-8")
    alias = project / "alias"
    alias.symlink_to(real, target_is_directory=True)

    assert lite.load_voice(alias) == "root\n\nchild"
    for completed in _run_lite_clis(alias):
        assert completed.returncode == 0
        assert completed.stdout.strip() == "root\n\nchild"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
def test_lite_loaders_reject_broken_candidate_symlink(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (tmp_path / "VOICE.override.md").symlink_to(tmp_path / "missing.md")
    (tmp_path / "VOICE.md").write_text("must not load", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be resolved safely"):
        lite.load_voice(tmp_path)
    for completed in _run_lite_clis(tmp_path):
        assert completed.returncode == 1
        assert "cannot be resolved safely" in completed.stderr


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
def test_lite_loaders_reject_symlink_to_environment_secret(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    secret = tmp_path / ".env.local"
    secret.write_text("AUDIT_SENTINEL=must-not-load", encoding="utf-8")
    (tmp_path / "VOICE.md").symlink_to(secret)

    with pytest.raises(ValueError, match="Secret environment files"):
        lite.load_voice(tmp_path)
    for completed in _run_lite_clis(tmp_path):
        assert completed.returncode == 1
        assert "Secret environment files" in completed.stderr
        assert "AUDIT_SENTINEL" not in completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_node_and_python_follow_fallback_marker_symlinks_consistently(tmp_path: Path):
    lite = _lite_module()
    project = tmp_path / "project"
    shared = tmp_path / "shared"
    project.mkdir()
    shared.mkdir()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    marker_target = project / "marker.toml"
    marker_target.write_text("[project]", encoding="utf-8")
    (project / "pyproject.toml").symlink_to(marker_target)
    (shared / "VOICE.md").write_text("outside", encoding="utf-8")
    (project / "VOICE.md").symlink_to(shared / "VOICE.md")

    with pytest.raises(ValueError, match="outside canonical project root"):
        lite.load_voice(project)
    for completed in _run_lite_clis(project):
        assert completed.returncode == 1
        assert "outside canonical project root" in completed.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_lite_loaders_use_the_exact_voice_body_trim_set(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    expected = "\u0085Boundary body\u0085"
    (tmp_path / "VOICE.md").write_text(
        f" \t{expected}\t ",
        encoding="utf-8",
    )

    assert lite.load_voice(tmp_path) == expected
    for completed in _run_lite_clis(tmp_path):
        assert completed.returncode == 0
        assert completed.stdout == expected + "\n"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
def test_lite_nested_symlink_escape_is_rejected_below_ambient_symlink(tmp_path: Path):
    lite = _lite_module()
    physical = tmp_path / "physical"
    project = physical / "project"
    project.mkdir(parents=True)
    (project / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (project / "VOICE.md").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "VOICE.md").write_text("outside", encoding="utf-8")
    (project / "linked").symlink_to(outside, target_is_directory=True)
    ambient_alias = tmp_path / "ambient"
    ambient_alias.symlink_to(physical, target_is_directory=True)
    start = ambient_alias / "project" / "linked"

    with pytest.raises(ValueError, match="outside canonical project root"):
        lite.load_voice(start)
    for completed in _run_lite_clis(start):
        assert completed.returncode == 1
        assert "outside canonical project root" in completed.stderr


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported")
def test_lite_configured_root_uses_canonical_containment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    lite = _lite_module()
    project = tmp_path / "project"
    project.mkdir()
    (project / "VOICE.md").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "VOICE.md").write_text("outside", encoding="utf-8")
    linked = project / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("VOICE_MD_ROOT", str(project))
    child_env = os.environ.copy()

    with pytest.raises(ValueError, match="VOICE_MD_ROOT must contain"):
        lite.load_voice(linked)
    for completed in _run_lite_clis(linked, env=child_env):
        assert completed.returncode == 1
        assert "VOICE_MD_ROOT must contain" in completed.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_lite_clis_work_when_repository_path_contains_spaces(tmp_path: Path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    (project / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (project / "VOICE.md").write_text("voice text", encoding="utf-8")
    repo = Path(__file__).parents[1]

    for command in (
        [sys.executable, str(repo / "lite/voice_loader.py"), str(project)],
        ["node", str(repo / "lite/load-voice.mjs"), str(project)],
        [str(repo / "lite/load-voice.sh"), str(project)],
    ):
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        assert completed.stdout.strip() == "voice text"

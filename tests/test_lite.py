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
def test_python_and_node_skip_empty_override(tmp_path: Path):
    lite = _lite_module()
    (tmp_path / ".voicemd-root").write_text("root\n", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("base", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / "VOICE.override.md").write_text("", encoding="utf-8")

    assert lite.load_voice(child) == "base"
    node_loader = Path(__file__).parents[1] / "lite/load-voice.mjs"
    completed = subprocess.run(
        ["node", str(node_loader), str(child)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "base"


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

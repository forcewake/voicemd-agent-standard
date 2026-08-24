from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


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

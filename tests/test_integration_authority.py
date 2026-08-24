from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from voicemd import compile_voice, decide_activation, load_voice

ROOT = Path(__file__).parents[1]


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transformers_places_voice_below_required_application_authority():
    adapter = _module(
        ROOT / "integrations/transformers/chat_template.py",
        "integration_transformers_chat_template",
    )

    rendered = adapter.compose_system_instructions(
        "Use only approved tools.",
        "Prefer short sentences.",
    )

    assert rendered.startswith("APPLICATION AUTHORITY (higher priority):")
    assert rendered.index("Use only approved tools.") < rendered.index(
        "VOICEMD COMMUNICATION CONTRACT (lower priority):"
    )
    assert rendered.endswith("Prefer short sentences.")
    with pytest.raises(ValueError, match="base instructions"):
        adapter.compose_system_instructions(" \t\r\n", "voice")


def test_ollama_builder_requires_and_orders_application_authority(tmp_path: Path):
    integration = tmp_path / "ollama"
    integration.mkdir()
    for name in ("build.sh", "Modelfile.template"):
        shutil.copy2(ROOT / "integrations/ollama" / name, integration / name)

    (integration / "VOICE.compiled.txt").write_text(
        "Prefer short sentences.\n", encoding="utf-8"
    )
    (integration / "BASE.instructions.txt").write_text(
        "Use only approved tools.\n", encoding="utf-8"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ollama = fake_bin / "ollama"
    fake_ollama.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_ollama.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

    subprocess.run(
        ["bash", "build.sh", "test-model", "base-model"],
        cwd=integration,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    generated = (integration / "Modelfile.generated").read_text(encoding="utf-8")
    assert generated.index("Use only approved tools.") < generated.index(
        "VOICEMD COMMUNICATION CONTRACT (lower priority):"
    )
    assert generated.index("VOICEMD COMMUNICATION CONTRACT (lower priority):") < generated.index(
        "Prefer short sentences."
    )

    (integration / "BASE.instructions.txt").write_text(" \t\r\n", encoding="utf-8")
    rejected = subprocess.run(
        ["bash", "build.sh", "test-model", "base-model"],
        cwd=integration,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "base instructions are empty" in rejected.stderr


def test_nemotron_combines_ascii_authority_and_voice_within_total_budget():
    adapter = _module(
        ROOT / "integrations/nemotron-voicechat/session_update.py",
        "integration_nemotron_session_update",
    )

    base_instructions = (
        ROOT / "examples/application/base-agent-instructions.txt"
    ).read_text(encoding="utf-8")
    prefix = adapter._instruction_prefix(base_instructions)
    voice_contract = compile_voice(
        path=ROOT / "VOICE.md",
        profile="nemotron_voicechat",
        output_format="nemotron-ascii",
        compact=True,
        max_chars=adapter.MAX_SESSION_INSTRUCTIONS_CHARS - len(prefix),
        include_global=False,
    )
    rendered = adapter._compose_session_instructions(base_instructions, voice_contract)

    assert rendered.isascii()
    assert len(rendered) <= adapter.MAX_SESSION_INSTRUCTIONS_CHARS
    assert rendered.index("Use only tools explicitly provided") < rendered.index(
        "VOICEMD COMMUNICATION CONTRACT (lower priority):"
    )
    with pytest.raises(ValueError, match="base instructions"):
        adapter._compose_session_instructions(" \t\r\n", "voice")
    with pytest.raises(ValueError, match="ASCII-only"):
        adapter._compose_session_instructions("Use approved tools — always.", "voice")


def test_application_request_context_selects_the_shipped_full_template():
    context = json.loads(
        (ROOT / "examples/application/request-context.json").read_text(encoding="utf-8")
    )
    contract = load_voice(path=ROOT / "templates/full/VOICE.md", include_global=False)

    decision = decide_activation(
        contract,
        context["output_kind"],
        exact_output=context["exact_output"],
        enabled=context["voice_enabled"],
        profile=context["profile"],
        audience=context["audience"],
        surface=context["surface"],
        tone=context["tone"],
    )

    assert decision.apply is True


def test_checked_in_compiled_examples_match_reference_compiler():
    contract_path = ROOT / "templates/full/VOICE.md"
    executive = compile_voice(
        path=contract_path,
        profile="executive_brief",
        include_global=False,
    )
    nemotron = compile_voice(
        path=contract_path,
        profile="nemotron_voicechat",
        output_format="nemotron-ascii",
        compact=True,
        include_global=False,
    )

    assert (ROOT / "examples/compiled/executive.prompt.md").read_text(
        encoding="utf-8"
    ) == executive.rstrip(" \t\r\n") + "\n"
    assert (ROOT / "examples/compiled/nemotron.prompt.txt").read_text(
        encoding="utf-8"
    ) == nemotron.rstrip(" \t\r\n") + "\n"


def test_application_integration_snippet_forwards_every_selector():
    documentation = (ROOT / "docs/APPLICATION_INTEGRATION.md").read_text(encoding="utf-8")

    assert "from voicemd import compile_voice, decide_activation, load_voice" in documentation
    compile_branch = documentation.split("if decision.apply:", 1)[1].split("else:", 1)[0]
    assert "tone=request.tone" in compile_branch

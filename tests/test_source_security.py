from pathlib import Path

import pytest

from voicemd import load_voice
from voicemd.contract import ContractError, load_contract


def _write(path: Path, content: str = "Direct.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize("reference_kind", ["absolute", "parent"])
def test_extends_cannot_escape_allowed_source_root(
    tmp_path: Path, reference_kind: str
) -> None:
    root = tmp_path / "project"
    contracts = root / "contracts"
    outside = _write(root / "outside.md", "outside secret material")
    reference = str(outside) if reference_kind == "absolute" else "../outside.md"
    voice = _write(contracts / "VOICE.md", f"---\nextends: {reference}\n---\nchild")

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(paths=[voice], allowed_source_root=contracts)
    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(explicit=voice, include_global=False)


def test_explicit_source_defaults_to_nearest_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    _write(project / "shared.md", "shared")
    voice = _write(
        project / "contracts" / "VOICE.md",
        "---\nextends: ../shared.md\n---\nchild",
    )

    contract = load_contract(explicit=voice, include_global=False)

    assert [source.path.name for source in contract.sources] == ["shared.md", "VOICE.md"]


def test_explicit_source_cannot_escape_nearest_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    _write(tmp_path / "outside.md")
    voice = _write(
        project / "contracts" / "VOICE.md",
        "---\nextends: ../../outside.md\n---\nchild",
    )

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(explicit=voice, include_global=False)


def test_explicit_and_discovered_sources_must_be_inside_configured_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    allowed = project / "contracts"
    allowed.mkdir(parents=True)
    (project / ".git").mkdir()
    outside = _write(project / "VOICE.md")

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(explicit=outside, allowed_source_root=allowed, include_global=False)
    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(start=project, allowed_source_root=allowed, include_global=False)
    with pytest.raises(ContractError, match="outside allowed source root"):
        load_voice(path=outside, allowed_source_root=allowed, include_global=False)


def test_symlink_target_cannot_escape_allowed_source_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = _write(tmp_path / "outside.md")
    link = root / "VOICE.md"
    link.symlink_to(outside)

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(paths=[link], allowed_source_root=root)
    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(explicit=link, include_global=False)


def test_symlinked_parent_cannot_widen_default_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    outside = tmp_path / "outside"
    _write(outside / "VOICE.md")
    (project / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(explicit=project / "linked" / "VOICE.md", include_global=False)


def test_automatic_discovery_rejects_symlink_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    outside = _write(tmp_path / "outside.md")
    (project / "VOICE.md").symlink_to(outside)

    with pytest.raises(ContractError, match="outside allowed source root"):
        load_contract(start=project, include_global=False)


def test_automatic_project_and_global_sources_keep_separate_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    _write(project / "VOICE.md", "project")
    global_home = tmp_path / "global"
    _write(global_home / "base.md", "global base")
    _write(global_home / "VOICE.md", "---\nextends: base.md\n---\nglobal")
    monkeypatch.setenv("VOICE_MD_HOME", str(global_home))

    contract = load_contract(start=project, include_global=True)

    assert [source.path for source in contract.sources] == [
        (global_home / "base.md").resolve(),
        (global_home / "VOICE.md").resolve(),
        (project / "VOICE.md").resolve(),
    ]


@pytest.mark.parametrize("name", [".env", ".env.local", ".ENV.production"])
def test_secret_environment_files_are_denied(tmp_path: Path, name: str) -> None:
    secret = _write(tmp_path / name, "AZURE_OPENAI_API_KEY=do-not-read")

    with pytest.raises(ContractError, match="Secret environment files"):
        load_contract(paths=[secret], allowed_source_root=tmp_path)


def test_symlink_to_secret_environment_file_is_denied(tmp_path: Path) -> None:
    secret = _write(tmp_path / ".env.private", "TOKEN=do-not-read")
    link = tmp_path / "VOICE.md"
    link.symlink_to(secret)

    with pytest.raises(ContractError, match="Secret environment files"):
        load_contract(paths=[link], allowed_source_root=tmp_path)


def test_per_file_and_aggregate_byte_limits(tmp_path: Path) -> None:
    base = _write(tmp_path / "base.md", "b" * 80)
    voice = _write(tmp_path / "VOICE.md", "---\nextends: base.md\n---\n" + "v" * 80)

    with pytest.raises(ContractError, match="file byte limit"):
        load_contract(paths=[voice], max_source_file_bytes=voice.stat().st_size - 1)

    total_bytes = base.stat().st_size + voice.stat().st_size
    with pytest.raises(ContractError, match="aggregate byte limit"):
        load_contract(
            paths=[voice],
            max_source_file_bytes=voice.stat().st_size,
            max_total_source_bytes=total_bytes - 1,
        )


def test_unique_source_count_is_bounded(tmp_path: Path) -> None:
    _write(tmp_path / "a.md")
    _write(tmp_path / "b.md")
    voice = _write(tmp_path / "VOICE.md", "---\nextends: [a.md, b.md]\n---\nroot")

    with pytest.raises(ContractError, match=r"Maximum source count \(2\)"):
        load_contract(paths=[voice], max_source_count=2)


def test_yaml_alias_expansion_consumes_expanded_node_budget(tmp_path: Path) -> None:
    voice = _write(
        tmp_path / "VOICE.md",
        """---
a: &a [x, x]
b: &b [*a, *a]
c: &c [*b, *b]
d: &d [*c, *c]
e: &e [*d, *d]
---
body
""",
    )

    with pytest.raises(ContractError, match="YAML expanded node limit exceeded"):
        load_contract(paths=[voice], max_yaml_nodes=80, max_yaml_aliases=100)


def test_yaml_alias_reference_count_is_bounded(tmp_path: Path) -> None:
    voice = _write(
        tmp_path / "VOICE.md",
        "---\nbase: &base [x]\ncopy: [*base, *base, *base]\n---\nbody",
    )

    with pytest.raises(ContractError, match="YAML alias reference limit exceeded"):
        load_contract(paths=[voice], max_yaml_aliases=2)


def test_yaml_merge_keys_cannot_bypass_expansion_budget(tmp_path: Path) -> None:
    voice = _write(
        tmp_path / "VOICE.md",
        "---\nbase: &base {opening: direct}\nprofile: {<<: *base}\n---\nbody",
    )

    with pytest.raises(ContractError, match="YAML merge keys are not supported"):
        load_contract(paths=[voice])


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("max_source_file_bytes", 0),
        ("max_total_source_bytes", -1),
        ("max_source_count", True),
        ("max_yaml_nodes", 1.5),
        ("max_yaml_aliases", 0),
    ],
)
def test_resource_limits_must_be_positive_integers(
    tmp_path: Path, option: str, value: object
) -> None:
    voice = _write(tmp_path / "VOICE.md")

    with pytest.raises(ContractError, match=f"{option} must be a positive integer"):
        load_contract(paths=[voice], **{option: value})  # type: ignore[arg-type]


def test_automatic_discovery_rejects_symlinked_start_outside_lexical_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    _write(project / ".voicemd-root", "root")
    _write(project / "VOICE.md", "inside")
    _write(outside / "VOICE.md", "outside")
    linked_start = project / "linked-start"
    linked_start.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileNotFoundError, match="symlink escape"):
        load_contract(start=linked_start, include_global=False)


def test_symlink_target_marker_cannot_redefine_lexical_project_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    _write(project / ".voicemd-root", "root")
    _write(project / "VOICE.md", "inside")
    _write(outside / ".voicemd-root", "root")
    _write(outside / "VOICE.md", "outside")
    linked_start = project / "linked-start"
    linked_start.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileNotFoundError, match="symlink escape"):
        load_contract(start=linked_start, include_global=False)

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]


def _load_script(name: str):
    path = REPOSITORY_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "--quiet")
    _git(path, "config", "user.email", "release-test@example.invalid")
    _git(path, "config", "user.name", "Release Test")
    _git(path, "config", "core.fileMode", "false")
    (path / "README.md").write_text("tracked\n", encoding="utf-8")
    (path / ".gitignore").write_text(".env\n.coverage\n", encoding="utf-8")
    _git(path, "add", "README.md", ".gitignore")
    _git(path, "commit", "--quiet", "-m", "fixture")
    return path


def test_release_builder_uses_only_tracked_files_and_canonical_metadata(tmp_path: Path):
    builder = _load_script("build_release")
    first_repository = _repository(tmp_path / "checkout-one")
    second_repository = _repository(tmp_path / "different-checkout-name")

    (first_repository / ".env").write_text("SECRET=not-packaged\n", encoding="utf-8")
    (first_repository / ".coverage").write_bytes(b"not packaged")
    os.chmod(second_repository / "README.md", 0o755)

    first = builder.build_release(first_repository, tmp_path / "first.zip")
    second = builder.build_release(second_repository, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()

    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            "voicemd-agent-standard/.gitignore",
            "voicemd-agent-standard/README.md",
        ]
        info = archive.getinfo("voicemd-agent-standard/README.md")
        assert (info.external_attr >> 16) & 0o777 == 0o644


def test_release_builder_rejects_tracked_symlink(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    outside = tmp_path / "outside.txt"
    outside.write_text("must not leak\n", encoding="utf-8")
    link = repository / "outside-link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    _git(repository, "add", "outside-link")
    _git(repository, "commit", "--quiet", "-m", "add unsafe link")

    with pytest.raises(builder.ReleaseBuildError, match="symbolic link"):
        builder.build_release(repository, tmp_path / "release.zip")


def test_release_builder_rejects_nonignored_untracked_file(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    (repository / "forgotten.txt").write_text("not staged\n", encoding="utf-8")

    with pytest.raises(builder.ReleaseBuildError, match="untracked files"):
        builder.build_release(repository, tmp_path / "release.zip")


def test_release_builder_rejects_tracked_changes(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    (repository / "README.md").write_text("modified\n", encoding="utf-8")

    with pytest.raises(builder.ReleaseBuildError, match="must match HEAD"):
        builder.build_release(repository, tmp_path / "release.zip")


def _wheel(
    path: Path,
    *,
    name: str = "voicemd",
    version: str = "0.1.0",
    files: dict[str, bytes] | None = None,
) -> None:
    dist_info = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}/__init__.py", "")
        for relative, content in (files or {}).items():
            archive.writestr(relative, content)
        archive.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")


def _sdist(
    path: Path,
    *,
    name: str = "voicemd",
    version: str = "0.1.0",
    files: dict[str, bytes] | None = None,
) -> None:
    root = f"{name}-{version}"
    content_by_name = dict(files or {})
    content_by_name["pyproject.toml"] = content_by_name.get(
        "pyproject.toml", b"[build-system]\nrequires = ['setuptools']\n"
    )
    content_by_name["PKG-INFO"] = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    ).encode()
    with tarfile.open(path, "w:gz") as archive:
        for relative, content in content_by_name.items():
            info = tarfile.TarInfo(f"{root}/{relative}")
            info.size = len(content)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_tree(tmp_path: Path, verifier, *, status: str = "current") -> Path:
    root = tmp_path / "voicemd-agent-standard"
    for relative in verifier.REQUIRED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"fixture for {relative}\n", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        '[project]\nname = "voicemd"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "SPECIFICATION.md").write_text(
        "# Specification\n\nVersion: `0.1.0-draft.1`\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "project": "VoiceMD",
                "release": "0.1.0-draft.1",
                "reference_implementation": {
                    "package": "voicemd",
                    "version": "0.1.0",
                },
            }
        ),
        encoding="utf-8",
    )

    wheel_name = "voicemd-0.1.0-py3-none-any.whl"
    sdist_name = "voicemd-0.1.0.tar.gz"
    wheel = root / "release" / wheel_name
    sdist = root / "release" / sdist_name
    package_files = {
        source.relative_to(root / "src").as_posix(): source.read_bytes()
        for source in (root / "src/voicemd").rglob("*")
        if source.is_file()
    }
    sdist_files = {
        source.relative_to(root).as_posix(): source.read_bytes()
        for source in verifier._sdist_sync_sources(root)
    }
    _wheel(wheel, files=package_files)
    _sdist(sdist, files=sdist_files)
    artifacts = {
        wheel_name: {"sha256": _digest(wheel)},
        sdist_name: {"sha256": _digest(sdist)},
    }
    build_info = {
        "project": "VoiceMD",
        "specification_version": "0.1.0-draft.1",
        "built_at": "2026-08-24",
        "tests_passed": 1,
        "package_name": "voicemd",
        "package_version": "0.1.0",
        "artifact_status": status,
        "source_revision": "a" * 40,
        "source_sha256": verifier.source_snapshot_sha256(root),
        "verification": ["fixture verification"],
        "artifacts": artifacts,
    }
    (root / "release/BUILD_INFO.json").write_text(
        json.dumps(build_info), encoding="utf-8"
    )
    (root / "release/SHA256SUMS").write_text(
        "".join(f"{metadata['sha256']}  {name}\n" for name, metadata in artifacts.items()),
        encoding="utf-8",
    )
    return root


def _zip_tree(root: Path, output: Path) -> Path:
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root.parent).as_posix())
    return output


def test_release_verifier_accepts_complete_current_artifacts(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "release.zip")
    verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_artifactless_release(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    build_info_path = root / "release/BUILD_INFO.json"
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    build_info["artifacts"] = {}
    build_info_path.write_text(json.dumps(build_info), encoding="utf-8")
    (root / "release/SHA256SUMS").write_text("", encoding="utf-8")
    for artifact in (root / "release").glob("voicemd-*"):
        artifact.unlink()
    archive = _zip_tree(root, tmp_path / "artifactless.zip")

    with pytest.raises(verifier.ReleaseVerificationError, match="empty|named artifacts"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_stale_or_mismatched_evidence(tmp_path: Path):
    verifier = _load_script("verify_release")
    stale_root = _release_tree(tmp_path / "stale", verifier, status="stale")
    with pytest.raises(verifier.ReleaseVerificationError, match="not current"):
        verifier.verify_artifacts(stale_root)

    mismatched_root = _release_tree(tmp_path / "mismatch", verifier)
    checksum_path = mismatched_root / "release/SHA256SUMS"
    checksum_path.write_text("0" * 64 + "  voicemd-0.1.0.tar.gz\n", encoding="utf-8")
    with pytest.raises(verifier.ReleaseVerificationError, match="does not match"):
        verifier.verify_artifacts(mismatched_root)


def test_release_verifier_rejects_artifact_that_is_stale_against_source(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    (root / "src/voicemd/cli.py").write_text("changed after build\n", encoding="utf-8")

    with pytest.raises(verifier.ReleaseVerificationError, match="source_sha256"):
        verifier.verify_artifacts(root)


def test_release_verifier_rejects_zip_path_traversal(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("voicemd-agent-standard/../../escape", "unsafe")
    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="unsafe ZIP member"),
    ):
        verifier._validate_archive_members(archive)


def test_release_verifier_restores_executable_intent(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "executable.zip"
    info = zipfile.ZipInfo("voicemd-agent-standard/lite/load-voice.sh")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o755) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "#!/bin/sh\n")

    destination = tmp_path / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        verifier._safe_extract(archive, destination)

    extracted = destination / info.filename
    assert extracted.stat().st_mode & 0o777 == 0o755


def test_release_builder_rejects_tracked_env_variant(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    (repository / ".env.local").write_text("SECRET=tracked\n", encoding="utf-8")
    _git(repository, "add", "-f", ".env.local")
    _git(repository, "commit", "--quiet", "-m", "unsafe env")

    with pytest.raises(builder.ReleaseBuildError, match="forbidden tracked release file"):
        builder.build_release(repository, tmp_path / "release.zip")


def test_release_verifier_rejects_source_snapshot_mismatch(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    (root / "README.md").write_text("changed after evidence\n", encoding="utf-8")

    with pytest.raises(verifier.ReleaseVerificationError, match="source_sha256"):
        verifier.load_build_info(root)


def test_sdist_rejects_forbidden_build_output(tmp_path: Path):
    verifier = _load_script("verify_release")
    sdist = tmp_path / "voicemd-0.1.0.tar.gz"
    _sdist(sdist, files={"integrations/typescript/node_modules/secret": b"bad"})

    with pytest.raises(verifier.ReleaseVerificationError, match="forbidden build/cache"):
        verifier.verify_sdist(
            sdist,
            package_name="voicemd",
            package_version="0.1.0",
        )


def test_runtime_verifier_scopes_voice_environment_to_contract_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    verifier = _load_script("verify_release")
    root = tmp_path / "root"
    root.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    wheel = tmp_path / "package.whl"
    sdist = tmp_path / "package.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    monkeypatch.setenv("VOICE_MD", "outside")
    monkeypatch.setenv("VOICE_MD_HOME", "outside")
    monkeypatch.setenv("VOICE_MD_ROOT", "outside")

    class FakeBuilder:
        def __init__(self, **_kwargs):
            pass

        def create(self, path: Path) -> None:
            path.mkdir(parents=True)

    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        assert cwd == root
        calls.append((command, env))
        if "compile" in command:
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("ASCII", encoding="utf-8")

    monkeypatch.setattr(verifier.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(verifier, "run", fake_run)
    verifier.verify_runtime(root, wheel, sdist, temporary)

    smoke_calls = [entry for entry in calls if "validate" in entry[0] or "compile" in entry[0]]
    pytest_call = next(entry for entry in calls if "pytest" in entry[0])
    assert all(env["VOICE_MD_ROOT"] == str(root) for _, env in smoke_calls)
    for variable in ("VOICE_MD", "VOICE_MD_HOME", "VOICE_MD_ROOT"):
        assert variable not in pytest_call[1]

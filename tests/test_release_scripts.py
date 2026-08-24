from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

import pytest
import yaml

from voicemd import __version__

REPOSITORY_ROOT = Path(__file__).parents[1]
FIXTURE_REVISION = "a" * 40
FIXTURE_PACKAGE_VERSION = __version__
FIXTURE_WHEEL_NAME = f"voicemd-{FIXTURE_PACKAGE_VERSION}-py3-none-any.whl"
FIXTURE_SDIST_NAME = f"voicemd-{FIXTURE_PACKAGE_VERSION}.tar.gz"


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


def _head(repository: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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

    with pytest.raises(builder.ReleaseBuildError, match="must match the selected release revision"):
        builder.build_release(repository, tmp_path / "release.zip")


def test_release_builder_rejects_assume_unchanged_worktree_changes(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    _git(repository, "update-index", "--assume-unchanged", "README.md")
    (repository / "README.md").write_text("hidden worktree change\n", encoding="utf-8")

    with pytest.raises(builder.ReleaseBuildError, match="must match the selected release revision"):
        builder.build_release(repository, tmp_path / "release.zip")


def test_release_builder_accepts_git_equivalent_crlf_checkout(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    _git(repository, "config", "core.autocrlf", "true")
    (repository / "README.md").write_bytes(b"tracked\r\n")
    (repository / ".gitignore").write_bytes(b".env\r\n.coverage\r\n")

    release = builder.build_release(repository, tmp_path / "release.zip")

    with zipfile.ZipFile(release) as archive:
        assert archive.read("voicemd-agent-standard/README.md") == b"tracked\n"
        assert archive.read("voicemd-agent-standard/.gitignore") == b".env\n.coverage\n"


def test_git_source_snapshot_uses_canonical_blobs_for_crlf_checkout(tmp_path: Path):
    builder = _load_script("build_release")
    verifier = _load_script("verify_release")
    repository = _repository(tmp_path / "repository")
    _git(repository, "config", "core.autocrlf", "true")
    (repository / "README.md").write_bytes(b"tracked\r\n")
    (repository / ".gitignore").write_bytes(b".env\r\n.coverage\r\n")
    revision = _head(repository)

    expected = builder._source_snapshot_sha256(
        repository, builder.tracked_files(repository, revision)
    )
    assert verifier.git_source_snapshot_sha256(repository, revision) == expected
    assert verifier.source_snapshot_sha256(repository) != expected


def test_raw_source_snapshot_keeps_lf_and_crlf_distinct(tmp_path: Path):
    verifier = _load_script("verify_release")
    source = tmp_path / "VOICE.md"
    source.write_bytes(b"Voice contract.\n")
    lf_snapshot = verifier.source_snapshot_sha256(tmp_path)
    source.write_bytes(b"Voice contract.\r\n")

    assert verifier.source_snapshot_sha256(tmp_path) != lf_snapshot


def test_sdist_normalization_is_deterministic(tmp_path: Path):
    builder = _load_script("build_release")

    def noncanonical(path: Path, *, mtime: int, reverse: bool) -> None:
        entries = [
            ("voicemd-0.1.0", None, 0o700),
            ("voicemd-0.1.0/tool.sh", b"#!/bin/sh\n", 0o755),
            ("voicemd-0.1.0/README.md", b"fixture\n", 0o600),
        ]
        with tarfile.open(path, "w:gz") as archive:
            for name, content, mode in reversed(entries) if reverse else entries:
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE if content is None else tarfile.REGTYPE
                info.size = 0 if content is None else len(content)
                info.mtime = mtime
                info.mode = mode
                info.uid = mtime
                info.gid = mtime
                info.uname = f"user-{mtime}"
                info.gname = f"group-{mtime}"
                archive.addfile(info, None if content is None else io.BytesIO(content))

    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    noncanonical(first, mtime=1, reverse=False)
    noncanonical(second, mtime=2, reverse=True)

    builder.normalize_sdist(first, epoch=1_700_000_000)
    builder.normalize_sdist(second, epoch=1_700_000_000)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == sorted(
            member.name for member in members
        )
        assert {member.mtime for member in members} == {1_700_000_000}
        assert {(member.uid, member.gid, member.uname, member.gname) for member in members} == {
            (0, 0, "", "")
        }
        assert archive.getmember("voicemd-0.1.0/tool.sh").mode == 0o755
        assert archive.getmember("voicemd-0.1.0/README.md").mode == 0o644


def _wheel(
    path: Path,
    *,
    name: str = "voicemd",
    version: str = FIXTURE_PACKAGE_VERSION,
    files: dict[str, bytes] | None = None,
    license_text: bytes = b"fixture license\n",
    notice_text: bytes = b"fixture notice\n",
    entry_points: bytes = (
        b"[console_scripts]\n"
        b"voicemd = voicemd.cli:main\n"
        b"voicemd-azure = voicemd.azure_voice.cli:main\n"
    ),
) -> None:
    dist_info = f"{name}-{version}.dist-info"
    content_by_name = {f"{name}/__init__.py": b"", **(files or {})}
    content_by_name.update(
        {
            f"{dist_info}/licenses/LICENSE": license_text,
            f"{dist_info}/licenses/NOTICE": notice_text,
            f"{dist_info}/METADATA": (
                f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
            ).encode(),
            f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            f"{dist_info}/entry_points.txt": entry_points,
            f"{dist_info}/top_level.txt": f"{name}\n".encode(),
        }
    )
    record_name = f"{dist_info}/RECORD"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for relative, content in sorted(content_by_name.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow((relative, f"sha256={digest}", str(len(content))))
    writer.writerow((record_name, "", ""))
    content_by_name[record_name] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for relative, content in content_by_name.items():
            archive.writestr(relative, content)


def _sdist(
    path: Path,
    *,
    name: str = "voicemd",
    version: str = FIXTURE_PACKAGE_VERSION,
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
    content_by_name.setdefault(
        "setup.cfg",
        b"[egg_info]\ntag_build = \ntag_date = 0\n\n",
    )
    with tarfile.open(path, "w:gz") as archive:
        for relative, content in content_by_name.items():
            info = tarfile.TarInfo(f"{root}/{relative}")
            info.size = len(content)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_tree(
    tmp_path: Path,
    verifier,
    *,
    status: str = "current",
    required_wav_bytes: bytes | None = None,
) -> Path:
    builder = _load_script("build_release")
    root = tmp_path / "voicemd-agent-standard"
    for relative in verifier.REQUIRED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"fixture for {relative}\n", encoding="utf-8")
    if required_wav_bytes is not None:
        (root / "site/audio/calm-support.wav").write_bytes(required_wav_bytes)
    (root / "LICENSE").write_text("fixture license\n", encoding="utf-8")
    (root / "NOTICE").write_text("fixture notice\n", encoding="utf-8")
    (root / "src/voicemd/__init__.py").write_text("", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        f'[project]\nname = "voicemd"\nversion = "{FIXTURE_PACKAGE_VERSION}"\n',
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
                "specification_version": "0.1.0-draft.1",
                "reference_implementation": {
                    "package": "voicemd",
                    "version": FIXTURE_PACKAGE_VERSION,
                },
            }
        ),
        encoding="utf-8",
    )

    wheel_name = FIXTURE_WHEEL_NAME
    sdist_name = FIXTURE_SDIST_NAME
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
    _wheel(
        wheel,
        files=package_files,
        license_text=(root / "LICENSE").read_bytes(),
        notice_text=(root / "NOTICE").read_bytes(),
    )
    _sdist(sdist, files=sdist_files)
    artifacts = {
        wheel_name: {"sha256": _digest(wheel)},
        sdist_name: {"sha256": _digest(sdist)},
    }
    # The fixture must remain runnable from an sdist, where the project has no .git.
    source_revision = FIXTURE_REVISION
    release_revision = source_revision
    source_snapshot = verifier.source_snapshot_sha256(root)
    distribution_metadata = builder.DistributionMetadata(
        name="voicemd",
        version=FIXTURE_PACKAGE_VERSION,
        license_expression="Apache-2.0",
        requirements=(),
        artifacts=(wheel, sdist),
    )
    sbom_path = root / "release/SBOM.spdx.json"
    sbom_path.write_bytes(
        builder._canonical_json(
            builder._spdx_document(
                distribution_metadata,
                source_revision=source_revision,
                source_snapshot=source_snapshot,
                created="2026-08-24T00:00:00Z",
            )
        )
    )
    provenance_path = root / "release/PROVENANCE.intoto.jsonl"
    provenance_path.write_bytes(
        builder._canonical_json(
            builder._provenance_statement(
                {
                    wheel_name: artifacts[wheel_name]["sha256"],
                    sdist_name: artifacts[sdist_name]["sha256"],
                    sbom_path.name: _digest(sbom_path),
                },
                package_name="voicemd",
                package_version=FIXTURE_PACKAGE_VERSION,
                source_revision=source_revision,
                release_revision=release_revision,
                source_snapshot=source_snapshot,
                build_type="urn:voicemd:build:python-distributions:v1",
            )
        )
    )
    release_metadata = {
        sbom_path.name: {"sha256": _digest(sbom_path)},
        provenance_path.name: {"sha256": _digest(provenance_path)},
    }
    build_info = {
        "project": "VoiceMD",
        "specification_version": "0.1.0-draft.1",
        "built_at": "2026-08-24",
        "tests_passed": 1,
        "package_name": "voicemd",
        "package_version": FIXTURE_PACKAGE_VERSION,
        "artifact_status": status,
        "source_revision": source_revision,
        "release_revision": release_revision,
        "source_sha256": source_snapshot,
        "verification": ["fixture verification"],
        "artifacts": artifacts,
        "release_metadata": release_metadata,
    }
    (root / "release/BUILD_INFO.json").write_text(
        json.dumps(build_info), encoding="utf-8"
    )
    (root / "release/SHA256SUMS").write_text(
        "".join(
            f"{metadata['sha256']}  {name}\n"
            for name, metadata in {**artifacts, **release_metadata}.items()
        ),
        encoding="utf-8",
    )
    return root


def _zip_tree(root: Path, output: Path) -> Path:
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(root.parent).as_posix()
                archive.writestr(_regular_zip_info(relative), path.read_bytes())
    return output


def _regular_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_STORED
    return info


def test_release_verifier_keeps_canonical_unix_member_requirement(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "windows-member.zip"
    info = zipfile.ZipInfo(f"{verifier.ARCHIVE_ROOT}/README.md")
    info.create_system = 0
    info.external_attr = 0
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"fixture\n")

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="Unix regular file"),
    ):
        verifier._validate_archive_members(archive)


def _insert_before_central_directory(path: Path, payload: bytes) -> None:
    content = bytearray(path.read_bytes())
    eocd = content.rfind(b"PK\x05\x06")
    assert eocd >= 0
    central_offset = int.from_bytes(content[eocd + 16 : eocd + 20], "little")
    content[central_offset:central_offset] = payload
    eocd += len(payload)
    content[eocd + 16 : eocd + 20] = (central_offset + len(payload)).to_bytes(4, "little")
    path.write_bytes(content)


def test_release_verifier_accepts_complete_current_artifacts(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "release.zip")
    verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_accepts_non_utf8_required_wav(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(
        tmp_path,
        verifier,
        required_wav_bytes=b"RIFF\xff\xfe\x80\x00WAVEfmt ",
    )
    archive = _zip_tree(root, tmp_path / "release-with-binary-audio.zip")

    verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_normalizes_invalid_utf8_in_semantic_text(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    (root / "manifest.json").write_bytes(b"\xff\xfe")
    archive = _zip_tree(root, tmp_path / "invalid-utf8.zip")

    with pytest.raises(verifier.ReleaseVerificationError, match="valid UTF-8"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_invalid_utf8_in_required_text(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    (root / ".github/workflows/ci.yml").write_bytes(b"\xff\xfe")
    archive = _zip_tree(root, tmp_path / "invalid-required-text.zip")

    with pytest.raises(verifier.ReleaseVerificationError, match="valid UTF-8"):
        verifier.verify_archive(archive, install_checks=False)


def test_read_nonempty_normalizes_io_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    verifier = _load_script("verify_release")
    path = tmp_path / "required.txt"
    path.write_text("present\n", encoding="utf-8")

    def deny_read(_path: Path) -> bytes:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    with pytest.raises(verifier.ReleaseVerificationError, match="could not read required file"):
        verifier._read_nonempty(path)


@pytest.mark.parametrize(
    "relative",
    ["release/undeclared.bin", "release/nested/undeclared.bin"],
)
def test_release_verifier_rejects_undeclared_release_inventory(
    tmp_path: Path, relative: str
):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    unexpected = root / relative
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"undeclared")
    archive = _zip_tree(root, tmp_path / "undeclared-release-member.zip")

    with pytest.raises(verifier.ReleaseVerificationError, match="release inventory mismatch"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_zip_prefix(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "prefixed.zip")
    archive.write_bytes(b"UNACCOUNTED-PREFIX" + archive.read_bytes())

    with pytest.raises(verifier.ReleaseVerificationError, match="prefix|prepended"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_zip_trailing_bytes(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "trailed.zip")
    archive.write_bytes(archive.read_bytes() + b"UNACCOUNTED-TRAILER")

    with pytest.raises(verifier.ReleaseVerificationError, match="trailing bytes"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_zip_comment(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "commented.zip")
    with zipfile.ZipFile(archive, "a") as packaged:
        packaged.comment = b"unaccounted comment"

    with pytest.raises(verifier.ReleaseVerificationError, match="comments are not allowed"):
        verifier.verify_archive(archive, install_checks=False)


def test_release_verifier_rejects_zip_member_comment(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "member-comment.zip"
    info = _regular_zip_info(f"{verifier.ARCHIVE_ROOT}/README.md")
    info.comment = b"unaccounted comment"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"fixture\n")

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="member comments"),
    ):
        verifier._validate_canonical_zip_container(archive_path, archive)


def test_release_verifier_rejects_local_only_zip_extra_field(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "local-extra.zip"
    info = _regular_zip_info(f"{verifier.ARCHIVE_ROOT}/README.md")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"fixture\n")

    content = bytearray(archive_path.read_bytes())
    name_size = int.from_bytes(content[26:28], "little")
    local_extra = b"\xfe\xca\x00\x00"
    content[28:30] = len(local_extra).to_bytes(2, "little")
    insert_at = verifier.ZIP_LOCAL_HEADER_SIZE + name_size
    content[insert_at:insert_at] = local_extra
    archive_path.write_bytes(content)

    # Update the EOCD central-directory offset for the inserted local-only field.
    content = bytearray(archive_path.read_bytes())
    eocd = content.rfind(b"PK\x05\x06")
    central_offset = int.from_bytes(content[eocd + 16 : eocd + 20], "little")
    content[eocd + 16 : eocd + 20] = (central_offset + len(local_extra)).to_bytes(
        4, "little"
    )
    archive_path.write_bytes(content)

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="local ZIP extra fields"),
    ):
        verifier._validate_canonical_zip_container(archive_path, archive)


def test_release_verifier_rejects_gap_before_central_directory(tmp_path: Path):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "central-gap.zip"
    info = _regular_zip_info(f"{verifier.ARCHIVE_ROOT}/README.md")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"fixture\n")
    _insert_before_central_directory(archive_path, b"JUNK")

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="before its central directory"),
    ):
        verifier._validate_canonical_zip_container(archive_path, archive)


@pytest.mark.parametrize(
    ("name", "mode"),
    [
        ("voicemd-agent-standard/not-a-directory", stat.S_IFDIR | 0o755),
        ("voicemd-agent-standard/not-a-file/", stat.S_IFREG | 0o644),
    ],
)
def test_release_verifier_rejects_zip_member_name_type_mismatch(
    tmp_path: Path, name: str, mode: int
):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "type-mismatch.zip"
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"payload")

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(verifier.ReleaseVerificationError, match="name/type mismatch"),
    ):
        verifier._validate_archive_members(archive)


def test_release_verifier_normalizes_archive_open_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    verifier = _load_script("verify_release")
    archive_path = tmp_path / "release.zip"
    archive_path.write_bytes(b"present")

    def deny_open(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(verifier.zipfile, "ZipFile", deny_open)
    with pytest.raises(verifier.ReleaseVerificationError, match="invalid release ZIP"):
        verifier.verify_archive(archive_path, install_checks=False)


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
    checksum_path.write_text("0" * 64 + f"  {FIXTURE_SDIST_NAME}\n", encoding="utf-8")
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


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows does not expose portable POSIX executable permission bits",
)
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


def test_release_builder_rejects_nested_mixed_case_env_directory(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    secret = repository / "src/voicemd/.EnV.local/secret.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("TOKEN=tracked\n", encoding="utf-8")
    _git(repository, "add", "-f", secret.relative_to(repository).as_posix())
    _git(repository, "commit", "--quiet", "-m", "unsafe nested env")

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
    sdist = tmp_path / FIXTURE_SDIST_NAME
    _sdist(sdist, files={"integrations/typescript/node_modules/secret": b"bad"})

    with pytest.raises(verifier.ReleaseVerificationError, match="forbidden build/cache"):
        verifier.verify_sdist(
            sdist,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
        )


def test_sdist_rejects_nested_mixed_case_env_directory(tmp_path: Path):
    verifier = _load_script("verify_release")
    sdist = tmp_path / FIXTURE_SDIST_NAME
    _sdist(sdist, files={"docs/.EnV.local/secret.txt": b"TOKEN=leaked\n"})

    with pytest.raises(verifier.ReleaseVerificationError, match="forbidden build/cache"):
        verifier.verify_sdist(
            sdist,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
        )


def test_ordinary_sdist_build_excludes_env_path_components(tmp_path: Path):
    required_tools = {
        "build": "1.5.0",
        "setuptools": "84.0.0",
        "wheel": "0.48.0",
    }
    for distribution, expected in required_tools.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            pytest.skip(f"{distribution} is unavailable in this test environment")
        if actual != expected:
            pytest.skip(f"{distribution} {expected} is required, found {actual}")

    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    shutil.copytree(
        REPOSITORY_ROOT,
        source_root,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".env",
            ".env.*",
            "release",
            "build",
            "dist",
            "node_modules",
            "*.egg-info",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
        ),
    )
    secrets = {
        "docs/.EnV.local": "TOKEN=direct-file\n",
        "docs/nested/.EnV.local/secret.txt": "TOKEN=nested-docs\n",
        "integrations/python/.env/secret.txt": "TOKEN=nested-integration\n",
        "src/voicemd/resources/.eNv.production/secret.txt": "TOKEN=package-data\n",
    }
    for relative, content in secrets.items():
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    distributions = tmp_path / "dist"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--sdist",
            "--outdir",
            str(distributions),
        ],
        cwd=source_root,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1700000000"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    sdist = next(distributions.glob("*.tar.gz"))
    with tarfile.open(sdist, "r:gz") as archive:
        archived = {member.name for member in archive.getmembers()}
    assert not any(
        part.casefold() == ".env" or part.casefold().startswith(".env.")
        for name in archived
        for part in PurePosixPath(name).parts
    )
    verifier.verify_sdist(
        sdist,
        package_name="voicemd",
        package_version=__version__,
        source_root=source_root,
    )


def test_wheel_rejects_record_tampering(tmp_path: Path):
    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    package_root = source_root / "src/voicemd"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_bytes(b"tampered\n")
    (source_root / "LICENSE").write_bytes(b"fixture license\n")
    (source_root / "NOTICE").write_bytes(b"fixture notice\n")
    original = tmp_path / "original.whl"
    wheel = tmp_path / FIXTURE_WHEEL_NAME
    _wheel(original, files={"voicemd/__init__.py": b"original\n"})
    with zipfile.ZipFile(original) as archive:
        contents = {info.filename: archive.read(info) for info in archive.infolist()}
    contents["voicemd/__init__.py"] = b"tampered\n"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)

    with pytest.raises(verifier.ReleaseVerificationError, match="RECORD hash or size"):
        verifier.verify_wheel(
            wheel,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_root=source_root,
        )


def test_wheel_rejects_unexpected_payload(tmp_path: Path):
    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    package_root = source_root / "src/voicemd"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_bytes(b"")
    (source_root / "LICENSE").write_bytes(b"fixture license\n")
    (source_root / "NOTICE").write_bytes(b"fixture notice\n")
    wheel = tmp_path / FIXTURE_WHEEL_NAME
    _wheel(wheel, files={"voicemd/undeclared_payload.bin": b"unexpected"})

    with pytest.raises(verifier.ReleaseVerificationError, match="unexpected files"):
        verifier.verify_wheel(
            wheel,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_root=source_root,
        )


def test_sdist_rejects_unexpected_payload(tmp_path: Path):
    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    source_root.mkdir()
    pyproject = b"[build-system]\nrequires = ['setuptools']\n"
    (source_root / "pyproject.toml").write_bytes(pyproject)
    sdist = tmp_path / FIXTURE_SDIST_NAME
    _sdist(sdist, files={"pyproject.toml": pyproject, "setup.py": b"raise SystemExit\n"})

    with pytest.raises(verifier.ReleaseVerificationError, match="inventory mismatch"):
        verifier.verify_sdist(
            sdist,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_root=source_root,
        )


def test_sdist_source_sync_excludes_only_generated_azure_voice_artifacts(tmp_path: Path):
    verifier = _load_script("verify_release")
    ignored = tmp_path / "examples/azure-voice/artifacts/run/manifest.json"
    neighbor = tmp_path / "examples/azure-voice/artifacts-reviewed/manifest.json"
    ignored.parent.mkdir(parents=True)
    neighbor.parent.mkdir(parents=True)
    ignored.write_text("{}\n", encoding="utf-8")
    neighbor.write_text("{}\n", encoding="utf-8")

    sources = {path.relative_to(tmp_path).as_posix() for path in verifier._sdist_sync_sources(tmp_path)}

    assert "examples/azure-voice/artifacts/run/manifest.json" not in sources
    assert "examples/azure-voice/artifacts-reviewed/manifest.json" in sources
    first_snapshot = verifier.source_snapshot_sha256(tmp_path)
    ignored.write_text('{"ignored": true}\n', encoding="utf-8")
    assert verifier.source_snapshot_sha256(tmp_path) == first_snapshot
    neighbor.write_text('{"tracked": true}\n', encoding="utf-8")
    assert verifier.source_snapshot_sha256(tmp_path) != first_snapshot


def test_wheel_rejects_missing_azure_console_entrypoint(tmp_path: Path):
    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    package_root = source_root / "src/voicemd"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_bytes(b"")
    (source_root / "LICENSE").write_bytes(b"fixture license\n")
    (source_root / "NOTICE").write_bytes(b"fixture notice\n")
    wheel = tmp_path / FIXTURE_WHEEL_NAME
    _wheel(
        wheel,
        entry_points=b"[console_scripts]\nvoicemd = voicemd.cli:main\n",
    )

    with pytest.raises(verifier.ReleaseVerificationError, match="console entry point"):
        verifier.verify_wheel(
            wheel,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_root=source_root,
        )


def test_sdist_rejects_tampered_generated_setup_cfg(tmp_path: Path):
    verifier = _load_script("verify_release")
    source_root = tmp_path / "source"
    source_root.mkdir()
    pyproject = b"[build-system]\nrequires = ['setuptools']\n"
    (source_root / "pyproject.toml").write_bytes(pyproject)
    sdist = tmp_path / FIXTURE_SDIST_NAME
    _sdist(
        sdist,
        files={
            "pyproject.toml": pyproject,
            "setup.cfg": b"[options]\npy_modules = injected\n",
        },
    )

    with pytest.raises(verifier.ReleaseVerificationError, match="setup.cfg"):
        verifier.verify_sdist(
            sdist,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_root=source_root,
        )


@pytest.mark.parametrize(
    "names, message",
    [
        (["root/File.txt", "root/file.txt"], "case-insensitive"),
        (["root/caf\N{LATIN SMALL LETTER E WITH ACUTE}", "root/cafe\N{COMBINING ACUTE ACCENT}"], "Unicode-normalized"),
        (["root/CON.txt"], "Windows-reserved"),
    ],
)
def test_archive_member_portability_collisions_are_rejected(names: list[str], message: str):
    verifier = _load_script("verify_release")

    with pytest.raises(verifier.ReleaseVerificationError, match=message):
        verifier._validate_member_collisions(names, label="test archive")


def test_archive_member_count_is_bounded(monkeypatch: pytest.MonkeyPatch):
    verifier = _load_script("verify_release")
    monkeypatch.setattr(verifier, "MAX_ARCHIVE_MEMBERS", 1)

    with pytest.raises(verifier.ReleaseVerificationError, match="member limit"):
        verifier._validate_member_collisions(["root/a", "root/b"], label="test archive")


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
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://sensitive.example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("CUSTOM_CREDENTIAL", "custom-secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.invalid:8080")
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/corporate-ca.pem")

    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        assert cwd == root
        calls.append((command, env))
        if "compile" in command:
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("ASCII", encoding="utf-8")

    monkeypatch.setattr(verifier, "run", fake_run)
    verifier.verify_runtime(root, wheel, sdist, temporary)

    smoke_calls = [entry for entry in calls if "validate" in entry[0] or "compile" in entry[0]]
    pytest_call = next(entry for entry in calls if "pytest" in entry[0])
    assert all(env["VOICE_MD_ROOT"] == str(root) for _, env in smoke_calls)
    for variable in ("VOICE_MD", "VOICE_MD_HOME", "VOICE_MD_ROOT"):
        assert variable not in pytest_call[1]
    doctor_call = next(
        entry
        for entry in calls
        if Path(entry[0][0]).name in {"voicemd-azure", "voicemd-azure.exe"}
        and entry[0][-1] == "doctor"
    )
    assert doctor_call[1]["AZURE_OPENAI_ENDPOINT"] == (
        "https://release-smoke.openai.azure.invalid"
    )
    assert doctor_call[1]["AZURE_OPENAI_API_KEY"] == "release-smoke-placeholder"
    for command, environment in calls:
        for variable in (
            "OPENAI_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "CUSTOM_CREDENTIAL",
        ):
            assert variable not in environment
        if command != doctor_call[0]:
            assert "AZURE_OPENAI_ENDPOINT" not in environment
            assert "AZURE_OPENAI_API_KEY" not in environment
        assert environment["HTTPS_PROXY"] == "http://proxy.example.invalid:8080"
        assert environment["SSL_CERT_FILE"] == "/tmp/corporate-ca.pem"
        assert environment["HOME"] == str((temporary / "runtime-home").resolve())
        assert environment["USERPROFILE"] == environment["HOME"]
    venv_calls = [command for command, _ in calls if "venv" in command]
    assert len(venv_calls) == 2
    assert all("-I" in command for command in venv_calls)
    pip_calls = [command for command, _ in calls if "pip" in command]
    assert pip_calls and all("--isolated" in command for command in pip_calls)
    install_calls = [command for command in pip_calls if "install" in command]
    assert all("--no-input" in command and "--no-cache-dir" in command for command in install_calls)
    wheel_install = next(command for command in install_calls if str(wheel) in " ".join(command))
    assert f"{wheel}[azure-voice]" in wheel_install


def test_runtime_environment_is_allowlisted_and_drops_credential_families():
    verifier = _load_script("verify_release")
    environment = verifier.runtime_subprocess_environment(
        {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "https_proxy": "http://proxy.example.invalid:8080",
            "REQUESTS_CA_BUNDLE": "/tmp/ca.pem",
            "AZURE_OPENAI_API_KEY": "azure-secret",
            "OPENAI_API_KEY": "openai-secret",
            "AWS_SESSION_TOKEN": "aws-secret",
            "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/google.json",
            "GITHUB_TOKEN": "github-secret",
            "HOME": "/sensitive/home",
            "PYTHONPATH": "/untrusted/python",
            "CUSTOM_SECRET": "custom-secret",
        }
    )
    assert environment == {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "https_proxy": "http://proxy.example.invalid:8080",
        "REQUESTS_CA_BUNDLE": "/tmp/ca.pem",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


@pytest.mark.parametrize(
    "proxy",
    [
        "http://user:password@proxy.example.invalid:8080",
        "user:password@proxy.example.invalid:8080",
    ],
)
def test_runtime_environment_rejects_proxy_credentials(proxy: str):
    verifier = _load_script("verify_release")

    with pytest.raises(verifier.ReleaseVerificationError, match="credential-bearing proxy"):
        verifier.runtime_subprocess_environment({"PATH": "/usr/bin", "HTTPS_PROXY": proxy})


def test_runtime_subprocess_output_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    verifier = _load_script("verify_release")
    monkeypatch.setattr(verifier, "MAX_SUBPROCESS_OUTPUT", 128)
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(verifier.ReleaseVerificationError, match="command failed"):
        verifier.run(
            [
                sys.executable,
                "-c",
                "import sys;sys.stdout.write('A'*4096);sys.stderr.write('B'*4096);sys.exit(7)",
            ],
            cwd=tmp_path,
            env=verifier.runtime_subprocess_environment(home=home),
        )

    stderr = capsys.readouterr().err
    assert stderr.count("release verifier truncated subprocess output") == 2
    assert len(stderr) < 1024


def test_runtime_subprocess_has_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    verifier = _load_script("verify_release")
    monkeypatch.setattr(verifier, "SUBPROCESS_TIMEOUT_SECONDS", 0.05)
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(verifier.ReleaseVerificationError, match="command timed out"):
        verifier.run(
            [sys.executable, "-c", "import time;time.sleep(1)"],
            cwd=tmp_path,
            env=verifier.runtime_subprocess_environment(home=home),
        )


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows does not expose portable POSIX executable permission bits",
)
def test_source_snapshot_binds_executable_intent(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = tmp_path / "source"
    root.mkdir()
    script = root / "tool.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)
    regular_digest = verifier.source_snapshot_sha256(root)
    script.chmod(0o755)
    executable_digest = verifier.source_snapshot_sha256(root)
    assert regular_digest != executable_digest


def test_release_metadata_is_deterministic_and_verifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    builder = _load_script("build_release")
    verifier = _load_script("verify_release")
    repository = _repository(tmp_path / "repository")
    distributions = tmp_path / "distributions"
    distributions.mkdir()
    wheel = distributions / FIXTURE_WHEEL_NAME
    sdist = distributions / FIXTURE_SDIST_NAME
    _wheel(wheel)
    _sdist(sdist)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1787529600")

    first = tmp_path / "metadata-first"
    second = tmp_path / "metadata-second"
    source_revision = _head(repository)
    release_revision = source_revision
    first_paths = builder.generate_release_metadata(
        repository,
        distributions,
        first,
        source_revision=source_revision,
        release_revision=release_revision,
    )
    second_paths = builder.generate_release_metadata(
        repository,
        distributions,
        second,
        source_revision=source_revision,
        release_revision=release_revision,
    )
    assert [path.read_bytes() for path in first_paths] == [
        path.read_bytes() for path in second_paths
    ]
    provenance = json.loads(first_paths[1].read_text(encoding="utf-8"))
    tool_versions = provenance["predicate"]["buildDefinition"]["internalParameters"][
        "buildToolVersions"
    ]
    assert tool_versions["python"]

    verifier.verify_supply_chain_metadata(
        first,
        package_name="voicemd",
        package_version=FIXTURE_PACKAGE_VERSION,
        source_revision=source_revision,
        release_revision=release_revision,
        source_snapshot=verifier.git_source_snapshot_sha256(repository, source_revision),
        artifacts={wheel.name: _digest(wheel), sdist.name: _digest(sdist)},
    )


def test_release_metadata_rejects_unknown_source_revision(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")

    with pytest.raises(builder.ReleaseBuildError, match="Git command failed|Not a valid object"):
        builder._revision(repository, "f" * 40)


def test_release_metadata_rejects_mismatched_source_tree(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    source_revision = _head(repository)
    (repository / "README.md").write_text("new source\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "--quiet", "-m", "change source")
    release_revision = _head(repository)
    distributions = tmp_path / "distributions"
    distributions.mkdir()
    _wheel(distributions / FIXTURE_WHEEL_NAME)
    _sdist(distributions / FIXTURE_SDIST_NAME)

    with pytest.raises(builder.ReleaseBuildError, match="does not match --source-revision"):
        builder.generate_release_metadata(
            repository,
            distributions,
            tmp_path / "metadata",
            source_revision=source_revision,
            release_revision=release_revision,
        )


def test_release_metadata_allows_release_only_commit_after_source_revision(
    tmp_path: Path,
):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    source_revision = _head(repository)
    release_file = repository / "release/README.md"
    release_file.parent.mkdir()
    release_file.write_text("release metadata\n", encoding="utf-8")
    _git(repository, "add", "release/README.md")
    _git(repository, "commit", "--quiet", "-m", "release metadata")
    release_revision = _head(repository)
    distributions = tmp_path / "distributions"
    distributions.mkdir()
    _wheel(distributions / FIXTURE_WHEEL_NAME)
    _sdist(distributions / FIXTURE_SDIST_NAME)

    sbom, provenance = builder.generate_release_metadata(
        repository,
        distributions,
        tmp_path / "metadata",
        source_revision=source_revision,
        release_revision=release_revision,
    )

    assert sbom.is_file()
    statement = json.loads(provenance.read_text(encoding="utf-8"))
    internal = statement["predicate"]["buildDefinition"]["internalParameters"]
    assert internal["sourceRevision"] == source_revision
    assert internal["releaseRevision"] == release_revision


def test_release_metadata_tampering_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    builder = _load_script("build_release")
    verifier = _load_script("verify_release")
    repository = _repository(tmp_path / "repository")
    distributions = tmp_path / "distributions"
    distributions.mkdir()
    wheel = distributions / FIXTURE_WHEEL_NAME
    sdist = distributions / FIXTURE_SDIST_NAME
    _wheel(wheel)
    _sdist(sdist)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1787529600")
    metadata = tmp_path / "metadata"
    builder.generate_release_metadata(
        repository,
        distributions,
        metadata,
        source_revision=_head(repository),
        release_revision=_head(repository),
    )
    sbom_path = metadata / "SBOM.spdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["files"][0]["checksums"][0]["checksumValue"] = "0" * 64
    sbom_path.write_bytes(builder._canonical_json(sbom))

    with pytest.raises(verifier.ReleaseVerificationError, match="artifact inventory"):
        verifier.verify_supply_chain_metadata(
            metadata,
            package_name="voicemd",
            package_version=FIXTURE_PACKAGE_VERSION,
            source_revision=_head(repository),
            release_revision=_head(repository),
            source_snapshot=verifier.source_snapshot_sha256(repository),
            artifacts={wheel.name: _digest(wheel), sdist.name: _digest(sdist)},
        )


def test_outer_zip_provenance_binds_release_and_source_revisions(tmp_path: Path):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    archive = builder.build_release(repository, tmp_path / "release.zip")
    provenance = builder.generate_archive_provenance(
        repository, archive, tmp_path / "release.intoto.jsonl"
    )
    statement = json.loads(provenance.read_text(encoding="utf-8"))
    revision = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    internal = statement["predicate"]["buildDefinition"]["internalParameters"]
    assert internal["sourceRevision"] == revision
    assert internal["releaseRevision"] == revision
    assert statement["subject"] == [
        {"digest": {"sha256": _digest(archive)}, "name": archive.name}
    ]


def test_outer_zip_provenance_rejects_archive_from_a_different_release_tree(
    tmp_path: Path,
):
    builder = _load_script("build_release")
    repository = _repository(tmp_path / "repository")
    release_file = repository / "release/README.md"
    release_file.parent.mkdir()
    release_file.write_text("first release metadata\n", encoding="utf-8")
    _git(repository, "add", "release/README.md")
    _git(repository, "commit", "--quiet", "-m", "first release tree")
    archive = builder.build_release(repository, tmp_path / "release.zip")

    release_file.write_text("second release metadata\n", encoding="utf-8")
    _git(repository, "add", "release/README.md")
    _git(repository, "commit", "--quiet", "-m", "second release tree")

    with pytest.raises(builder.ReleaseBuildError, match="do(?:es)? not match"):
        builder.generate_archive_provenance(
            repository,
            archive,
            tmp_path / "release.intoto.jsonl",
        )


def test_outer_zip_provenance_is_verified_against_expected_commit(tmp_path: Path):
    builder = _load_script("build_release")
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "release.zip")
    build_info = json.loads((root / "release/BUILD_INFO.json").read_text(encoding="utf-8"))
    statement = builder._provenance_statement(
        {archive.name: _digest(archive)},
        package_name=build_info["package_name"],
        package_version=build_info["package_version"],
        source_revision=build_info["source_revision"],
        release_revision=build_info["release_revision"],
        source_snapshot=build_info["source_sha256"],
        build_type="urn:voicemd:build:source-release-zip:v1",
    )
    provenance = tmp_path / "release.intoto.jsonl"
    provenance.write_bytes(builder._canonical_json(statement))
    verifier.verify_archive_provenance(
        archive,
        provenance,
        expected_release_revision=build_info["release_revision"],
    )
    with pytest.raises(verifier.ReleaseVerificationError, match="release revision mismatch"):
        verifier.verify_archive_provenance(
            archive,
            provenance,
            expected_release_revision="c" * 40,
        )


def test_invalid_external_provenance_blocks_extraction_and_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    builder = _load_script("build_release")
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    archive = _zip_tree(root, tmp_path / "release.zip")
    build_info = json.loads((root / "release/BUILD_INFO.json").read_text(encoding="utf-8"))
    statement = builder._provenance_statement(
        {archive.name: "0" * 64},
        package_name=build_info["package_name"],
        package_version=build_info["package_version"],
        source_revision=build_info["source_revision"],
        release_revision=build_info["release_revision"],
        source_snapshot=build_info["source_sha256"],
        build_type="urn:voicemd:build:source-release-zip:v1",
    )
    provenance = tmp_path / "tampered.intoto.jsonl"
    provenance.write_bytes(builder._canonical_json(statement))
    extraction_attempted = False

    def forbidden_extract(*_args, **_kwargs):
        nonlocal extraction_attempted
        extraction_attempted = True
        raise AssertionError("archive extraction happened before provenance verification")

    monkeypatch.setattr(verifier, "_safe_extract", forbidden_extract)
    with pytest.raises(verifier.ReleaseVerificationError, match="subjects or checksums"):
        verifier.verify_release_archive(
            archive,
            install_checks=True,
            provenance_path=provenance,
            expected_release_revision=build_info["release_revision"],
        )
    assert extraction_attempted is False


def test_release_verifier_rejects_invalid_release_revision(tmp_path: Path):
    verifier = _load_script("verify_release")
    root = _release_tree(tmp_path, verifier)
    build_info_path = root / "release/BUILD_INFO.json"
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    build_info["release_revision"] = "main"
    build_info_path.write_text(json.dumps(build_info), encoding="utf-8")
    with pytest.raises(verifier.ReleaseVerificationError, match="release_revision"):
        verifier.load_build_info(root)


def test_release_verifier_cli_is_metadata_only_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    verifier = _load_script("verify_release")
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"fixture")
    calls: list[bool] = []

    def fake_verify(_archive: Path, *, install_checks: bool, **_kwargs) -> None:
        calls.append(install_checks)

    monkeypatch.setattr(verifier, "verify_release_archive", fake_verify)
    monkeypatch.setattr(sys, "argv", ["verify_release.py", str(archive)])
    assert verifier.main() == 0
    assert calls == [False]
    assert "PASS_METADATA_ONLY" in capsys.readouterr().out

    calls.clear()
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_release.py", str(archive), "--trusted-runtime-checks"],
    )
    assert verifier.main() == 0
    output = capsys.readouterr()
    assert calls == [True]
    assert "PASS_TRUSTED_RUNTIME" in output.out
    assert "not a sandbox or authenticity check" in output.err


def _docker_pattern_regex(pattern: str) -> re.Pattern[str]:
    """Translate the small Docker-ignore glob subset used by this repository."""

    pattern = pattern.rstrip("/")
    translated: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            translated.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            translated.append(".*")
            index += 2
        elif pattern[index] == "*":
            translated.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            translated.append("[^/]")
            index += 1
        elif pattern[index] == "[":
            closing = pattern.find("]", index + 1)
            if closing == -1:
                translated.append(r"\[")
                index += 1
            else:
                translated.append(pattern[index : closing + 1])
                index = closing + 1
        else:
            translated.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(translated) + "$")


def _docker_context_includes(relative: str, rules: list[str]) -> bool:
    included = True
    for raw_rule in rules:
        rule = raw_rule.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        pattern = rule[1:] if negated else rule
        if _docker_pattern_regex(pattern).fullmatch(relative):
            included = negated
    return included


def test_docker_context_allowlist_does_not_reopen_secret_paths():
    rules = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    first_final_deny = next(
        index for index, rule in enumerate(rules) if rule == "**/.[eE][nN][vV]"
    )
    assert all(not rule.startswith("!") for rule in rules[first_final_deny:])
    assert "!src/**" not in rules

    allowed = {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "NOTICE",
        "src/voicemd/cli.py",
        "src/voicemd/azure_voice/cli.py",
        "src/voicemd/resources/voice.schema.json",
        "src/voicemd/resources/azure_voice/scenarios.json",
        "src/voicemd/resources/skill/SKILL.md",
        "src/voicemd/resources/templates/full.VOICE.md",
        "integrations/docker/Dockerfile",
    }
    blocked = {
        ".env",
        "src/.env.local",
        "src/.EnV.local/secret.txt",
        "src/voicemd/.ENV.production/key",
        "src/voicemd/resources/.env/secret.txt",
        "src/voicemd/resources/skill/.credentials",
        "src/voicemd/__pycache__/cli.cpython-314.pyc",
        "src/voicemd.egg-info/PKG-INFO",
        "integrations/docker/README.md",
        "release/voicemd.whl",
    }
    assert all(_docker_context_includes(path, rules) for path in allowed)
    assert all(not _docker_context_includes(path, rules) for path in blocked)

    actual_context = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in REPOSITORY_ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(REPOSITORY_ROOT).parts
        and _docker_context_includes(path.relative_to(REPOSITORY_ROOT).as_posix(), rules)
    }
    expected_context = {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "NOTICE",
        "integrations/docker/Dockerfile",
        *(path.relative_to(REPOSITORY_ROOT).as_posix()
          for path in (REPOSITORY_ROOT / "src/voicemd").glob("*.py")),
        *(path.relative_to(REPOSITORY_ROOT).as_posix()
          for path in (REPOSITORY_ROOT / "src/voicemd/azure_voice").glob("*.py")),
        "src/voicemd/resources/voice.schema.json",
        *(path.relative_to(REPOSITORY_ROOT).as_posix()
          for path in (REPOSITORY_ROOT / "src/voicemd/resources/azure_voice").rglob("*")
          if path.is_file()),
        "src/voicemd/resources/skill/SKILL.md",
        *(path.relative_to(REPOSITORY_ROOT).as_posix()
          for path in (REPOSITORY_ROOT / "src/voicemd/resources/templates").glob("*.VOICE.md")),
    }
    assert actual_context == expected_context


def test_ci_and_publish_workflows_cover_release_gates_with_pinned_actions():
    ci_text = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    publish_text = (REPOSITORY_ROOT / ".github/workflows/publish.yml").read_text(
        encoding="utf-8"
    )
    ci = yaml.load(ci_text, Loader=yaml.BaseLoader)
    publish = yaml.load(publish_text, Loader=yaml.BaseLoader)

    assert ci["jobs"]["test"]["strategy"]["matrix"]["python-version"][-1] == "3.14"
    platforms = {
        item["os"]
        for item in ci["jobs"]["cross-platform"]["strategy"]["matrix"]["include"]
    }
    assert platforms == {"macos-latest", "windows-latest"}
    assert "docker run --detach" in ci_text
    assert "--trusted-runtime-checks" in ci_text
    assert "--no-isolation" in ci_text
    package_checkout = ci["jobs"]["package"]["steps"][0]
    assert package_checkout["with"] == {
        "fetch-depth": "0",
        "persist-credentials": "false",
    }
    assert (
        "node integrations/typescript/generated/conformance-verifier.js "
        "conformance/vectors.json"
    ) in ci_text

    publish_job = publish["jobs"]["publish"]
    assert publish_job["permissions"] == {"id-token": "write"}
    assert publish_job["environment"]["name"] == "pypi"
    assert "PYPI_TOKEN" not in publish_text
    assert "fetch-depth: 0" in publish_text
    assert "constraints/build.txt" in publish_text
    assert "SOURCE_DATE_EPOCH" in publish_text
    assert "git merge-base --is-ancestor" in publish_text
    assert "--normalize-sdist" in publish_text
    assert "cmp \"/tmp/dist-a/$WHEEL_NAME\" \"release/$WHEEL_NAME\"" in publish_text
    assert 'cp "release/$WHEEL_NAME" "release/$SDIST_NAME" dist/' in publish_text
    assert "npm --prefix integrations/typescript ci" in publish_text
    assert "git diff --exit-code -- integrations/typescript/generated" in publish_text
    assert "gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in (
        publish_text
    )
    uses = re.findall(r"(?m)^\s*-\s+uses:\s*[^@\s]+@([^\s#]+)", publish_text)
    assert uses
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in uses)

    dockerfile = (REPOSITORY_ROOT / "integrations/docker/Dockerfile").read_text(
        encoding="utf-8"
    )
    assert re.search(r"(?m)^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$", dockerfile)

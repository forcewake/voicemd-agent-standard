#!/usr/bin/env python3
"""Verify a VoiceMD release ZIP and its embedded release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REQUIRED = {
    "README.md",
    "START_HERE_RU.md",
    "PACKAGE_CONTENTS.md",
    "SPECIFICATION.md",
    "VOICE.md",
    ".voicemd-root",
    "schema/voice.schema.json",
    "pyproject.toml",
    "src/voicemd/cli.py",
    "src/voicemd/resources/skill/SKILL.md",
    ".agents/skills/voice-contract/SKILL.md",
    "integrations/http/openapi.yaml",
    "integrations/nemotron-voicechat/session_update.py",
    "release/SHA256SUMS",
}
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(root: Path) -> None:
    checksum_file = root / "release/SHA256SUMS"
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*")
        target = root / "release" / relative
        if not target.is_file():
            raise RuntimeError(f"checksum target missing: {target}")
        actual = sha256(target)
        if actual != expected:
            raise RuntimeError(f"checksum mismatch for {target.name}: {actual} != {expected}")


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if completed.returncode:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.expanduser().resolve()
    if not archive.is_file():
        raise SystemExit(f"archive not found: {archive}")

    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"corrupt ZIP member: {bad}")
        members = [Path(name) for name in zf.namelist() if not name.endswith("/")]
        roots = {member.parts[0] for member in members if member.parts}
        if len(roots) != 1:
            raise RuntimeError(f"archive must contain exactly one root directory: {sorted(roots)}")
        root_name = next(iter(roots))
        relative_members = {Path(*member.parts[1:]).as_posix() for member in members}
        missing = sorted(REQUIRED - relative_members)
        if missing:
            raise RuntimeError("required archive members missing: " + ", ".join(missing))
        polluted = [
            member.as_posix()
            for member in members
            if any(part in FORBIDDEN_PARTS or part.endswith(".egg-info") for part in member.parts)
            or member.suffix in {".pyc", ".pyo"}
        ]
        if polluted:
            raise RuntimeError("forbidden build/cache members found: " + ", ".join(polluted[:10]))

        with tempfile.TemporaryDirectory(prefix="voicemd-release-") as tmp:
            zf.extractall(tmp)
            root = Path(tmp) / root_name
            verify_checksums(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root / "src")
            smoke_env = env.copy()
            smoke_env["VOICE_MD_ROOT"] = str(root)
            run(
                [sys.executable, "-m", "voicemd", "validate", "--path", "VOICE.md", "--strict"],
                cwd=root,
                env=smoke_env,
            )
            run(
                [
                    sys.executable,
                    "-m",
                    "voicemd",
                    "compile",
                    "--path",
                    "VOICE.md",
                    "--profile",
                    "nemotron_voicechat",
                    "--format",
                    "nemotron-ascii",
                    "--compact",
                    "--max-chars",
                    "5000",
                    "--output",
                    str(root / ".voice/verify-nemotron.txt"),
                ],
                cwd=root,
                env=smoke_env,
            )
            prompt = (root / ".voice/verify-nemotron.txt").read_text(encoding="utf-8")
            if not prompt.isascii() or len(prompt) > 5000:
                raise RuntimeError("Nemotron smoke output is not valid ASCII within budget")
            run([sys.executable, "-m", "pytest", "-q"], cwd=root, env=env)

    print(f"PASS {archive} sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

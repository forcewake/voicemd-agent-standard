#!/usr/bin/env python3
"""Create a reproducible source ZIP from the repository root."""

from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist/voicemd-agent-standard.zip")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = (2026, 8, 24, 0, 0, 0)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == output:
                continue
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.suffix in EXCLUDED_SUFFIXES:
                continue
            info = zipfile.ZipInfo(str(Path(root.name) / relative).replace(os.sep, "/"), timestamp)
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

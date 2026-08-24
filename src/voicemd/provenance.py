from __future__ import annotations

import hashlib
from pathlib import Path


def _content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_label(path: str | Path, *, root: str | Path | None = None) -> str:
    """Return provenance that is useful without exposing an absolute filesystem path."""

    resolved = Path(path).resolve()
    if root is not None:
        try:
            relative = resolved.relative_to(Path(root).resolve())
        except ValueError:
            pass
        else:
            return relative.as_posix()
    return f"external:{resolved.name}@sha256:{_content_digest(resolved)[:12]}"


def source_labels(
    paths: list[Path], *, root: str | Path | None = None
) -> list[str]:
    return [source_label(path, root=root) for path in paths]

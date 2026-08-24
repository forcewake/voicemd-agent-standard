from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class FrontmatterError(ValueError):
    pass


def parse_text(text: str, *, source: str = "<memory>") -> tuple[dict[str, Any], str]:
    """Parse optional YAML frontmatter and return metadata plus Markdown body."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip()

    end = normalized.find("\n---\n", 4)
    if end == -1:
        if normalized.endswith("\n---"):
            end = len(normalized) - 4
            body_start = len(normalized)
        else:
            raise FrontmatterError(f"{source}: opening frontmatter delimiter has no closing delimiter")
    else:
        body_start = end + len("\n---\n")

    raw = normalized[4:end]
    try:
        loaded = yaml.safe_load(raw) if raw.strip() else {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"{source}: invalid YAML frontmatter: {exc}") from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise FrontmatterError(f"{source}: YAML frontmatter must be a mapping")
    return loaded, normalized[body_start:].strip()


def parse_file(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FrontmatterError(f"{path}: VOICE.md must be UTF-8") from exc
    return parse_text(text, source=str(path))

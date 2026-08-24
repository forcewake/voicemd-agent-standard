from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import yaml


class FrontmatterError(ValueError):
    pass


class _VoiceLoader(yaml.SafeLoader):
    """Safe YAML loader restricted to deterministic JSON-compatible values."""


# PyYAML follows YAML 1.1 and otherwise treats yes/no/on/off as booleans and
# date-shaped scalars as datetime objects. VOICE.md uses the YAML 1.2 boolean
# spelling and leaves timestamps as strings so every parsed value can be
# represented in strict JSON.
_VoiceLoader.yaml_implicit_resolvers = {
    key: list(resolvers) for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for first_char, resolvers in list(_VoiceLoader.yaml_implicit_resolvers.items()):
    _VoiceLoader.yaml_implicit_resolvers[first_char] = [
        (tag, resolver)
        for tag, resolver in resolvers
        if tag not in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
    ]
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", flags=re.IGNORECASE),
    list("tTfF"),
)


def _construct_mapping(
    loader: _VoiceLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_VoiceLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _assert_json_compatible(
    value: Any, *, source: str, path: str = "frontmatter", active: set[int] | None = None
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FrontmatterError(f"{source}: {path} contains a non-finite number")
        return
    if active is None:
        active = set()
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise FrontmatterError(f"{source}: {path} contains a recursive YAML alias")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _assert_json_compatible(item, source=source, path=f"{path}[{index}]", active=active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise FrontmatterError(f"{source}: {path} contains a recursive YAML alias")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise FrontmatterError(f"{source}: {path} contains a non-string key {key!r}")
                child = f"{path}.{key}" if path else key
                _assert_json_compatible(item, source=source, path=child, active=active)
        finally:
            active.remove(identity)
        return
    raise FrontmatterError(
        f"{source}: {path} contains unsupported YAML value of type {type(value).__name__}"
    )


def parse_text(text: str, *, source: str = "<memory>") -> tuple[dict[str, Any], str]:
    """Parse optional YAML frontmatter and return metadata plus Markdown body."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip()

    if normalized.startswith("---\n---\n"):
        end = 4
        body_start = 8
    else:
        end = normalized.find("\n---\n", 4)
    if end == -1:
        if normalized.endswith("\n---"):
            end = len(normalized) - 4
            body_start = len(normalized)
        else:
            raise FrontmatterError(
                f"{source}: opening frontmatter delimiter has no closing delimiter"
            )
    elif not normalized.startswith("---\n---\n"):
        body_start = end + len("\n---\n")

    raw = normalized[4:end]
    try:
        loaded = yaml.load(raw, Loader=_VoiceLoader) if raw.strip() else {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"{source}: invalid YAML frontmatter: {exc}") from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise FrontmatterError(f"{source}: YAML frontmatter must be a mapping")
    _assert_json_compatible(loaded, source=source)
    return loaded, normalized[body_start:].strip()


def parse_file(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FrontmatterError(f"{path}: VOICE.md must be UTF-8") from exc
    return parse_text(text, source=str(path))

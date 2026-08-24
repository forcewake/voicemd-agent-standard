from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent


class FrontmatterError(ValueError):
    pass


class _VoiceLoader(yaml.SafeLoader):
    """Safe YAML loader restricted to deterministic JSON-compatible values."""

    def __init__(
        self,
        stream: str,
        *,
        max_yaml_nodes: int,
        max_yaml_aliases: int,
    ) -> None:
        super().__init__(stream)
        self._max_yaml_nodes = max_yaml_nodes
        self._max_yaml_aliases = max_yaml_aliases
        self._yaml_nodes = 0
        self._yaml_aliases = 0

    def compose_node(self, parent: yaml.Node | None, index: Any) -> yaml.Node:
        event = self.peek_event()
        if getattr(event, "tag", None) is not None:
            raise yaml.composer.ComposerError(
                None,
                None,
                "explicit YAML tags are not supported by the VoiceMD JSON-schema subset",
                event.start_mark,
            )
        self._yaml_nodes += 1
        if self._yaml_nodes > self._max_yaml_nodes:
            raise yaml.composer.ComposerError(
                None,
                None,
                f"YAML node limit exceeded ({self._max_yaml_nodes})",
                self.peek_event().start_mark,
            )
        if self.check_event(AliasEvent):
            self._yaml_aliases += 1
            if self._yaml_aliases > self._max_yaml_aliases:
                raise yaml.composer.ComposerError(
                    None,
                    None,
                    f"YAML alias reference limit exceeded ({self._max_yaml_aliases})",
                    self.peek_event().start_mark,
                )
        return super().compose_node(parent, index)


# PyYAML follows YAML 1.1 scalar resolution. VOICE.md instead uses the YAML 1.2
# JSON schema: only lowercase JSON booleans/null and JSON-number spellings are
# implicit typed scalars. Legacy octal/sexagesimal/underscore numbers and
# date-shaped scalars remain strings.
_VoiceLoader.yaml_implicit_resolvers = {
    key: list(resolvers) for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for first_char, resolvers in list(_VoiceLoader.yaml_implicit_resolvers.items()):
    _VoiceLoader.yaml_implicit_resolvers[first_char] = [
        (tag, resolver)
        for tag, resolver in resolvers
        if tag
        not in {
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:float",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:null",
            "tag:yaml.org,2002:timestamp",
        }
    ]
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$"),
    list("tf"),
)
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:null",
    re.compile(r"^null$"),
    ["n"],
)
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^-?(?:0|[1-9][0-9]*)$"),
    list("-0123456789"),
)
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)$"
    ),
    list("-0123456789"),
)
_VoiceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"),
    list("-+."),
)


def _construct_mapping(
    loader: _VoiceLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    if any(key_node.tag == "tag:yaml.org,2002:merge" for key_node, _ in node.value):
        raise yaml.constructor.ConstructorError(
            "while constructing a mapping",
            node.start_mark,
            "YAML merge keys are not supported",
            node.start_mark,
        )
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


def _consume_expanded_node(
    visited: list[int], *, source: str, max_yaml_nodes: int
) -> None:
    visited[0] += 1
    if visited[0] > max_yaml_nodes:
        raise FrontmatterError(f"{source}: YAML expanded node limit exceeded ({max_yaml_nodes})")


def _assert_json_compatible(
    value: Any,
    *,
    source: str,
    max_yaml_nodes: int,
    path: str = "frontmatter",
    active: set[int] | None = None,
    visited: list[int] | None = None,
) -> None:
    if visited is None:
        visited = [0]
    _consume_expanded_node(visited, source=source, max_yaml_nodes=max_yaml_nodes)
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise FrontmatterError(f"{source}: {path} contains a lone Unicode surrogate") from exc
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
                _assert_json_compatible(
                    item,
                    source=source,
                    max_yaml_nodes=max_yaml_nodes,
                    path=f"{path}[{index}]",
                    active=active,
                    visited=visited,
                )
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
                _consume_expanded_node(
                    visited,
                    source=source,
                    max_yaml_nodes=max_yaml_nodes,
                )
                if not isinstance(key, str):
                    raise FrontmatterError(f"{source}: {path} contains a non-string key {key!r}")
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise FrontmatterError(
                        f"{source}: {path} contains a key with a lone Unicode surrogate"
                    ) from exc
                child = f"{path}.{key}" if path else key
                _assert_json_compatible(
                    item,
                    source=source,
                    max_yaml_nodes=max_yaml_nodes,
                    path=child,
                    active=active,
                    visited=visited,
                )
        finally:
            active.remove(identity)
        return
    raise FrontmatterError(
        f"{source}: {path} contains unsupported YAML value of type {type(value).__name__}"
    )


def _positive_limit(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FrontmatterError(f"{name} must be a positive integer")
    return value


def parse_text(
    text: str,
    *,
    source: str = "<memory>",
    max_yaml_nodes: int = 20_000,
    max_yaml_aliases: int = 100,
) -> tuple[dict[str, Any], str]:
    """Parse optional YAML frontmatter and return metadata plus Markdown body."""
    max_yaml_nodes = _positive_limit(max_yaml_nodes, name="max_yaml_nodes")
    max_yaml_aliases = _positive_limit(max_yaml_aliases, name="max_yaml_aliases")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.removeprefix("\ufeff")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip(" \t\n\r")

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
        if raw.strip():
            loader = _VoiceLoader(
                raw,
                max_yaml_nodes=max_yaml_nodes,
                max_yaml_aliases=max_yaml_aliases,
            )
            try:
                loaded = loader.get_single_data()
            finally:
                loader.dispose()
        else:
            loaded = {}
    except (RecursionError, yaml.YAMLError) as exc:
        raise FrontmatterError(f"{source}: invalid YAML frontmatter: {exc}") from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise FrontmatterError(f"{source}: YAML frontmatter must be a mapping")
    _assert_json_compatible(loaded, source=source, max_yaml_nodes=max_yaml_nodes)
    return loaded, normalized[body_start:].strip(" \t\n\r")


def parse_file(
    path: Path,
    *,
    max_file_bytes: int = 1_048_576,
    max_yaml_nodes: int = 20_000,
    max_yaml_aliases: int = 100,
) -> tuple[dict[str, Any], str]:
    max_file_bytes = _positive_limit(max_file_bytes, name="max_file_bytes")
    try:
        with path.open("rb") as source_file:
            raw = source_file.read(max_file_bytes + 1)
    except OSError as exc:
        raise FrontmatterError(f"{path}: unable to read VOICE.md source") from exc
    if len(raw) > max_file_bytes:
        raise FrontmatterError(f"{path}: source file exceeds byte limit ({max_file_bytes})")
    return parse_bytes(
        raw,
        source=str(path),
        max_yaml_nodes=max_yaml_nodes,
        max_yaml_aliases=max_yaml_aliases,
    )


def parse_bytes(
    raw: bytes,
    *,
    source: str = "<memory>",
    max_yaml_nodes: int = 20_000,
    max_yaml_aliases: int = 100,
) -> tuple[dict[str, Any], str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontmatterError(f"{source}: VOICE.md must be UTF-8") from exc
    return parse_text(
        text,
        source=source,
        max_yaml_nodes=max_yaml_nodes,
        max_yaml_aliases=max_yaml_aliases,
    )

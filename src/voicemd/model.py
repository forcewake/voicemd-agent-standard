from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    metadata: dict[str, Any]
    body: str
    level: int
    via: str = "discovery"


@dataclass
class ResolvedVoiceContract:
    data: dict[str, Any]
    bodies: list[tuple[Path, str]] = field(default_factory=list)
    sources: list[SourceDocument] = field(default_factory=list)
    dependency_edges: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.data.get("name") or "Unnamed voice contract")

    @property
    def body(self) -> str:
        trim = " \t\n\r"
        return "\n\n".join(
            body.strip(trim) for _, body in self.bodies if body.strip(trim)
        ).strip(trim)

    def source_paths(self) -> list[Path]:
        return [source.path for source in self.sources]

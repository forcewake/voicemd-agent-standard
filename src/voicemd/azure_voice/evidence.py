from __future__ import annotations

import hashlib
import html
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .common import (
    MAX_OUTPUT_AUDIO_BYTES,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    bytes_sha256,
    canonical_json_bytes,
    safe_relative_artifact,
    strict_json_loads,
)

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = MAX_OUTPUT_AUDIO_BYTES + 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PACKAGED_EVIDENCE_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "azure_voice"
    / "evidence.schema.json"
)
SOURCE_EVIDENCE_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "azure-voice"
    / "evidence.schema.json"
)
FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "bearer_token",
        "client_secret",
        "endpoint",
        "endpoint_url",
        "headers",
        "secret",
        "token",
        "url",
    }
)


def safe_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (normalized or "run")[:80]


def create_run_directory(
    output_root: str | Path,
    *,
    lane: str,
    deployment: str,
    label: str,
) -> Path:
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    name = "-".join(
        (
            stamp,
            safe_slug(lane),
            safe_slug(deployment),
            safe_slug(label),
            uuid.uuid4().hex[:8],
        )
    )
    run_dir = root / name
    run_dir.mkdir(mode=0o755)
    return run_dir


def write_event_trace(path: str | Path, events: tuple[dict[str, object], ...]) -> None:
    lines = b"".join(canonical_json_bytes(event) + b"\n" for event in events)
    atomic_write_bytes(path, lines)


def artifact_descriptor(run_dir: Path, path: Path, *, media_type: str) -> dict[str, object]:
    resolved_run = run_dir.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_run)
    except ValueError as exc:
        raise ValueError("artifact is outside its run directory") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact must be a regular non-symlink file")
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds the evidence size limit")
    data = path.read_bytes()
    return {
        "path": relative.as_posix(),
        "media_type": media_type,
        "bytes": size,
        "sha256": bytes_sha256(data),
    }


def write_checksums(run_dir: Path, artifacts: dict[str, dict[str, object]]) -> Path:
    lines: list[str] = []
    for name, descriptor in sorted(artifacts.items()):
        if name == "checksums":
            continue
        path = descriptor.get("path")
        digest = descriptor.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise TypeError(f"artifact descriptor {name} is incomplete")
        safe_relative_artifact(path)
        lines.append(f"{digest}  {path}")
    target = run_dir / "checksums.sha256"
    atomic_write_text(target, "\n".join(lines) + "\n")
    return target


def write_manifest(run_dir: Path, manifest: dict[str, object]) -> Path:
    validate_manifest_payload(manifest)
    target = run_dir / "manifest.json"
    atomic_write_json(target, manifest)
    if target.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("evidence manifest exceeds the size limit")
    return target


def _scan_forbidden_keys(value: object, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            if key.casefold() in FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"evidence contains forbidden secret-bearing field {path}.{key}")
            _scan_forbidden_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_keys(child, path=f"{path}[{index}]")


@lru_cache(maxsize=1)
def _manifest_validator() -> Draft202012Validator:
    schema_path = (
        PACKAGED_EVIDENCE_SCHEMA
        if PACKAGED_EVIDENCE_SCHEMA.is_file()
        else SOURCE_EVIDENCE_SCHEMA
    )
    if not schema_path.is_file():
        raise FileNotFoundError("packaged Azure voice evidence schema is missing")
    schema = strict_json_loads(schema_path.read_bytes())
    if not isinstance(schema, dict):
        raise TypeError("Azure voice evidence schema must be a JSON object")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_manifest_payload(manifest: dict[str, object]) -> None:
    """Reject secrets and schema-invalid evidence before writing any manifest bytes."""

    _scan_forbidden_keys(manifest)
    errors = sorted(
        _manifest_validator().iter_errors(manifest),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
        raise ValueError(f"Azure voice evidence schema violation at {location}: {error.message}")


def _read_manifest(path: Path) -> dict[str, object]:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("evidence manifest exceeds the size limit")
    payload = strict_json_loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise TypeError("evidence manifest must be a JSON object")
    return payload


def verify_manifest(path: str | Path) -> dict[str, object]:
    manifest_path = Path(path).resolve()
    manifest = _read_manifest(manifest_path)
    validate_manifest_payload(manifest)
    endpoint_hash = manifest.get("endpoint_sha256")
    if not isinstance(endpoint_hash, str) or not SHA256_RE.fullmatch(endpoint_hash):
        raise ValueError("evidence endpoint fingerprint is missing or invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise TypeError("evidence manifest has no artifacts")
    verified: dict[str, object] = {}
    verified_paths: set[str] = set()
    run_dir = manifest_path.parent
    for name, raw_descriptor in artifacts.items():
        if not isinstance(name, str) or not isinstance(raw_descriptor, dict):
            raise TypeError("evidence artifact descriptors must be named objects")
        relative_text = raw_descriptor.get("path")
        expected_hash = raw_descriptor.get("sha256")
        expected_size = raw_descriptor.get("bytes")
        if not isinstance(relative_text, str):
            raise TypeError(f"artifact {name} has no relative path")
        relative = safe_relative_artifact(relative_text)
        if relative_text in verified_paths:
            raise ValueError(f"artifact {name} reuses another artifact path")
        verified_paths.add(relative_text)
        target = run_dir.joinpath(*relative.parts)
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"artifact {name} is missing or is a symlink")
        resolved = target.resolve()
        try:
            resolved.relative_to(run_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"artifact {name} escapes its run directory") from exc
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise ValueError(f"artifact {name} exceeds the size limit")
        if not isinstance(expected_size, int) or expected_size != size:
            raise ValueError(f"artifact {name} size mismatch")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise ValueError(f"artifact {name} has an invalid SHA-256")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected_hash:
            raise ValueError(f"artifact {name} SHA-256 mismatch")
        verified[name] = {"bytes": size, "sha256": digest}

    checksums_descriptor = artifacts.get("checksums")
    if not isinstance(checksums_descriptor, dict):
        raise TypeError("evidence manifest has no checksums artifact")
    checksums_relative = checksums_descriptor.get("path")
    if checksums_relative != "checksums.sha256":
        raise ValueError("checksums artifact path must be checksums.sha256")
    checksum_lines = (run_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    declared_checksums: dict[str, str] = {}
    for number, line in enumerate(checksum_lines, start=1):
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError(f"invalid checksums.sha256 line {number}")
        digest, relative_text = fields
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 on checksums.sha256 line {number}")
        safe_relative_artifact(relative_text)
        if relative_text in declared_checksums:
            raise ValueError(f"duplicate checksums.sha256 path: {relative_text}")
        declared_checksums[relative_text] = digest
    expected_checksums = {
        str(descriptor["path"]): str(descriptor["sha256"])
        for name, descriptor in artifacts.items()
        if name != "checksums" and isinstance(descriptor, dict)
    }
    if declared_checksums != expected_checksums:
        raise ValueError("checksums.sha256 does not match the manifest artifact inventory")

    def verify_link(
        *,
        record: object,
        field: str,
        artifact_name: str,
        label: str,
    ) -> None:
        if not isinstance(record, dict) or field not in record:
            return
        expected = record[field]
        if expected is None and field == "scenario_sha256":
            return
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise ValueError(f"{label} is missing or invalid")
        artifact = verified.get(artifact_name)
        if not isinstance(artifact, dict):
            raise TypeError(f"{label} has no bound {artifact_name} artifact")
        if artifact.get("sha256") != expected:
            raise ValueError(f"{label} does not match the {artifact_name} artifact")

    voice = manifest.get("voice")
    verify_link(
        record=voice,
        field="contract_sha256",
        artifact_name="voice_resolved",
        label="VOICE.md resolved contract SHA-256",
    )
    if isinstance(voice, dict) and voice.get("applied") is True:
        verify_link(
            record=voice,
            field="compiled_sha256",
            artifact_name="voice_compiled",
            label="VOICE.md compiled prompt SHA-256",
        )
    verify_link(
        record=manifest.get("base_instructions"),
        field="sha256",
        artifact_name="base_instructions",
        label="base instructions SHA-256",
    )
    verify_link(
        record=manifest.get("request"),
        field="instructions_sha256",
        artifact_name="session_instructions",
        label="session instructions SHA-256",
    )
    response = manifest.get("response")
    verify_link(
        record=response,
        field="transcript_sha256",
        artifact_name="output_transcript",
        label="output transcript SHA-256",
    )
    verify_link(
        record=response,
        field="rendered_transcript_sha256",
        artifact_name="raw_transcript",
        label="rendered raw transcript SHA-256",
    )
    verify_link(
        record=response,
        field="spoken_transcript_sha256",
        artifact_name="output_transcript",
        label="spoken response transcript SHA-256",
    )
    verify_link(
        record=response,
        field="audio_sha256",
        artifact_name="output_audio",
        label="output audio SHA-256",
    )
    verify_link(
        record=manifest,
        field="scenario_sha256",
        artifact_name="scenario",
        label="scenario SHA-256",
    )
    return {
        "status": "verified",
        "manifest": manifest_path.name,
        "lane": manifest.get("lane"),
        "deployment": manifest.get("deployment"),
        "artifacts": verified,
    }


def verify_tree(root: str | Path) -> dict[str, object]:
    evidence_root = Path(root).resolve()
    manifests = sorted(evidence_root.glob("*/manifest.json"))
    if not manifests:
        raise ValueError("no evidence manifests found")
    results = [verify_manifest(path) for path in manifests]
    return {"status": "verified", "manifests": len(results), "results": results}


def _artifact_href(manifest_path: Path, descriptor: object, output_path: Path) -> str | None:
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str):
        return None
    target = manifest_path.parent / descriptor["path"]
    relative = os.path.relpath(target, output_path.parent)
    return Path(relative).as_posix()


def render_gallery(root: str | Path, output: str | Path | None = None) -> Path:
    evidence_root = Path(root).resolve()
    manifests = sorted(evidence_root.glob("*/manifest.json"))
    if not manifests:
        raise ValueError("no evidence manifests found")
    output_path = Path(output).resolve() if output else evidence_root / "index.html"
    cards: list[str] = []
    for manifest_path in manifests:
        verify_manifest(manifest_path)
        manifest = _read_manifest(manifest_path)
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, dict)
        transcript_descriptor = artifacts.get("output_transcript") or artifacts.get(
            "raw_transcript"
        )
        transcript = ""
        if isinstance(transcript_descriptor, dict) and isinstance(
            transcript_descriptor.get("path"), str
        ):
            transcript = (manifest_path.parent / transcript_descriptor["path"]).read_text(
                encoding="utf-8"
            )
        audio_href = _artifact_href(
            manifest_path,
            artifacts.get("output_audio"),
            output_path,
        )
        voice = manifest.get("voice")
        voice_name = "raw transcript boundary"
        if isinstance(voice, dict):
            voice_name = str(voice.get("label") or voice.get("activation_reason") or voice_name)
        timing = manifest.get("timings_ms")
        total = timing.get("total") if isinstance(timing, dict) else None
        audio_markup = (
            f'<audio controls preload="none" src="{html.escape(audio_href, quote=True)}"></audio>'
            if audio_href
            else '<div class="no-audio">No output audio for this lane</div>'
        )
        assertions = manifest.get("assertions")
        passed = assertions.get("passed") if isinstance(assertions, dict) else None
        status_class = "pass" if passed is True else "fail" if passed is False else "neutral"
        status_text = "PASS" if passed is True else "FAIL" if passed is False else "UNSCORED"
        cards.append(
            "\n".join(
                (
                    '<article class="card">',
                    (
                        '<div class="eyebrow">'
                        f'{html.escape(str(manifest.get("lane", "unknown")))} · '
                        f'{html.escape(str(manifest.get("deployment", "unknown")))}'
                        "</div>"
                    ),
                    f"<h2>{html.escape(voice_name)}</h2>",
                    f'<div class="status {status_class}">{status_text}</div>',
                    audio_markup,
                    f"<p class=\"transcript\">{html.escape(transcript)}</p>",
                    '<dl class="metrics">',
                    f"<dt>Total</dt><dd>{html.escape(str(total))} ms</dd>",
                    f"<dt>Scenario</dt><dd>{html.escape(str(manifest.get('scenario_id') or 'custom'))}</dd>",
                    "</dl>",
                    "</article>",
                )
            )
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoiceMD Azure Voice Proof Lab</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 0; background: #071018; color: #edf6ff; }}
main {{ max-width: 1240px; margin: auto; padding: 48px 24px 80px; }}
h1 {{ margin: 0; font-size: clamp(2rem, 6vw, 4.8rem); letter-spacing: -.05em; }}
.lead {{ max-width: 760px; color: #9fb4c8; font-size: 1.05rem; line-height: 1.6; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(300px,1fr)); gap: 16px; margin-top: 36px; }}
.card {{ position: relative; padding: 22px; border: 1px solid #24384a; border-radius: 18px; background: linear-gradient(145deg,#0d1a25,#0a141d); box-shadow: 0 18px 50px #0005; }}
.card h2 {{ margin: 7px 70px 18px 0; font-size: 1.35rem; }}
.eyebrow {{ color: #6bdcff; font: 700 .72rem ui-monospace, monospace; text-transform: uppercase; letter-spacing: .08em; }}
.status {{ position: absolute; right: 18px; top: 18px; padding: 5px 9px; border-radius: 99px; font: 800 .7rem ui-monospace, monospace; }}
.pass {{ color: #07130d; background: #68eca2; }} .fail {{ color: #260508; background: #ff7380; }} .neutral {{ background: #435362; }}
audio {{ width: 100%; margin: 4px 0 16px; }} .no-audio {{ color: #74899c; margin: 12px 0 20px; }}
.transcript {{ min-height: 5.5em; color: #d9e6f2; line-height: 1.55; }}
.metrics {{ display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 20px 0 0; padding-top: 14px; border-top: 1px solid #223544; font: .82rem ui-monospace, monospace; }}
.metrics dt {{ color: #7890a5; }} .metrics dd {{ margin: 0; text-align: right; }}
</style>
</head>
<body><main>
<div class="eyebrow">Reproducible evidence · VoiceMD</div>
<h1>Azure Voice Proof Lab</h1>
<p class="lead">Same facts and acoustic voice, different communication contracts. Every card is backed by a sanitized manifest, artifact hashes, and deterministic checks. Raw transcription remains outside VoiceMD.</p>
<section class="grid">{''.join(cards)}</section>
</main></body></html>
"""
    atomic_write_text(output_path, document)
    return output_path

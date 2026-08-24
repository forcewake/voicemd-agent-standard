"""Verify the closed, secret-free GitHub Pages evidence snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

SNAPSHOT_REL = Path("proof/azure-2026-08-24")
SUMS_SHA256 = "423b21467a8aa8cb2dfc76f8fe97ade909c5b4cef250b1bf820a238900aec430"
RUN_FILE_COUNT = 116
RUN_BYTES = 12_233_657
CHECKSUMMED_FILE_COUNT = 117
MAX_FILE_BYTES = 2_100_000
MAX_SITE_BYTES = 20_000_000

PROMPT_SHA256 = "93e28a873dab4fc9f0e70de2431316e34a2537b1876c7846e6d07bf912d71e35"
SCENARIO_SHA256 = "7a5611cd0e21f5a45f4f63ac339d1c3d61b73dcc88c4e07c228fb5b788e9064c"
ENDPOINT_SHA256 = "e205294e8755ccefccd9b9ca81aecf3050fceca2af329be5b1895ea05dcc70cc"
INPUT_AUDIO_SHA256 = "fd9774bc0b6cdeb2d8cfd5e6b5bfd8364ec179f6966e2e8f9765d5a08e15482a"
RAW_TRANSCRIPT_SHA256 = "f3a4cb6ea4194925410fa6aa116ed860833d3d1a550734a94da641fbf82dc7c8"

ALLOWED_PUBLIC_URLS = {
    "https://github.com/forcewake/voicemd-agent-standard#readme",
    "https://github.com/forcewake/voicemd-agent-standard/blob/main/SPECIFICATION.md",
    "https://pypi.org/project/voicemd/",
}
STATIC_SITE_FILES = {
    "azure-proof.html",
    "index.html",
    "assets/app.js",
    "assets/site.css",
}
L3_FIXTURES = {
    "incident_commander": (
        "The service is degraded. No data loss is reported. The ninety-fifth percentile latency "
        "is 840 milliseconds. Keep the rollout paused while we verify the cause."
    ),
    "calm_support": (
        "I know this disruption is frustrating. The service is degraded, with 840-millisecond "
        "latency, but no data loss is reported. Please keep the rollout paused while the team "
        "investigates the unconfirmed cause."
    ),
    "executive_brief": (
        "Decision: keep the rollout paused. The service is degraded, with 840-millisecond latency "
        "and no reported data loss. The cause is unconfirmed, so resuming now creates avoidable "
        "operational risk."
    ),
}
FEATURED_AUDIO = {
    "audio/incident-commander.wav": (
        "20260824T194204.308057Z-realtime-gpt-realtime-2.1-incident_commander-6a90db07",
        "89dd63f0aed0e2092d3ca8e785e01bcdd5faef209ea030a18cab23ea30a2b212",
    ),
    "audio/calm-support.wav": (
        "20260824T194223.718529Z-realtime-gpt-realtime-2.1-calm_support-93fda5ca",
        "e1b39d7e88dfcae7e225ed8ced877a10cb50a6754703be4ca609cd2b386b0d1f",
    ),
    "audio/executive-brief.wav": (
        "20260824T194241.914739Z-realtime-gpt-realtime-2.1-executive_brief-cb7442f4",
        "5f2616555d12f00441553ccb169559dbb964a6112a4ef7693135ce71d5172881",
    ),
}

SAFE_FILE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".sha256",
    ".txt",
    ".wav",
}
FORBIDDEN_JSON_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "baseurl",
    "clientsecret",
    "endpoint",
    "endpointurl",
    "idtoken",
    "password",
    "refreshtoken",
    "secret",
    "uri",
    "url",
    "websocketurl",
}
FORBIDDEN_BYTES = (
    re.compile(rb"(?:https?|wss?)://", re.IGNORECASE),
    re.compile(rb"authorization\s*[:=]", re.IGNORECASE),
    re.compile(rb"bearer\s+[a-z0-9._~-]+", re.IGNORECASE),
    re.compile(rb"api[-_ ]?key\s*[:=]", re.IGNORECASE),
    re.compile(rb"client[-_ ]?secret\s*[:=]", re.IGNORECASE),
    re.compile(rb"(?:access|refresh)[-_ ]?token\s*[:=]", re.IGNORECASE),
    re.compile(rb"[a-z0-9-]+\.openai\.azure\.com", re.IGNORECASE),
)
FORBIDDEN_JS_SINKS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
)


@dataclass(frozen=True)
class ExpectedRun:
    run_id: str
    kind: str
    contract: str
    lane: str
    deployment: str
    passed: bool
    failed_checks: tuple[str, ...] = ()


EXPECTED_RUNS = (
    ExpectedRun(
        "20260824T194157.533898Z-audio-completion-gpt-audio-1.5-incident_commander-6e683a5e",
        "matrix",
        "incident_commander",
        "audio-completion",
        "gpt-audio-1.5",
        True,
    ),
    ExpectedRun(
        "20260824T194204.308057Z-realtime-gpt-realtime-2.1-incident_commander-6a90db07",
        "matrix",
        "incident_commander",
        "realtime",
        "gpt-realtime-2.1",
        True,
    ),
    ExpectedRun(
        "20260824T194209.980765Z-realtime-gpt-realtime-2.1-mini-incident_commander-b1d59f5e",
        "matrix",
        "incident_commander",
        "realtime",
        "gpt-realtime-2.1-mini",
        True,
    ),
    ExpectedRun(
        "20260824T194216.327146Z-audio-completion-gpt-audio-1.5-calm_support-846e36c8",
        "matrix",
        "calm_support",
        "audio-completion",
        "gpt-audio-1.5",
        False,
        ("contains-any:3",),
    ),
    ExpectedRun(
        "20260824T194223.718529Z-realtime-gpt-realtime-2.1-calm_support-93fda5ca",
        "matrix",
        "calm_support",
        "realtime",
        "gpt-realtime-2.1",
        True,
    ),
    ExpectedRun(
        "20260824T194229.518482Z-realtime-gpt-realtime-2.1-mini-calm_support-31016aec",
        "matrix",
        "calm_support",
        "realtime",
        "gpt-realtime-2.1-mini",
        False,
        ("voicemd-lint-clean",),
    ),
    ExpectedRun(
        "20260824T194235.019161Z-audio-completion-gpt-audio-1.5-executive_brief-eb468df0",
        "matrix",
        "executive_brief",
        "audio-completion",
        "gpt-audio-1.5",
        False,
        ("contains-any:1", "contains-any:3"),
    ),
    ExpectedRun(
        "20260824T194241.914739Z-realtime-gpt-realtime-2.1-executive_brief-cb7442f4",
        "matrix",
        "executive_brief",
        "realtime",
        "gpt-realtime-2.1",
        False,
        ("voicemd-lint-clean",),
    ),
    ExpectedRun(
        "20260824T194245.805194Z-realtime-gpt-realtime-2.1-mini-executive_brief-b02007bd",
        "matrix",
        "executive_brief",
        "realtime",
        "gpt-realtime-2.1-mini",
        True,
    ),
    ExpectedRun(
        "20260824T194314.030856Z-transcription-gpt-live-transcribe-raw-73bf939c",
        "transcription",
        "raw transcript boundary",
        "transcription",
        "gpt-live-transcribe",
        True,
    ),
    ExpectedRun(
        "20260824T194341.852993Z-showcase-gpt-realtime-2.1-executive_brief-08187965",
        "showcase",
        "executive_brief",
        "transcribe-to-realtime",
        "gpt-realtime-2.1",
        True,
    ),
)


class VerificationError(ValueError):
    """Raised when the public site violates its closed evidence contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise VerificationError(f"non-finite JSON number: {value}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid JSON in {path}: {error}") from error


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def inspect_json(value: Any, source: Path) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = normalized_key(key)
            if not normalized.endswith("sha256"):
                require(normalized not in FORBIDDEN_JSON_KEYS, f"secret-bearing field in {source}: {key}")
            inspect_json(child, source)
    elif isinstance(value, list):
        for child in value:
            inspect_json(child, source)


def validate_posix_path(raw: str, *, allow_proof_index: bool = False) -> PurePosixPath:
    require(bool(re.fullmatch(r"[A-Za-z0-9._/-]+", raw)), f"unsafe inventory path: {raw}")
    path = PurePosixPath(raw)
    require(not path.is_absolute(), f"absolute inventory path: {raw}")
    require(".." not in path.parts and "." not in path.parts, f"traversal in inventory path: {raw}")
    require(not any(part.startswith(".") for part in path.parts), f"hidden inventory path: {raw}")
    allowed = path.parts[0] == "runs" or (allow_proof_index and raw == "proof-index.json")
    require(allowed, f"inventory path outside immutable snapshot: {raw}")
    return path


def parse_sums(path: Path) -> dict[str, str]:
    require(sha256_file(path) == SUMS_SHA256, "SHA256SUMS does not match its code-anchored digest")
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        require(match is not None, f"malformed SHA256SUMS line {line_number}")
        digest, raw_path = match.groups()
        validate_posix_path(raw_path, allow_proof_index=True)
        require(raw_path not in result, f"duplicate SHA256SUMS path: {raw_path}")
        result[raw_path] = digest
    require(len(result) == CHECKSUMMED_FILE_COUNT, "unexpected SHA256SUMS entry count")
    return result


def collect_site_files(site: Path) -> dict[str, Path]:
    require(site.exists() and site.is_dir(), f"site directory does not exist: {site}")
    require(not site.is_symlink(), "site root must not be a symlink")
    files: dict[str, Path] = {}
    for root, directories, names in os.walk(site, followlinks=False):
        root_path = Path(root)
        for directory in directories:
            candidate = root_path / directory
            require(not candidate.is_symlink(), f"directory symlink is forbidden: {candidate}")
            require(not directory.startswith("."), f"hidden directory is forbidden: {candidate}")
        for name in names:
            candidate = root_path / name
            relative = candidate.relative_to(site).as_posix()
            file_stat = candidate.lstat()
            require(stat.S_ISREG(file_stat.st_mode), f"non-regular file is forbidden: {relative}")
            require(file_stat.st_nlink == 1, f"hard-linked file is forbidden: {relative}")
            require(not name.startswith("."), f"hidden file is forbidden: {relative}")
            suffix = candidate.suffix.lower()
            require(
                suffix in SAFE_FILE_SUFFIXES or name == "SHA256SUMS",
                f"unexpected file type: {relative}",
            )
            require(file_stat.st_size <= MAX_FILE_BYTES, f"file exceeds size cap: {relative}")
            files[relative] = candidate
    require(sum(path.stat().st_size for path in files.values()) <= MAX_SITE_BYTES, "site exceeds size cap")
    return files


def exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == expected, f"unexpected {label} fields: {sorted(set(value) ^ expected)}")


def verify_index(index: dict[str, Any]) -> None:
    exact_keys(
        index,
        {
            "$schema",
            "schema_version",
            "snapshot_id",
            "captured_date",
            "provider",
            "voicemd_version",
            "inventory",
            "matrix",
            "transcription_boundary",
            "featured_audio",
            "runs",
        },
        "proof index",
    )
    require(index["$schema"] == "urn:voicemd:pages-proof-index:1", "wrong proof index schema")
    require(index["schema_version"] == 1, "wrong proof index version")
    require(index["snapshot_id"] == "azure-2026-08-24", "wrong snapshot id")
    require(index["captured_date"] == "2026-08-24", "wrong captured date")
    require(index["provider"] == "azure-openai", "wrong provider")
    require(index["voicemd_version"] == "0.1.0a3", "wrong VoiceMD version")

    inventory = index["inventory"]
    exact_keys(
        inventory,
        {"checksums", "run_count", "run_file_count", "run_bytes", "checksummed_file_count"},
        "inventory",
    )
    require(inventory == {
        "checksums": "SHA256SUMS",
        "run_count": 11,
        "run_file_count": RUN_FILE_COUNT,
        "run_bytes": RUN_BYTES,
        "checksummed_file_count": CHECKSUMMED_FILE_COUNT,
    }, "proof inventory declaration changed")

    matrix = index["matrix"]
    exact_keys(
        matrix,
        {"scenario_id", "contracts", "columns", "controls", "expected_results"},
        "matrix",
    )
    require(matrix["scenario_id"] == "degraded-service-en", "wrong matrix scenario")
    require(
        matrix["contracts"] == ["incident_commander", "calm_support", "executive_brief"],
        "wrong matrix contracts",
    )
    expected_columns = [
        {"lane": "audio-completion", "deployment": "gpt-audio-1.5", "label": "Audio completion"},
        {"lane": "realtime", "deployment": "gpt-realtime-2.1", "label": "Realtime"},
        {"lane": "realtime", "deployment": "gpt-realtime-2.1-mini", "label": "Realtime mini"},
    ]
    require(matrix["columns"] == expected_columns, "wrong matrix columns")
    require(matrix["controls"] == {
        "acoustic_voice": "alloy",
        "prompt_sha256": PROMPT_SHA256,
        "scenario_sha256": SCENARIO_SHA256,
        "endpoint_sha256": ENDPOINT_SHA256,
    }, "matrix controls changed")
    require(matrix["expected_results"] == {"total": 9, "passed": 5, "failed": 4}, "wrong matrix counts")

    boundary = index["transcription_boundary"]
    exact_keys(
        boundary,
        {"input_audio_published", "input_audio_bytes", "input_audio_sha256", "raw_transcript_sha256", "statement"},
        "transcription boundary",
    )
    require(boundary["input_audio_published"] is False, "input audio must remain unpublished")
    require(boundary["input_audio_bytes"] == 758_400, "input audio byte count changed")
    require(boundary["input_audio_sha256"] == INPUT_AUDIO_SHA256, "input audio digest changed")
    require(boundary["raw_transcript_sha256"] == RAW_TRANSCRIPT_SHA256, "raw transcript digest changed")

    require(isinstance(index["featured_audio"], list), "featured_audio must be a list")
    require(len(index["featured_audio"]) == len(FEATURED_AUDIO), "wrong featured audio count")
    for item in index["featured_audio"]:
        exact_keys(item, {"path", "source_run_id", "sha256"}, "featured audio entry")
        require(item["path"] in FEATURED_AUDIO, f"unexpected featured audio: {item['path']}")
        binding = (item["source_run_id"], item["sha256"])
        require(binding == FEATURED_AUDIO[item["path"]], "featured audio binding changed")

    require(isinstance(index["runs"], list), "runs must be a list")
    require(len(index["runs"]) == len(EXPECTED_RUNS), "wrong run count")
    run_keys = {
        "run_id",
        "kind",
        "contract",
        "lane",
        "deployment",
        "passed",
        "failed_checks",
        "manifest",
        "transcript",
        "raw_transcript",
        "audio",
    }
    for item, expected in zip(index["runs"], EXPECTED_RUNS, strict=True):
        exact_keys(item, run_keys, "run entry")
        require(item["run_id"] == expected.run_id, "run order or id changed")
        for field in ("kind", "contract", "lane", "deployment", "passed"):
            require(item[field] == getattr(expected, field), f"run {expected.run_id} changed {field}")
        require(tuple(item["failed_checks"]) == expected.failed_checks, f"run {expected.run_id} failed checks changed")
        prefix = f"runs/{expected.run_id}/"
        require(item["manifest"] == f"{prefix}manifest.json", "manifest path changed")
        transcript_name = "raw.transcript.txt" if expected.kind == "transcription" else "output.transcript.txt"
        require(item["transcript"] == f"{prefix}{transcript_name}", "transcript path changed")
        expected_raw = f"{prefix}raw.transcript.txt" if expected.kind == "showcase" else None
        require(item["raw_transcript"] == expected_raw, "raw transcript path changed")
        expected_audio = None if expected.kind == "transcription" else f"{prefix}output.wav"
        require(item["audio"] == expected_audio, "audio path changed")


def parse_run_sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        require(match is not None, f"malformed run checksum line {line_number}: {path}")
        digest, name = match.groups()
        require(name not in result, f"duplicate run checksum path: {path}/{name}")
        result[name] = digest
    return result


def verify_manifest(snapshot: Path, item: dict[str, Any], expected: ExpectedRun) -> dict[str, Any]:
    manifest_path = snapshot / item["manifest"]
    manifest = load_json(manifest_path)
    require(isinstance(manifest, dict), f"manifest is not an object: {manifest_path}")
    inspect_json(manifest, manifest_path)
    require(manifest.get("run_id") == expected.run_id, f"manifest run id mismatch: {expected.run_id}")
    require(manifest.get("provider") == "azure-openai", f"manifest provider mismatch: {expected.run_id}")
    require(manifest.get("provider_model") == expected.deployment, f"provider model mismatch: {expected.run_id}")
    require(manifest.get("deployment") == expected.deployment, f"deployment mismatch: {expected.run_id}")
    require(manifest.get("lane") == expected.lane, f"lane mismatch: {expected.run_id}")
    require(manifest.get("voice", {}).get("label") == expected.contract, f"contract mismatch: {expected.run_id}")
    require(manifest.get("assertions", {}).get("passed") is expected.passed, f"result mismatch: {expected.run_id}")
    failed = tuple(
        check.get("id")
        for check in manifest.get("assertions", {}).get("checks", [])
        if check.get("passed") is False
    )
    require(failed == expected.failed_checks, f"failed checks mismatch: {expected.run_id}")

    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict), f"artifacts missing: {expected.run_id}")
    run_directory = manifest_path.parent
    expected_names = {"manifest.json"}
    for descriptor in artifacts.values():
        require(isinstance(descriptor, dict), f"invalid artifact descriptor: {expected.run_id}")
        exact_keys(descriptor, {"bytes", "media_type", "path", "sha256"}, "artifact descriptor")
        artifact_name = descriptor["path"]
        require(bool(re.fullmatch(r"[A-Za-z0-9._-]+", artifact_name)), f"unsafe artifact path: {artifact_name}")
        artifact_path = run_directory / artifact_name
        require(artifact_path.is_file(), f"missing artifact: {artifact_path}")
        require(artifact_path.stat().st_size == descriptor["bytes"], f"artifact size mismatch: {artifact_path}")
        require(sha256_file(artifact_path) == descriptor["sha256"], f"artifact hash mismatch: {artifact_path}")
        expected_names.add(artifact_name)
    actual_names = {path.name for path in run_directory.iterdir() if path.is_file()}
    require(actual_names == expected_names, f"run inventory mismatch: {expected.run_id}")

    run_sums = parse_run_sums(run_directory / "checksums.sha256")
    expected_sums = {
        descriptor["path"]: descriptor["sha256"]
        for descriptor in artifacts.values()
        if descriptor["path"] != "checksums.sha256"
    }
    require(run_sums == expected_sums, f"run checksums do not match manifest: {expected.run_id}")
    return manifest


def verify_matrix(manifests: dict[str, dict[str, Any]]) -> None:
    matrix = [expected for expected in EXPECTED_RUNS if expected.kind == "matrix"]
    require(sum(expected.passed for expected in matrix) == 5, "matrix pass count changed")
    require(sum(not expected.passed for expected in matrix) == 4, "matrix failure count changed")
    expected_cells = {
        (contract, lane, deployment)
        for contract in ("incident_commander", "calm_support", "executive_brief")
        for lane, deployment in (
            ("audio-completion", "gpt-audio-1.5"),
            ("realtime", "gpt-realtime-2.1"),
            ("realtime", "gpt-realtime-2.1-mini"),
        )
    }
    actual_cells = {(item.contract, item.lane, item.deployment) for item in matrix}
    require(actual_cells == expected_cells, "matrix is not the exact 3x3 Cartesian product")

    expected_facts = {
        "cause_confirmed": False,
        "data_loss_reported": False,
        "latency_p95_ms": 840,
        "rollout_status": "paused",
        "service_status": "degraded",
    }
    for expected in matrix:
        manifest = manifests[expected.run_id]
        require(manifest.get("scenario_id") == "degraded-service-en", "matrix scenario id changed")
        require(manifest.get("scenario_sha256") == SCENARIO_SHA256, "matrix scenario hash changed")
        require(manifest.get("prompt_sha256") == PROMPT_SHA256, "matrix prompt hash changed")
        require(manifest.get("endpoint_sha256") == ENDPOINT_SHA256, "matrix endpoint fingerprint changed")
        require(manifest.get("request", {}).get("acoustic_voice") == "alloy", "matrix acoustic voice changed")
        require(manifest.get("facts") == expected_facts, "matrix facts changed")
        require(manifest.get("voice", {}).get("applied") is True, "VoiceMD was not applied to matrix response")


def verify_boundary(manifests: dict[str, dict[str, Any]]) -> None:
    transcription = manifests[EXPECTED_RUNS[9].run_id]
    showcase = manifests[EXPECTED_RUNS[10].run_id]
    require(transcription["voice"]["applied"] is False, "VoiceMD must not alter raw transcription")
    require(transcription["request"]["input_audio_bytes"] == 758_400, "transcription input byte count changed")
    require(transcription["request"]["input_audio_sha256"] == INPUT_AUDIO_SHA256, "transcription input hash changed")
    require(transcription["response"]["rendered_transcript_sha256"] == RAW_TRANSCRIPT_SHA256, "raw transcript hash changed")
    require(showcase["request"]["input_audio_sha256"] == INPUT_AUDIO_SHA256, "showcase input hash changed")
    require(showcase["response"]["rendered_transcript_sha256"] == RAW_TRANSCRIPT_SHA256, "showcase raw transcript changed")
    require(showcase["transcription_voice_boundary"]["applied"] is False, "showcase changed raw transcription")
    require(showcase["voice"]["applied"] is True, "showcase did not apply VoiceMD to response")
    fingerprints = showcase["connection_fingerprints"]
    require(set(fingerprints.values()) == {ENDPOINT_SHA256}, "showcase connection fingerprint changed")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.references: list[str] = []
        self.forbidden_elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            require(element_id not in self.ids, f"duplicate HTML id: {element_id}")
            self.ids.add(element_id)
        for name in ("href", "src", "data-proof-index"):
            value = attributes.get(name)
            if value:
                self.references.append(value)
        if tag in {"base", "embed", "form", "iframe", "object"}:
            self.forbidden_elements.append(tag)
        if tag == "script":
            require(bool(attributes.get("src")), "inline scripts are forbidden")


def verify_html_page(site: Path, page_name: str) -> str:
    html = (site / page_name).read_text(encoding="utf-8")
    require("immutable" not in html.lower(), f"mutable Pages claim in {page_name}")
    parser = PageParser()
    parser.feed(html)
    require(
        not parser.forbidden_elements,
        f"forbidden HTML elements in {page_name}: {parser.forbidden_elements}",
    )
    for reference in parser.references:
        if reference.startswith("https://"):
            require(reference in ALLOWED_PUBLIC_URLS, f"unexpected public URL: {reference}")
            continue
        require(not reference.startswith(("http://", "//", "data:", "javascript:")), f"unsafe URL: {reference}")
        if reference.startswith("#"):
            require(reference[1:] in parser.ids, f"broken HTML fragment: {reference}")
            continue
        raw_path = reference.split("#", 1)[0].split("?", 1)[0].removeprefix("./")
        path = PurePosixPath(raw_path)
        require(not path.is_absolute() and ".." not in path.parts, f"unsafe local URL: {reference}")
        require((site / Path(*path.parts)).is_file(), f"broken local URL: {reference}")
    return html


def verify_pages(site: Path) -> None:
    landing = verify_html_page(site, "index.html")
    evidence = verify_html_page(site, "azure-proof.html")
    require("5 PASS" not in landing and "4 FAIL" not in landing, "result tally leaked into landing")
    require("data-page=\"azure-proof\"" in evidence, "Azure proof page marker is missing")

    repository_root = Path(__file__).resolve().parents[1]
    for contract, fixture in L3_FIXTURES.items():
        require(landing.count(fixture) == 1, f"landing fixture mismatch: {contract}")
        encoded = f"response: {json.dumps(fixture, ensure_ascii=False)}"
        sources = (
            repository_root / "examples" / "azure-voice" / "contracts" / contract / "VOICE.md",
            repository_root
            / "src"
            / "voicemd"
            / "resources"
            / "azure_voice"
            / "contracts"
            / contract
            / "VOICE.md",
        )
        for source in sources:
            require(encoded in source.read_text(encoding="utf-8"), f"fixture drift: {source}")

    javascript = (site / "assets/app.js").read_text(encoding="utf-8")
    for sink in FORBIDDEN_JS_SINKS:
        require(sink not in javascript, f"unsafe DOM sink in app.js: {sink}")
    require(".textContent" in javascript, "app.js must render transcript text with textContent")


def verify_secret_boundary(snapshot: Path, checksum_paths: set[str]) -> None:
    for relative in sorted(checksum_paths):
        path = snapshot / relative
        data = path.read_bytes()
        for pattern in FORBIDDEN_BYTES:
            require(pattern.search(data) is None, f"URL or secret-like material in proof file: {relative}")
        if path.suffix == ".json":
            inspect_json(load_json(path), path)
        elif path.suffix == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line, object_pairs_hook=strict_object, parse_constant=reject_constant)
                except json.JSONDecodeError as error:
                    raise VerificationError(f"invalid JSONL in {relative}:{line_number}: {error}") from error
                inspect_json(value, path)


def verify(site: Path) -> dict[str, int]:
    require(not site.is_symlink(), "site root must not be a symlink")
    site = site.resolve(strict=True)
    snapshot = site / SNAPSHOT_REL
    sums_path = snapshot / "SHA256SUMS"
    checksums = parse_sums(sums_path)
    files = collect_site_files(site)

    snapshot_files = {f"{SNAPSHOT_REL.as_posix()}/{path}" for path in checksums}
    expected_files = STATIC_SITE_FILES | set(FEATURED_AUDIO) | snapshot_files | {
        f"{SNAPSHOT_REL.as_posix()}/SHA256SUMS"
    }
    require(set(files) == expected_files, f"site inventory mismatch: {sorted(set(files) ^ expected_files)}")

    run_paths = [path for path in checksums if path.startswith("runs/")]
    require(len(run_paths) == RUN_FILE_COUNT, "run file count changed")
    require(sum((snapshot / path).stat().st_size for path in run_paths) == RUN_BYTES, "run byte count changed")
    for relative, expected_hash in checksums.items():
        path = snapshot / relative
        require(path.is_file(), f"missing checksummed file: {relative}")
        require(sha256_file(path) == expected_hash, f"snapshot hash mismatch: {relative}")

    index_path = snapshot / "proof-index.json"
    index = load_json(index_path)
    require(isinstance(index, dict), "proof index must be an object")
    inspect_json(index, index_path)
    verify_index(index)

    manifests: dict[str, dict[str, Any]] = {}
    for item, expected in zip(index["runs"], EXPECTED_RUNS, strict=True):
        manifests[expected.run_id] = verify_manifest(snapshot, item, expected)
    verify_matrix(manifests)
    verify_boundary(manifests)

    for relative, (source_run_id, expected_hash) in FEATURED_AUDIO.items():
        featured_path = site / relative
        require(sha256_file(featured_path) == expected_hash, f"featured audio hash mismatch: {relative}")
        source_path = snapshot / "runs" / source_run_id / "output.wav"
        require(featured_path.read_bytes() == source_path.read_bytes(), f"featured audio differs from source: {relative}")

    verify_secret_boundary(snapshot, set(checksums))
    verify_pages(site)
    return {
        "site_files": len(files),
        "checksummed_files": len(checksums),
        "runs": len(EXPECTED_RUNS),
        "matrix_passed": 5,
        "matrix_failed": 4,
        "site_bytes": sum(path.stat().st_size for path in files.values()),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", default="site", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = verify(args.site)
    except (OSError, VerificationError) as error:
        print(f"Pages verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "verified", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

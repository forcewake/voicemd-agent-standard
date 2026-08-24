from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, RLock
from urllib.parse import parse_qs, urlparse

from .compiler import compile_contract
from .contract import DEFAULT_MAX_SOURCE_FILE_BYTES, ContractError, load_contract
from .discovery import discover_paths
from .linter import lint_text
from .normalization import is_nonblank_selector
from .provenance import source_label
from .validator import validate_contract, validate_selected_contract

DEFAULT_MAX_BODY_BYTES = 262_144
DEFAULT_MAX_WORKERS = 16
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0


def _load_validated_contract_config(
    *,
    root: Path,
    path: Path | str | list[Path | str] | None,
    include_global: bool,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
):
    contract = load_contract(
        start=root,
        explicit=path,
        include_global=include_global,
    )
    validation = validate_contract(contract, strict=False)
    if not validation.ok:
        raise ContractError("active VOICE.md failed validation")
    selected_validation = validate_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        strict=False,
    )
    if not selected_validation.ok:
        raise ValueError("selected VOICE.md failed validation")
    return contract


def _load_validated_contract(
    server: object,
    *,
    profile: str | None = None,
    audience: str | None = None,
    surface: str | None = None,
    tone: str | None = None,
):
    try:
        current_state = _server_source_state(server, server.voice_contract)
    except OSError:
        current_state = None
    if current_state != server.voice_source_state:
        with server.voice_reload_lock:
            try:
                current_state = _server_source_state(server, server.voice_contract)
            except OSError:
                current_state = None
            if current_state != server.voice_source_state:
                contract = _load_validated_contract_config(
                    root=server.voice_root,
                    path=server.voice_path,
                    include_global=server.include_global,
                )
                server.voice_contract = contract
                server.voice_source_state = _server_source_state(server, contract)

    contract = server.voice_contract
    selected_validation = validate_selected_contract(
        contract,
        profile=profile,
        audience=audience,
        surface=surface,
        tone=tone,
        strict=False,
    )
    if not selected_validation.ok:
        raise ValueError("selected VOICE.md failed validation")
    return contract


def _bounded_source_digest(path: Path) -> str:
    digest = hashlib.sha256()
    remaining = DEFAULT_MAX_SOURCE_FILE_BYTES + 1
    try:
        with path.open("rb") as stream:
            while remaining > 0:
                chunk = stream.read(min(65_536, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
    except OSError as exc:
        return f"unreadable:{exc.errno}"
    if remaining == 0:
        return "oversize"
    return digest.hexdigest()


def _path_state(path: Path, *, include_content: bool) -> tuple[object, ...]:
    lexical = Path(os.path.abspath(path.expanduser()))
    try:
        status = lexical.lstat()
    except OSError as exc:
        return (str(lexical), "missing", exc.errno)

    link_target: str | None = None
    if stat.S_ISLNK(status.st_mode):
        try:
            link_target = os.readlink(lexical)
        except OSError as exc:
            link_target = f"unreadable:{exc.errno}"
    try:
        resolved = lexical.resolve(strict=True)
        resolved_label = str(resolved)
    except (OSError, RuntimeError, ValueError) as exc:
        resolved = None
        resolved_label = f"unresolved:{type(exc).__name__}"

    content_digest: str | None = None
    # Do not open a newly retargeted path merely to compute cache state. Its
    # identity forces a fail-closed reload, which applies source-root/.env checks.
    if (
        include_content
        and resolved == lexical
        and stat.S_ISREG(status.st_mode)
        and status.st_size <= DEFAULT_MAX_SOURCE_FILE_BYTES
    ):
        content_digest = _bounded_source_digest(lexical)

    return (
        str(lexical),
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
        link_target,
        resolved_label,
        content_digest,
    )


def _server_source_state(server: object, contract: object) -> tuple[tuple[object, ...], ...]:
    discovered = discover_paths(
        start=server.voice_root,
        explicit=server.voice_path,
        include_global=server.include_global,
    )
    result: list[tuple[object, ...]] = []
    key = lambda item: str(item).encode("utf-8")
    for path in sorted(set(discovered), key=key):
        result.append(("discovered", *_path_state(path, include_content=False)))
    for path in sorted(set(contract.dependency_edges), key=key):
        result.append(("dependency", *_path_state(path, include_content=False)))
    for path in sorted(set(contract.source_paths()), key=key):
        result.append(("source", *_path_state(path, include_content=True)))
    return tuple(result)


def _query_parameters(raw_query: str, *, allowed: set[str]) -> dict[str, str]:
    if len(raw_query) > 8192:
        raise ValueError("query string is too long")
    values = parse_qs(raw_query, keep_blank_values=True, max_num_fields=32)
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown query parameter: {min(unknown)}")
    repeated = [key for key, items in values.items() if len(items) != 1]
    if repeated:
        raise ValueError(f"query parameter must occur once: {min(repeated)}")
    return {key: items[0] for key, items in values.items()}


def _query_boolean(query: dict[str, str], key: str, *, default: bool) -> bool:
    value = query.get(key)
    if value is None:
        return default
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{key} must be exactly 'true' or 'false'")


def _query_integer(query: dict[str, str], key: str) -> int | None:
    value = query.get(key)
    if value is None:
        return None
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError(f"{key} must be a base-10 integer")
    return int(value)


def _strict_json_loads(raw: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(raw, parse_constant=reject_constant)


def _lint_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        raise TypeError("JSON body must contain a text string")
    allowed = {"text", "profile", "audience", "surface", "tone"}
    unknown = set(value) - allowed
    if unknown:
        raise TypeError(f"unknown JSON field: {min(unknown)}")
    for key in allowed - {"text"}:
        selected = value.get(key)
        if selected is not None and not is_nonblank_selector(selected):
            raise TypeError(f"{key} must be a non-empty string")
    return value


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *args: object,
        max_workers: int = DEFAULT_MAX_WORKERS,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        **kwargs: object,
    ):
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if (
            isinstance(request_timeout_seconds, bool)
            or not isinstance(request_timeout_seconds, (int, float))
            or not math.isfinite(request_timeout_seconds)
            or request_timeout_seconds <= 0
        ):
            raise ValueError("request_timeout_seconds must be a positive finite number")
        self._worker_slots = BoundedSemaphore(max_workers)
        self.request_timeout_seconds = request_timeout_seconds
        super().__init__(*args, **kwargs)

    def process_request(self, request: object, client_address: object) -> None:
        if not self._worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request: object, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(self.request_timeout_seconds)
        return request, client_address


class VoiceRequestHandler(BaseHTTPRequestHandler):
    server_version = "VoiceMD/0.1"

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _contract(
        self,
        *,
        profile: str | None = None,
        audience: str | None = None,
        surface: str | None = None,
        tone: str | None = None,
    ):
        return _load_validated_contract(
            self.server,
            profile=profile,
            audience=audience,
            surface=surface,
            tone=tone,
        )

    def _source_name(self, path: Path) -> str:
        root = self.server.voice_root  # type: ignore[attr-defined]
        return source_label(path, root=root)

    def _request_error(self, status: HTTPStatus, code: str, exc: Exception | None = None) -> None:
        if exc is not None and not getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            self.log_error("%s: %s", type(exc).__name__, exc)
        self._json(status, {"error": code})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                _query_parameters(parsed.query, allowed=set())
                self._contract()
                self._json(
                    HTTPStatus.OK,
                    {"status": "ok", "service": "voicemd", "contract": "valid"},
                )
                return
            if parsed.path == "/v1/voice/contract":
                _query_parameters(parsed.query, allowed=set())
                contract = self._contract()
                self._json(
                    HTTPStatus.OK,
                    {
                        "contract": contract.data,
                        "body": contract.body,
                        "sources": [self._source_name(path) for path in contract.source_paths()],
                    },
                )
                return
            if parsed.path == "/v1/voice/prompt":
                query = _query_parameters(
                    parsed.query,
                    allowed={"profile", "audience", "surface", "tone", "format", "compact", "max_chars"},
                )
                contract = self._contract(
                    profile=query.get("profile"),
                    audience=query.get("audience"),
                    surface=query.get("surface"),
                    tone=query.get("tone"),
                )
                prompt = compile_contract(
                    contract,
                    profile=query.get("profile"),
                    audience=query.get("audience"),
                    surface=query.get("surface"),
                    tone=query.get("tone"),
                    output_format=query.get("format", "prompt"),
                    compact=_query_boolean(query, "compact", default=False),
                    max_chars=_query_integer(query, "max_chars"),
                )
                self._json(HTTPStatus.OK, {"prompt": prompt})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (ContractError, FileNotFoundError) as exc:
            self._request_error(HTTPStatus.SERVICE_UNAVAILABLE, "contract_unavailable", exc)
        except (TypeError, ValueError) as exc:
            self._request_error(HTTPStatus.BAD_REQUEST, "invalid_request", exc)
        except Exception as exc:  # noqa: BLE001 - HTTP exception boundary
            self._request_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/v1/voice/lint":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            if self.headers.get_content_type() != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "json_required"})
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "content_length_required"})
                return
            if re.fullmatch(r"[0-9]+", raw_length) is None:
                raise ValueError("Content-Length must be a non-negative base-10 integer")
            length = int(raw_length)
            if length < 0:
                raise ValueError("Content-Length must not be negative")
            max_body_bytes = self.server.max_body_bytes  # type: ignore[attr-defined]
            if length > max_body_bytes:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "payload_too_large"})
                return
            payload = _lint_payload(
                _strict_json_loads(self.rfile.read(length).decode("utf-8"))
            )
            contract = self._contract(
                profile=payload.get("profile"),
                audience=payload.get("audience"),
                surface=payload.get("surface"),
                tone=payload.get("tone"),
            )
            issues = lint_text(
                contract,
                payload["text"],
                profile=payload.get("profile"),
                audience=payload.get("audience"),
                surface=payload.get("surface"),
                tone=payload.get("tone"),
            )
            self._json(
                HTTPStatus.OK,
                {"ok": not any(issue.severity == "error" for issue in issues), "issues": [issue.as_dict() for issue in issues]},
            )
        except (ContractError, FileNotFoundError) as exc:
            self._request_error(HTTPStatus.SERVICE_UNAVAILABLE, "contract_unavailable", exc)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as exc:
            self._request_error(HTTPStatus.BAD_REQUEST, "invalid_request", exc)
        except Exception as exc:  # noqa: BLE001 - HTTP exception boundary
            self._request_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc)

    def log_message(self, format: str, *args: object) -> None:
        if not getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            super().log_message(format, *args)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    root: Path | str | None = None,
    path: Path | str | list[Path | str] | None = None,
    include_global: bool = True,
    quiet: bool = False,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    max_workers: int = DEFAULT_MAX_WORKERS,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> None:
    server = create_server(
        host=host,
        port=port,
        root=root,
        path=path,
        include_global=include_global,
        quiet=quiet,
        max_body_bytes=max_body_bytes,
        max_workers=max_workers,
        request_timeout_seconds=request_timeout_seconds,
    )
    if not quiet:
        bound_host, bound_port = server.server_address[:2]
        print(f"VoiceMD sidecar listening on http://{bound_host}:{bound_port}", file=sys.stderr)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    root: Path | str | None = None,
    path: Path | str | list[Path | str] | None = None,
    include_global: bool = True,
    quiet: bool = False,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    max_workers: int = DEFAULT_MAX_WORKERS,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> BoundedThreadingHTTPServer:
    if (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError("max_body_bytes must be a positive integer")
    voice_root = Path(root or Path.cwd()).resolve()
    # Validate before ThreadingHTTPServer binds its listening socket. Every
    # request checks source identity/size/timestamps and revalidates the exact
    # selected context; a detected runtime change is reloaded fail-closed.
    contract = _load_validated_contract_config(
        root=voice_root,
        path=path,
        include_global=include_global,
    )
    server = BoundedThreadingHTTPServer(
        (host, port),
        VoiceRequestHandler,
        max_workers=max_workers,
        request_timeout_seconds=request_timeout_seconds,
    )
    server.voice_root = voice_root  # type: ignore[attr-defined]
    server.voice_path = path  # type: ignore[attr-defined]
    server.include_global = include_global  # type: ignore[attr-defined]
    server.quiet = quiet  # type: ignore[attr-defined]
    server.max_body_bytes = max_body_bytes  # type: ignore[attr-defined]
    server.voice_contract = contract  # type: ignore[attr-defined]
    server.voice_reload_lock = RLock()  # type: ignore[attr-defined]
    server.voice_source_state = _server_source_state(server, contract)  # type: ignore[attr-defined]
    return server

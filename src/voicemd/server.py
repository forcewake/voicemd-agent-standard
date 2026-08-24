from __future__ import annotations

import hashlib
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlparse

from .compiler import compile_contract
from .contract import ContractError, load_contract
from .linter import lint_text
from .validator import validate_contract

DEFAULT_MAX_BODY_BYTES = 262_144
DEFAULT_MAX_WORKERS = 16
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0


def _load_validated_contract(server: object):
    contract = load_contract(
        start=server.voice_root,
        explicit=server.voice_path,
        include_global=server.include_global,
    )
    validation = validate_contract(contract, strict=False)
    if not validation.ok:
        raise ContractError("active VOICE.md failed validation")
    return contract


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *args: object,
        max_workers: int = DEFAULT_MAX_WORKERS,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        **kwargs: object,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
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

    def _contract(self):
        return _load_validated_contract(self.server)

    def _source_name(self, path: Path) -> str:
        root = self.server.voice_root  # type: ignore[attr-defined]
        try:
            return str(path.resolve().relative_to(root))
        except ValueError:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            return f"external:{path.name}@sha256:{digest}"

    def _request_error(self, status: HTTPStatus, code: str, exc: Exception | None = None) -> None:
        if exc is not None and not getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            self.log_error("%s: %s", type(exc).__name__, exc)
        self._json(status, {"error": code})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/health":
                self._contract()
                self._json(
                    HTTPStatus.OK,
                    {"status": "ok", "service": "voicemd", "contract": "valid"},
                )
                return
            contract = self._contract()
            if parsed.path == "/v1/voice/contract":
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
                prompt = compile_contract(
                    contract,
                    profile=query.get("profile"),
                    audience=query.get("audience"),
                    surface=query.get("surface"),
                    tone=query.get("tone"),
                    output_format=query.get("format", "prompt"),
                    compact=query.get("compact", "false").lower() == "true",
                    max_chars=int(query["max_chars"]) if query.get("max_chars") else None,
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
            length = int(raw_length)
            if length < 0:
                raise ValueError("Content-Length must not be negative")
            max_body_bytes = self.server.max_body_bytes  # type: ignore[attr-defined]
            if length > max_body_bytes:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "payload_too_large"})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise TypeError("JSON body must contain a text string")
            contract = self._contract()
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
    if max_body_bytes < 1:
        raise ValueError("max_body_bytes must be positive")
    server = BoundedThreadingHTTPServer(
        (host, port),
        VoiceRequestHandler,
        max_workers=max_workers,
        request_timeout_seconds=request_timeout_seconds,
    )
    server.voice_root = Path(root or Path.cwd()).resolve()  # type: ignore[attr-defined]
    server.voice_path = path  # type: ignore[attr-defined]
    server.include_global = include_global  # type: ignore[attr-defined]
    server.quiet = quiet  # type: ignore[attr-defined]
    server.max_body_bytes = max_body_bytes  # type: ignore[attr-defined]
    try:
        _load_validated_contract(server)
    except Exception:
        server.server_close()
        raise
    return server

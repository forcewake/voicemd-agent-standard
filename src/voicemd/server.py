from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .compiler import compile_contract
from .contract import load_contract
from .linter import lint_text


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
        return load_contract(
            start=self.server.voice_root,  # type: ignore[attr-defined]
            explicit=self.server.voice_path,  # type: ignore[attr-defined]
            include_global=self.server.include_global,  # type: ignore[attr-defined]
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/health":
                self._json(HTTPStatus.OK, {"status": "ok", "service": "voicemd"})
                return
            contract = self._contract()
            if parsed.path == "/v1/voice/contract":
                self._json(
                    HTTPStatus.OK,
                    {
                        "contract": contract.data,
                        "body": contract.body,
                        "sources": [str(path) for path in contract.source_paths()],
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
        except Exception as exc:  # Reference sidecar: convert errors to JSON, never a traceback.
            self._json(HTTPStatus.BAD_REQUEST, {"error": type(exc).__name__, "message": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/v1/voice/lint":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2_000_000:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "payload_too_large"})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise ValueError("JSON body must contain a text string")
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
        except Exception as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": type(exc).__name__, "message": str(exc)})

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
) -> None:
    server = ThreadingHTTPServer((host, port), VoiceRequestHandler)
    server.voice_root = Path(root or Path.cwd()).resolve()  # type: ignore[attr-defined]
    server.voice_path = path  # type: ignore[attr-defined]
    server.include_global = include_global  # type: ignore[attr-defined]
    server.quiet = quiet  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    finally:
        server.server_close()

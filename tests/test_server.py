import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from voicemd.contract import ContractError
from voicemd.server import create_server


def _voice(path: Path) -> None:
    path.write_text(
        '''---
voice_spec: "0.1"
kind: VoiceContract
name: Sidecar test
identity:
  sounds_like: [direct]
---
''',
        encoding="utf-8",
    )


def test_server_refuses_invalid_contract_at_startup(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    path.write_text("---\nname: broken\n---\n", encoding="utf-8")
    with pytest.raises(ContractError):
        create_server(port=0, path=path, include_global=False, quiet=True)
    _voice(path)
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        create_server(
            port=0,
            path=path,
            include_global=False,
            quiet=True,
            request_timeout_seconds=0,
        )


def test_health_revalidates_contract_and_errors_do_not_leak_paths(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    _voice(path)
    server = create_server(port=0, path=path, include_global=False, quiet=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/health") as response:
            assert json.load(response)["contract"] == "valid"

        path.write_text("---\nname: broken\n---\n", encoding="utf-8")
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/health")
        assert error.value.code == 503
        payload = json.load(error.value)
        assert payload == {"error": "contract_unavailable"}
        assert str(tmp_path) not in json.dumps(payload)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_lint_requires_json_and_enforces_body_limit(tmp_path: Path):
    path = tmp_path / "VOICE.md"
    _voice(path)
    server = create_server(
        port=0,
        path=path,
        include_global=False,
        quiet=True,
        max_body_bytes=32,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1/voice/lint"
    try:
        request = Request(url, data=b"{}", method="POST")
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 415

        request = Request(
            url,
            data=b'{"text":"this payload is deliberately too long"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 413
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_external_source_provenance_is_distinct_without_leaking_path(tmp_path: Path):
    root = tmp_path / "root"
    external = tmp_path / "outside" / "VOICE.md"
    root.mkdir()
    external.parent.mkdir()
    _voice(external)
    server = create_server(
        port=0,
        root=root,
        path=external,
        include_global=False,
        quiet=True,
        request_timeout_seconds=5,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/v1/voice/contract"
        ) as response:
            payload = json.load(response)
        assert payload["sources"][0].startswith("external:VOICE.md@sha256:")
        assert str(tmp_path) not in json.dumps(payload["sources"])
        assert server.request_timeout_seconds == 5
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

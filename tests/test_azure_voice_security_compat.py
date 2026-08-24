from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType

import pytest

from voicemd.azure_voice import realtime, transcribe
from voicemd.azure_voice.common import harden_websocket_connect, utc_now
from voicemd.azure_voice.evidence import create_run_directory


class _SecurityError(Exception):
    pass


class _Redirect(Exception):
    pass


class _ModernConnect:
    def process_redirect(self, exc: Exception) -> Exception | str:
        if isinstance(exc, _Redirect):
            return "wss://other-origin.example/realtime"
        return exc


class _LegacyConnect:
    def handle_redirect(self, uri: str) -> None:
        raise AssertionError(f"base connector followed redirect to {uri}")


def test_utc_timestamps_are_aware_and_python_310_compatible(tmp_path):
    timestamp = utc_now()
    parsed = datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00")
    assert timestamp.endswith("Z")
    assert parsed.utcoffset() is not None

    run_dir = create_run_directory(
        tmp_path,
        lane="realtime",
        deployment="deployment",
        label="contract",
    )
    stamp = run_dir.name.split("-", 1)[0]
    parsed_stamp = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    assert parsed_stamp.utcoffset() is not None


def test_modern_websocket_connector_rejects_redirects_and_preserves_other_errors():
    connector = harden_websocket_connect(_ModernConnect, _SecurityError)
    instance = connector()

    redirect_result = instance.process_redirect(_Redirect())
    assert isinstance(redirect_result, _SecurityError)
    assert str(redirect_result) == "Azure WebSocket redirects are not allowed"

    handshake_error = RuntimeError("handshake failed")
    assert instance.process_redirect(handshake_error) is handshake_error


def test_legacy_websocket_connector_rejects_redirects():
    connector = harden_websocket_connect(_LegacyConnect, _SecurityError)

    with pytest.raises(_SecurityError, match="redirects are not allowed"):
        connector().handle_redirect("wss://other-origin.example/realtime")


@pytest.mark.parametrize("adapter", [realtime, transcribe])
def test_azure_adapters_harden_the_imported_connector(adapter, monkeypatch):
    websockets_package = ModuleType("websockets")
    websockets_package.__path__ = []
    asyncio_package = ModuleType("websockets.asyncio")
    asyncio_package.__path__ = []
    client_module = ModuleType("websockets.asyncio.client")
    client_module.connect = _ModernConnect
    exceptions_module = ModuleType("websockets.exceptions")
    exceptions_module.SecurityError = _SecurityError
    monkeypatch.setitem(sys.modules, "websockets", websockets_package)
    monkeypatch.setitem(sys.modules, "websockets.asyncio", asyncio_package)
    monkeypatch.setitem(sys.modules, "websockets.asyncio.client", client_module)
    monkeypatch.setitem(sys.modules, "websockets.exceptions", exceptions_module)

    connector = adapter._websocket_connect()
    assert connector.__name__ == "NoRedirectConnect"
    assert isinstance(connector().process_redirect(_Redirect()), _SecurityError)

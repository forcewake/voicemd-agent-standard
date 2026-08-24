#!/usr/bin/env python3
"""Call an OpenAI-compatible /v1/chat/completions endpoint using VoiceMD."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from voicemd import compile_voice, decide_activation, load_voice, require_valid_voice

MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so bearer credentials cannot cross an origin boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler())


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_base_url(
    value: str,
    *,
    credentialed: bool,
    allow_insecure_http: bool = False,
) -> str:
    """Validate transport policy and return a normalized endpoint base URL."""
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("--base-url contains an invalid port or authority") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise ValueError("--base-url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("--base-url must not contain user information")
    if parsed.query or parsed.fragment:
        raise ValueError("--base-url must not contain a query or fragment")
    if port is not None and not 1 <= port <= 65535:  # pragma: no cover - urlsplit rejects this
        raise ValueError("--base-url contains an invalid port")
    if credentialed and parsed.scheme != "https":
        raise ValueError("credentialed requests require an HTTPS --base-url")
    if (
        parsed.scheme == "http"
        and not credentialed
        and not allow_insecure_http
        and not _is_loopback_hostname(parsed.hostname)
    ):
        raise ValueError(
            "credential-free HTTP is restricted to loopback; "
            "use HTTPS or explicitly pass --allow-insecure-http"
        )
    return urllib.parse.urlunsplit(parsed).rstrip("/")


def compose_messages(
    prompt: str,
    *,
    voice_path: str | Path,
    profile: str | None = None,
    compact: bool = False,
    output_kind: str = "chat",
    exact_output: bool = False,
    voice_enabled: bool = True,
    voice_explicit: bool = False,
    marker_text: str | None = None,
) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": "Answer the user's request accurately."},
    ]
    contract = load_voice(path=voice_path, include_global=False)
    require_valid_voice(contract, profile=profile)
    decision = decide_activation(
        contract,
        output_kind,
        exact_output=exact_output,
        enabled=voice_enabled,
        explicit=voice_explicit,
        marker_text=marker_text,
        profile=profile,
    )
    if decision.apply:
        messages.append(
            {
                "role": "system",
                "content": compile_voice(contract, profile=profile, compact=compact),
            }
        )
    messages.append({"role": "user", "content": prompt})
    return messages


def _strict_json(raw: bytes) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument(
        "--base-url", default=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1")
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable containing the bearer token; secrets are not accepted in argv.",
    )
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "local-model"))
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--profile")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--output-kind", default="chat")
    parser.add_argument("--exact-output", action="store_true")
    parser.add_argument("--no-voice", action="store_true")
    parser.add_argument("--voice-explicit", action="store_true")
    parser.add_argument(
        "--voice-marker",
        help="Trusted activation marker metadata; the user prompt is never scanned for markers.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow credential-free HTTP to a non-loopback host; bearer tokens still require HTTPS.",
    )
    args = parser.parse_args(argv)

    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be a positive finite number")

    api_key = os.getenv(args.api_key_env)
    try:
        base_url = validate_base_url(
            args.base_url,
            credentialed=bool(api_key),
            allow_insecure_http=args.allow_insecure_http,
        )
    except ValueError as exc:
        parser.error(str(exc))

    messages = compose_messages(
        args.prompt,
        voice_path=args.voice,
        profile=args.profile,
        compact=args.compact,
        output_kind=args.output_kind,
        exact_output=args.exact_output,
        voice_enabled=not args.no_voice,
        voice_explicit=args.voice_explicit,
        marker_text=args.voice_marker,
    )
    payload = {
        "model": args.model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=args.timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds the configured size limit")
        result = _strict_json(raw)
        if not isinstance(result, dict):
            raise TypeError("response must be a JSON object")
        choices = result.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("response must contain exactly one choice")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise TypeError("response choice must contain text content")
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            print(f"request failed: redirect refused (HTTP {exc.code})")
        else:
            print(f"HTTP error: {exc.code}")
        return 1
    except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"request failed: {exc}")
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate VoiceMD regression outputs from an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from voicemd import __version__, compile_voice, contract_sha256, decide_activation, load_voice

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def strict_json_loads(text: str) -> object:
    return json.loads(text, parse_constant=_reject_json_constant)


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting the process environment."""

    if not path.is_file():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.replace("_", "a").isalnum() or key[:1].isdigit():
            raise ValueError(f"{path}:{line_number}: invalid environment variable name")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def read_jsonl(path: Path):
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = strict_json_loads(line)
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("prompt"), str)
        ):
            raise TypeError(f"{path}:{line_number}: expected object with string id and prompt")
        if item["id"] in seen:
            raise ValueError(f"{path}:{line_number}: duplicate case id: {item['id']}")
        seen.add(item["id"])
        yield item


def case_boolean(case: dict[str, object], key: str, default: bool) -> bool:
    value = case.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"case {case['id']}: {key} must be a boolean")
    return value


def request_config(
    *,
    provider: str,
    endpoint: str,
    api_key: str,
    model: str,
    deployment: str,
    api_version: str,
    messages: list[dict[str, str]],
    temperature: float | None,
    reasoning_effort: str | None,
) -> tuple[str, dict[str, str], dict[str, object]]:
    payload: dict[str, object] = {"messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    if provider == "azure":
        if not endpoint or not deployment or not api_version or not api_key:
            raise ValueError(
                "Azure mode requires endpoint, deployment, api-version, and API key"
            )
        encoded_deployment = urllib.parse.quote(deployment, safe="")
        query = urllib.parse.urlencode({"api-version": api_version})
        url = (
            endpoint.rstrip("/")
            + f"/openai/deployments/{encoded_deployment}/chat/completions?{query}"
        )
        headers = {"api-key": api_key, "Content-Type": "application/json"}
    else:
        if not endpoint or not model:
            raise ValueError("OpenAI-compatible mode requires base URL and model")
        payload["model"] = model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = endpoint.rstrip("/") + "/chat/completions"
    return url, headers, payload


def call(
    *,
    provider: str,
    endpoint: str,
    api_key: str,
    model: str,
    deployment: str,
    api_version: str,
    messages: list[dict[str, str]],
    temperature: float | None,
    reasoning_effort: str | None,
    timeout: float,
) -> tuple[str, int, dict[str, object]]:
    url, headers, payload = request_config(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        deployment=deployment,
        api_version=api_version,
        messages=messages,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("endpoint response exceeded the size limit")
            result = strict_json_loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"endpoint returned HTTP {exc.code}") from exc
    if not isinstance(result, dict):
        raise TypeError("endpoint returned an invalid response object")
    choices = result.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("endpoint must return exactly one completion choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise TypeError("endpoint completion did not contain text")
    finish_reason = choice.get("finish_reason")
    if finish_reason not in {None, "stop"}:
        raise RuntimeError(f"endpoint completion did not finish normally: {finish_reason}")
    latency_ms = round((time.perf_counter() - started) * 1000)
    metadata = {
        "response_id": result.get("id"),
        "provider_model": result.get("model"),
        "system_fingerprint": result.get("system_fingerprint"),
        "finish_reason": finish_reason,
        "content_filter_results": choice.get("content_filter_results"),
        "prompt_filter_results": result.get("prompt_filter_results"),
        "usage": result.get("usage"),
    }
    return message["content"], latency_ms, metadata


def main() -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")
    pre_parser.add_argument("--no-env-file", action="store_true")
    pre_args, _ = pre_parser.parse_known_args()
    if not pre_args.no_env_file:
        load_env_file(Path(pre_args.env_file))

    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=pre_args.env_file)
    parser.add_argument("--no-env-file", action="store_true")
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--cases", default="evals/prompts.jsonl")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only the named case ID. Repeat to select multiple cases.",
    )
    parser.add_argument("--output", default="evals/results.jsonl")
    parser.add_argument(
        "--provider",
        choices=("auto", "azure", "openai-compatible"),
        default="auto",
    )
    parser.add_argument("--base-url", default=os.getenv("VOICEMD_BASE_URL", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("VOICEMD_API_KEY", ""))
    parser.add_argument("--model", default=os.getenv("VOICEMD_MODEL", "local-model"))
    parser.add_argument("--azure-endpoint", default=os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    parser.add_argument(
        "--azure-deployment", default=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
    )
    parser.add_argument(
        "--azure-api-version",
        default=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    parser.add_argument(
        "--azure-api-key", default=os.getenv("AZURE_OPENAI_API_KEY", "")
    )
    parser.add_argument(
        "--reasoning-effort", default=os.getenv("AZURE_OPENAI_REASONING_EFFORT")
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--profile")
    parser.add_argument("--audience")
    parser.add_argument("--surface")
    parser.add_argument("--tone")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        raise ValueError("timeout must be positive")

    provider = args.provider
    if provider == "auto":
        provider = (
            "azure"
            if args.azure_endpoint and args.azure_deployment and args.azure_api_key
            else "openai-compatible"
        )
    endpoint = args.azure_endpoint if provider == "azure" else args.base_url
    api_key = args.azure_api_key if provider == "azure" else args.api_key
    model_name = args.azure_deployment if provider == "azure" else args.model
    endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
    contract = load_voice(path=args.voice, include_global=False)

    cases_path = Path(args.cases).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if output_path == cases_path:
        raise ValueError("--output must not overwrite --cases")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected_case_ids = set(args.case)
    completed_cases = 0
    completed_ids: set[str] = set()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            for case in read_jsonl(cases_path):
                if selected_case_ids and case["id"] not in selected_case_ids:
                    continue
                profile = args.profile or case.get("profile")
                audience = args.audience or case.get("audience")
                surface = args.surface or case.get("surface")
                tone = args.tone or case.get("tone")
                marker_text = case.get("marker_text")
                if marker_text is not None and not isinstance(marker_text, str):
                    raise TypeError(f"case {case['id']}: marker_text must be a string")
                output_kind = case.get("output_kind", "chat")
                if not isinstance(output_kind, str) or not output_kind.strip():
                    raise TypeError(f"case {case['id']}: output_kind must be a string")
                decision = decide_activation(
                    contract,
                    output_kind,
                    exact_output=case_boolean(case, "exact_output", False),
                    enabled=case_boolean(case, "voice_enabled", True),
                    explicit=case_boolean(case, "voice_explicit", False),
                    marker_text=marker_text,
                    profile=profile,
                    audience=audience,
                    surface=surface,
                    tone=tone,
                )
                active_contract_sha256 = contract_sha256(
                    contract,
                    profile=profile,
                    audience=audience,
                    surface=surface,
                    tone=tone,
                )
                messages = [
                    {
                        "role": "system",
                        "content": "Answer accurately and preserve exact-output requirements.",
                    }
                ]
                voice = None
                if decision.apply:
                    voice = compile_voice(
                        contract,
                        profile=profile,
                        audience=audience,
                        surface=surface,
                        tone=tone,
                        compact=args.compact,
                    )
                    messages.append({"role": "system", "content": voice})
                messages.append({"role": "user", "content": case["prompt"]})
                response, latency_ms, response_metadata = call(
                    provider=provider,
                    endpoint=endpoint,
                    api_key=api_key,
                    model=args.model,
                    deployment=args.azure_deployment,
                    api_version=args.azure_api_version,
                    messages=messages,
                    temperature=args.temperature,
                    reasoning_effort=args.reasoning_effort,
                    timeout=args.timeout,
                )
                result = {
                    **case,
                    "selectors": {
                        "profile": profile,
                        "audience": audience,
                        "surface": surface,
                        "tone": tone,
                    },
                    "activation": {
                        "apply": decision.apply,
                        "mode": decision.mode,
                        "reason": decision.reason,
                    },
                    "response": response,
                    "provider": provider,
                    "model": model_name,
                    "api_version": args.azure_api_version if provider == "azure" else None,
                    "endpoint_sha256": endpoint_hash,
                    "temperature": args.temperature,
                    "reasoning_effort": args.reasoning_effort,
                    "compact": args.compact,
                    "voicemd_version": __version__,
                    "contract_sha256": active_contract_sha256,
                    "compiled_prompt_sha256": (
                        hashlib.sha256(voice.encode("utf-8")).hexdigest() if voice else None
                    ),
                    "generated_at": datetime.now(UTC).isoformat(),
                    "latency_ms": latency_ms,
                    **response_metadata,
                }
                output.write(
                    json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n"
                )
                output.flush()
                completed_cases += 1
                completed_ids.add(case["id"])
                print(f"completed: {case['id']}")
        missing = sorted(selected_case_ids - completed_ids)
        if missing:
            raise ValueError("unknown --case IDs: " + ", ".join(missing))
        if completed_cases == 0:
            raise ValueError("no evaluation cases matched --case selection")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

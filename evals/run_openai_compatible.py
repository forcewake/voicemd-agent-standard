#!/usr/bin/env python3
"""Generate VoiceMD regression outputs from an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from voicemd import __version__, compile_voice, contract_sha256, decide_activation, load_voice
from voicemd.normalization import is_nonblank_selector

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_JSONL_LINE_BYTES = MAX_RESPONSE_BYTES + 1024 * 1024
MAX_JSONL_FILE_BYTES = 64 * 1024 * 1024
MAX_JSONL_RECORDS = 10_000
MAX_ENV_FILE_BYTES = 64 * 1024
MAX_AUXILIARY_FILE_BYTES = 1024 * 1024
BASE_SYSTEM_INSTRUCTION = "Answer accurately and preserve exact-output requirements."
SELECTOR_KEYS = ("profile", "audience", "surface", "tone")


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so authentication headers never reach another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler())


class RejectSecretArgument(argparse.Action):
    """Fail without echoing a secret supplied on the command line."""

    def __call__(self, parser, namespace, values, option_string=None):
        variable = (
            "AZURE_OPENAI_API_KEY" if option_string == "--azure-api-key" else "VOICEMD_API_KEY"
        )
        raise argparse.ArgumentError(
            self,
            f"is disabled; set {variable} in the environment or --env-file",
        )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def strict_json_loads(text: str) -> object:
    return json.loads(text, parse_constant=_reject_json_constant)


def json_sha256(value: object) -> str:
    """Hash a JSON value using this eval pack's deterministic encoding."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def corpus_sha256(cases: list[dict[str, object]]) -> str:
    return json_sha256(cases)


def add_secret_argument_guards(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-key",
        action=RejectSecretArgument,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--azure-api-key",
        action=RejectSecretArgument,
        help=argparse.SUPPRESS,
    )


def environment_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean flag")


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_endpoint_policy(
    *,
    provider: str,
    endpoint: str,
    api_key: str,
    allow_insecure_http: bool = False,
) -> urllib.parse.SplitResult:
    """Validate transport policy before constructing a credentialed request."""

    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("endpoint URL must not contain a query or fragment")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint URL contains an invalid port") from exc

    if provider == "azure":
        if parsed.scheme != "https":
            raise ValueError("Azure OpenAI endpoints must use HTTPS")
        return parsed

    if provider != "openai-compatible":
        raise ValueError(f"unsupported provider: {provider}")
    if parsed.scheme == "http":
        if api_key:
            raise ValueError("credentials must not be sent over HTTP")
        if not _is_loopback_hostname(parsed.hostname) and not allow_insecure_http:
            raise ValueError("non-loopback HTTP requires --allow-insecure-http and no credentials")
    return parsed


def candidate_messages(
    *,
    contract: object,
    case: dict[str, object],
    selectors: dict[str, str | None],
    compact: bool,
    apply_voice: bool,
) -> tuple[list[dict[str, str]], str | None]:
    prompt = case.get("prompt")
    if not isinstance(prompt, str):
        raise TypeError(f"case {case.get('id')}: prompt must be a string")
    messages = [{"role": "system", "content": BASE_SYSTEM_INSTRUCTION}]
    voice = None
    if apply_voice:
        voice = compile_voice(contract, compact=compact, **selectors)
        messages.append({"role": "system", "content": voice})
    messages.append({"role": "user", "content": prompt})
    return messages, voice


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def validated_selector_kwargs(
    selectors: object,
    *,
    case_id: object,
) -> dict[str, str | None]:
    if not isinstance(selectors, dict) or set(selectors) != set(SELECTOR_KEYS):
        raise TypeError(f"case {case_id}: selectors must contain exactly {sorted(SELECTOR_KEYS)}")
    selector_kwargs = {key: selectors[key] for key in SELECTOR_KEYS}
    if any(
        value is not None and not is_nonblank_selector(value)
        for value in selector_kwargs.values()
    ):
        raise TypeError(f"case {case_id}: selector provenance requires strings or null")
    return selector_kwargs


def validate_candidate_result(
    item: dict[str, object],
    *,
    expected_case: dict[str, object],
    expected_corpus_sha256: str,
    contract: object,
) -> dict[str, object]:
    """Bind a candidate result to the canonical case, corpus, and current contract."""

    case_id = expected_case["id"]
    if item.get("id") != case_id:
        raise ValueError(f"case {case_id}: result ID does not match canonical case")
    mismatched_fields = [
        key for key, value in expected_case.items() if key not in item or item[key] != value
    ]
    if mismatched_fields:
        raise ValueError(
            f"case {case_id}: result does not match corpus fields: " + ", ".join(mismatched_fields)
        )

    expected_case_sha256 = json_sha256(expected_case)
    if item.get("case_sha256") != expected_case_sha256:
        raise ValueError(f"case {case_id}: case provenance mismatch")
    if item.get("corpus_sha256") != expected_corpus_sha256:
        raise ValueError(f"case {case_id}: corpus provenance mismatch")

    response = item.get("response")
    if not isinstance(response, str):
        raise TypeError(f"case {case_id}: missing response string")
    if len(response.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError(f"case {case_id}: response exceeds the size limit")
    response_sha256 = _text_sha256(response)
    if item.get("response_sha256") != response_sha256:
        raise ValueError(f"case {case_id}: response provenance mismatch")

    selector_kwargs = validated_selector_kwargs(item.get("selectors"), case_id=case_id)

    current_contract_sha256 = contract_sha256(contract, **selector_kwargs)
    if item.get("contract_sha256") != current_contract_sha256:
        raise ValueError(f"case {case_id}: contract provenance mismatch")

    activation = item.get("activation")
    if not isinstance(activation, dict) or set(activation) != {"apply", "mode", "reason"}:
        raise TypeError(f"case {case_id}: activation must contain exactly apply, mode, reason")
    marker_text = expected_case.get("marker_text")
    if marker_text is not None and not isinstance(marker_text, str):
        raise TypeError(f"case {case_id}: marker_text must be a string")
    output_kind = expected_case.get("output_kind", "chat")
    if not isinstance(output_kind, str) or not output_kind.strip():
        raise TypeError(f"case {case_id}: output_kind must be a string")
    decision = decide_activation(
        contract,
        output_kind,
        exact_output=case_boolean(expected_case, "exact_output", False),
        enabled=case_boolean(expected_case, "voice_enabled", True),
        explicit=case_boolean(expected_case, "voice_explicit", False),
        marker_text=marker_text,
        **selector_kwargs,
    )
    expected_activation = {
        "apply": decision.apply,
        "mode": decision.mode,
        "reason": decision.reason,
    }
    if activation != expected_activation:
        raise ValueError(f"case {case_id}: activation provenance mismatch")

    compact = item.get("compact", False)
    if not isinstance(compact, bool):
        raise TypeError(f"case {case_id}: compact must be boolean")
    messages, active_voice = candidate_messages(
        contract=contract,
        case=expected_case,
        selectors=selector_kwargs,
        compact=compact,
        apply_voice=decision.apply,
    )
    messages_sha256 = json_sha256(messages)
    if item.get("messages_sha256") != messages_sha256:
        raise ValueError(f"case {case_id}: request-message provenance mismatch")
    compiled_prompt_sha256 = _text_sha256(active_voice) if active_voice is not None else None
    if item.get("compiled_prompt_sha256") != compiled_prompt_sha256:
        raise ValueError(f"case {case_id}: prompt provenance mismatch")

    provider = item.get("provider")
    if provider not in {"azure", "openai-compatible"}:
        raise ValueError(f"case {case_id}: invalid provider provenance")
    if not isinstance(item.get("model"), str) or not item["model"]:
        raise TypeError(f"case {case_id}: model provenance must be a non-empty string")
    if provider == "azure":
        if not isinstance(item.get("api_version"), str) or not item["api_version"]:
            raise TypeError(f"case {case_id}: Azure API version provenance is required")
    elif item.get("api_version") is not None:
        raise ValueError(f"case {case_id}: generic result must not record Azure API version")
    if not _valid_sha256(item.get("endpoint_sha256")):
        raise TypeError(f"case {case_id}: endpoint provenance must be a SHA-256 digest")
    if item.get("voicemd_version") != __version__:
        raise ValueError(f"case {case_id}: VoiceMD version provenance mismatch")
    if "finish_reason" not in item or item["finish_reason"] not in {None, "stop"}:
        raise ValueError(f"case {case_id}: completion provenance is not successful")
    temperature = item.get("temperature")
    if temperature is not None and (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature)
    ):
        raise TypeError(f"case {case_id}: temperature provenance must be finite or null")
    reasoning_effort = item.get("reasoning_effort")
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise TypeError(f"case {case_id}: reasoning provenance must be a string or null")

    return {
        "case": expected_case,
        "response": response,
        "selectors": selector_kwargs,
        "activation": expected_activation,
        "active_voice": active_voice,
        "contract_sha256": current_contract_sha256,
        "compiled_prompt_sha256": compiled_prompt_sha256,
        "messages_sha256": messages_sha256,
        "response_sha256": response_sha256,
        "case_sha256": expected_case_sha256,
        "corpus_sha256": expected_corpus_sha256,
        "result_sha256": json_sha256(item),
    }


def read_bounded_text(path: Path, *, max_bytes: int, label: str) -> str:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"{label} exceeds the size limit ({max_bytes} bytes): {path}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8: {path}") from exc


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting the process environment."""

    if not path.is_file():
        return
    content = read_bounded_text(path, max_bytes=MAX_ENV_FILE_BYTES, label="environment file")
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
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
    total_bytes = 0
    record_count = 0
    with path.open("rb") as stream:
        line_number = 0
        while True:
            raw_line = stream.readline(MAX_JSONL_LINE_BYTES + 1)
            if not raw_line:
                break
            line_number += 1
            total_bytes += len(raw_line)
            if total_bytes > MAX_JSONL_FILE_BYTES:
                raise ValueError(f"{path}: JSONL file exceeds the size limit")
            if len(raw_line) > MAX_JSONL_LINE_BYTES:
                raise ValueError(f"{path}:{line_number}: JSONL record exceeds the size limit")
            if not raw_line.strip():
                continue
            record_count += 1
            if record_count > MAX_JSONL_RECORDS:
                raise ValueError(f"{path}: JSONL record count exceeds the limit")
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSONL must be UTF-8") from exc
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
    allow_insecure_http: bool = False,
) -> tuple[str, dict[str, str], dict[str, object]]:
    validate_endpoint_policy(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        allow_insecure_http=allow_insecure_http,
    )
    payload: dict[str, object] = {"messages": messages}
    if temperature is not None:
        if isinstance(temperature, bool) or not math.isfinite(temperature):
            raise ValueError("temperature must be finite")
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    if provider == "azure":
        if not endpoint or not deployment or not api_version or not api_key:
            raise ValueError("Azure mode requires endpoint, deployment, api-version, and API key")
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
    allow_insecure_http: bool = False,
) -> tuple[str, int, dict[str, object]]:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
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
        allow_insecure_http=allow_insecure_http,
    )
    request_body = json.dumps(payload, allow_nan=False).encode("utf-8")
    if len(request_body) > MAX_REQUEST_BYTES:
        raise RuntimeError("endpoint request exceeded the size limit")
    request = urllib.request.Request(
        url,
        data=request_body,
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("endpoint response exceeded the size limit")
            result = strict_json_loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise RuntimeError("endpoint redirects are not allowed") from exc
        raise RuntimeError(f"endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("endpoint request failed") from exc
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
    parser.add_argument(
        "--base-url", default=os.getenv("VOICEMD_BASE_URL", "http://127.0.0.1:8000/v1")
    )
    parser.add_argument("--model", default=os.getenv("VOICEMD_MODEL", "local-model"))
    parser.add_argument("--azure-endpoint", default=os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    parser.add_argument("--azure-deployment", default=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", ""))
    parser.add_argument(
        "--azure-api-version",
        default=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    add_secret_argument_guards(parser)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=environment_flag("VOICEMD_ALLOW_INSECURE_HTTP"),
        help="Allow credential-free HTTP to a non-loopback OpenAI-compatible endpoint.",
    )
    parser.add_argument("--reasoning-effort", default=os.getenv("AZURE_OPENAI_REASONING_EFFORT"))
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

    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("timeout must be finite and positive")

    provider = args.provider
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    compatible_api_key = os.getenv("VOICEMD_API_KEY", "")
    if provider == "auto":
        provider = (
            "azure"
            if args.azure_endpoint and args.azure_deployment and azure_api_key
            else "openai-compatible"
        )
    endpoint = args.azure_endpoint if provider == "azure" else args.base_url
    api_key = azure_api_key if provider == "azure" else compatible_api_key
    validate_endpoint_policy(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        allow_insecure_http=args.allow_insecure_http,
    )
    model_name = args.azure_deployment if provider == "azure" else args.model
    endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
    contract = load_voice(path=args.voice, include_global=False)

    cases_path = Path(args.cases).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    protected_inputs = {
        "--cases": cases_path,
        "--voice": Path(args.voice).expanduser().resolve(),
        "--env-file": Path(args.env_file).expanduser().resolve(),
    }
    for input_name, input_path in protected_inputs.items():
        if output_path == input_path:
            raise ValueError(f"--output must not overwrite {input_name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_cases = list(read_jsonl(cases_path))
    evaluation_corpus_sha256 = corpus_sha256(all_cases)
    selected_case_ids = set(args.case) or {case["id"] for case in all_cases}
    unknown_case_ids = sorted(selected_case_ids - {case["id"] for case in all_cases})
    if unknown_case_ids:
        raise ValueError("unknown --case IDs: " + ", ".join(unknown_case_ids))
    selected_cases = [case for case in all_cases if case["id"] in selected_case_ids]
    if not selected_cases:
        raise ValueError("no evaluation cases matched --case selection")
    completed_cases = 0
    completed_ids: set[str] = set()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            for case in selected_cases:
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
                selectors = {
                    "profile": profile,
                    "audience": audience,
                    "surface": surface,
                    "tone": tone,
                }
                messages, voice = candidate_messages(
                    contract=contract,
                    case=case,
                    selectors=selectors,
                    compact=args.compact,
                    apply_voice=decision.apply,
                )
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
                    allow_insecure_http=args.allow_insecure_http,
                )
                result = {
                    **case,
                    "case_sha256": json_sha256(case),
                    "corpus_sha256": evaluation_corpus_sha256,
                    "selectors": selectors,
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
                    "messages_sha256": json_sha256(messages),
                    "compiled_prompt_sha256": (
                        hashlib.sha256(voice.encode("utf-8")).hexdigest() if voice else None
                    ),
                    "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "latency_ms": latency_ms,
                    **response_metadata,
                }
                output.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
                output.flush()
                completed_cases += 1
                completed_ids.add(case["id"])
                print(f"completed: {case['id']}")
        missing = sorted(selected_case_ids - completed_ids)
        if missing:
            raise RuntimeError("runner did not complete selected cases: " + ", ".join(missing))
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

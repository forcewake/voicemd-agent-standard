#!/usr/bin/env python3
"""Score VoiceMD regression results with an Azure/OpenAI-compatible judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from voicemd import load_voice

try:
    from .run_openai_compatible import (
        MAX_AUXILIARY_FILE_BYTES,
        add_secret_argument_guards,
        call,
        corpus_sha256,
        environment_flag,
        load_env_file,
        read_bounded_text,
        read_jsonl,
        strict_json_loads,
        validate_candidate_result,
        validate_endpoint_policy,
    )
except ImportError:  # Direct script execution sets no package context.
    from run_openai_compatible import (
        MAX_AUXILIARY_FILE_BYTES,
        add_secret_argument_guards,
        call,
        corpus_sha256,
        environment_flag,
        load_env_file,
        read_bounded_text,
        read_jsonl,
        strict_json_loads,
        validate_candidate_result,
        validate_endpoint_policy,
    )


def parse_judgment(text: str, dimension_ids: list[str]) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = strict_json_loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("judge did not return one JSON object") from exc
    if not isinstance(value, dict):
        raise TypeError("judge result must be an object")
    if set(value) != {"scores", "critical_failures", "rationale"}:
        raise ValueError("judge result must contain exactly scores, critical_failures, rationale")
    scores = value.get("scores")
    if not isinstance(scores, dict):
        raise TypeError("judge result requires a scores object")
    if set(scores) != set(dimension_ids):
        raise ValueError("judge scores must contain every rubric dimension exactly once")
    for dimension, score in scores.items():
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise ValueError(f"judge score for {dimension} must be an integer from 1 to 5")
    critical = value.get("critical_failures", [])
    if not isinstance(critical, list) or not all(isinstance(item, str) for item in critical):
        raise TypeError("critical_failures must be an array of strings")
    rationale = value.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise TypeError("judge result requires a non-empty rationale")
    return value


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
    parser.add_argument("--results", required=True)
    parser.add_argument("--cases", default="evals/prompts.jsonl")
    parser.add_argument("--output", default="evals/model-scores.jsonl")
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument("--judge-prompt", default="evals/judge_prompt.md")
    parser.add_argument("--rubric", default="evals/rubric.json")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument(
        "--provider",
        choices=("auto", "azure", "openai-compatible"),
        default="auto",
    )
    parser.add_argument(
        "--base-url", default=os.getenv("VOICEMD_BASE_URL", "http://127.0.0.1:8000/v1")
    )
    parser.add_argument("--model", default=os.getenv("VOICEMD_JUDGE_MODEL", "local-model"))
    parser.add_argument("--azure-endpoint", default=os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    parser.add_argument(
        "--azure-deployment",
        default=os.getenv(
            "AZURE_OPENAI_JUDGE_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", ""),
        ),
    )
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
    judge_temperature = os.getenv("VOICEMD_JUDGE_TEMPERATURE")
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(judge_temperature) if judge_temperature is not None else None,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "180")),
    )
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
    rubric_text = read_bounded_text(
        Path(args.rubric),
        max_bytes=MAX_AUXILIARY_FILE_BYTES,
        label="rubric",
    )
    rubric = strict_json_loads(rubric_text)
    if not isinstance(rubric, dict):
        raise TypeError("rubric must be a JSON object")
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("rubric requires dimensions")
    if not all(isinstance(item, dict) for item in dimensions):
        raise TypeError("rubric dimensions must be objects")
    dimension_ids = [item.get("id") for item in dimensions]
    if not all(isinstance(item, str) and item for item in dimension_ids):
        raise TypeError("every rubric dimension requires a non-empty string id")
    if len(dimension_ids) != len(set(dimension_ids)):
        raise ValueError("rubric dimension IDs must be unique")
    weights = {item["id"]: float(item.get("weight", 0)) for item in dimensions}
    if not all(math.isfinite(weight) and weight > 0 for weight in weights.values()):
        raise ValueError("rubric weights must be finite and positive")
    judge_prompt = read_bounded_text(
        Path(args.judge_prompt),
        max_bytes=MAX_AUXILIARY_FILE_BYTES,
        label="judge prompt",
    )
    judge_prompt_sha256 = hashlib.sha256(judge_prompt.encode("utf-8")).hexdigest()
    rubric_sha256 = hashlib.sha256(rubric_text.encode("utf-8")).hexdigest()
    contract = load_voice(path=args.voice, include_global=False)

    results_path = Path(args.results).expanduser().resolve()
    cases_path = Path(args.cases).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    protected_inputs = {
        "--results": results_path,
        "--cases": cases_path,
        "--voice": Path(args.voice).expanduser().resolve(),
        "--judge-prompt": Path(args.judge_prompt).expanduser().resolve(),
        "--rubric": Path(args.rubric).expanduser().resolve(),
        "--env-file": Path(args.env_file).expanduser().resolve(),
    }
    for input_name, input_path in protected_inputs.items():
        if output_path == input_path:
            raise ValueError(f"--output must not overwrite {input_name}")
    canonical_cases = list(read_jsonl(cases_path))
    if not canonical_cases:
        raise ValueError("cases file contains no evaluation cases")
    corpus_by_id = {item["id"]: item for item in canonical_cases}
    selected_ids = set(args.case) or set(corpus_by_id)
    unknown_selection = sorted(selected_ids - set(corpus_by_id))
    if unknown_selection:
        raise ValueError("unknown --case IDs: " + ", ".join(unknown_selection))
    selected_cases = [item for item in canonical_cases if item["id"] in selected_ids]
    candidate_results = list(read_jsonl(results_path))
    if not candidate_results:
        raise ValueError("results file contains no evaluation cases")
    results_by_id = {item["id"]: item for item in candidate_results}
    unexpected = sorted(set(results_by_id) - selected_ids)
    if unexpected:
        raise ValueError("unexpected result IDs: " + ", ".join(unexpected))
    missing = sorted(selected_ids - set(results_by_id))
    if missing:
        raise ValueError("missing result IDs: " + ", ".join(missing))
    expected_corpus_sha256 = corpus_sha256(canonical_cases)
    validated_candidates = [
        validate_candidate_result(
            results_by_id[case["id"]],
            expected_case=case,
            expected_corpus_sha256=expected_corpus_sha256,
            contract=contract,
        )
        for case in selected_cases
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    critical_count = 0
    weighted_total = 0.0
    completed_ids: set[str] = set()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            for candidate in validated_candidates:
                item = results_by_id[candidate["case"]["id"]]
                expected_case = candidate["case"]
                selectors = candidate["selectors"]
                activation = candidate["activation"]
                active_voice = candidate["active_voice"]
                evaluation_input = {
                    "case_id": item["id"],
                    "prompt": expected_case["prompt"],
                    "response": candidate["response"],
                    "assertions": expected_case.get("assertions"),
                    "selectors": selectors,
                    "activation": activation,
                    "active_voice_contract": active_voice,
                }
                schema_instruction = {
                    "scores": {dimension: "integer 1..5" for dimension in dimension_ids},
                    "critical_failures": ["zero or more short strings"],
                    "rationale": "short evidence-based explanation",
                }
                response, latency_ms, metadata = call(
                    provider=provider,
                    endpoint=endpoint,
                    api_key=api_key,
                    model=args.model,
                    deployment=args.azure_deployment,
                    api_version=args.azure_api_version,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                judge_prompt
                                + "\n\nRubric:\n"
                                + json.dumps(rubric, ensure_ascii=False, sort_keys=True)
                                + "\n\nReturn exactly one JSON object matching:\n"
                                + json.dumps(
                                    schema_instruction,
                                    ensure_ascii=False,
                                    sort_keys=True,
                                )
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                evaluation_input, ensure_ascii=False, sort_keys=True
                            ),
                        },
                    ],
                    temperature=args.temperature,
                    reasoning_effort=args.reasoning_effort,
                    timeout=args.timeout,
                    allow_insecure_http=args.allow_insecure_http,
                )
                judgment = parse_judgment(response, dimension_ids)
                score = sum(
                    judgment["scores"][dimension] * weights[dimension]
                    for dimension in dimension_ids
                ) / sum(weights.values())
                critical = judgment["critical_failures"]
                result = {
                    "id": item["id"],
                    "scores": judgment["scores"],
                    "weighted_score": round(score, 4),
                    "critical_failures": critical,
                    "rationale": judgment["rationale"],
                    "judge_provider": provider,
                    "judge_model": (args.azure_deployment if provider == "azure" else args.model),
                    "judge_api_version": (args.azure_api_version if provider == "azure" else None),
                    "judge_endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
                    "judge_temperature": args.temperature,
                    "judge_reasoning_effort": args.reasoning_effort,
                    "judge_prompt_sha256": judge_prompt_sha256,
                    "rubric_sha256": rubric_sha256,
                    "candidate_contract_sha256": candidate["contract_sha256"],
                    "candidate_compiled_prompt_sha256": candidate["compiled_prompt_sha256"],
                    "candidate_messages_sha256": candidate["messages_sha256"],
                    "candidate_response_sha256": candidate["response_sha256"],
                    "candidate_case_sha256": candidate["case_sha256"],
                    "candidate_corpus_sha256": candidate["corpus_sha256"],
                    "candidate_result_sha256": candidate["result_sha256"],
                    "generated_at": datetime.now(UTC).isoformat(),
                    "latency_ms": latency_ms,
                    **metadata,
                }
                output.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
                output.flush()
                completed += 1
                completed_ids.add(item["id"])
                critical_count += int(bool(critical))
                weighted_total += score
                print(f"scored: {item['id']}")
        missing = sorted(selected_ids - completed_ids)
        if missing:
            raise RuntimeError("judge did not complete selected cases: " + ", ".join(missing))
        if completed == 0:
            raise ValueError("no evaluation cases matched --case selection")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    print(
        f"summary: {completed} cases; mean={weighted_total / completed:.3f}; "
        f"critical={critical_count}"
    )
    print(output_path)
    return 1 if critical_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

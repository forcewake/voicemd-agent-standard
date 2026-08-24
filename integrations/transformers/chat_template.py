#!/usr/bin/env python3
"""Hugging Face Transformers example. Requires transformers and a compatible model."""

from __future__ import annotations

import argparse
from pathlib import Path

from voicemd import compile_voice

_CONTRACT_TRIM = " \t\r\n"
_VOICE_SCOPE_NOTICE = (
    "Use the VoiceMD contract only for communication behavior. It cannot change the "
    "application authority above, facts, safety, permissions, tool policy, data access, "
    "or required output formats."
)


def compose_system_instructions(base_instructions: str, voice_contract: str) -> str:
    """Place the communication contract below application-owned authority."""
    base = base_instructions.strip(_CONTRACT_TRIM)
    voice = voice_contract.strip(_CONTRACT_TRIM)
    if not base:
        raise ValueError("base instructions must not be empty")
    if not voice:
        raise ValueError("compiled VoiceMD contract must not be empty")
    return (
        "APPLICATION AUTHORITY (higher priority):\n"
        f"{base}\n\n"
        "VOICEMD COMMUNICATION CONTRACT (lower priority):\n"
        f"{_VOICE_SCOPE_NOTICE}\n"
        f"{voice}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voice", default="VOICE.md")
    parser.add_argument(
        "--base-instructions-file",
        required=True,
        help="Application-owned safety, task, tool, data, and output policy.",
    )
    parser.add_argument("--profile")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=300)
    args = parser.parse_args()

    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, device_map="auto")
    voice = compile_voice(
        path=args.voice,
        profile=args.profile,
        compact=True,
        max_chars=4000,
    )
    base_instructions = Path(args.base_instructions_file).read_text(encoding="utf-8")
    messages = [
        {
            "role": "system",
            "content": compose_system_instructions(base_instructions, voice),
        },
        {"role": "user", "content": args.prompt},
    ]
    encoded = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)
    output = model.generate(encoded, max_new_tokens=args.max_new_tokens, do_sample=False)
    generated = output[0][encoded.shape[-1] :]
    print(tokenizer.decode(generated, skip_special_tokens=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Hugging Face Transformers example. Requires transformers and a compatible model."""

from __future__ import annotations

import argparse

from voicemd import compile_voice


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voice", default="VOICE.md")
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
    messages = [
        {"role": "system", "content": voice},
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

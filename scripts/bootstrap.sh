#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
TARGET="${2:-all}"

python3 -m pip install -e .
if [ ! -f VOICE.md ]; then
  voicemd init --mode "$MODE"
fi
voicemd install --target "$TARGET" --mode auto
voicemd validate
voicemd doctor

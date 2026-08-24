#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${VOICEMD_URL:-http://127.0.0.1:8765}"

curl -fsS "$BASE_URL/health"
curl -fsS "$BASE_URL/v1/voice/prompt?profile=executive_brief"

curl -fsS -X POST "$BASE_URL/v1/voice/lint" \
  -H 'Content-Type: application/json' \
  -d '{"profile":"executive_brief","text":"The decision is to proceed."}'

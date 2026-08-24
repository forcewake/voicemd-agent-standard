#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <new-model-name> <base-model>" >&2
  exit 2
fi

NEW_MODEL="$1"
BASE_MODEL="$2"
VOICE_FILE="${VOICE_FILE:-VOICE.compiled.txt}"

if [ ! -f "$VOICE_FILE" ]; then
  echo "missing $VOICE_FILE; generate it with voicemd compile --compact --output $VOICE_FILE" >&2
  exit 2
fi

python3 - "$BASE_MODEL" "$VOICE_FILE" <<'PY'
from pathlib import Path
import sys
base, voice_file = sys.argv[1:]
template = Path("Modelfile.template").read_text(encoding="utf-8")
voice = Path(voice_file).read_text(encoding="utf-8")
if '"""' in voice:
    raise SystemExit('VOICE prompt contains triple quotes; use dynamic injection instead')
Path("Modelfile.generated").write_text(
    template.replace("__BASE_MODEL__", base).replace("__VOICE_PROMPT__", voice),
    encoding="utf-8",
)
PY

ollama create "$NEW_MODEL" -f Modelfile.generated

# VoiceMD: с чего начать

VoiceMD — независимый draft стандарта `VOICE.md` для управляемого communication behavior AI-агентов. Он не выдаётся за уже принятый vendor standard. Пакет можно использовать сейчас: как обычный Markdown, как testable contract, через coding-agent adapters или как runtime layer внутри приложения.

## За пять минут

### 1. Самый простой вариант без установки

```bash
cp templates/simple/VOICE.md ./VOICE.md
```

Передавайте содержимое `VOICE.md` модели только для текста, который читает или слышит человек. Не применяйте voice transformation к code, tool calls/results, обязательному JSON, raw data и exact quotations.

Для dependency-free загрузки доступны:

```bash
python lite/voice_loader.py
node lite/load-voice.mjs
bash lite/load-voice.sh
```

### 2. Полный CLI и coding-agent adapters

Установка из готового wheel:

Перед установкой убедитесь, что `release/BUILD_INFO.json` содержит `"artifact_status": "current"`. Если checkout находится в процессе разработки и artifacts помечены `stale`, используйте editable install или пересоберите release.

```bash
python -m pip install release/voicemd-0.1.0a1-py3-none-any.whl
```

Или editable install из репозитория:

```bash
python -m pip install -e .
```

Затем:

```bash
voicemd validate --strict
voicemd compile --profile architecture_review
voicemd install --target all --mode auto
voicemd doctor
```

`--mode auto` ставит небольшие managed bootstraps и Agent Skill. Полный contract активируется для human-facing output, а не для code patches, structured data и tool traffic.

`--mode explicit` использует native explicit-only metadata там, где harness это поддерживает. Запуск: `$voice-contract` в Codex и `/voice-contract` в Claude Code, Copilot CLI или Cursor. Маркер `@voice` не может сам загрузить skill, скрытый native invocation policy. Aider требует явного запуска `aider --config .aider.voice.yml`.

### 3. Любое приложение или orchestration framework

Самый переносимый вариант — HTTP sidecar:

```bash
voicemd serve --host 127.0.0.1 --port 8765
curl 'http://127.0.0.1:8765/v1/voice/prompt?surface=chat&audience=engineer'
```

OpenAPI: `integrations/http/openapi.yaml`.

Также есть Python API, TypeScript и .NET clients, OpenAI-compatible middleware, optional MCP, Docker и Kubernetes sidecar.

### 4. Local models и speech

Для небольшой модели:

```bash
voicemd compile --compact --max-chars 3500 --output .voice/system.txt
```

Для NVIDIA NemotronLabs VoiceChat:

```bash
voicemd compile \
  --profile nemotron_voicechat \
  --format nemotron-ascii \
  --compact \
  --output .voice/nemotron-system.txt
```

Рабочий `session.update` adapter: `integrations/nemotron-voicechat/session_update.py`.

## Какие файлы читать

- `SPECIFICATION.md` — нормативный draft.
- `VOICE.md` — полный reference contract, которым репозиторий пользуется сам.
- `templates/simple/VOICE.md` — простой человеческий вариант.
- `templates/full/VOICE.md` — structured/testable вариант.
- `templates/spoken/VOICE.md` — speech-first вариант.
- `docs/HARNESS_COMPATIBILITY.md` — Codex, Claude Code, Gemini CLI, Cursor, Copilot, Cline, Windsurf, OpenCode, Aider.
- `docs/APPLICATION_INTEGRATION.md` — application patterns.
- `docs/LOCAL_MODELS.md` и `docs/NEMOTRON_VOICECHAT.md` — local inference и realtime speech.
- `docs/SECURITY_MODEL.md` — authority boundary и threat model.
- `PACKAGE_CONTENTS.md` — полный состав release pack.

## Базовый lifecycle

```bash
voicemd discover
voicemd validate --strict
voicemd compile --surface chat --audience engineer
voicemd compile --surface chat --audience engineer --format sha256
voicemd lint --file generated-answer.md
voicemd test
```

Discovery идёт broad-to-specific. Корень задаётся `VOICE_MD_ROOT` либо определяется через `.voicemd-root`, VCS marker или common project manifest. Local `extends` разрешены; remote `extends` core implementation намеренно не загружает.

## Жёсткая граница полномочий

`VOICE.md` может управлять tone, vocabulary, structure, verbosity, disagreement, uncertainty, audience adaptation и spoken delivery. Он не может менять safety, facts, permissions, tools, legal obligations, exact quotations или required output schema. При конфликте эти ограничения всегда выше voice contract.

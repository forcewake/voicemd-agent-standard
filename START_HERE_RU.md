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

Установка из release wheel возможна после его сборки для текущего source tree. Для текущей reference implementation ожидаемое имя файла — `voicemd-0.1.0a3-py3-none-any.whl`.

Перед установкой убедитесь, что файл существует, `release/BUILD_INFO.json` содержит `"artifact_status": "current"`, а release verifier проходит. Если checkout находится в процессе разработки, wheel отсутствует или artifacts помечены `stale`, используйте editable install либо пересоберите release.

```bash
python -m pip install release/voicemd-0.1.0a3-py3-none-any.whl
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

### 4. Azure OpenAI для regression evals

Да, Azure OpenAI поддерживается. Runner по умолчанию читает repository-local `.env`, поэтому ключ не нужно и нельзя передавать через CLI:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_CHAT_DEPLOYMENT=YOUR-DEPLOYMENT
AZURE_OPENAI_API_VERSION=2024-10-21
```

```bash
python evals/run_openai_compatible.py \
  --provider azure \
  --cases evals/prompts.jsonl \
  --output evals/results.azure.jsonl
```

Azure endpoint обязан использовать HTTPS. Ключ принимается только из environment или `--env-file`; redirects запрещены, чтобы credential header не ушёл на другой origin. Результаты не сохраняют ключ или URL endpoint. Подробности: `evals/README.md`.

### 5. Azure Voice Proof Lab

Для `gpt-audio-1.5`, `gpt-realtime-2.1`, `gpt-realtime-2.1-mini` и
`gpt-live-transcribe` есть отдельный доказательный harness:

```bash
python -m pip install -e '.[azure-voice]'
voicemd-azure doctor
voicemd-azure audio \
  --scenario degraded-service-en \
  --voice examples/azure-voice/contracts/incident_commander/VOICE.md
voicemd-azure realtime --mini \
  --scenario customer-impact-ru \
  --voice examples/azure-voice/contracts/calm_support/VOICE.md
```

Команда `doctor` не вызывает Azure. Реальные `audio`, `realtime`, `transcribe`,
`showcase` и `matrix` создают billable calls. Ключ читается только из environment
или игнорируемого `.env`; в evidence сохраняется fingerprint endpoint, но не URL
и не credential.

`gpt-live-transcribe` сохраняет provider segments и rendered raw transcript без
VoiceMD transformation. `showcase` применяет контракт только к следующему
spoken response. Полная документация, FFmpeg-команда для PCM16 24 kHz mono,
proof boundaries и ссылки на Microsoft: `examples/azure-voice/README.md`.

### 6. Local models и speech

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
  --output .voice/nemotron-voice.txt
```

Это только lower-priority communication fragment, а не полный system prompt. Рабочий `session.update` adapter `integrations/nemotron-voicechat/session_update.py` требует отдельный application-owned base instructions file и объединяет оба слоя в пределах общего лимита.

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

Каждый source после canonical path resolution должен остаться внутри approved source root; symlink не может расширить эту границу, а `.env` и `.env.*` не загружаются как contracts. Reference loader ограничивает размер одного файла, суммарный объём, количество sources, YAML nodes/aliases и глубину `extends`.

После применения profile/audience/surface/tone проверяется уже точный selected contract. Невалидный вариант даёт `nonconforming` и останавливает compilation, lint, sidecar output или provider submission.

## Проверка переносимости

Frontmatter использует YAML 1.2 JSON schema subset и запрещает explicit YAML tags. Canonical JSON и SHA-256 строятся по RFC 8785 JCS после дополнительной VoiceMD-проверки safe-integer domain и не содержат filesystem paths. Language-neutral vectors и независимый от Python core verifier запускаются так:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

Этот verifier покрывает merge, selection, compact rendering, JCS и hashing, но не является полной второй реализацией YAML/discovery/runtime adapters.

## Жёсткая граница полномочий

`VOICE.md` может управлять tone, vocabulary, structure, verbosity, disagreement, uncertainty, audience adaptation и spoken delivery. Он не может менять safety, facts, permissions, tools, legal obligations, exact quotations или required output schema. При конфликте эти ограничения всегда выше voice contract.

## Чего пока не хватает

Draft ещё не имеет vendor adoption или standards-body approval. В metadata проекта пока не зафиксированы canonical public remote и опубликованный canonical schema URL. Нет внешней полной реализации или опубликованного independent security review; цель по проверке минимум на десяти независимых real-world contracts остаётся открытой.

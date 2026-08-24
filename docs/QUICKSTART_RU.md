# Быстрый старт VoiceMD

## Самый простой вариант

Скопируйте `templates/simple/VOICE.md` в корень проекта. Это обычный Markdown без YAML и зависимостей.

```bash
cp templates/simple/VOICE.md ./VOICE.md
```

В приложении его можно просто добавить к system prompt только тогда, когда модель формирует текст для человека:

```python
from pathlib import Path

voice = Path("VOICE.md").read_text(encoding="utf-8")
system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + voice
```

Не добавляйте его при генерации строго заданного JSON, tool calls, SQL, patch/diff или точных цитат.

## Полный вариант

Из исходников:

```bash
python -m pip install -e .
voicemd init --mode full
voicemd validate --strict
voicemd install --target all --mode auto
voicemd doctor
```

Либо из wheel, собранного для текущего release pack. Для draft.2 ожидаемое имя — `voicemd-0.1.0a2-py3-none-any.whl`.

Сначала проверьте, что файл существует, в `release/BUILD_INFO.json` указано `"artifact_status": "current"`, а release verifier проходит. Отсутствующий wheel или wheel со статусом `stale` нельзя считать сборкой текущего source tree.

```bash
python -m pip install release/voicemd-0.1.0a2-py3-none-any.whl
voicemd doctor
```

`--mode auto` ставит маленький bootstrap и Agent Skill. Полный `VOICE.md` должен подтягиваться для человеческого текста, а не для каждой операции агента.

В `--mode explicit` используйте `$voice-contract` в Codex и `/voice-contract` в Claude Code, Copilot CLI или Cursor. Текстовый `@voice` работает только после загрузки contract и не обходит native explicit-only policy. Для Aider явный opt-in — `aider --config .aider.voice.yml`.

## Основные команды

```bash
# Показать все активные VOICE.md от общего к наиболее специфичному
voicemd discover

# Проверить schema и semantic constraints
voicemd validate --strict

# Собрать prompt для обычного чата
voicemd compile --surface chat --audience engineer

# Короткий prompt для небольшой local model
voicemd compile --compact --max-chars 3500

# Spoken profile
voicemd compile --profile voicechat --compact

# NVIDIA NemotronLabs VoiceChat: ASCII-only VoiceMD fragment
voicemd compile \
  --profile nemotron_voicechat \
  --format nemotron-ascii \
  --output .voice/nemotron-voice.txt

# Проверить готовый ответ
voicemd lint --profile executive_brief --file answer.md

# Запустить test cases из VOICE.md
voicemd test
```

Не отправляйте этот fragment как единственный `session.instructions`. Reference adapter требует отдельные application-owned base instructions и добавляет VoiceMD ниже них.

## Как устроены overrides

VoiceMD ищет по одному файлу на каждом уровне от project root до текущей директории. Корень определяется через `VOICE_MD_ROOT`, `.voicemd-root`, ближайший VCS root или common project manifest (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`):

1. `VOICE.override.md`;
2. `VOICE.md`;
3. `.voice/VOICE.override.md`;
4. `.voice/VOICE.md`.

Более близкий файл имеет больший приоритет. Например:

```text
repo/VOICE.md                         общие правила компании
repo/apps/VOICE.md                    правила продукта
repo/apps/support/VOICE.override.md   правила support-agent
```

Для наследования общих contracts можно использовать локальный `extends`:

```yaml
extends:
  - ../../brand/VOICE.md
  - ../../shared/technical-advisor.md
```

Remote URL намеренно не поддерживается core implementation: иначе незаметное изменение удалённого файла меняло бы поведение production-agent.

Все explicit, discovered и inherited sources после canonical path resolution должны остаться внутри approved source root. Symlink не может расширить этот root, а `.env` и `.env.*` не могут быть contract или `extends`. Reference loader также ограничивает один source до 1 MiB, суммарный объём до 4 MiB, уникальные sources до 64, expanded YAML nodes до 20 000, alias references до 100 и глубину `extends` до восьми рёбер. В node budget входят и mapping keys, и values после каждого alias expansion. Эти defaults можно понизить через Python API.

## Profiles

Profile связывает audience, surface и tone:

```yaml
profiles:
  executive_brief:
    audience: executive
    surface: executive_summary
    tone: neutral
  architecture_review:
    audience: engineer
    surface: document
    tone: tough_review
```

Использование:

```bash
voicemd compile --profile architecture_review
```

Profile и explicit selectors применяются до финальной schema/semantic validation. `default_language` нормализуется в `language.default` и проверяется на конфликт после этого merge; в canonical payload alias не остаётся. Blank selector определяется фиксированным Unicode-набором стандарта, а не host-language `trim()`; U+200B считается nonblank. Если конкретная комбинация profile/audience/surface/tone создаёт невалидный contract, runtime обязан остановиться; fallback к непроверенному варианту запрещён.

## Переносимый format и conformance

Structured frontmatter следует YAML 1.2 JSON schema subset. Legacy YAML 1.1 spellings вроде `yes`, `012`, `1_000` и `1:20` остаются строками. Исполняемые count/budget fields принимают finite integral JSON Numbers (`1.0`, `1e0`), нормализуют их в integer и ограничены максимумом `9007199254740991`.

Canonical contract и его hash:

```bash
voicemd compile --profile architecture_review --format canonical-json
voicemd compile --profile architecture_review --format sha256
```

Canonical JSON использует RFC 8785 JCS после более строгой VoiceMD-проверки safe-integer domain и не включает host paths. Language-neutral conformance vectors можно проверить независимым от Python core verifier:

```bash
node integrations/typescript/generated/conformance-verifier.js \
  conformance/vectors.json
```

Он проверяет merge, selection, compact rendering, JCS и hash, но не заменяет полную независимую реализацию parser/discovery/runtime.

Core regex rules используют ASCII-паттерны `portable-safe-v1`: отдельные flags `i`, `m`, `s` разрешены, а alternation, repetition, shorthand classes, lookaround, inline modifiers, backreferences, Unicode escapes и named groups — нет.

## Azure OpenAI regression evals

Runner автоматически читает `.env` из repository root. Нужны следующие environment variables:

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_CHAT_DEPLOYMENT=YOUR-DEPLOYMENT
AZURE_OPENAI_API_VERSION=2024-10-21
```

```bash
python evals/run_openai_compatible.py \
  --provider azure \
  --voice VOICE.md \
  --cases evals/prompts.jsonl \
  --output evals/results.azure.jsonl
```

Azure mode принимает только HTTPS endpoint, берёт ключ только из environment или `--env-file` и не следует redirects. Это не даёт credential header уйти на другой origin и не раскрывает secret в process list. Для отключения repository-local `.env` используйте `--no-env-file`. Полная eval-процедура описана в `evals/README.md` и `docs/EVALS.md`.

## Приложения без Python SDK

Запустите sidecar:

```bash
voicemd serve --host 127.0.0.1 --port 8765
```

Получите prompt:

```bash
curl 'http://127.0.0.1:8765/v1/voice/prompt?profile=executive_brief'
```

Проверьте текст:

```bash
curl -X POST http://127.0.0.1:8765/v1/voice/lint \
  -H 'Content-Type: application/json' \
  -d '{"profile":"executive_brief","text":"Your generated answer"}'
```

OpenAPI лежит в `integrations/http/openapi.yaml`.

## Что принципиально нельзя класть в VOICE.md

`VOICE.md` не должен выдавать агенту permissions, разрешать tool calls, обходить safety, менять факты, требовать раскрытия hidden reasoning, переопределять юридические требования или ломать обязательную output schema. Такие инструкции runtime обязан игнорировать независимо от содержимого файла.

## Как начать именно со своего агента

Возьмите `templates/full/VOICE.md`, замените `identity`, `epistemics`, `interaction`, `audiences`, `surfaces` и примеры. Не начинайте с двадцати прилагательных. Начните с контрастов и наблюдаемого поведения:

```text
Плохо: professional, helpful, concise.

Хорошо:
- При достаточных данных говорит вывод прямо.
- При нехватке данных называет конкретно отсутствующую переменную.
- Не усиливает уверенность из-за повторного вопроса.
- Поправляет неверную premise до дальнейшего анализа.
- Для executive сначала даёт impact и decision; для engineer — mechanism и failure mode.
```

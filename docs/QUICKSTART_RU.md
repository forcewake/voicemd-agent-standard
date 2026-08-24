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

Либо из готового wheel внутри release pack:

```bash
python -m pip install release/voicemd-0.1.0a1-py3-none-any.whl
voicemd doctor
```

`--mode auto` ставит маленький bootstrap и Agent Skill. Полный `VOICE.md` должен подтягиваться для человеческого текста, а не для каждой операции агента.

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

# NVIDIA NemotronLabs VoiceChat: ASCII-only system instructions
voicemd compile \
  --profile nemotron_voicechat \
  --format nemotron-ascii \
  --output .voice/nemotron-system.txt

# Проверить готовый ответ
voicemd lint --profile executive_brief --file answer.md

# Запустить test cases из VOICE.md
voicemd test
```

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

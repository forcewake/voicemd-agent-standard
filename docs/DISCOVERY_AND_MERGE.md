# Discovery, inheritance, and merge

## Candidate search

The reference CLI discovers one source per directory. Candidate priority is:

```text
VOICE.override.md
VOICE.md
.voice/VOICE.override.md
.voice/VOICE.md
```

Example:

```text
repo/
  VOICE.md                         # selected at root
  apps/
    VOICE.md                       # selected for all apps
    sales/
      .voice/VOICE.md              # selected for sales
      proposal/
        VOICE.override.md          # selected for proposal work
        VOICE.md                   # ignored at this same level
```

Running from `repo/apps/sales/proposal` produces this broad-to-specific chain:

```text
repo/VOICE.md
repo/apps/VOICE.md
repo/apps/sales/.voice/VOICE.md
repo/apps/sales/proposal/VOICE.override.md
```

## Project root selection

The reference implementation resolves the root in this order:

1. `VOICE_MD_ROOT`, when explicitly set and containing the start directory;
2. the nearest `.voicemd-root`, `.git`, `.hg`, or `.svn` marker;
3. the nearest `pyproject.toml`, `package.json`, `go.mod`, or `Cargo.toml`;
4. the discovery start directory.

Use an empty `.voicemd-root` file in exported source archives, containers, monorepo subtrees, or other non-Git deployments that need deterministic hierarchy.

## Explicit source behavior

`--path` and `VOICE_MD` are intended for CI, containers, packaged applications, and deterministic production deployments. They replace project discovery rather than mixing unpredictably with it.

Multiple paths are overlays in the order provided:

```bash
voicemd compile \
  --path contracts/company.md \
  --path contracts/product.md \
  --path contracts/spoken-support.md
```

## Local inheritance

Use `extends` when a file is compositionally based on another contract, even outside the current working-directory hierarchy:

```yaml
extends:
  - ../../contracts/brand.md
  - ../../contracts/technical-advisor.md
```

Each extended source loads before its child. Cycles fail validation.

## Why remote inheritance is off

An unpinned URL makes agent behavior depend on mutable remote content. Risks include:

- supply-chain compromise;
- accidental breaking changes;
- nondeterministic builds;
- hidden changes to production behavior;
- authentication and availability failures;
- prompt injection from an external publisher.

Vendor the file into the repository or implement an organization-controlled resolver with immutable digest pinning and signatures.

## Merge examples

### Scalars replace

```yaml
# broad
response:
  max_words: 300

# specific
response:
  max_words: 100
```

Resolved value: `100`.

### Objects deep-merge

```yaml
# broad
response:
  max_words: 300
  opening: conclusion_first

# specific
response:
  max_words: 100
```

Resolved response keeps `opening` and overrides `max_words`.

### Lists usually replace

A local audience list or arbitrary sequence replaces its inherited value. This avoids ambiguous concatenation.

### Selected lists append uniquely

Forbidden phrases and activation categories are cumulative by default:

```yaml
# broad
lexicon:
  forbidden: ["Great question"]

# specific
lexicon:
  forbidden: ["Absolutely"]
```

Resolved list contains both.

### Dormant selector deletions

`null` inside an audience, surface, tone, or profile-local override is retained
while filesystem sources merge. It is a tombstone for the eventual selector
merge, not a request to erase the dormant overlay entry early. Once that exact
selector is applied, the key is deleted and no core merge-time `null` remains.

The same delayed-consumption rule applies to `rules`, `tests`, and `examples`
items with `disabled: true`. A later source must retain that ID tombstone inside
the dormant selector so applying the selector can remove the inherited top-level
item.

### ID-based arrays

```yaml
# broad
rules:
  - id: no-hype
    severity: warning
    pattern: "game-changing"
    flags: [i]

# specific
rules:
  - id: no-hype
    severity: error
```

The item deep-merges by ID. To remove it:

```yaml
rules:
  - id: no-hype
    disabled: true
```

## Markdown body precedence

Bodies are concatenated broad-to-specific. Avoid implicit contradictions in prose because structured merge cannot resolve them. Use explicit headings and contrast:

```md
## Override of company default

For this emergency-support surface, acknowledge user impact once before the technical diagnosis.
```

For highly governed deployments, prefer structured fields for rules that must be mechanically selected or tested.

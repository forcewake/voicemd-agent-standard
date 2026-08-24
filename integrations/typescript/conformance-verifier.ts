import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";

type JsonPrimitive = null | boolean | number | string;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };
type Selectors = {
  profile?: string | null;
  audience?: string | null;
  surface?: string | null;
  tone?: string | null;
};

type ActiveSelectors = {
  profile: string | null;
  audience: string | null;
  surface: string | null;
  tone: string | null;
};

type SelectionResult = {
  contract: JsonObject;
  active: ActiveSelectors;
};

type CoreAssertions = {
  must_contain?: string[];
  must_not_contain?: string[];
  max_words?: number;
  ascii_only?: boolean;
  lint_clean?: boolean;
  [key: string]: JsonValue | undefined;
};

const APPEND_UNIQUE_PATHS = new Set([
  "activation/include",
  "activation/exclude",
  "authority/may_control",
  "authority/must_not_control",
  "language/allowed",
  "lexicon/preferred",
  "lexicon/forbidden",
  "formatting/avoid",
  "speech/avoid",
]);
const MERGE_BY_ID_KEYS = new Set(["rules", "tests", "examples"]);
const SELECTOR_CATEGORIES = new Set(["audiences", "surfaces", "tones"]);
const PORTABLE_SELECTOR_WHITESPACE_ONLY =
  /^[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u;
const COMPACT_SECTIONS = [
  "identity",
  "response",
  "language",
  "lexicon",
  "epistemics",
  "interaction",
  "formatting",
  "speech",
] as const;

class ConformanceError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ConformanceError";
    this.code = code;
  }
}

function isDormantSelectorOverlay(path: string[]): boolean {
  if (path.length >= 2 && SELECTOR_CATEGORIES.has(path[0])) return true;
  return path.length >= 3 && path[0] === "profiles" && path[2] === "overrides";
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone<T extends JsonValue>(value: T): T {
  return structuredClone(value);
}

function appendUnique(base: JsonValue[], override: JsonValue[]): JsonValue[] {
  const result = clone(base);
  for (const item of override) {
    if (!result.some((existing) => isDeepStrictEqual(existing, item))) {
      result.push(clone(item));
    }
  }
  return result;
}

function normalizedCopy(
  value: JsonValue,
  path: string[],
  appendUniqueArrays: boolean,
): JsonValue {
  if (isObject(value)) {
    return deepMerge({}, value, path, appendUniqueArrays);
  }
  if (Array.isArray(value)) {
    return value.map((item, index) =>
      typeof item === "object" && item !== null
        ? normalizedCopy(item, [...path, String(index)], appendUniqueArrays)
        : clone(item),
    );
  }
  return clone(value);
}

function mergeById(
  base: JsonValue[],
  override: JsonValue[],
  path: string[],
  appendUniqueArrays: boolean,
): JsonValue[] {
  const result = clone(base);
  const preserveTombstones = appendUniqueArrays && isDormantSelectorOverlay(path);
  let positions = idPositions(result);
  for (const item of override) {
    if (!isObject(item) || typeof item.id !== "string") {
      result.push(clone(item));
      continue;
    }
    const itemId = item.id;
    if (item.disabled === true) {
      if (preserveTombstones) {
        const tombstone = clone(item);
        const position = positions.get(itemId);
        if (position !== undefined) {
          result[position] = tombstone;
        } else {
          positions.set(itemId, result.length);
          result.push(tombstone);
        }
        continue;
      }
      const position = positions.get(itemId);
      if (position !== undefined) {
        result.splice(position, 1);
        positions = idPositions(result);
      }
      continue;
    }
    const position = positions.get(itemId);
    if (position !== undefined) {
      if (
        preserveTombstones &&
        isObject(result[position]) &&
        result[position].disabled === true
      ) {
        result[position] = normalizedCopy(item, [...path, itemId], appendUniqueArrays);
      } else {
        result[position] = deepMerge(
          result[position],
          item,
          [...path, itemId],
          appendUniqueArrays,
        );
      }
    } else {
      positions.set(itemId, result.length);
      result.push(normalizedCopy(item, [...path, itemId], appendUniqueArrays));
    }
  }
  return result;
}

function idPositions(items: JsonValue[]): Map<string, number> {
  const positions = new Map<string, number>();
  items.forEach((item, index) => {
    if (isObject(item) && typeof item.id === "string") {
      positions.set(item.id, index);
    }
  });
  return positions;
}

export function deepMerge(
  base: JsonValue,
  override: JsonValue,
  path: string[] = [],
  appendUniqueArrays = true,
): JsonValue {
  if (base === null) {
    return normalizedCopy(override, path, appendUniqueArrays);
  }
  if (override === null) {
    return null;
  }
  if (isObject(base) && isObject(override)) {
    const result = clone(base);
    for (const [key, value] of Object.entries(override)) {
      if (value === null) {
        if (appendUniqueArrays && isDormantSelectorOverlay(path)) {
          result[key] = null;
        } else {
          delete result[key];
        }
      } else if (Object.hasOwn(result, key)) {
        result[key] = deepMerge(result[key], value, [...path, key], appendUniqueArrays);
      } else {
        const childPath = [...path, key];
        result[key] =
          Array.isArray(value) && MERGE_BY_ID_KEYS.has(key)
            ? mergeById([], value, childPath, appendUniqueArrays)
            : normalizedCopy(value, childPath, appendUniqueArrays);
      }
    }
    return result;
  }
  if (Array.isArray(base) && Array.isArray(override)) {
    const key = path.at(-1);
    if (key !== undefined && MERGE_BY_ID_KEYS.has(key)) {
      return mergeById(base, override, path, appendUniqueArrays);
    }
    if (appendUniqueArrays && APPEND_UNIQUE_PATHS.has(path.join("/"))) {
      return appendUnique(base, override);
    }
    return clone(override);
  }
  return clone(override);
}

function requiredObject(value: JsonValue | undefined, code: string, message: string): JsonObject {
  if (!isObject(value)) {
    throw new ConformanceError(code, message);
  }
  return value;
}

function selectorValue(value: JsonValue | undefined, label: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") {
    throw new ConformanceError("selector-not-string", `${label} selector must be a string`);
  }
  if (PORTABLE_SELECTOR_WHITESPACE_ONLY.test(value)) {
    throw new ConformanceError("empty-selector", `${label} selector must not be empty`);
  }
  return value;
}

function validateSelectorNames(data: JsonObject): void {
  for (const category of ["audiences", "surfaces", "tones", "profiles"] as const) {
    const mapping = data[category];
    if (!isObject(mapping)) continue;
    for (const name of Object.keys(mapping)) {
      if (PORTABLE_SELECTOR_WHITESPACE_ONLY.test(name)) {
        throw new ConformanceError(
          "empty-selector",
          `${category} contains an empty selector name`,
        );
      }
    }
  }
  const profiles = data.profiles;
  if (isObject(profiles)) {
    for (const [name, rawProfile] of Object.entries(profiles)) {
      if (!isObject(rawProfile)) continue;
      for (const selector of ["audience", "surface", "tone"] as const) {
        selectorValue(rawProfile[selector], `profile '${name}' ${selector}`);
      }
    }
  }
  const tests = data.tests;
  if (Array.isArray(tests)) {
    tests.forEach((rawTest, index) => {
      if (!isObject(rawTest)) return;
      for (const selector of ["profile", "audience", "surface", "tone"] as const) {
        selectorValue(rawTest[selector], `test ${index} ${selector}`);
      }
    });
  }
}

function normalizeLanguageAliases(mapping: JsonObject, path: string[]): void {
  if (!Object.hasOwn(mapping, "default_language")) return;
  const legacy = mapping.default_language;
  const selectorOverlay = isDormantSelectorOverlay(path);
  if (legacy !== null && typeof legacy !== "string") {
    throw new ConformanceError(
      "default-language-type",
      `${path.join(".") || "contract"}.default_language must be a string`,
    );
  }
  if (legacy === null && !selectorOverlay) {
    throw new ConformanceError(
      "default-language-type",
      `${path.join(".") || "contract"}.default_language must be a string`,
    );
  }

  let language = mapping.language;
  if (language === undefined || (legacy === null && language === null)) {
    language = {};
    mapping.language = language;
  }
  if (!isObject(language)) {
    throw new ConformanceError(
      "default-language-conflict",
      `${path.join(".") || "contract"}.default_language requires language to be an object`,
    );
  }
  if (Object.hasOwn(language, "default") && language.default !== legacy) {
    throw new ConformanceError(
      "default-language-conflict",
      `${path.join(".") || "contract"}.default_language conflicts with language.default`,
    );
  }
  language.default = legacy;
  delete mapping.default_language;
}

function prepareSelectorOverlay(data: JsonObject): JsonObject {
  const prepared = clone(data);
  if (!Object.hasOwn(prepared, "default_language") || prepared.default_language !== null) {
    return prepared;
  }
  const language = prepared.language;
  if (language === undefined) {
    prepared.language = { default: null };
  } else if (language !== null) {
    if (!isObject(language)) {
      throw new ConformanceError(
        "default-language-conflict",
        "selector default_language requires language to be an object",
      );
    }
    if (Object.hasOwn(language, "default") && language.default !== null) {
      throw new ConformanceError(
        "default-language-conflict",
        "selector default_language conflicts with language.default",
      );
    }
    language.default = null;
  }
  delete prepared.default_language;
  return prepared;
}

function normalizeContractData(
  data: JsonObject,
  normalizeDormantAliases = true,
): JsonObject {
  const normalized = clone(data);

  const visit = (mapping: JsonObject, path: string[]): void => {
    if (path.length === 0 || normalizeDormantAliases) {
      normalizeLanguageAliases(mapping, path);
    }
    for (const category of ["audiences", "surfaces", "tones"] as const) {
      const variants = mapping[category];
      if (!isObject(variants)) continue;
      for (const [name, override] of Object.entries(variants)) {
        if (isObject(override)) visit(override, [...path, category, name]);
      }
    }
    const profiles = mapping.profiles;
    if (!isObject(profiles)) return;
    for (const [name, rawProfile] of Object.entries(profiles)) {
      if (!isObject(rawProfile) || !isObject(rawProfile.overrides)) continue;
      visit(rawProfile.overrides, [...path, "profiles", name, "overrides"]);
    }
  };

  visit(normalized, []);
  return normalized;
}

function requirePortableInteger(value: JsonValue, path: string, minimum: number): void {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    !Number.isSafeInteger(value) ||
    value < minimum
  ) {
    throw new ConformanceError(
      "invalid-executable-integer",
      `${path} must be a safe integer greater than or equal to ${minimum}`,
    );
  }
}

function validateExecutableIntegers(data: JsonObject): void {
  const response = data.response;
  if (isObject(response)) {
    for (const key of ["max_words", "max_sentences"] as const) {
      if (Object.hasOwn(response, key)) {
        requirePortableInteger(response[key], `response.${key}`, 0);
      }
    }
  }
  const runtime = data.runtime;
  if (isObject(runtime) && Object.hasOwn(runtime, "max_prompt_chars")) {
    requirePortableInteger(runtime.max_prompt_chars, "runtime.max_prompt_chars", 256);
  }
  const tests = data.tests;
  if (!Array.isArray(tests)) return;
  tests.forEach((rawTest, index) => {
    if (!isObject(rawTest) || !isObject(rawTest.assertions)) return;
    if (Object.hasOwn(rawTest.assertions, "max_words")) {
      requirePortableInteger(
        rawTest.assertions.max_words,
        `tests[${index}].assertions.max_words`,
        0,
      );
    }
  });
}

export function selectContract(data: JsonObject, selectors: Selectors = {}): SelectionResult {
  let selected = normalizeContractData(data, false);
  validateSelectorNames(selected);

  const profiles = selected.profiles;
  let activeProfile = selectorValue(selectors.profile, "profile");
  if (activeProfile === null && isObject(profiles) && Object.hasOwn(profiles, "default")) {
    activeProfile = "default";
  }

  let audience = selectorValue(selectors.audience, "audience");
  let surface = selectorValue(selectors.surface, "surface");
  let tone = selectorValue(selectors.tone, "tone");
  let profileOverrides: JsonObject = {};
  if (activeProfile !== null) {
    if (!isObject(profiles) || !Object.hasOwn(profiles, activeProfile)) {
      throw new ConformanceError("unknown-profile", `Unknown profile: ${activeProfile}`);
    }
    const profile = requiredObject(
      profiles[activeProfile],
      "profile-not-object",
      `Profile '${activeProfile}' must be an object`,
    );
    const profileAudience = selectorValue(profile.audience, `profile '${activeProfile}' audience`);
    const profileSurface = selectorValue(profile.surface, `profile '${activeProfile}' surface`);
    const profileTone = selectorValue(profile.tone, `profile '${activeProfile}' tone`);
    if (audience === null) audience = profileAudience;
    if (surface === null) surface = profileSurface;
    if (tone === null) tone = profileTone;
    const rawOverrides = profile.overrides ?? {};
    profileOverrides = requiredObject(
      rawOverrides,
      "profile-overrides-not-object",
      `Profile '${activeProfile}' overrides must be an object`,
    );
  }

  for (const [category, name] of [
    ["audiences", audience],
    ["surfaces", surface],
    ["tones", tone],
  ] as const) {
    if (name === null) continue;
    const variants = selected[category];
    const singular = category.slice(0, -1);
    if (!isObject(variants) || !Object.hasOwn(variants, name)) {
      throw new ConformanceError(`unknown-${singular}`, `Unknown ${singular}: ${name}`);
    }
    const variant = requiredObject(
      variants[name],
      `${singular}-not-object`,
      `${singular} '${name}' must be an object`,
    );
    selected = requiredObject(
      deepMerge(selected, prepareSelectorOverlay(variant), [], false),
      "selection-not-object",
      "Selected contract must be an object",
    );
  }
  selected = requiredObject(
    deepMerge(selected, prepareSelectorOverlay(profileOverrides), [], false),
    "selection-not-object",
    "Selected contract must be an object",
  );
  selected = normalizeContractData(selected);
  validateExecutableIntegers(selected);
  return {
    contract: selected,
    active: { profile: activeProfile, audience, surface, tone },
  };
}

function assertWellFormedUnicode(value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new ConformanceError("invalid-unicode", "JCS input contains a lone surrogate");
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new ConformanceError("invalid-unicode", "JCS input contains a lone surrogate");
    }
  }
}

export function canonicalize(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) {
      throw new ConformanceError(
        "non-ijson-number",
        "JCS number is outside the VoiceMD interoperability domain",
      );
    }
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    assertWellFormedUnicode(value);
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalize(item)).join(",")}]`;
  }
  const members = Object.keys(value)
    .sort()
    .map((key) => {
      assertWellFormedUnicode(key);
      return `${JSON.stringify(key)}:${canonicalize(value[key])}`;
    });
  return `{${members.join(",")}}`;
}

function trimVoiceWhitespace(value: string): string {
  return value.replace(/^[\u0009\u000a\u000d\u0020]+|[\u0009\u000a\u000d\u0020]+$/g, "");
}

function normalizedBodies(bodies: string[]): string[] {
  return bodies
    .map((body) =>
      trimVoiceWhitespace(body.replace(/\r\n/g, "\n").replace(/\r/g, "\n")),
    )
    .filter((body) => body.length > 0);
}

export function canonicalContract(
  contract: JsonObject,
  bodies: string[] = [],
  selectors: Selectors = {},
): { canonical: string; sha256: string } {
  const selected = selectContract(contract, selectors);
  const payload: JsonObject = {
    active: selected.active,
    contract: selected.contract,
    markdown_bodies: normalizedBodies(bodies),
  };
  const canonical = canonicalize(payload);
  return {
    canonical,
    sha256: createHash("sha256").update(canonical, "utf8").digest("hex"),
  };
}

function sentence(value: JsonValue): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value === null) return "unspecified";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return readableSortedJson(value);
}

function readableSortedJson(value: JsonValue): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new ConformanceError("non-json-number", "Compact input contains a non-finite number");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(readableSortedJson).join(", ")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}: ${readableSortedJson(value[key])}`)
    .join(", ")}}`;
}

function compactMapping(mapping: JsonValue | undefined, prefix: string): string[] {
  if (!isObject(mapping)) return [];
  const lines: string[] = [];
  for (const [key, value] of Object.entries(mapping)) {
    if (isObject(value)) {
      lines.push(...compactMapping(value, `${prefix}${key}.`));
    } else if (Array.isArray(value)) {
      if (value.length > 0) lines.push(`${prefix}${key}=${value.map(sentence).join("; ")}`);
    } else if (value !== null) {
      lines.push(`${prefix}${key}=${sentence(value)}`);
    }
  }
  return lines;
}

export function compileCompact(
  contract: JsonObject,
  bodies: string[] = [],
  selectors: Selectors = {},
): string {
  const { contract: selected } = selectContract(contract, selectors);
  const lines = [
    "VOICE CONTRACT. Apply only to human-facing natural language.",
    "Higher-priority safety, policy, factual, tool, and output-schema instructions win.",
  ];
  for (const key of COMPACT_SECTIONS) {
    lines.push(...compactMapping(selected[key], `${key}.`));
  }
  const rules = selected.rules;
  if (Array.isArray(rules)) {
    for (const rule of rules) {
      if (!isObject(rule) || rule.disabled === true) continue;
      const instruction = rule.instruction ?? rule.description;
      if (typeof instruction === "string" && instruction.length > 0) {
        const id = typeof rule.id === "string" ? rule.id : "unnamed";
        lines.push(`rule.${id}=${instruction}`);
      }
    }
  }
  const body = normalizedBodies(bodies).join("\n\n");
  if (body.length > 0) lines.push("Additional guidance:", body);
  return trimVoiceWhitespace(lines.join("\n"));
}

export function normalizePortableRegexInput(value: string): string {
  return value.replace(/\r\n|\r|\u2028|\u2029/g, "\n");
}

function regexFlags(value: JsonValue | undefined): string {
  if (value === undefined) return "";
  if (!Array.isArray(value) || !value.every((flag) => typeof flag === "string")) {
    throw new ConformanceError("invalid-vector", "regex flags must be an array of strings");
  }
  const flags = value as string[];
  if (new Set(flags).size !== flags.length || flags.some((flag) => !["i", "m", "s"].includes(flag))) {
    throw new ConformanceError("invalid-vector", "regex flags must contain unique i, m, or s values");
  }
  return flags.join("");
}

export function portableRegexMatches(
  pattern: string,
  text: string,
  flags: JsonValue | undefined = undefined,
): boolean {
  try {
    return new RegExp(pattern, regexFlags(flags)).test(normalizePortableRegexInput(text));
  } catch (error) {
    if (error instanceof ConformanceError) throw error;
    throw new ConformanceError("invalid-vector", `invalid regex vector: ${String(error)}`);
  }
}

export function asciiCaseFold(value: string): string {
  return value.replace(/[A-Z]/g, (character) => character.toLowerCase());
}

export function countPortableWords(value: string): number {
  let count = 0;
  let inWord = false;
  for (const character of value) {
    const code = character.codePointAt(0) as number;
    const separator =
      (code >= 0x00 && code <= 0x2f) ||
      (code >= 0x3a && code <= 0x40) ||
      (code >= 0x5b && code <= 0x60) ||
      (code >= 0x7b && code <= 0x7e);
    if (separator) {
      inWord = false;
    } else if (!inWord) {
      count += 1;
      inWord = true;
    }
  }
  return count;
}

function stringArray(value: JsonValue | undefined, label: string): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new ConformanceError("invalid-vector", `${label} must be an array of strings`);
  }
  return value as string[];
}

export function evaluateCoreAssertions(
  response: string,
  assertions: CoreAssertions,
): { passed: boolean; failures: string[] } {
  const supported = new Set([
    "must_contain",
    "must_not_contain",
    "max_words",
    "ascii_only",
    "lint_clean",
  ]);
  const unknown = Object.keys(assertions).filter(
    (key) => !supported.has(key) && !key.startsWith("x-"),
  );
  if (unknown.length > 0) {
    throw new ConformanceError("invalid-vector", `unsupported assertion: ${unknown.sort()[0]}`);
  }

  const folded = asciiCaseFold(response);
  const failures: string[] = [];
  const required = stringArray(assertions.must_contain, "must_contain");
  const forbidden = stringArray(assertions.must_not_contain, "must_not_contain");
  let effective = required.length > 0 || forbidden.length > 0;
  for (const phrase of required) {
    if (!folded.includes(asciiCaseFold(phrase))) failures.push(`must_contain:${phrase}`);
  }
  for (const phrase of forbidden) {
    if (folded.includes(asciiCaseFold(phrase))) failures.push(`must_not_contain:${phrase}`);
  }

  const maxWords = assertions.max_words;
  if (
    maxWords !== undefined &&
    (typeof maxWords !== "number" || !Number.isSafeInteger(maxWords) || maxWords < 0)
  ) {
    throw new ConformanceError("invalid-vector", "max_words must be a non-negative safe integer");
  }
  if (typeof maxWords === "number" && countPortableWords(response) > maxWords) {
    failures.push("max_words");
  }
  if (typeof maxWords === "number") effective = true;

  const asciiOnly = assertions.ascii_only;
  if (asciiOnly !== undefined && typeof asciiOnly !== "boolean") {
    throw new ConformanceError("invalid-vector", "ascii_only must be a boolean");
  }
  if (asciiOnly === true && !/^[\x00-\x7f]*$/.test(response)) failures.push("ascii_only");
  if (asciiOnly === true) effective = true;

  if (assertions.lint_clean === true) {
    throw new ConformanceError(
      "invalid-vector",
      "lint_clean vectors require a selected contract and are outside this standalone runner",
    );
  }
  if (assertions.lint_clean !== undefined && typeof assertions.lint_clean !== "boolean") {
    throw new ConformanceError("invalid-vector", "lint_clean must be a boolean");
  }
  if (!effective) failures.push("no-effective-assertion");
  return { passed: failures.length === 0, failures };
}

function pointerValue(document: JsonValue, pointer: string): { found: boolean; value?: JsonValue } {
  if (pointer === "") return { found: true, value: document };
  if (!pointer.startsWith("/")) {
    throw new ConformanceError("invalid-vector", `Invalid JSON Pointer: ${pointer}`);
  }
  let current: JsonValue = document;
  for (const rawPart of pointer.slice(1).split("/")) {
    const part = rawPart.replace(/~1/g, "/").replace(/~0/g, "~");
    if (Array.isArray(current)) {
      if (!/^\d+$/.test(part) || Number(part) >= current.length) return { found: false };
      current = current[Number(part)];
    } else if (isObject(current) && Object.hasOwn(current, part)) {
      current = current[part];
    } else {
      return { found: false };
    }
  }
  return { found: true, value: current };
}

function setPointerValue(document: JsonObject, pointer: string, value: JsonValue): void {
  if (!pointer.startsWith("/") || pointer === "/") {
    throw new ConformanceError("invalid-vector", `Invalid mutation JSON Pointer: ${pointer}`);
  }
  const parts = pointer
    .slice(1)
    .split("/")
    .map((part) => part.replace(/~1/g, "/").replace(/~0/g, "~"));
  let current: JsonObject = document;
  for (const part of parts.slice(0, -1)) {
    current = requiredObject(current[part], "invalid-vector", `Mutation path not found: ${pointer}`);
  }
  current[parts.at(-1) as string] = value;
}

function contractFromVector(vector: JsonObject, label: string): JsonObject {
  const contract = clone(vectorObject(vector.contract, label));
  for (const raw of vectorArray(vector.encoded_values ?? [], "encoded_values")) {
    const encoded = vectorObject(raw, "encoded value");
    const pointer = vectorString(encoded.pointer, "encoded value pointer");
    const rawUnits = vectorArray(encoded.utf16_code_units, "utf16_code_units");
    if (
      !rawUnits.every(
        (unit) => typeof unit === "number" && Number.isInteger(unit) && unit >= 0 && unit <= 0xffff,
      )
    ) {
      throw new ConformanceError("invalid-vector", "UTF-16 code units must be integers from 0 to 65535");
    }
    setPointerValue(contract, pointer, String.fromCharCode(...(rawUnits as number[])));
  }
  return contract;
}

function vectorObject(value: JsonValue | undefined, label: string): JsonObject {
  return requiredObject(value, "invalid-vector", `${label} must be an object`);
}

function vectorArray(value: JsonValue | undefined, label: string): JsonValue[] {
  if (!Array.isArray(value)) {
    throw new ConformanceError("invalid-vector", `${label} must be an array`);
  }
  return value;
}

function vectorString(value: JsonValue | undefined, label: string): string {
  if (typeof value !== "string") {
    throw new ConformanceError("invalid-vector", `${label} must be a string`);
  }
  return value;
}

function selectorsFrom(value: JsonValue | undefined): Selectors {
  const object = vectorObject(value ?? {}, "selectors");
  const selectors: Selectors = {};
  for (const key of ["profile", "audience", "surface", "tone"] as const) {
    const selector = object[key];
    if (selector !== undefined && selector !== null && typeof selector !== "string") {
      throw new ConformanceError("invalid-vector", `selectors.${key} must be a string or null`);
    }
    if (selector !== undefined) selectors[key] = selector as string | null;
  }
  return selectors;
}

function bodiesFrom(value: JsonValue | undefined): string[] {
  const bodies = vectorArray(value ?? [], "bodies");
  if (!bodies.every((body) => typeof body === "string")) {
    throw new ConformanceError("invalid-vector", "bodies entries must be strings");
  }
  return bodies as string[];
}

function resolveSelectionContract(vector: JsonObject, selectionById: Map<string, JsonObject>): JsonObject {
  if (vector.contract !== undefined) return vectorObject(vector.contract, "selection contract");
  const reference = vectorString(vector.contract_ref, "contract_ref");
  const referenced = selectionById.get(reference);
  if (referenced === undefined) {
    throw new ConformanceError("invalid-vector", `Unknown selection contract_ref: ${reference}`);
  }
  return vectorObject(referenced.contract, "referenced selection contract");
}

function verifyExpectedError(vector: JsonObject): void {
  const expected = vectorString(vector.expected_error, "expected_error");
  try {
    const operation = vectorString(vector.operation, "operation");
    const contract = contractFromVector(vector, "invalid contract");
    if (operation === "selection") {
      selectContract(contract, selectorsFrom(vector.selectors));
    } else if (operation === "canonical") {
      canonicalContract(contract, bodiesFrom(vector.bodies), selectorsFrom(vector.selectors));
    } else {
      throw new ConformanceError("invalid-vector", `Unknown invalid operation: ${operation}`);
    }
  } catch (error) {
    if (error instanceof ConformanceError && error.code === expected) return;
    const actual = error instanceof ConformanceError ? error.code : String(error);
    throw new ConformanceError(
      "unexpected-error",
      `${vectorString(vector.id, "id")}: expected ${expected}, got ${actual}`,
    );
  }
  throw new ConformanceError(
    "missing-error",
    `${vectorString(vector.id, "id")}: expected ${expected}, but operation succeeded`,
  );
}

export function verifyCorpus(corpus: JsonObject): { passed: number; total: number } {
  if (corpus.suite_version !== "0.1.0") {
    throw new ConformanceError("unsupported-suite", "Unsupported conformance suite version");
  }
  const groups = vectorObject(corpus.vectors, "vectors");
  const failures: string[] = [];
  let passed = 0;
  let total = 0;
  const seenIds = new Set<string>();
  const record = (vector: JsonObject, action: () => void): void => {
    total += 1;
    let id = "<missing-id>";
    try {
      id = vectorString(vector.id, "id");
      if (seenIds.has(id)) throw new ConformanceError("duplicate-id", `Duplicate vector id: ${id}`);
      seenIds.add(id);
      action();
      passed += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failures.push(`${id}: ${message}`);
    }
  };

  for (const raw of vectorArray(groups.merge, "vectors.merge")) {
    const vector = vectorObject(raw, "merge vector");
    record(vector, () => {
      const actual = deepMerge(
        vector.base ?? null,
        vector.override ?? null,
        [],
        vector.append_unique_arrays !== false,
      );
      if (!isDeepStrictEqual(actual, vector.expected)) {
        throw new ConformanceError(
          "mismatch",
          `merge mismatch: ${JSON.stringify(actual)}`,
        );
      }
    });
  }

  const selectionVectors = vectorArray(groups.selection, "vectors.selection").map((raw) =>
    vectorObject(raw, "selection vector"),
  );
  const selectionById = new Map(
    selectionVectors.map((vector) => [vectorString(vector.id, "id"), vector]),
  );
  for (const vector of selectionVectors) {
    record(vector, () => {
      const result = selectContract(
        resolveSelectionContract(vector, selectionById),
        selectorsFrom(vector.selectors),
      );
      if (!isDeepStrictEqual(result.active, vector.expected_active)) {
        throw new ConformanceError("mismatch", `active selector mismatch: ${JSON.stringify(result.active)}`);
      }
      const expectedValues = vectorObject(vector.expected_values, "expected_values");
      for (const [pointer, expected] of Object.entries(expectedValues)) {
        const actual = pointerValue(result.contract, pointer);
        if (!actual.found || !isDeepStrictEqual(actual.value, expected)) {
          throw new ConformanceError("mismatch", `${pointer} mismatch`);
        }
      }
      for (const rawPointer of vectorArray(vector.expected_absent ?? [], "expected_absent")) {
        const pointer = vectorString(rawPointer, "expected_absent entry");
        if (pointerValue(result.contract, pointer).found) {
          throw new ConformanceError("mismatch", `${pointer} should be absent`);
        }
      }
    });
  }

  for (const raw of vectorArray(groups.canonical, "vectors.canonical")) {
    const vector = vectorObject(raw, "canonical vector");
    record(vector, () => {
      const actual = canonicalContract(
        vectorObject(vector.contract, "canonical contract"),
        bodiesFrom(vector.bodies),
        selectorsFrom(vector.selectors),
      );
      if (actual.canonical !== vector.expected_canonical) {
        throw new ConformanceError("mismatch", `canonical mismatch: ${actual.canonical}`);
      }
      if (actual.sha256 !== vector.expected_sha256) {
        throw new ConformanceError("mismatch", `SHA-256 mismatch: ${actual.sha256}`);
      }
    });
  }

  for (const raw of vectorArray(groups.compact, "vectors.compact")) {
    const vector = vectorObject(raw, "compact vector");
    record(vector, () => {
      const actual = compileCompact(
        vectorObject(vector.contract, "compact contract"),
        bodiesFrom(vector.bodies),
        selectorsFrom(vector.selectors),
      );
      if (actual !== vector.expected) {
        throw new ConformanceError("mismatch", `compact mismatch: ${JSON.stringify(actual)}`);
      }
    });
  }

  for (const raw of vectorArray(groups.regex, "vectors.regex")) {
    const vector = vectorObject(raw, "regex vector");
    record(vector, () => {
      const actual = portableRegexMatches(
        vectorString(vector.pattern, "regex pattern"),
        vectorString(vector.text, "regex text"),
        vector.flags,
      );
      if (typeof vector.expected_match !== "boolean") {
        throw new ConformanceError("invalid-vector", "expected_match must be a boolean");
      }
      if (actual !== vector.expected_match) {
        throw new ConformanceError("mismatch", `regex match mismatch: ${String(actual)}`);
      }
    });
  }

  for (const raw of vectorArray(groups.assertions, "vectors.assertions")) {
    const vector = vectorObject(raw, "assertion vector");
    record(vector, () => {
      const result = evaluateCoreAssertions(
        vectorString(vector.response, "assertion response"),
        vectorObject(vector.assertions, "assertions") as CoreAssertions,
      );
      if (typeof vector.expected_pass !== "boolean") {
        throw new ConformanceError("invalid-vector", "expected_pass must be a boolean");
      }
      if (result.passed !== vector.expected_pass) {
        throw new ConformanceError(
          "mismatch",
          `assertion result mismatch: ${JSON.stringify(result.failures)}`,
        );
      }
    });
  }

  for (const raw of vectorArray(groups.invalid, "vectors.invalid")) {
    const vector = vectorObject(raw, "invalid vector");
    record(vector, () => verifyExpectedError(vector));
  }

  if (failures.length > 0) {
    throw new ConformanceError("suite-failed", failures.join("\n"));
  }
  return { passed, total };
}

export function verifyCorpusFile(path: string): { passed: number; total: number } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new ConformanceError("invalid-corpus", `Could not parse corpus: ${String(error)}`);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ConformanceError("invalid-corpus", "Corpus root must be an object");
  }
  return verifyCorpus(parsed as JsonObject);
}

function main(argv: string[]): number {
  if (argv.length !== 1) {
    process.stderr.write("usage: conformance-verifier <conformance/vectors.json>\n");
    return 2;
  }
  try {
    const result = verifyCorpusFile(argv[0]);
    process.stdout.write(`VoiceMD conformance: ${result.passed}/${result.total} passed\n`);
    return 0;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`VoiceMD conformance failed:\n${message}\n`);
    return 1;
  }
}

if (process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main(process.argv.slice(2));
}

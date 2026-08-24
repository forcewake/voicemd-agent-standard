type JsonPrimitive = null | boolean | number | string;
type JsonValue = JsonPrimitive | JsonValue[] | {
    [key: string]: JsonValue;
};
type JsonObject = {
    [key: string]: JsonValue;
};
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
export declare function deepMerge(base: JsonValue, override: JsonValue, path?: string[], appendUniqueArrays?: boolean): JsonValue;
export declare function selectContract(data: JsonObject, selectors?: Selectors): SelectionResult;
export declare function canonicalize(value: JsonValue): string;
export declare function canonicalContract(contract: JsonObject, bodies?: string[], selectors?: Selectors): {
    canonical: string;
    sha256: string;
};
export declare function compileCompact(contract: JsonObject, bodies?: string[], selectors?: Selectors): string;
export declare function normalizePortableRegexInput(value: string): string;
export declare function portableRegexMatches(pattern: string, text: string, flags?: JsonValue | undefined): boolean;
export declare function asciiCaseFold(value: string): string;
export declare function countPortableWords(value: string): number;
export declare function evaluateCoreAssertions(response: string, assertions: CoreAssertions): {
    passed: boolean;
    failures: string[];
};
export declare function verifyCorpus(corpus: JsonObject): {
    passed: number;
    total: number;
};
export declare function verifyCorpusFile(path: string): {
    passed: number;
    total: number;
};
export {};

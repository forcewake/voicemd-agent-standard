import { existsSync, lstatSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const candidates = ["VOICE.override.md", "VOICE.md", ".voice/VOICE.override.md", ".voice/VOICE.md"];
const rootMarkers = [".voicemd-root", ".git", ".hg", ".svn"];
const fallbackRootMarkers = ["pyproject.toml", "package.json", "go.mod", "Cargo.toml"];
const voiceTrimPattern = /^[\u0009\u000a\u000d\u0020]+|[\u0009\u000a\u000d\u0020]+$/g;
const humanOutputs = new Set([
  "chat", "message", "email", "document", "report", "summary",
  "explanation", "ui_copy", "spoken", "speech",
]);
const machineOutputs = new Set([
  "code", "patch", "diff", "json", "xml", "yaml", "sql", "tool_call",
  "tool_result", "structured_data", "exact_quote", "raw_data",
]);

function lexicalDirectory(start) {
  const value = resolve(start);
  let resolved;
  try {
    resolved = realpathSync(value);
  } catch (error) {
    throw new Error(`Discovery start cannot be resolved safely: ${value}`, { cause: error });
  }
  const metadata = statSync(resolved);
  if (metadata.isFile()) return dirname(value);
  if (!metadata.isDirectory()) {
    throw new Error(`Discovery start is not a file or directory: ${value}`);
  }
  return value;
}

function contains(root, child) {
  const rel = relative(root, child);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

function isFile(path) {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function isSymlink(path) {
  try {
    return lstatSync(path).isSymbolicLink();
  } catch {
    return false;
  }
}

function containsSecretEnvComponent(path) {
  const parsedPath = resolve(path);
  const root = parse(parsedPath).root;
  return relative(root, parsedPath)
    .split(sep)
    .filter(Boolean)
    .some((component) => {
      const folded = component.toLowerCase();
      return folded === ".env" || folded.startsWith(".env.");
    });
}

function trimVoiceWhitespace(value) {
  return value.replace(voiceTrimPattern, "");
}

function resolveDirectory(path, label) {
  let resolved;
  try {
    resolved = realpathSync(path);
  } catch (error) {
    throw new Error(`${label} cannot be resolved safely: ${path}`, { cause: error });
  }
  if (!statSync(resolved).isDirectory()) {
    throw new Error(`${label} is not a directory: ${resolved}`);
  }
  return resolved;
}

function symlinkComponents(path) {
  const parsedPath = resolve(path);
  const root = parse(parsedPath).root;
  const components = relative(root, parsedPath).split(sep).filter(Boolean);
  let cursor = root;
  const result = [];
  for (const component of components) {
    cursor = join(cursor, component);
    if (isSymlink(cursor)) result.push(cursor);
  }
  return result;
}

function markerRoot(chain) {
  for (const candidate of chain) {
    if (rootMarkers.some((name) => existsSync(join(candidate, name)))) return candidate;
  }
  for (const candidate of chain) {
    if (fallbackRootMarkers.some((name) => isFile(join(candidate, name)))) return candidate;
  }
  return undefined;
}

function ancestorChain(start) {
  const chain = [];
  let cursor = start;
  while (true) {
    chain.push(cursor);
    const parent = dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  return chain;
}

function discoveryContext(start) {
  const lexicalCurrent = lexicalDirectory(start);
  const current = resolveDirectory(lexicalCurrent, "Discovery start");
  if (process.env.VOICE_MD_ROOT) {
    const root = resolveDirectory(resolve(process.env.VOICE_MD_ROOT), "VOICE_MD_ROOT");
    if (!contains(root, current)) {
      throw new Error("VOICE_MD_ROOT must contain the discovery start directory");
    }
    return { current, root };
  }

  const lexicalChain = ancestorChain(lexicalCurrent);
  const symlinks = symlinkComponents(lexicalCurrent);
  let protectiveChain = [];
  if (symlinks.length > 0) {
    const symlinkParent = dirname(symlinks.at(-1));
    protectiveChain = lexicalChain.filter(
      (path) => path === symlinkParent || contains(path, symlinkParent),
    );
  }
  const lexicalRoot = markerRoot(protectiveChain) ?? markerRoot(lexicalChain);
  if (lexicalRoot !== undefined) {
    const root = resolveDirectory(lexicalRoot, "Project root");
    if (!contains(root, current)) {
      throw new Error(
        `Discovery start is outside canonical project root ${root}: ${current}`,
      );
    }
    return { current, root };
  }

  const canonicalRoot = markerRoot(ancestorChain(current)) ?? current;
  return { current, root: resolveDirectory(canonicalRoot, "Project root") };
}

function resolveCandidate(candidate, root) {
  if (containsSecretEnvComponent(candidate)) {
    throw new Error(`Secret environment files cannot be VOICE.md sources: ${candidate}`);
  }
  const parent = dirname(candidate);
  if (!existsSync(parent)) {
    if (isSymlink(parent)) {
      throw new Error(`VOICE.md candidate parent cannot be resolved: ${parent}`);
    }
    return undefined;
  }
  const resolvedParent = resolveDirectory(parent, "VOICE.md candidate parent");
  if (!contains(root, resolvedParent)) {
    throw new Error(
      `VOICE.md candidate parent is outside canonical project root ${root}: ${resolvedParent}`,
    );
  }

  if (!existsSync(candidate) && !isSymlink(candidate)) return undefined;
  let resolved;
  try {
    resolved = realpathSync(candidate);
  } catch (error) {
    throw new Error(`VOICE.md candidate cannot be resolved safely: ${candidate}`, { cause: error });
  }
  if (containsSecretEnvComponent(resolved)) {
    throw new Error(`Secret environment files cannot be VOICE.md sources: ${resolved}`);
  }
  if (!contains(root, resolved)) {
    throw new Error(
      `VOICE.md candidate is outside canonical project root ${root}: ${resolved}`,
    );
  }
  if (!statSync(resolved).isFile()) {
    if (isSymlink(candidate)) {
      throw new Error(`VOICE.md symlink does not resolve to a regular file: ${candidate}`);
    }
    return undefined;
  }
  return resolved;
}

export function loadVoice(start = ".") {
  const { current: cwd, root } = discoveryContext(start);
  const chain = [];
  let current = cwd;
  while (true) {
    chain.push(current);
    if (current === root) break;
    const parent = dirname(current);
    if (parent === current || !contains(root, current)) break;
    current = parent;
  }
  const files = [];
  for (const base of chain.reverse()) {
    let candidate;
    for (const name of candidates) {
      candidate = resolveCandidate(join(base, name), root);
      if (candidate !== undefined) break;
    }
    if (candidate) files.push(candidate);
  }
  if (files.length === 0) throw new Error("No VOICE.md found");
  return files.map((path) => trimVoiceWhitespace(readFileSync(path, "utf8"))).join("\n\n");
}

export function shouldApply(outputKind, { exactOutput = false, enabled = true } = {}) {
  const kind = String(outputKind).trim().toLocaleLowerCase("und");
  return enabled && !exactOutput && humanOutputs.has(kind) && !machineOutputs.has(kind);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    console.log(loadVoice(process.argv[2] ?? "."));
  } catch (error) {
    console.error(`error: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

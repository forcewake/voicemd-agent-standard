import { existsSync, lstatSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const candidates = ["VOICE.override.md", "VOICE.md", ".voice/VOICE.override.md", ".voice/VOICE.md"];
const rootMarkers = [".voicemd-root", ".git", ".hg", ".svn"];
const fallbackRootMarkers = ["pyproject.toml", "package.json", "go.mod", "Cargo.toml"];

function directory(start) {
  const value = resolve(start);
  return existsSync(value) && lstatSync(value).isFile() ? dirname(value) : value;
}

function projectRoot(start) {
  const current = directory(start);
  if (process.env.VOICE_MD_ROOT) {
    const root = resolve(process.env.VOICE_MD_ROOT);
    if (!existsSync(root) || (current !== root && !current.startsWith(`${root}/`))) {
      throw new Error("VOICE_MD_ROOT must be a directory containing the start path");
    }
    return root;
  }

  const chain = [];
  let cursor = current;
  while (true) {
    chain.push(cursor);
    const parent = dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  for (const candidate of chain) {
    if (rootMarkers.some((name) => existsSync(join(candidate, name)))) return candidate;
  }
  for (const candidate of chain) {
    if (fallbackRootMarkers.some((name) => existsSync(join(candidate, name)))) return candidate;
  }
  return current;
}

export function loadVoice(start = ".") {
  const cwd = directory(start);
  const root = projectRoot(cwd);
  const chain = [];
  let current = cwd;
  while (true) {
    chain.push(current);
    if (current === root) break;
    const parent = dirname(current);
    if (parent === current || (current !== root && !current.startsWith(`${root}/`))) break;
    current = parent;
  }
  const files = [];
  for (const base of chain.reverse()) {
    const candidate = candidates
      .map((name) => join(base, name))
      .find((path) => existsSync(path) && lstatSync(path).isFile());
    if (candidate) files.push(candidate);
  }
  if (files.length === 0) throw new Error("No VOICE.md found");
  return files.map((path) => readFileSync(path, "utf8").trim()).join("\n\n");
}

if (import.meta.url === `file://${process.argv[1]}`) console.log(loadVoice(process.argv[2] ?? "."));

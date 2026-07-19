/**
 * Autocomplete sources for the input line:
 *   - `@path` → fuzzy file completion (walks cwd for files)
 *   - `/cmd`  → slash-command completion (queries the command registry)
 *   - `!cmd`  → passthrough marker (no completion, just coloring)
 *
 * Exposed as a pure function: given the current line + cursor, return
 * suggestions. The TUI renders a popup below the input.
 */

import { readdirSync, statSync } from "node:fs";
import { join, relative, sep, basename } from "node:path";

export interface Suggestion {
  /** The full text to replace the trigger token with. */
  replacement: string;
  /** Short label for the popup. */
  label: string;
  /** Optional description / detail line. */
  detail?: string;
}

export interface CompletionContext {
  line: string;
  cursor: number;
  cwd: string;
  commands: string[];
}

/** File/dir globs to skip during @ completion (keeps the list relevant). */
const IGNORE_DIRS = new Set([
  "node_modules", ".git", ".svn", ".hg", "dist", "build", "out", ".next",
  "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
  ".cache", ".turbo", "coverage", ".nyc_output",
]);

const IGNORE_SUFFIXES = [".pyc", ".pyo", ".o", ".a", ".so", ".dylib", ".class"];

/**
 * Compute suggestions for the token at the cursor. Returns [] if no trigger
 * (@ or /) is active.
 */
export function completionsFor(ctx: CompletionContext): Suggestion[] {
  const { line, cursor, commands } = ctx;
  // Find the token start: walk back to whitespace.
  let start = cursor;
  while (start > 0 && !/\s/.test(line[start - 1]!)) start -= 1;
  const token = line.slice(start, cursor);

  // /cmd completion — only if the token is the first thing on the line.
  if (token.startsWith("/") && start === 0) {
    const prefix = token.slice(1).toLowerCase();
    return commands
      .filter((c) => c.toLowerCase().startsWith(prefix))
      .map((c) => ({
        // No trailing space: it emptied the token and broke Tab-cycling.
        replacement: `/${c}`,
        label: `/${c}`,
        detail: commandDescription(c),
      }))
      .slice(0, 12);
  }

  // @path completion — find the @ trigger in the current token.
  const atIdx = token.lastIndexOf("@");
  if (atIdx >= 0) {
    const partial = token.slice(atIdx + 1);
    return fileCompletions(ctx.cwd, partial).slice(0, 15);
  }

  return [];
}

/** Walk cwd (one level, plus descent into the typed prefix) for file matches. */
export function fileCompletions(cwd: string, partial: string): Suggestion[] {
  // Split partial into dir + name prefix.
  const dirPart = partial.includes(sep) ? partial.slice(0, partial.lastIndexOf(sep) + 1) : "";
  const namePart = partial.includes(sep) ? partial.slice(partial.lastIndexOf(sep) + 1) : partial;
  const searchDir = dirPart ? join(cwd, dirPart) : cwd;

  let entries: { name: string; isDir: boolean }[];
  try {
    entries = readdirSync(searchDir, { withFileTypes: true })
      .filter((d) => !IGNORE_DIRS.has(d.name) && !IGNORE_SUFFIXES.some((s) => d.name.endsWith(s)))
      .map((d) => ({ name: d.name, isDir: d.isDirectory() }));
  } catch {
    return [];
  }

  return entries
    .filter((e) => e.name.toLowerCase().includes(namePart.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((e) => {
      const rel = dirPart + e.name + (e.isDir ? sep : "");
      return {
        replacement: `@${rel}`,
        label: e.name + (e.isDir ? "/" : ""),
        detail: e.isDir ? "dir" : undefined,
      };
    });
}

const DESCRIPTIONS: Record<string, string> = {
  help: "show available commands",
  theme: "change color theme",
  model: "switch model",
  resume: "resume a saved session",
  sessions: "list saved sessions",
  rename: "rename this session",
  compact: "compress conversation context",
  steps: "show recent tool steps",
  tools: "list available tools",
  status: "show engine status",
  record: "toggle trace recording",
  export: "export session transcript",
  dump_context: "dump raw history to console",
  clear: "clear the transcript",
  new: "start a fresh session",
  quit: "exit mist",
  exit: "exit mist",
  cd: "change working directory",
  set: "adjust config setting",
  show: "show a config value",
  reasoning: "set reasoning effort",
  verbosity: "set output verbosity",
  pop: "remove last turn from history",
  prune: "trim history to N turns",
  truncate: "truncate history to token budget",
  mcp: "manage MCP servers",
  lens: "explainability: tokens, tools, subagents (html/json)",
};

function commandDescription(cmd: string): string {
  return DESCRIPTIONS[cmd] ?? "";
}

/** Detect `!cmd` passthrough: line starts with ! → run as bare shell. */
export function isShellPassthrough(line: string): boolean {
  return line.trimStart().startsWith("!");
}

/** Extract the shell command from a `!cmd` line. */
export function shellCommand(line: string): string {
  return line.trimStart().slice(1).trim();
}

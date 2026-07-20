/**
 * AGENTS.md discovery — repository guidelines injected into the system
 * prompt, codex-style.
 *
 * Chain (broad → specific, CSS-like: deeper files override by coming later):
 *   ~/.mist/AGENTS.md            user-global preferences
 *   <git-root>/AGENTS.md         repo-wide rules
 *   …intermediate dirs…          package/area rules
 *   <cwd>/AGENTS.md              most specific
 *
 * Per level, MIST.md wins over AGENTS.md when both exist. The walk stops at
 * the repo root (`.git` marker); without one, only cwd is consulted. Total
 * budget 32 KiB — this text is re-sent every request forever, so every byte
 * has a permanent recurring cost.
 *
 * CACHE CONTRACT: callers must load ONCE per session and freeze the result
 * into the stable prefix. Mid-session edits are handled by appending a
 * supersede message at the tail (see MistEngine) — never by re-rendering
 * the prefix, which would bust every cached byte after it.
 */

import { stat } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

export interface ProjectDocs {
  /** Concatenated docs, separator-framed, "" when none exist. */
  text: string;
  /** Absolute paths of the files included, in injection order. */
  files: string[];
}

const TOTAL_CAP = 32 * 1024;
const NAMES = ["MIST.md", "AGENTS.md"]; // first existing name wins per level

// Bun.file().exists() is false for directories — .git is usually a dir
// (and a FILE in worktrees), so stat covers both marker shapes.
const exists = (p: string): Promise<boolean> =>
  stat(p).then(
    () => true,
    () => false,
  );

async function docAt(dir: string): Promise<string | null> {
  for (const name of NAMES) {
    const p = join(dir, name);
    if (await exists(p)) return p;
  }
  return null;
}

export async function discoverProjectDocs(
  cwd: string,
  globalPath = join(homedir(), ".mist", "AGENTS.md"),
): Promise<ProjectDocs> {
  // Walk cwd → git root; levels are collected specific-first then reversed.
  const levels: string[] = [];
  let dir = resolve(cwd);
  for (;;) {
    levels.push(dir);
    if (await exists(join(dir, ".git"))) break;
    const parent = dirname(dir);
    if (parent === dir) {
      // No repo root anywhere above — only cwd is trustworthy.
      levels.length = 1;
      break;
    }
    dir = parent;
  }
  levels.reverse(); // root first

  const files: string[] = [];
  if (await exists(globalPath)) files.push(globalPath);
  for (const level of levels) {
    const p = await docAt(level);
    if (p) files.push(p);
  }
  if (files.length === 0) return { text: "", files: [] };

  let text = "";
  const included: string[] = [];
  for (const p of files) {
    let body = (await Bun.file(p).text()).trim();
    if (!body) continue;
    const remaining = TOTAL_CAP - text.length;
    if (remaining <= 0) break;
    if (body.length > remaining) body = `${body.slice(0, remaining)}\n…(truncated at 32 KiB budget)`;
    text += `${text ? "\n\n" : ""}--- ${p} ---\n${body}`;
    included.push(p);
  }
  return { text, files: included };
}

/**
 * The /init command is prompt-sugar: this canned user message is submitted
 * through the normal agent loop, so the model explores the actual repo and
 * writes the file with its ordinary tools (subject to hooks like any write).
 */
export const INIT_PROMPT = `Create an AGENTS.md file at the root of this repository titled "Repository Guidelines".

FIRST check whether AGENTS.md (or MIST.md) already exists at the repo root. If it does, do NOT overwrite or modify it — review it against the codebase and report what is missing or stale instead.

The file is injected into every future agent session, so every word has a permanent recurring token cost: keep it 200–400 words, terse and factual. Explore the repository first, then cover:
- Project structure & module organization (the real directories, not boilerplate)
- Build, test, and dev commands (the exact commands that work here)
- Coding style & naming conventions actually used
- Testing conventions (framework, how to run one test, where tests live)
- Commit & PR guidelines — infer the style from the actual git history

Write in imperative instructions ("Run bun test before committing"), not descriptions. No marketing prose, no generic advice a model already knows.`;

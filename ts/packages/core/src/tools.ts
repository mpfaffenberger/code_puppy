/**
 * The Mist tool belt, ported (Phase 3 subset): file ops with exact-match
 * edit semantics, ranged reads, grep, listing, and a guarded shell runner.
 * Each tool returns a string result for the model plus a short human label
 * the UI renders as a ✓ step row.
 */

import { readdir } from "node:fs/promises";
import { join, resolve } from "node:path";

export interface ToolContext {
  cwd: string;
  onStep: (label: string) => void;
}

export interface ToolResult {
  content: string;
  isError?: boolean;
}

type Handler = (input: Record<string, unknown>, ctx: ToolContext) => Promise<ToolResult>;

export interface ToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  handler: Handler;
}

const s = (v: unknown): string => (typeof v === "string" ? v : "");
const n = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);

// Destructive-command guard, ported from the Python shell safety heuristics.
const FORBIDDEN = [
  /\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)[a-z]*\s+\/(?:\s|$)/i, // rm -rf /
  /\bgit\s+push\s+.*--force(?!-with-lease)/i,
  /\bgit\s+reset\s+--hard\b/i,
  /\bmkfs\b|\bdd\s+if=/i,
];

export const TOOLS: ToolDef[] = [
  {
    name: "read_file",
    description:
      "Read a file. Prefer targeted reads: pass start_line/num_lines for just the relevant span of large files.",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
        start_line: { type: "number" },
        num_lines: { type: "number" },
      },
      required: ["path"],
    },
    handler: async (input, ctx) => {
      const path = resolve(ctx.cwd, s(input["path"]));
      const text = await Bun.file(path).text();
      const start = n(input["start_line"]);
      const count = n(input["num_lines"]);
      ctx.onStep(`read ${s(input["path"])}${start ? `:${start}` : ""}`);
      if (!start) {
        return text.length > 200_000
          ? { content: `${text.slice(0, 200_000)}\n…(truncated; use start_line/num_lines)` }
          : { content: text };
      }
      const lines = text.split("\n");
      const slice = lines.slice(start - 1, count ? start - 1 + count : undefined);
      return {
        content: slice.map((l, i) => `${start + i}: ${l}`).join("\n"),
      };
    },
  },
  {
    name: "create_file",
    description: "Create or overwrite a file with the given content.",
    input_schema: {
      type: "object",
      properties: { path: { type: "string" }, content: { type: "string" } },
      required: ["path", "content"],
    },
    handler: async (input, ctx) => {
      const path = resolve(ctx.cwd, s(input["path"]));
      await Bun.write(path, s(input["content"]));
      ctx.onStep(`created ${s(input["path"])}`);
      return { content: `wrote ${s(input["content"]).length} chars to ${path}` };
    },
  },
  {
    name: "replace_in_file",
    description:
      "Edit a file by exact, unique string match. old_str must appear exactly once (including whitespace); the edit fails otherwise.",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
        old_str: { type: "string" },
        new_str: { type: "string" },
      },
      required: ["path", "old_str", "new_str"],
    },
    handler: async (input, ctx) => {
      const path = resolve(ctx.cwd, s(input["path"]));
      const text = await Bun.file(path).text();
      const old = s(input["old_str"]);
      const occurrences = text.split(old).length - 1;
      if (occurrences === 0) return { content: "old_str not found — read the file and retry with an exact snippet", isError: true };
      if (occurrences > 1) return { content: `old_str matches ${occurrences} times — make it unique`, isError: true };
      await Bun.write(path, text.replace(old, s(input["new_str"])));
      ctx.onStep(`edited ${s(input["path"])}`);
      return { content: "edit applied" };
    },
  },
  {
    name: "list_files",
    description: "List files in a directory (non-recursive; names + dirs marked with /).",
    input_schema: {
      type: "object",
      properties: { directory: { type: "string" } },
    },
    handler: async (input, ctx) => {
      const dir = resolve(ctx.cwd, s(input["directory"]) || ".");
      const entries = await readdir(dir, { withFileTypes: true });
      ctx.onStep(`listed ${s(input["directory"]) || "."}`);
      return {
        content: entries
          .filter((e) => !e.name.startsWith(".") || e.name === ".gitignore")
          .map((e) => (e.isDirectory() ? `${e.name}/` : e.name))
          .sort()
          .join("\n"),
      };
    },
  },
  {
    name: "grep",
    description: "Search file contents recursively for a string (literal). Returns path:line matches.",
    input_schema: {
      type: "object",
      properties: { pattern: { type: "string" }, directory: { type: "string" } },
      required: ["pattern"],
    },
    handler: async (input, ctx) => {
      const dir = resolve(ctx.cwd, s(input["directory"]) || ".");
      const proc = Bun.spawn(
        ["grep", "-rn", "--binary-files=without-match", "-m", "50", s(input["pattern"]), dir,
         "--exclude-dir=node_modules", "--exclude-dir=.git", "--exclude-dir=.venv",
         "--exclude-dir=.venv-user", "--exclude-dir=__pycache__"],
        { stdout: "pipe", stderr: "ignore" },
      );
      const out = await new Response(proc.stdout).text();
      const count = out ? out.trim().split("\n").length : 0;
      ctx.onStep(`grep '${s(input["pattern"]).slice(0, 40)}' — ${count} matches`);
      return { content: out.slice(0, 60_000) || "(no matches)" };
    },
  },
  {
    name: "shell",
    description:
      "Run a shell command (bash -c). Streaming output captured; 60s default timeout. Use for builds, tests, git status/diff/log.",
    input_schema: {
      type: "object",
      properties: { command: { type: "string" }, timeout_seconds: { type: "number" } },
      required: ["command"],
    },
    handler: async (input, ctx) => {
      const command = s(input["command"]);
      if (FORBIDDEN.some((re) => re.test(command))) {
        return { content: "blocked: destructive command (rm -rf /, force-push, hard reset, …)", isError: true };
      }
      ctx.onStep(command.length > 80 ? `$ ${command.slice(0, 79)}…` : `$ ${command}`);
      const proc = Bun.spawn(["bash", "-lc", command], {
        cwd: ctx.cwd,
        stdout: "pipe",
        stderr: "pipe",
      });
      const timeoutMs = (n(input["timeout_seconds"]) ?? 60) * 1000;
      const timer = setTimeout(() => proc.kill(), timeoutMs);
      const [out, err] = await Promise.all([
        new Response(proc.stdout).text(),
        new Response(proc.stderr).text(),
      ]);
      const code = await proc.exited;
      clearTimeout(timer);
      const body = `${out}${err ? `\n[stderr]\n${err}` : ""}`.slice(0, 40_000);
      return { content: `exit ${code}\n${body}`, isError: code !== 0 };
    },
  },
];

export const toolSpecs = TOOLS.map(({ name, description, input_schema }) => ({
  name,
  description,
  input_schema,
}));

export async function runTool(
  name: string,
  input: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  const tool = TOOLS.find((t) => t.name === name);
  if (!tool) return { content: `unknown tool: ${name}`, isError: true };
  try {
    return await tool.handler(input, ctx);
  } catch (err) {
    return { content: `tool error: ${(err as Error).message}`, isError: true };
  }
}

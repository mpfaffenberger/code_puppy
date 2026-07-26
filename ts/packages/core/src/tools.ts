/**
 * The Mist tool belt, ported (Phase 3 subset): file ops with exact-match
 * edit semantics, ranged reads, grep, listing, and a guarded shell runner.
 * Each tool returns a string result for the model plus a short human label
 * the UI renders as a ✓ step row.
 */

import { readdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import {
  getBgJob,
  killBgJob,
  killProcessTree,
  listBgJobs,
  markBgExited,
  readBgOutput,
  registerBgJob,
} from "./background";

export interface DiffLine {
  type: "add" | "del";
  line: number; // 1-based line number in the file (post-edit for adds, pre-edit for dels)
  text: string;
}

export interface DiffPayload {
  path: string;
  action: "update" | "create";
  added: number;
  removed: number;
  lines: DiffLine[]; // capped for display
  truncated: boolean;
}

const DIFF_DISPLAY_CAP = 12;

/** Compute a display diff for an exact-match replacement. Pure. */
export function computeEditDiff(
  path: string,
  fileContent: string,
  oldStr: string,
  newStr: string,
): DiffPayload {
  const before = fileContent.slice(0, fileContent.indexOf(oldStr));
  const startLine = before.split("\n").length;
  const delLines = oldStr.split("\n");
  const addLines = newStr.split("\n");
  const lines: DiffLine[] = [];
  delLines.slice(0, DIFF_DISPLAY_CAP).forEach((text, i) => {
    lines.push({ type: "del", line: startLine + i, text });
  });
  addLines.slice(0, DIFF_DISPLAY_CAP).forEach((text, i) => {
    lines.push({ type: "add", line: startLine + i, text });
  });
  return {
    path,
    action: "update",
    added: addLines.length,
    removed: delLines.length,
    lines,
    truncated: delLines.length > DIFF_DISPLAY_CAP || addLines.length > DIFF_DISPLAY_CAP,
  };
}

export interface ToolContext {
  cwd: string;
  onStep: (label: string) => void;
  onDiff?: (diff: DiffPayload) => void;
  /** Ctrl+B — detach the running command and let the turn continue. */
  bgSignal?: AbortSignal;
  /** Esc — hard-stop the running command (kills the process tree). */
  abortSignal?: AbortSignal;
}

// ---- Dynamic shell timeouts ------------------------------------------------
// A `git status` that hangs for 10 minutes is a bug; a `bun install` killed at
// 60s is a false failure. Classify the command and pick a sensible ceiling —
// the model can still override per call, clamped to the hard max.

const QUICK_CMD =
  /^\s*(git\s+(status|log|diff|show|branch|rev-parse|remote|config)|ls|pwd|echo|cat|head|tail|wc|which|whoami|date|env|stat|du|df)\b/;
const LONG_CMD =
  /\b((npm|yarn|pnpm|bun)\s+(install|ci|add|update)|pip\s+install|cargo\s+(build|test|run)|make|gradle|mvn|docker\s+(build|compose)|pytest|jest|vitest|(go|cargo)\s+test|tsc|webpack|(next|vite|nuxt)\s+build|bun\s+(test|run\s+build)|npm\s+(test|run\s+(build|test)))\b/;

export const SHELL_TIMEOUT = {
  quick: 30,
  default: 120, // Claude Code's default
  long: 600, // installs/builds/test suites
  max: 600,
} as const;

/** Seconds a command gets when the model doesn't say. Exported for tests. */
export function shellTimeoutFor(command: string, requested?: number): number {
  const max = Number(process.env.MIST_SHELL_MAX_TIMEOUT ?? SHELL_TIMEOUT.max);
  if (requested && requested > 0) return Math.min(requested, max);
  const configured = Number(process.env.MIST_SHELL_TIMEOUT ?? 0);
  if (configured > 0) return Math.min(configured, max);
  if (QUICK_CMD.test(command)) return SHELL_TIMEOUT.quick;
  if (LONG_CMD.test(command)) return Math.min(SHELL_TIMEOUT.long, max);
  return Math.min(SHELL_TIMEOUT.default, max);
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
      const content = s(input["content"]);
      await Bun.write(path, content);
      ctx.onStep(`created ${s(input["path"])}`);
      const allLines = content.split("\n");
      ctx.onDiff?.({
        path: s(input["path"]),
        action: "create",
        added: allLines.length,
        removed: 0,
        lines: allLines.slice(0, DIFF_DISPLAY_CAP).map((text, i) => ({ type: "add" as const, line: i + 1, text })),
        truncated: allLines.length > DIFF_DISPLAY_CAP,
      });
      return { content: `wrote ${content.length} chars to ${path}` };
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
      const diff = computeEditDiff(s(input["path"]), text, old, s(input["new_str"]));
      await Bun.write(path, text.replace(old, s(input["new_str"])));
      ctx.onStep(`edited ${s(input["path"])}`);
      ctx.onDiff?.(diff);
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
      "Run a shell command (bash -c). Timeout adapts to the command: ~30s for quick git/ls/cat, 120s default, up to 600s for installs/builds/test suites. Pass timeout_seconds to override (max 600). A command that outlives its timeout is killed with its whole process tree; long-running servers/watchers should be started with run_in_background: true instead.",
    input_schema: {
      type: "object",
      properties: {
        command: { type: "string" },
        timeout_seconds: { type: "number", description: "override the adaptive timeout (max 600)" },
        run_in_background: {
          type: "boolean",
          description: "start it detached and return immediately — for servers, watchers, tails",
        },
      },
      required: ["command"],
    },
    handler: async (input, ctx) => {
      const command = s(input["command"]);
      if (FORBIDDEN.some((re) => re.test(command))) {
        return { content: "blocked: destructive command (rm -rf /, force-push, hard reset, …)", isError: true };
      }
      ctx.onStep(command.length > 80 ? `$ ${command.slice(0, 79)}…` : `$ ${command}`);
      const timeoutSec = shellTimeoutFor(command, n(input["timeout_seconds"]));
      return runShell(command, ctx, timeoutSec * 1000, Boolean(input["run_in_background"]));
    },
  },
  {
    name: "bg_output",
    description:
      "Read captured output from a background job (started with run_in_background or detached with Ctrl+B). Returns its status and recent output.",
    input_schema: {
      type: "object",
      properties: { id: { type: "string" }, max_chars: { type: "number" } },
      required: ["id"],
    },
    handler: async (input) => {
      const id = s(input["id"]);
      const job = getBgJob(id);
      if (!job) {
        const known = listBgJobs().map((j) => j.id).join(", ") || "none";
        return { content: `no background job '${id}' (known: ${known})`, isError: true };
      }
      const out = await readBgOutput(id, n(input["max_chars"]) ?? 8000);
      const status =
        job.status === "running"
          ? `running (pid ${job.pid}, ${Math.round((Date.now() - job.startedAt) / 1000)}s)`
          : `${job.status}${job.exitCode !== undefined ? ` (exit ${job.exitCode})` : ""}`;
      return { content: `[${id}] ${status}\n$ ${job.command}\n${out || "(no output yet)"}` };
    },
  },
  {
    name: "bg_kill",
    description: "Stop a background job and its child processes.",
    input_schema: {
      type: "object",
      properties: { id: { type: "string" } },
      required: ["id"],
    },
    handler: async (input, ctx) => {
      const id = s(input["id"]);
      const ok = killBgJob(id);
      ctx.onStep(ok ? `⏹ killed ${id}` : `${id} was not running`);
      return { content: ok ? `killed ${id}` : `no running background job '${id}'`, isError: !ok };
    },
  },
];

/**
 * Run a shell command without ever hanging the turn.
 *
 * The trap this avoids: killing bash does NOT close its stdout pipe when a
 * grandchild inherited it, so `new Response(proc.stdout).text()` waits for an
 * EOF that never comes — the turn stalls forever with no error. So output is
 * drained incrementally (partial output survives), every wait is raced against
 * a deadline, and timeouts kill the whole process tree.
 */
async function runShell(
  command: string,
  ctx: ToolContext,
  timeoutMs: number,
  startDetached: boolean,
): Promise<ToolResult> {
  const startedAt = Date.now();
  const proc = Bun.spawn(["bash", "-lc", command], {
    cwd: ctx.cwd,
    stdout: "pipe",
    stderr: "pipe",
  });
  const buf = { out: "", err: "" };
  const drain = async (stream: ReadableStream<Uint8Array>, key: "out" | "err") => {
    const reader = stream.getReader();
    const dec = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf[key] += dec.decode(value, { stream: true });
    }
  };
  const draining = Promise.all([drain(proc.stdout, "out"), drain(proc.stderr, "err")]).catch(
    () => {},
  );
  const body = () => `${buf.out}${buf.err ? `\n[stderr]\n${buf.err}` : ""}`.slice(0, 40_000);

  /** Detach: keep it running, stream output to a log file, return now. */
  const detach = (reason: string): ToolResult => {
    const job = registerBgJob(command, proc.pid, startedAt);
    void (async () => {
      const flush = () => Bun.write(job.logPath, body()).catch(() => {});
      const timer = setInterval(() => void flush(), 1000);
      try {
        await Promise.race([draining, proc.exited]);
        markBgExited(job.id, await proc.exited);
      } finally {
        clearInterval(timer);
        await flush();
      }
    })();
    return {
      content: `[${reason} as ${job.id} — pid ${proc.pid}, still running]\n${body().slice(-2000)}\n[check it with bg_output("${job.id}"), stop it with bg_kill("${job.id}")]`,
    };
  };

  if (startDetached) return detach("started in background");

  const signals: Promise<{ kind: "bg" | "abort" }>[] = [];
  if (ctx.bgSignal) signals.push(onAbort(ctx.bgSignal, { kind: "bg" }));
  if (ctx.abortSignal) signals.push(onAbort(ctx.abortSignal, { kind: "abort" }));

  const outcome = await Promise.race([
    proc.exited.then((code) => ({ kind: "exited" as const, code })),
    Bun.sleep(timeoutMs).then(() => ({ kind: "timeout" as const })),
    ...signals,
  ]);

  if (outcome.kind === "bg") return detach("backgrounded");

  if (outcome.kind === "exited") {
    // Give the pipes a beat to flush, but never wait on them indefinitely —
    // a surviving grandchild holds them open forever.
    await Promise.race([draining, Bun.sleep(500)]);
    return { content: `exit ${outcome.code}\n${body()}`, isError: outcome.code !== 0 };
  }

  // Timeout or user abort: kill the tree, keep whatever output we captured.
  killProcessTree(proc.pid, "SIGTERM");
  await Promise.race([draining, Bun.sleep(300)]);
  killProcessTree(proc.pid, "SIGKILL");
  const secs = Math.round((Date.now() - startedAt) / 1000);
  const note =
    outcome.kind === "abort"
      ? `[interrupted by the user after ${secs}s — process tree killed]`
      : `[timed out after ${secs}s — process tree killed. Re-run with a larger timeout_seconds, or run_in_background: true if it is meant to keep running.]`;
  return { content: `${note}\n${body()}`, isError: true };
}

function onAbort<T>(signal: AbortSignal, value: T): Promise<T> {
  if (signal.aborted) return Promise.resolve(value);
  return new Promise((resolve) =>
    signal.addEventListener("abort", () => resolve(value), { once: true }),
  );
}

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
  // Outer watchdog: shell polices itself precisely, but ANY tool (an MCP
  // server on a dead socket, a huge readdir) must be unable to stall a turn
  // forever. Generous by design — this is a backstop, not a work budget.
  const watchdogMs =
    name === "shell"
      ? (shellTimeoutFor(s(input["command"]), n(input["timeout_seconds"])) + 30) * 1000
      : Number(process.env.MIST_TOOL_TIMEOUT ?? 300) * 1000;
  try {
    const result = await Promise.race([
      tool.handler(input, ctx),
      Bun.sleep(watchdogMs).then(
        (): ToolResult => ({
          content: `[tool '${name}' exceeded the ${Math.round(watchdogMs / 1000)}s watchdog and was abandoned — it may still be running. Try a narrower call.]`,
          isError: true,
        }),
      ),
    ]);
    return result;
  } catch (err) {
    return { content: `tool error: ${(err as Error).message}`, isError: true };
  }
}

/**
 * Training-data exporter — turn stored Mist sessions into SFT-ready JSONL
 * trajectories for training open models.
 *
 * Each session becomes one JSONL line carrying the system prompt, the tool
 * specs the model saw, and the full multi-turn message history (tool calls +
 * results included). Two shapes:
 *
 *   - `anthropic` — the native content-block shape (tool_use / tool_result)
 *   - `openai`    — the function-calling shape (assistant.tool_calls +
 *                   role:"tool" messages) that most open-model SFT stacks
 *                   (LLaMA-Factory, Axolotl, torchtune) consume directly
 *
 * Hygiene: a redaction pass scrubs common secret shapes (API keys, bearer
 * tokens, GitHub PATs, AWS keys) — NEVER ship trajectories with live
 * credentials into a training corpus. The pass is pattern-based; review a
 * sample before large-scale use.
 */

import { SessionStore } from "./store";
import { SYSTEM_PROMPT, ENGINE_TOOLS } from "./agent";
import { toolSpecs } from "./tools";
import { toOpenAIMessages } from "./openai";
import type { ChatMessage } from "./models";

export interface TrainingExportOptions {
  format: "anthropic" | "openai";
  /** Skip sessions with fewer genuine user turns than this (default 1). */
  minTurns: number;
  redact: boolean;
}

const SECRET_PATTERNS: [RegExp, string][] = [
  [/sk-ant-[A-Za-z0-9_-]{8,}/g, "[REDACTED_ANTHROPIC_KEY]"],
  [/sk-[A-Za-z0-9]{20,}/g, "[REDACTED_API_KEY]"],
  [/gh[pousr]_[A-Za-z0-9]{20,}/g, "[REDACTED_GITHUB_TOKEN]"],
  [/xox[baprs]-[A-Za-z0-9-]{10,}/g, "[REDACTED_SLACK_TOKEN]"],
  [/AKIA[A-Z0-9]{16}/g, "[REDACTED_AWS_KEY]"],
  [/Bearer\s+[A-Za-z0-9._~+/-]{16,}=*/g, "Bearer [REDACTED]"],
  [/("(?:api_key|apiKey|token|secret|password|authorization)"\s*:\s*")[^"]{6,}(")/gi, "$1[REDACTED]$2"],
];

export function redactSecrets(text: string): string {
  let out = text;
  for (const [re, sub] of SECRET_PATTERNS) out = out.replace(re, sub);
  return out;
}

function redactMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((m) => {
    if (typeof m.content === "string") return { ...m, content: redactSecrets(m.content) };
    return {
      ...m,
      content: m.content.map((b) => {
        if (b.type === "text") return { ...b, text: redactSecrets(b.text) };
        if (b.type === "tool_result") return { ...b, content: redactSecrets(b.content) };
        if (b.type === "tool_use") {
          return { ...b, input: JSON.parse(redactSecrets(JSON.stringify(b.input ?? {}))) };
        }
        return b;
      }),
    };
  });
}

/** Count genuine user prompts (string content, not engine plumbing). */
function realTurns(messages: ChatMessage[]): number {
  return messages.filter(
    (m) =>
      m.role === "user" &&
      typeof m.content === "string" &&
      !m.content.startsWith("[auto-continue]") &&
      !m.content.startsWith("[conversation summary"),
  ).length;
}

export interface TrainingExportResult {
  written: number;
  skipped: number;
  outPath: string;
}

/**
 * Export every stored session for `cwd` as JSONL trajectories. One line per
 * session; newest sessions last.
 */
export async function exportTraining(
  cwd: string,
  outPath: string,
  opts: Partial<TrainingExportOptions> = {},
): Promise<TrainingExportResult> {
  const format = opts.format ?? "anthropic";
  const minTurns = opts.minTurns ?? 1;
  const redact = opts.redact ?? true;

  const store = new SessionStore(cwd);
  const metas = (await store.list()).reverse(); // oldest first
  const lines: string[] = [];
  let skipped = 0;

  const tools = [...ENGINE_TOOLS, ...toolSpecs].map((t) => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema,
  }));

  for (const meta of metas) {
    const stored = await store.load(meta.id);
    if (!stored || realTurns(stored.messages) < minTurns) {
      skipped += 1;
      continue;
    }
    const messages = redact ? redactMessages(stored.messages) : stored.messages;
    const base = {
      session_id: meta.id,
      title: redact ? redactSecrets(meta.title) : meta.title,
      created_at: meta.created_at,
      source: "mist",
      format,
    };
    if (format === "openai") {
      lines.push(
        JSON.stringify({
          ...base,
          // OpenAI function-calling shape: system message + tool_calls/tool
          // roles — consumable by most open-model SFT frameworks as-is.
          tools: tools.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.input_schema } })),
          messages: toOpenAIMessages(SYSTEM_PROMPT, messages),
        }),
      );
    } else {
      lines.push(JSON.stringify({ ...base, system: SYSTEM_PROMPT, tools, messages }));
    }
  }

  await Bun.write(outPath, lines.join("\n") + (lines.length ? "\n" : ""));
  return { written: lines.length, skipped, outPath };
}

/**
 * One-shot headless runner — `mist -p "prompt" --output json`.
 *
 * Builds an EngineSession in-process, submits the prompt, and emits one JSON
 * line per EventEnvelope to stdout (the same contract the SSE stream serves).
 * Exits 0 on clean turn, non-zero on error. Used by CI/programmatic callers.
 *
 * With `--output text` (or omitted), prints only the final assistant text.
 */

import { EngineSession } from "./session";

export interface HeadlessRunOptions {
  cwd?: string;
  output?: "json" | "text";
}

export interface HeadlessResult {
  exitCode: number;
  finalText: string;
  events: number;
}

export async function runHeadless(
  prompt: string,
  opts: HeadlessRunOptions = {},
): Promise<HeadlessResult> {
  const cwd = opts.cwd ?? process.cwd();
  const format = opts.output ?? "text";
  const session = new EngineSession(cwd);

  let finalText = "";
  let eventCount = 0;

  const unsubscribe = session.subscribe((env) => {
    eventCount += 1;
    if (format === "json") {
      // One JSON line per envelope (JSONL).
      process.stdout.write(`${JSON.stringify(stripDates(env))}\n`);
    }
    // Capture the final assistant text in both modes.
    if (env.type === "AgentResponseMessage") {
      const content = (env.data as { content?: string }).content;
      if (content) finalText += content;
    }
  });

  try {
    await session.submit(prompt);
    unsubscribe();
    if (format === "text" && finalText.trim()) {
      process.stdout.write(`${finalText}\n`);
    }
    return { exitCode: 0, finalText, events: eventCount };
  } catch (e) {
    unsubscribe();
    if (format === "json") {
      process.stdout.write(
        `${JSON.stringify({ type: "session.error", error: (e as Error).message })}\n`,
      );
    } else {
      process.stderr.write(`error: ${(e as Error).message}\n`);
    }
    return { exitCode: 1, finalText, events: eventCount };
  }
}

/** Date objects aren't JSON-stable across processes; emit ISO strings. */
function stripDates(env: unknown): unknown {
  const raw = JSON.parse(JSON.stringify(env)) as Record<string, unknown>;
  return raw;
}

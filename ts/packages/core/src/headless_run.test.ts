/**
 * Headless one-shot runner tests: `mist -p "prompt" --output json`.
 *
 * Self-sufficient: each test writes its own registry and sets MIST_MODEL /
 * MIST_MODELS_JSON itself (stash + restore). Never rely on env leaked from
 * sibling test files — file execution order differs between local and CI.
 */

import { describe, expect, test } from "bun:test";
import { runHeadless } from "./headless_run";
process.env.MOCK_FAST = "1"; // unpaced mock — don't rely on sibling files setting it
import { startMockModel } from "./testing/mock_model";

/** Point the engine at a fresh mock on a dedicated port for the duration of fn. */
async function withMockEngine(port: number, fn: () => Promise<void>): Promise<void> {
  const mock = startMockModel(port);
  const prevModel = process.env.MIST_MODEL;
  const prevRegistry = process.env.MIST_MODELS_JSON;
  const dir = `/tmp/mist-headless-${port}`;
  await Bun.$`mkdir -p ${dir}`;
  const registry = `${dir}/models.json`;
  await Bun.write(
    registry,
    JSON.stringify({
      "mock-headless": {
        type: "custom_anthropic",
        name: "mock",
        custom_endpoint: { url: mock.url, api_key: "x" },
      },
    }),
  );
  process.env.MIST_MODEL = "mock-headless";
  process.env.MIST_MODELS_JSON = registry;
  try {
    await fn();
  } finally {
    if (prevModel !== undefined) process.env.MIST_MODEL = prevModel;
    else delete process.env.MIST_MODEL;
    if (prevRegistry !== undefined) process.env.MIST_MODELS_JSON = prevRegistry;
    else delete process.env.MIST_MODELS_JSON;
    mock.stop();
  }
}

describe("runHeadless", () => {
  test("text mode: prints final assistant text to stdout", async () => {
    await withMockEngine(9931, async () => {
      const original = process.stdout.write.bind(process.stdout);
      let captured = "";
      process.stdout.write = (chunk: string | Uint8Array) => {
        captured += typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
        return true;
      };
      try {
        const res = await runHeadless("say hello", { output: "text" });
        expect(res.exitCode).toBe(0);
        expect(captured.length).toBeGreaterThan(0);
      } finally {
        process.stdout.write = original;
      }
    });
  });

  test("json mode: emits one JSON envelope line per event", async () => {
    await withMockEngine(9932, async () => {
      const original = process.stdout.write.bind(process.stdout);
      const lines: string[] = [];
      process.stdout.write = (chunk: string | Uint8Array) => {
        const s = typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
        for (const line of s.split("\n")) if (line.trim()) lines.push(line);
        return true;
      };
      try {
        const res = await runHeadless("say hello", { output: "json" });
        expect(res.exitCode).toBe(0);
        expect(lines.length).toBeGreaterThan(0);
        // Every line must be valid JSON with a "type" field.
        for (const line of lines) {
          const obj = JSON.parse(line) as { type: string; session_id?: string };
          expect(obj.type).toBeTruthy();
        }
        const types = lines.map((l) => (JSON.parse(l) as { type: string }).type);
        expect(types).toContain("session.running");
        expect(types).toContain("session.idle");
      } finally {
        process.stdout.write = original;
      }
    });
  });
});

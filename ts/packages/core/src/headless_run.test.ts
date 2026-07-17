/**
 * Headless one-shot runner tests: `mist -p "prompt" --output json`.
 */

import { describe, expect, test } from "bun:test";
import { runHeadless } from "./headless_run";
import { startMockModel } from "./testing/mock_model";

describe("runHeadless", () => {
  test("text mode: prints final assistant text to stdout", async () => {
    process.env.ANTHROPIC_BASE_URL = "http://127.0.0.1:9871";
    process.env.ANTHROPIC_API_KEY = "test-key";
    const mock = startMockModel(9871);
    // Capture stdout.
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
      mock.stop();
    }
  });

  test("json mode: emits one JSON envelope line per event", async () => {
    process.env.ANTHROPIC_BASE_URL = "http://127.0.0.1:9899";
    process.env.ANTHROPIC_API_KEY = "test-key";
    const mock = startMockModel(9899);
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
      mock.stop();
    }
  });
});

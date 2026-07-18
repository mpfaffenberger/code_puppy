/**
 * Focused tests for the GeminiClient against the mock Gemini server.
 */

import { describe, expect, test } from "bun:test";
import { GeminiClient } from "./gemini";
import type { ChatMessage, ToolSpec } from "./models";
import { startMockGemini } from "./testing/mock_gemini";

const TOOLS: ToolSpec[] = [
  {
    name: "shell",
    description: "Run a shell command.",
    input_schema: {
      type: "object",
      properties: { command: { type: "string" } },
      required: ["command"],
    },
  },
];

describe("GeminiClient", () => {
  test("parses a complete functionCall and maps stop_reason/usage", async () => {
    const mock = startMockGemini(9895);
    const client = new GeminiClient(mock.url, "test-key", "gemini-2.0-flash", "gemini");

    const deltas: string[] = [];
    const toolStarts: string[] = [];
    const result = await client.stream(
      "you are helpful",
      [{ role: "user", content: "run seq 1 4" }],
      TOOLS,
      {
        onTextDelta: (t) => deltas.push(t),
        onToolUse: (n) => toolStarts.push(n),
      },
    );

    expect(result.toolUses).toHaveLength(1);
    expect(result.toolUses[0]!.name).toBe("shell");
    expect(result.toolUses[0]!.input).toEqual({ command: "seq 1 4" });
    // functionCall present → stop_reason forced to "tool_use" (reference parity).
    expect(result.stopReason).toBe("tool_use");
    expect(result.inputTokens).toBe(11);
    expect(result.outputTokens).toBe(7);
    expect(deltas.join("")).toContain("Running it.");
    expect(toolStarts).toEqual(["shell"]);
    mock.stop();
  });

  test("round-trips tool_use + tool_result history and streams the final answer", async () => {
    const mock = startMockGemini(9896);
    const client = new GeminiClient(mock.url, "test-key", "gemini-2.0-flash", "gemini");

    const history: ChatMessage[] = [
      { role: "user", content: "run seq 1 4" },
      {
        role: "assistant",
        content: [
          { type: "text", text: "Running it." },
          { type: "tool_use", id: "call_shell", name: "shell", input: { command: "seq 1 4" } },
        ],
      },
      {
        role: "user",
        content: [{ type: "tool_result", tool_use_id: "call_shell", content: "1\n2\n3\n4" }],
      },
    ];

    const deltas: string[] = [];
    const result = await client.stream("you are helpful", history, TOOLS, {
      onTextDelta: (t) => deltas.push(t),
    });

    // Mock only streams the final answer when it sees a functionResponse part
    // in the translated history — proves the round-trip worked.
    expect(result.toolUses).toHaveLength(0);
    expect(result.stopReason).toBe("stop");
    expect(deltas.join("")).toContain("**four numbers**");
    // promptTokenCount 50 with 35 cached → uncached remainder + cached
    // subset (sum = 50).
    expect(result.inputTokens).toBe(15);
    expect(result.cacheReadTokens).toBe(35);
    mock.stop();
  });

  test("sends x-goog-api-key and a strict-schema tool payload", async () => {
    let capturedHeaders: Record<string, string> = {};
    let capturedBody: any = null;
    const intercept = Bun.serve({
      port: 9897,
      async fetch(req) {
        capturedHeaders = Object.fromEntries(req.headers.entries());
        capturedBody = await req.json();
        return sseMinimal();
      },
    });
    const client = new GeminiClient(
      `http://127.0.0.1:${intercept.port}`,
      "my-key",
      "gemini-2.0-flash",
      "gemini",
    );
    await client.stream("sys", [{ role: "user", content: "hi" }], TOOLS, {});
    intercept.stop(true);

    expect(capturedHeaders["x-goog-api-key"]).toBe("my-key");
    expect(capturedHeaders["authorization"]).toBeUndefined();
    expect(capturedBody.contents[0].role).toBe("user");
    expect(capturedBody.systemInstruction.parts[0].text).toBe("sys");
    // Strict proto parser: declarations carry ONLY name/description/parameters
    // (a spread-in input_schema or extra toolConfig field is a 400).
    const decl = capturedBody.tools[0].functionDeclarations[0];
    expect(decl.name).toBe("shell");
    expect(decl.input_schema).toBeUndefined();
    expect(decl.parameters).toBeDefined();
    expect(capturedBody.toolConfig.functionCallingConfig.mode).toBe("AUTO");
    expect(capturedBody.toolConfig.functionCallingConfig.streamFunctionCallArguments).toBeUndefined();
  });
});

function sseMinimal(): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          `data: ${JSON.stringify({
            candidates: [{ content: { parts: [{ text: "ok" }] }, finishReason: "STOP" }],
          })}\n\n`,
        ),
      );
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

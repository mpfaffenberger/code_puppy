/**
 * Focused tests for the OpenAIClient against the mock OpenAI server.
 * Verifies the three riskiest behaviors:
 *   1. streamed tool-call arguments split across deltas are accumulated + parsed
 *   2. stop_reason "tool_calls" maps to "tool_use" (what the agent loop checks)
 *   3. usage tokens are read from the trailing usage chunk
 *   4. history translation: an assistant tool_use + a tool_result round-trip
 *      correctly into OpenAI's assistant.tool_calls / role:"tool" messages
 *   5. tools are translated into the function-calling schema
 *   6. text deltas are forwarded live via onTextDelta
 */

import { describe, expect, test } from "bun:test";
import { OpenAIClient } from "./openai";
import type { ChatMessage, ToolSpec } from "./models";
import { startMockOpenAI } from "./testing/mock_openai";

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

describe("OpenAIClient", () => {
  test("streams + accumulates a split tool call and maps stop_reason/usage", async () => {
    const mock = startMockOpenAI(9891);
    const client = new OpenAIClient(mock.url, "test-key", "gpt-4o", "openai");

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

    // Tool-call argument accumulation: split '{"command":' + '"seq 1 4"}' → parsed object.
    expect(result.toolUses).toHaveLength(1);
    expect(result.toolUses[0]!.name).toBe("shell");
    expect(result.toolUses[0]!.id).toBe("call_shell");
    expect(result.toolUses[0]!.input).toEqual({ command: "seq 1 4" });

    // stop_reason mapped from "tool_calls" → "tool_use" (the agent loop's check).
    expect(result.stopReason).toBe("tool_use");

    // Usage read from the trailing chunk.
    expect(result.inputTokens).toBe(21);
    expect(result.outputTokens).toBe(9);

    // Narration text streamed live + tool start announced as soon as named.
    expect(deltas.join("")).toContain("Running the numbers.");
    expect(toolStarts).toEqual(["shell"]);

    mock.stop();
  });

  test("round-trips assistant tool_use + tool_result history and streams a final answer", async () => {
    const mock = startMockOpenAI(9892);
    const client = new OpenAIClient(mock.url, "test-key", "gpt-4o", "openai");

    // The exact Anthropic-shaped history the agent loop produces after a tool call.
    const history: ChatMessage[] = [
      { role: "user", content: "run seq 1 4" },
      {
        role: "assistant",
        content: [
          { type: "text", text: "Running the numbers." },
          { type: "tool_use", id: "call_shell", name: "shell", input: { command: "seq 1 4" } },
        ],
      },
      {
        role: "user",
        content: [
          {
            type: "tool_result",
            tool_use_id: "call_shell",
            content: "1\n2\n3\n4",
          },
        ],
      },
    ];

    const deltas: string[] = [];
    const result = await client.stream("you are helpful", history, TOOLS, {
      onTextDelta: (t) => deltas.push(t),
    });

    // The mock only streams the final answer when it sees a role:"tool" message
    // in the translated history — so a clean final text + stop proves the
    // assistant.tool_use → tool_calls and user.tool_result → role:"tool"
    // translations both round-tripped correctly.
    expect(result.toolUses).toHaveLength(0);
    expect(result.stopReason).toBe("stop");
    expect(deltas.join("")).toContain("**four numbers**");
    // prompt_tokens 42 with 30 cached → inputTokens is the uncached
    // remainder, cacheReadTokens the cached subset (sum = 42).
    expect(result.inputTokens).toBe(12);
    expect(result.cacheReadTokens).toBe(30);
    expect(result.outputTokens).toBe(55);

    mock.stop();
  });

  test("sends tools in the OpenAI function-calling schema", async () => {
    let sentBody: any = null;
    const intercept = Bun.serve({
      port: 9893,
      async fetch(req) {
        sentBody = await req.json();
        return sseMinimal();
      },
    });
    const client = new OpenAIClient(
      `http://127.0.0.1:${intercept.port}`,
      "k",
      "gpt-4o",
      "openai",
    );
    await client.stream("s", [{ role: "user", content: "hi" }], TOOLS, {});
    intercept.stop(true);

    expect(sentBody.tools).toEqual([
      {
        type: "function",
        function: {
          name: "shell",
          description: "Run a shell command.",
          parameters: {
            type: "object",
            properties: { command: { type: "string" } },
            required: ["command"],
          },
        },
      },
    ]);
    expect(sentBody.model).toBe("gpt-4o");
    expect(sentBody.stream).toBe(true);
    expect(sentBody.stream_options.include_usage).toBe(true);
  });
});

function sseMinimal(): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          `data: ${JSON.stringify({ choices: [{ delta: { content: "ok" }, finish_reason: "stop" }] })}\n\n`,
        ),
      );
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

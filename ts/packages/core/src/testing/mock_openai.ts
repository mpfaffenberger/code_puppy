/**
 * Protocol-faithful mock of the OpenAI Chat Completions streaming API
 * (`/v1/chat/completions` with `stream: true`).
 *
 * The OpenAI twin of mock_model.ts — deterministic verification of the
 * OpenAIClient's history translation, streamed tool-call argument
 * accumulation, and stop-reason/usage mapping, with zero live quota.
 *
 * Behavior mirrors mock_model.ts across the OpenAI wire format:
 *   - first request (no prior tool messages): stream a tool_call to `shell`
 *     with arguments split across multiple deltas (exercises accumulation)
 *   - follow-up (after the tool result): stream a markdown answer in small
 *     text deltas, then finish with a usage chunk and [DONE]
 */

function sse(events: Record<string, unknown>[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const e of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`));
      }
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

function chunk(delta: Record<string, unknown>, finish?: string): Record<string, unknown> {
  const choice: Record<string, unknown> = { delta };
  if (finish) choice.finish_reason = finish;
  return { choices: [choice] };
}

const ANSWER = [
  "## Result\n",
  "\n",
  "The command printed **four numbers** in order.\n",
  "\n",
  "- `seq 1 4` emitted 1 through 4\n",
  "- exit code was `0`\n",
].flatMap((line) => line.match(/.{1,7}/gs) ?? []);

export function startMockOpenAI(port = 9877) {
  const server = Bun.serve({
    port,
    async fetch(req) {
      if (!req.url.endsWith("/chat/completions")) return new Response("nf", { status: 404 });
      const payload = (await req.json()) as {
        messages: { role: string; tool_call_id?: string }[];
        tools?: unknown[];
      };

      const hasToolResult = payload.messages.some((m) => m.role === "tool");

      // Step 2 (after the shell tool result): stream the markdown answer.
      if (hasToolResult) {
        return sse([
          ...ANSWER.map((t) => chunk({ role: "assistant", content: t })),
          chunk({}, "stop"),
          { choices: [], usage: { prompt_tokens: 42, completion_tokens: 55, total_tokens: 97 } },
        ]);
      }

      // Step 1: stream a tool_call whose arguments arrive in pieces.
      return sse([
        // narration first
        chunk({ role: "assistant", content: "Running the numbers." }),
        // tool call: id + name on the first delta, then split JSON args
        chunk({
          role: "assistant",
          tool_calls: [
            {
              index: 0,
              id: "call_shell",
              type: "function",
              function: { name: "shell", arguments: "" },
            },
          ],
        }),
        chunk({
          tool_calls: [{ index: 0, function: { arguments: '{"command":' } }],
        }),
        chunk({
          tool_calls: [{ index: 0, function: { arguments: '"seq 1 4"}' } }],
        }),
        chunk({}, "tool_calls"),
        { choices: [], usage: { prompt_tokens: 21, completion_tokens: 9, total_tokens: 30 } },
      ]);
    },
  });
  return {
    url: `http://127.0.0.1:${port}`,
    stop: () => server.stop(true),
  };
}

if (import.meta.main) {
  const port = Number(process.argv[2] ?? 9877);
  startMockOpenAI(port);
  console.log(`mock openai model listening on :${port}`);
}

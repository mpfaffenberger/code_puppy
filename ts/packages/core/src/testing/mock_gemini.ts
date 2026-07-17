/**
 * Protocol-faithful mock of Google's Gemini `:streamGenerateContent?alt=sse`
 * endpoint. The Gemini twin of mock_model.ts — deterministic verification of
 * the GeminiClient's history translation, function-call parsing, and
 * usageMetadata reading, with zero live quota.
 *
 * Mirrors mock_model.ts across the Gemini wire format:
 *   - first request (no prior functionResponse): emit a functionCall (complete
 *     args) to `shell`
 *   - follow-up (after the functionResponse): stream a markdown answer as
 *     text-part fragments, then finish with STOP + usageMetadata
 *
 * No `[DONE]` sentinel on the generativelanguage API — stream just ends.
 */

function sse(events: Record<string, unknown>[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const e of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

const ANSWER = [
  "## Result\n",
  "\n",
  "Printed **four numbers**.\n",
  "\n",
  "- exit code `0`\n",
].flatMap((line) => line.match(/.{1,7}/gs) ?? []);

export function startMockGemini(port = 9894) {
  const server = Bun.serve({
    port,
    async fetch(req) {
      if (!req.url.includes(":streamGenerateContent")) return new Response("nf", { status: 404 });
      const payload = (await req.json().catch(() => ({}))) as {
        contents?: { role: string; parts?: unknown[] }[];
      };
      const hasToolResult = (payload.contents ?? []).some((c) =>
        (c.parts ?? []).some(
          (p) => p && typeof p === "object" && "functionResponse" in (p as object),
        ),
      );

      if (hasToolResult) {
        return sse([
          {
            candidates: [
              {
                content: {
                  parts: ANSWER.map((t) => ({ text: t })),
                },
                finishReason: "STOP",
              },
            ],
          },
          {
            usageMetadata: { promptTokenCount: 50, candidatesTokenCount: 60, totalTokenCount: 110 },
          },
        ]);
      }

      // Step 1: emit a complete functionCall.
      return sse([
        {
          candidates: [
            {
              content: {
                parts: [{ text: "Running it." }],
              },
            },
          ],
        },
        {
          candidates: [
            {
              content: {
                parts: [
                  {
                    functionCall: {
                      name: "shell",
                      id: "call_shell",
                      args: { command: "seq 1 4" },
                    },
                  },
                ],
              },
              finishReason: "STOP",
            },
          ],
        },
        {
          usageMetadata: { promptTokenCount: 11, candidatesTokenCount: 7, totalTokenCount: 18 },
        },
      ]);
    },
  });
  return {
    url: `http://127.0.0.1:${port}`,
    stop: () => server.stop(true),
  };
}

if (import.meta.main) {
  const port = Number(process.argv[2] ?? 9894);
  startMockGemini(port);
  console.log(`mock gemini model listening on :${port}`);
}

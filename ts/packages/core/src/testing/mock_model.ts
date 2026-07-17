/**
 * Protocol-faithful mock of the Anthropic Messages streaming API.
 *
 * Purpose (plan §2/§8): deterministic engine verification and the seed of the
 * golden-transcript parity harness — the agent loop, tool dispatch, delta
 * streaming, and stop-reason handling all exercise the exact wire format
 * without a live provider (or its quota).
 *
 * Behavior: first request in a conversation returns a `tool_use` asking to run
 * `seq 1 4`; the follow-up (which carries the tool_result) streams a markdown
 * answer as many small text_deltas, then end_turn.
 */

function sse(events: Record<string, unknown>[]): Response {
  const body = events
    .map((e) => `event: ${e["type"]}\ndata: ${JSON.stringify(e)}\n\n`)
    .join("");
  return new Response(body, {
    headers: { "content-type": "text/event-stream" },
  });
}

const ANSWER = [
  "## Result\n",
  "\n",
  "The command printed **four numbers** in order (see core/src/agent.rs:42).\n",
  "\n",
  "- `seq 1 4` emitted 1 through 4\n",
  "- exit code was `0`\n",
  "\n",
  "| # | Gap | Detail |\n",
  "|---|-----|--------|\n",
  "| 1 | Sandboxing | Platform sandboxes constrain every tool exec via sandboxing/src/manager.rs policies |\n",
  "| 2 | Exec policy | Declarative allow/prompt/forbidden rules in core/src/exec_policy.rs with prefix matching |\n",
].flatMap((line) => line.match(/.{1,7}/gs) ?? []);

export function startMockModel(port = 9876) {
  const server = Bun.serve({
    port,
    async fetch(req) {
      if (!req.url.endsWith("/v1/messages")) return new Response("nf", { status: 404 });
      const payload = (await req.json()) as { messages: { role: string; content: unknown }[]; tools?: unknown[] };
      // Summarizer calls carry no tools — answer with a canned summary.
      if (!payload.tools || (Array.isArray(payload.tools) && payload.tools.length === 0)) {
        return sse([
          { type: "message_start", message: { usage: { input_tokens: 10 } } },
          { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } },
          { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "- GOAL: demo\n- NEXT ACTION: continue" } },
          { type: "content_block_stop", index: 0 },
          { type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 12 } },
          { type: "message_stop" },
        ]);
      }
      // Realistic latency so live UI (plan panel, heartbeat) is observable —
      // and demos feel like a real model. Disable with MOCK_FAST=1 (tests).
      if (process.env.MOCK_FAST !== "1") await Bun.sleep(1500);
      const toolResultCount = payload.messages.filter(
        (m) =>
          Array.isArray(m.content) &&
          (m.content as { type?: string }[]).some((b) => b.type === "tool_result"),
      ).length;
      if (toolResultCount === 0) {
        // Scripted step 1: publish a plan (exercises plan.updated → TUI panel).
        const planJson = JSON.stringify({
          items: [
            { id: "p1", title: "Inspect the demo directory", status: "done" },
            { id: "p2", title: "Run the numbers", status: "active" },
            { id: "p3", title: "Summarize the result", status: "pending" },
          ],
        });
        return sse([
          { type: "message_start", message: { usage: { input_tokens: 21 } } },
          {
            type: "content_block_start",
            index: 0,
            content_block: { type: "tool_use", id: "tu_plan", name: "update_plan", input: {} },
          },
          {
            type: "content_block_delta",
            index: 0,
            delta: { type: "input_json_delta", partial_json: planJson },
          },
          { type: "content_block_stop", index: 0 },
          { type: "message_delta", delta: { stop_reason: "tool_use" }, usage: { output_tokens: 9 } },
          { type: "message_stop" },
        ]);
      }
      if (toolResultCount === 1) {
        return sse([
          { type: "message_start", message: { usage: { input_tokens: 42 } } },
          {
            type: "content_block_start",
            index: 0,
            content_block: { type: "tool_use", id: "tu_1", name: "shell", input: {} },
          },
          {
            type: "content_block_delta",
            index: 0,
            delta: { type: "input_json_delta", partial_json: '{"command":' },
          },
          {
            type: "content_block_delta",
            index: 0,
            delta: { type: "input_json_delta", partial_json: '"seq 1 4"}' },
          },
          { type: "content_block_stop", index: 0 },
          { type: "message_delta", delta: { stop_reason: "tool_use" }, usage: { output_tokens: 17 } },
          { type: "message_stop" },
        ]);
      }
      return sse([
        { type: "message_start", message: { usage: { input_tokens: 99 } } },
        { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } },
        ...ANSWER.map((chunk) => ({
          type: "content_block_delta",
          index: 0,
          delta: { type: "text_delta", text: chunk },
        })),
        { type: "content_block_stop", index: 0 },
        { type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 55 } },
        { type: "message_stop" },
      ]);
    },
  });
  return {
    url: `http://127.0.0.1:${port}`,
    stop: () => server.stop(true),
  };
}

if (import.meta.main) {
  const port = Number(process.argv[2] ?? 9876);
  startMockModel(port);
  console.log(`mock model listening on :${port}`);
}

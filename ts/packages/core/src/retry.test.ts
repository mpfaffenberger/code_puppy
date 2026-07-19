import { afterEach, beforeEach, expect, test } from "bun:test";
import { AnthropicClient } from "./anthropic";
import { RetryingClient, isRetryableError } from "./retry";

// Fast, deterministic backoff for tests.
const saved: Record<string, string | undefined> = {};
beforeEach(() => {
  saved["MIST_RETRY_BASE_MS"] = process.env.MIST_RETRY_BASE_MS;
  saved["MIST_RETRIES"] = process.env.MIST_RETRIES;
  process.env.MIST_RETRY_BASE_MS = "5";
});
afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

const okStream = () =>
  new Response(
    [
      `data: ${JSON.stringify({ type: "message_start", message: { usage: { input_tokens: 5 } } })}`,
      `data: ${JSON.stringify({ type: "content_block_start", index: 0, content_block: { type: "text", text: "" } })}`,
      `data: ${JSON.stringify({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "recovered" } })}`,
      `data: ${JSON.stringify({ type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 2 } })}`,
      "",
    ].join("\n\n"),
    { headers: { "content-type": "text/event-stream" } },
  );

test("classifies retryable vs terminal errors", () => {
  expect(isRetryableError(new Error("model call failed: HTTP 529 overloaded"))).toBe(true);
  expect(isRetryableError(new Error("model call failed: HTTP 429 rate limited"))).toBe(true);
  expect(isRetryableError(new Error("model call failed: HTTP 503 upstream"))).toBe(true);
  expect(isRetryableError(new Error("fetch failed"))).toBe(true);
  expect(isRetryableError(new Error("stream error: Overloaded"))).toBe(true);
  expect(isRetryableError(new Error("model call failed: HTTP 400 bad request"))).toBe(false);
  expect(isRetryableError(new Error("model call failed: HTTP 401 bad key"))).toBe(false);
});

test("retries transient 529s with backoff, then succeeds", async () => {
  let calls = 0;
  const flaky = Bun.serve({
    port: 9951,
    fetch() {
      calls++;
      if (calls <= 2) return new Response("overloaded", { status: 529 });
      return okStream();
    },
  });
  try {
    const client = new RetryingClient(new AnthropicClient("http://127.0.0.1:9951", "k", "m"));
    const retriesSeen: number[] = [];
    const result = await client.stream("sys", [{ role: "user", content: "hi" }], [], {
      onRetry: (attempt) => retriesSeen.push(attempt),
    });
    expect(calls).toBe(3);
    expect(retriesSeen).toEqual([1, 2]);
    expect(result.text).toBe("recovered");
  } finally {
    flaky.stop(true);
  }
});

test("terminal errors (400) surface immediately — no retry", async () => {
  let calls = 0;
  const bad = Bun.serve({
    port: 9952,
    fetch() {
      calls++;
      return new Response("bad request", { status: 400 });
    },
  });
  try {
    const client = new RetryingClient(new AnthropicClient("http://127.0.0.1:9952", "k", "m"));
    await expect(client.stream("sys", [{ role: "user", content: "hi" }], [], {})).rejects.toThrow(
      "HTTP 400",
    );
    expect(calls).toBe(1);
  } finally {
    bad.stop(true);
  }
});

test("never retries after visible output — no duplicated text", async () => {
  let calls = 0;
  const midStream = Bun.serve({
    port: 9953,
    fetch() {
      calls++;
      // Streams a visible delta, THEN dies with a retryable stream error.
      return new Response(
        [
          `data: ${JSON.stringify({ type: "content_block_start", index: 0, content_block: { type: "text", text: "" } })}`,
          `data: ${JSON.stringify({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "partial" } })}`,
          `data: ${JSON.stringify({ type: "error", error: { message: "Overloaded" } })}`,
          "",
        ].join("\n\n"),
        { headers: { "content-type": "text/event-stream" } },
      );
    },
  });
  try {
    const client = new RetryingClient(new AnthropicClient("http://127.0.0.1:9953", "k", "m"));
    const deltas: string[] = [];
    await expect(
      client.stream("sys", [{ role: "user", content: "hi" }], [], {
        onTextDelta: (t) => deltas.push(t),
      }),
    ).rejects.toThrow("Overloaded");
    expect(calls).toBe(1); // guard held: partial text on screen → surface, don't re-send
    expect(deltas).toEqual(["partial"]);
  } finally {
    midStream.stop(true);
  }
});

test("MIST_RETRIES=0 disables retries entirely", async () => {
  let calls = 0;
  const flaky = Bun.serve({
    port: 9954,
    fetch() {
      calls++;
      return new Response("overloaded", { status: 529 });
    },
  });
  try {
    process.env.MIST_RETRIES = "0";
    const client = new RetryingClient(new AnthropicClient("http://127.0.0.1:9954", "k", "m"));
    await expect(client.stream("sys", [{ role: "user", content: "hi" }], [], {})).rejects.toThrow(
      "HTTP 529",
    );
    expect(calls).toBe(1);
  } finally {
    flaky.stop(true);
  }
});

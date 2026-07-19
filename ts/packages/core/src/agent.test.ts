import { afterAll, expect, test } from "bun:test";
import { MistEngine } from "./agent";
process.env.MOCK_FAST = "1";
// The scripted mock flow intentionally ends with plan items open — disable
// the anti-stall nudge except in the test that exercises it.
process.env.MIST_AUTO_CONTINUE = "0";
import { startMockModel } from "./testing/mock_model";

const mock = startMockModel(9871);
afterAll(() => mock.stop());

test("agent loop: tool_use → execute → stream final markdown", async () => {
  const dir = `/tmp/mist-ts-test-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  await Bun.write(`${dir}/demo.txt`, "say hello now");
  process.env.MIST_MODEL = "mock-model";
  const models = { "mock-model": { type: "custom_anthropic", name: "mock", custom_endpoint: { url: mock.url, api_key: "x" } } };
  const mpath = `${dir}/models.json`;
  await Bun.write(mpath, JSON.stringify(models));
  process.env.MIST_MODELS_JSON = mpath;

  const engine = new MistEngine(dir);
  const steps: string[] = [];
  let deltas = 0;
  const turn = await engine.runTurn("demo", {
    onTextDelta: () => { deltas++; },
    onStep: (l) => steps.push(l),
  });
  expect(steps.length).toBe(2);          // shell + edit steps
  expect(steps[0]).toContain("seq 1 4");
  expect(deltas).toBeGreaterThan(5);      // true token streaming
  expect(turn.finalText).toContain("## Result");
  expect(turn.finalText).toContain("**four numbers**");
});

test("plan tool publishes normalized items; steer is injected into history", async () => {
  const dir = `/tmp/mist-ts-test2-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  await Bun.write(`${dir}/demo.txt`, "say hello now");
  const engine = new MistEngine(dir);
  const plans: unknown[] = [];
  engine.queueSteer("prefer brevity");
  const turn = await engine.runTurn("demo", {
    onTextDelta: () => {},
    onStep: () => {},
    onPlan: (items) => plans.push(items),
  });
  expect(plans.length).toBe(1);
  expect((plans[0] as { title: string }[]).map((p) => p.title)).toContain("Run the numbers");
  expect(turn.finalText).toContain("## Result");
  // The steer landed in history as a user message before the first request.
  const hist = (engine as unknown as { history: { role: string; content: unknown }[] }).history;
  expect(JSON.stringify(hist)).toContain("prefer brevity");
});

test("subagents: parallel fan-out, isolated children, reports in history", async () => {
  process.env.MOCK_SUB = "1";
  try {
    const dir = `/tmp/mist-ts-sub-${Date.now()}`;
    await Bun.$`mkdir -p ${dir}`;
    await Bun.write(`${dir}/demo.txt`, "say hello now");
    const engine = new MistEngine(dir);
    const events: { phase: string; label: string }[] = [];
    const turn = await engine.runTurn("demo", {
      onTextDelta: () => {},
      onStep: () => {},
      onSubagent: (ev) => events.push({ phase: ev.phase, label: ev.label }),
    });
    // Two children started and finished; both reports fed the parent history.
    expect(events.filter((e) => e.phase === "started").length).toBe(2);
    expect(events.filter((e) => e.phase === "done").length).toBe(2);
    expect(events.map((e) => e.label)).toContain("area survey");
    const hist = JSON.stringify((engine as unknown as { history: unknown }).history);
    expect(hist).toContain('[subagent \\"area survey\\" report]');
    expect(hist).toContain("no anomalies");
    // The parent still reached a final answer afterwards.
    expect(turn.finalText.length).toBeGreaterThan(0);
  } finally {
    delete process.env.MOCK_SUB;
  }
});

test("engine parity: full runTurn loop against the OpenAI-protocol client", async () => {
  // Regression for the review's test-coverage gap: engine-level behavior was
  // only ever exercised on the Anthropic path; this drives the SAME loop
  // (tool dispatch, translated history, stop-reason mapping) via OpenAIClient.
  const { startMockOpenAI } = await import("./testing/mock_openai");
  const oai = startMockOpenAI(9879);
  const prevModel = process.env.MIST_MODEL;
  try {
    const dir = `/tmp/mist-ts-oai-${Date.now()}`;
    await Bun.$`mkdir -p ${dir}`;
    const models = {
      "mock-oai": { type: "custom_openai", name: "mock-oai", custom_endpoint: { url: oai.url, api_key: "x" } },
      // keep the anthropic mock resolvable — later tests reuse MIST_MODELS_JSON
      "mock-model": { type: "custom_anthropic", name: "mock", custom_endpoint: { url: mock.url, api_key: "x" } },
    };
    const mpath = `${dir}/models.json`;
    await Bun.write(mpath, JSON.stringify(models));
    process.env.MIST_MODELS_JSON = mpath;
    process.env.MIST_MODEL = "mock-oai";

    const engine = new MistEngine(dir);
    const steps: string[] = [];
    let deltas = 0;
    const turn = await engine.runTurn("demo", {
      onTextDelta: () => { deltas++; },
      onStep: (l) => steps.push(l),
    });
    expect(steps.length).toBe(1); // the shell call round-tripped
    expect(steps[0]).toContain("seq 1 4");
    expect(deltas).toBeGreaterThan(5); // streamed answer, not one blob
    expect(turn.finalText).toContain("## Result");
  } finally {
    process.env.MIST_MODEL = prevModel;
    oai.stop();
  }
});

test("context size prefers the API's real input_tokens over the estimate", async () => {
  const dir = `/tmp/mist-ts-tok-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  await Bun.write(`${dir}/demo.txt`, "say hello now");
  const engine = new MistEngine(dir);
  // Cold start: no API reading yet → falls back to the chars/2.5 estimate.
  expect(engine.estimateContextTokens()).toBeLessThan(10);
  await engine.runTurn("demo", { onTextDelta: () => {}, onStep: () => {} });
  // The mock's final request reports input_tokens: 99 + 40 cache-read +
  // 10 cache-write — the true prompt size is the SUM (input_tokens is only
  // the uncached remainder when prompt caching is active).
  expect(engine.estimateContextTokens()).toBe(149);
});

test("request cap: hitting the ceiling is loud and hands back a resume path", async () => {
  // Regression: the old cap (25) exited the loop SILENTLY — no final text, no
  // event — which is how the P0 session died mid-implementation.
  process.env.MIST_MAX_REQUESTS = "2"; // scripted flow needs 4 to finish
  try {
    const dir = `/tmp/mist-ts-cap-${Date.now()}`;
    await Bun.$`mkdir -p ${dir}`;
    await Bun.write(`${dir}/demo.txt`, "say hello now");
    const engine = new MistEngine(dir);
    const steps: string[] = [];
    const turn = await engine.runTurn("demo", {
      onTextDelta: () => {},
      onStep: (l) => steps.push(l),
    });
    expect(steps.some((l) => l.includes("request cap hit"))).toBe(true);
    expect(turn.finalText).toContain("Paused mid-task");
    expect(turn.finalText).toContain('send "continue"');
  } finally {
    delete process.env.MIST_MAX_REQUESTS;
  }
});

test("anti-stall: premature end_turn with open plan items triggers auto-continue", async () => {
  process.env.MOCK_STALL = "1";
  process.env.MIST_AUTO_CONTINUE = "2";
  try {
    const dir = `/tmp/mist-ts-stall-${Date.now()}`;
    await Bun.$`mkdir -p ${dir}`;
    const engine = new MistEngine(dir);
    const steps: string[] = [];
    const turn = await engine.runTurn("do the thing", {
      onTextDelta: () => {},
      onStep: (l) => steps.push(l),
    });
    expect(steps.some((l) => l.includes("auto-continue"))).toBe(true);
    expect(turn.finalText).toContain("Resumed and finished");
  } finally {
    delete process.env.MOCK_STALL;
    process.env.MIST_AUTO_CONTINUE = "0";
  }
});

test("lens: turn ledger records requests, tools, and totals", async () => {
  const dir = `/tmp/mist-ts-lens-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  await Bun.write(`${dir}/demo.txt`, "say hello now");
  const engine = new MistEngine(dir);
  await engine.runTurn("demo", { onTextDelta: () => {}, onStep: () => {} });

  const turns = engine.getLens();
  expect(turns).toHaveLength(1);
  const turn = turns[0]!;
  expect(turn.prompt).toBe("demo");
  // Scripted mock flow: plan → shell → edit → answer = 4 requests.
  expect(turn.requests.length).toBe(4);
  const tools = turn.requests.flatMap((r) => r.toolCalls);
  expect(tools.map((t) => t.name)).toEqual(["update_plan", "shell", "replace_in_file"]);
  const shell = tools.find((t) => t.name === "shell")!;
  expect(shell.outputChars).toBeGreaterThan(0);
  expect(shell.outputPreview).toContain("1"); // seq 1 4 output captured
  // Totals: billed input is the SUM across requests; usage came from the mock.
  const { lensTotals } = await import("./lens");
  const t = lensTotals(turn);
  expect(t.requests).toBe(4);
  expect(t.toolCalls).toBe(3);
  expect(t.billedInputTokens).toBeGreaterThan(0);
  expect(t.outputTokens).toBeGreaterThan(0);
  // Cache accounting from the final request's usage (40 read / 10 written).
  expect(t.cacheReadTokens).toBe(40);
  expect(t.cacheWriteTokens).toBe(10);
  const final = turn.requests[turn.requests.length - 1]!;
  expect(final.inputTokens).toBe(149); // 99 uncached + 40 read + 10 written
});

test("prompt-cache breakpoints are sent on the wire (and MIST_CACHE=0 disables)", async () => {
  let captured: Record<string, unknown> | null = null;
  const intercept = Bun.serve({
    port: 9941,
    async fetch(req) {
      captured = (await req.json()) as Record<string, unknown>;
      return new Response(
        `data: ${JSON.stringify({ type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 1 } })}\n\n`,
        { headers: { "content-type": "text/event-stream" } },
      );
    },
  });
  try {
    const { AnthropicClient } = await import("./anthropic");
    const client = new AnthropicClient(`http://127.0.0.1:9941`, "k", "m");
    await client.stream("sys", [{ role: "user", content: "hi" }], [], {});
    const sys = captured!["system"] as { cache_control?: unknown }[];
    expect(sys[0]!.cache_control).toEqual({ type: "ephemeral" });
    const msgs = captured!["messages"] as { content: { cache_control?: unknown }[] }[];
    expect(msgs[0]!.content[msgs[0]!.content.length - 1]!.cache_control).toEqual({ type: "ephemeral" });

    process.env.MIST_CACHE = "0";
    await client.stream("sys", [{ role: "user", content: "hi" }], [], {});
    expect(typeof captured!["system"]).toBe("string"); // plain, no breakpoints
  } finally {
    delete process.env.MIST_CACHE;
    intercept.stop(true);
  }
});

test("lens: subagent traffic is attributed to the subagent entry", async () => {
  process.env.MOCK_SUB = "1";
  try {
    const dir = `/tmp/mist-ts-lens-sub-${Date.now()}`;
    await Bun.$`mkdir -p ${dir}`;
    await Bun.write(`${dir}/demo.txt`, "say hello now");
    const engine = new MistEngine(dir);
    await engine.runTurn("demo", { onTextDelta: () => {}, onStep: () => {} });
    const turn = engine.getLens()[0]!;
    expect(turn.subagents.length).toBe(2);
    for (const s of turn.subagents) {
      expect(s.inputTokens).toBeGreaterThan(0); // child usage attributed here
      expect(s.reportChars).toBeGreaterThan(0);
      expect(s.error).toBeUndefined();
    }
  } finally {
    delete process.env.MOCK_SUB;
  }
});

test("pre-tool hook blocks a matching shell command", async () => {
  const dir = `/tmp/mist-ts-hook-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}/.mist`;
  await Bun.write(
    `${dir}/.mist/hooks.json`,
    JSON.stringify({
      intent: "This is a demo project.",
      pre_tool: [{ tool: "shell", pattern: "seq", action: "block", message: "no seq allowed" }],
    }),
  );
  const engine = new MistEngine(dir);
  const steps: string[] = [];
  await engine.runTurn("demo", { onTextDelta: () => {}, onStep: (l) => steps.push(l) });
  expect(steps.some((l) => l.includes("blocked by hook"))).toBe(true);
  const hist = JSON.stringify((engine as unknown as { history: unknown }).history);
  expect(hist).toContain("no seq allowed");
});

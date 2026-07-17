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

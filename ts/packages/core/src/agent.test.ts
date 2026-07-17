import { afterAll, expect, test } from "bun:test";
import { MistEngine } from "./agent";
process.env.MOCK_FAST = "1";
import { startMockModel } from "./testing/mock_model";

const mock = startMockModel(9871);
afterAll(() => mock.stop());

test("agent loop: tool_use → execute → stream final markdown", async () => {
  const dir = `/tmp/mist-ts-test-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
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
  expect(steps.length).toBe(1);          // one shell step
  expect(steps[0]).toContain("seq 1 4");
  expect(deltas).toBeGreaterThan(5);      // true token streaming
  expect(turn.finalText).toContain("## Result");
  expect(turn.finalText).toContain("**four numbers**");
});

test("plan tool publishes normalized items; steer is injected into history", async () => {
  const dir = `/tmp/mist-ts-test2-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
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

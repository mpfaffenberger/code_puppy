import { afterAll, expect, test } from "bun:test";
import { MistEngine } from "./agent";
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

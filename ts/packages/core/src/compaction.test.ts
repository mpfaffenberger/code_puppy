process.env.MOCK_FAST = "1";
import { afterAll, expect, test } from "bun:test";
import type { ChatMessage } from "./anthropic";
import { clearStaleToolResults, estimateTokens, splitForCompaction } from "./compaction";
import { MistEngine } from "./agent";
import { startMockModel } from "./testing/mock_model";

const mock = startMockModel(9872);
afterAll(() => mock.stop());

const BIG = "x".repeat(5000);

function toolTurn(id: string, content: string): ChatMessage[] {
  return [
    { role: "assistant", content: [{ type: "tool_use", id, name: "shell", input: {} }] },
    { role: "user", content: [{ type: "tool_result", tool_use_id: id, content }] },
  ];
}

test("clearStaleToolResults keeps recent, clears old, idempotent", () => {
  let messages: ChatMessage[] = [{ role: "user", content: "task" }];
  for (let i = 0; i < 6; i++) messages = [...messages, ...toolTurn(`t${i}`, BIG)];
  const first = clearStaleToolResults(messages, { keepRecent: 2, minChars: 2000 });
  expect(first.cleared).toBe(4);
  const again = clearStaleToolResults(first.messages, { keepRecent: 2, minChars: 2000 });
  expect(again.cleared).toBe(0); // idempotent
  // pairing intact: same number of tool_use and tool_result blocks
  const count = (msgs: ChatMessage[], type: string) =>
    msgs.flatMap((m) => (Array.isArray(m.content) ? m.content : [])).filter((b) => b.type === type).length;
  expect(count(first.messages, "tool_use")).toBe(count(first.messages, "tool_result"));
});

test("splitForCompaction only splits at real user-turn boundaries", () => {
  const messages: ChatMessage[] = [
    { role: "user", content: "first task ".repeat(2000) },
    { role: "assistant", content: [{ type: "text", text: "answer one ".repeat(2000) }] },
    ...toolTurn("a", BIG),
    { role: "user", content: "second task" },
    { role: "assistant", content: [{ type: "text", text: "answer two" }] },
  ];
  const split = splitForCompaction(messages, 8000);
  expect(split).not.toBeNull();
  // tail starts at the "second task" user boundary — pairs never severed
  expect(split!.tail[0]).toEqual({ role: "user", content: "second task" });
  expect(estimateTokens(split!.tail)).toBeLessThan(estimateTokens(messages));
});

test("engine.compact summarizes old context via the model", async () => {
  const dir = `/tmp/mist-compact-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  const models = { "mock-model": { type: "custom_anthropic", name: "mock", custom_endpoint: { url: mock.url, api_key: "x" } } };
  await Bun.write(`${dir}/models.json`, JSON.stringify(models));
  process.env.MIST_MODEL = "mock-model";
  process.env.MIST_MODELS_JSON = `${dir}/models.json`;

  const engine = new MistEngine(dir);
  engine.loadHistory([
    { role: "user", content: "old question ".repeat(3000) },
    { role: "assistant", content: [{ type: "text", text: "old answer ".repeat(3000) }] },
    { role: "user", content: "recent question" },
    { role: "assistant", content: [{ type: "text", text: "recent answer" }] },
  ]);
  const before = engine.estimateContextTokens();
  const r = await engine.compact();
  expect(r).not.toBeNull();
  expect(r!.afterTokens).toBeLessThan(before / 2);
  const hist = engine.exportHistory();
  expect(String(hist[0]!.content)).toContain("conversation summary");
  expect(String(hist[0]!.content)).toContain("GOAL: demo"); // mock's canned summary
  expect(hist[hist.length - 1]).toEqual({
    role: "assistant",
    content: [{ type: "text", text: "recent answer" }],
  });
});

process.env.MOCK_FAST = "1";
import { afterAll, expect, test } from "bun:test";
import type { ChatMessage } from "./anthropic";
import { clearStaleToolResults, dedupeSupersededReads, staleClearWorthIt, estimateTokens, splitForCompaction } from "./compaction";
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

function readTurn(id: string, input: Record<string, unknown>, content: string): ChatMessage[] {
  return [
    { role: "assistant", content: [{ type: "tool_use", id, name: "read_file", input }] },
    { role: "user", content: [{ type: "tool_result", tool_use_id: id, content }] },
  ];
}

test("dedupeSupersededReads: whole-file re-read evicts older reads of the same path", () => {
  const messages: ChatMessage[] = [
    { role: "user", content: "task" },
    ...readTurn("r1", { path: "a.ts" }, BIG),
    ...readTurn("r2", { path: "b.ts" }, BIG), // different path — untouched
    ...readTurn("r3", { path: "a.ts", start_line: 10, num_lines: 5 }, BIG), // contained in r4
    ...readTurn("r4", { path: "a.ts" }, BIG), // newest whole read — the truth
  ];
  const res = dedupeSupersededReads(messages);
  expect(res.cleared).toBe(2); // r1 + r3
  const body = (id: string) =>
    res.messages
      .flatMap((m) => (Array.isArray(m.content) ? m.content : []))
      .find((b) => b.type === "tool_result" && b.tool_use_id === id) as { content: string };
  expect(body("r1").content).toContain("superseded by a newer read of a.ts");
  expect(body("r2").content).toBe(BIG); // other path intact
  expect(body("r4").content).toBe(BIG); // newest read intact
  // Monotonic: second pass changes nothing (byte-stable for the cache).
  expect(dedupeSupersededReads(res.messages).cleared).toBe(0);
});

test("dedupeSupersededReads: different ranges don't supersede; identical inputs do; small results spared", () => {
  const messages: ChatMessage[] = [
    { role: "user", content: "task" },
    ...readTurn("r1", { path: "a.ts", start_line: 1, num_lines: 50 }, BIG),
    ...readTurn("r2", { path: "a.ts", start_line: 100, num_lines: 50 }, BIG), // different range — kept
    ...readTurn("r3", { path: "a.ts", start_line: 1, num_lines: 50 }, BIG), // identical to r1 — supersedes it
    ...readTurn("r4", { path: "c.ts" }, "tiny"),
    ...readTurn("r5", { path: "c.ts" }, BIG), // supersedes r4, but r4 is under minChars — spared
  ];
  const res = dedupeSupersededReads(messages);
  expect(res.cleared).toBe(1); // only r1
  const body = (id: string) =>
    res.messages
      .flatMap((m) => (Array.isArray(m.content) ? m.content : []))
      .find((b) => b.type === "tool_result" && b.tool_use_id === id) as { content: string };
  expect(body("r1").content).toContain("superseded");
  expect(body("r2").content).toBe(BIG);
  expect(body("r3").content).toBe(BIG);
  expect(body("r4").content).toBe("tiny");
});

test("clearStaleToolResults dry-run reports the plan without mutating", () => {
  let messages: ChatMessage[] = [{ role: "user", content: "task" }];
  for (let i = 0; i < 6; i++) messages = [...messages, ...toolTurn(`t${i}`, BIG)];
  const plan = clearStaleToolResults(messages, { keepRecent: 2, minChars: 2000, dryRun: true });
  expect(plan.cleared).toBe(4);
  expect(plan.savedChars).toBe(4 * BIG.length);
  expect(plan.tailChars).toBeGreaterThan(plan.savedChars); // tail spans cleared blocks + everything after
  expect(plan.messages).toBe(messages); // untouched
  // Applying for real matches the plan.
  const applied = clearStaleToolResults(messages, { keepRecent: 2, minChars: 2000 });
  expect(applied.cleared).toBe(4);
  expect(applied.savedChars).toBe(plan.savedChars);
});

test("staleClearWorthIt: adapts to observed cache behavior", () => {
  const plan = { savedChars: 25_000, tailChars: 250_000 }; // 10k tok savings, 100k tok tail
  // No cache on this endpoint → nothing to protect → always clear.
  expect(
    staleClearWorthIt(plan, { cacheLive: false, avgRequestsPerTurn: 30, cacheLikelyCold: false })
      .clear,
  ).toBe(true);
  // Cache live but cold (idle past TTL) → bust is free → clear.
  expect(
    staleClearWorthIt(plan, { cacheLive: true, avgRequestsPerTurn: 30, cacheLikelyCold: true })
      .clear,
  ).toBe(true);
  // Cache live + warm, short turns: 0.1×10k×2 = 2k savings < 1.25×100k bust → defer.
  const defer = staleClearWorthIt(plan, {
    cacheLive: true,
    avgRequestsPerTurn: 2,
    cacheLikelyCold: false,
  });
  expect(defer.clear).toBe(false);
  expect(defer.reason).toContain("deferred");
  // Same history but long turns: 0.1×10k×200 = 200k savings > 125k bust → clear.
  expect(
    staleClearWorthIt(plan, { cacheLive: true, avgRequestsPerTurn: 200, cacheLikelyCold: false })
      .clear,
  ).toBe(true);
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

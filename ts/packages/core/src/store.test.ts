import { expect, test } from "bun:test";
import { SessionStore } from "./store";

test("store: create → append → load → list → latest roundtrip", async () => {
  const cwd = `/tmp/mist-store-${Date.now()}`;
  process.env.MIST_SESSIONS_DIR = `${cwd}/.sessions`;
  const store = new SessionStore(cwd);
  await store.create("aaa111", "first task");
  await store.appendMessages("aaa111", [
    { role: "user", content: "first task" },
    { role: "assistant", content: [{ type: "text", text: "done" }] },
  ]);
  await store.snapshotPlan("aaa111", [{ id: "p1", title: "step", status: "done" }]);
  await Bun.sleep(15); // distinct mtime ordering
  await store.create("bbb222", "second task");

  const loaded = await store.load("aaa111");
  expect(loaded?.meta.title).toBe("first task");
  expect(loaded?.messages.length).toBe(2);
  expect(loaded?.plan[0]?.title).toBe("step");

  const list = await store.list();
  expect(list.length).toBe(2);
  expect((await store.latest())?.id).toBe("bbb222");
  delete process.env.MIST_SESSIONS_DIR;
});

test("store: lens turns roundtrip — /lens survives resume", async () => {
  const cwd = `/tmp/mist-store-lens-${Date.now()}`;
  process.env.MIST_SESSIONS_DIR = `${cwd}/.sessions`;
  const store = new SessionStore(cwd);
  await store.create("lll111", "lens task");
  const turn = {
    prompt: "do the thing",
    startedAt: new Date().toISOString(),
    ms: 1234,
    requests: [
      {
        index: 0, ms: 900, inputTokens: 149, cacheReadTokens: 40, cacheWriteTokens: 10,
        outputTokens: 55, estThinkingTokens: 0, thinkingMs: 0, stopReason: "end_turn",
        textChars: 20, toolCalls: [],
      },
    ],
    subagents: [],
    autoContinues: 0,
    capHit: false,
    compactions: [],
  };
  await store.appendLensTurn("lll111", turn);
  const loaded = await store.load("lll111");
  expect(loaded?.lensTurns.length).toBe(1);
  expect(loaded?.lensTurns[0]?.prompt).toBe("do the thing");
  expect(loaded?.lensTurns[0]?.requests[0]?.inputTokens).toBe(149);
  delete process.env.MIST_SESSIONS_DIR;
});

test("store: rename rewrites the meta title, keeps messages + plan", async () => {
  const cwd = `/tmp/mist-store-rn-${Date.now()}`;
  process.env.MIST_SESSIONS_DIR = `${cwd}/.sessions`;
  const store = new SessionStore(cwd);
  await store.create("ccc333", "what is the raw first question doing here");
  await store.appendMessages("ccc333", [{ role: "user", content: "q" }]);
  await store.snapshotPlan("ccc333", [{ id: "p1", title: "step", status: "done" }]);

  expect(await store.rename("ccc333", "auth bug hunt")).toBe(true);
  const loaded = await store.load("ccc333");
  expect(loaded?.meta.title).toBe("auth bug hunt");
  expect(loaded?.messages.length).toBe(1);
  expect(loaded?.plan.length).toBe(1);
  expect((await store.list())[0]?.title).toBe("auth bug hunt");

  expect(await store.rename("nope999", "x")).toBe(false);
  delete process.env.MIST_SESSIONS_DIR;
});

test("engine: loadHistory feeds the next request (resume continuity)", async () => {
  const { MistEngine } = await import("./agent");
  const engine = new MistEngine("/tmp");
  engine.loadHistory([
    { role: "user", content: "earlier question" },
    { role: "assistant", content: [{ type: "text", text: "earlier answer" }] },
  ]);
  expect(engine.exportHistory().length).toBe(2);
});

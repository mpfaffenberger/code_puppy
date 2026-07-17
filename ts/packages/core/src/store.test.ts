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

test("engine: loadHistory feeds the next request (resume continuity)", async () => {
  const { MistEngine } = await import("./agent");
  const engine = new MistEngine("/tmp");
  engine.loadHistory([
    { role: "user", content: "earlier question" },
    { role: "assistant", content: [{ type: "text", text: "earlier answer" }] },
  ]);
  expect(engine.exportHistory().length).toBe(2);
});

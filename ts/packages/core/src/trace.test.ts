import { expect, test } from "bun:test";
import { EngineSession } from "./session";

test("trace: start → events append → stop; replays buffered context", async () => {
  const dir = `/tmp/mist-trace-${Date.now()}`;
  await Bun.$`mkdir -p ${dir}`;
  const session = new EngineSession(dir); // emits session.created into buffer
  const path = `${dir}/trace.jsonl`;
  session.startTrace(path);
  session.steer("nudge one"); // emits steer.queued while tracing
  const r = session.stopTrace();
  expect(r).not.toBeNull();
  expect(r!.events).toBe(2); // replayed session.created + live steer.queued
  await Bun.sleep(20);
  const lines = (await Bun.file(path).text()).trim().split("\n");
  expect(lines.length).toBe(2);
  const types = lines.map((l) => JSON.parse(l).type);
  expect(types).toEqual(["session.created", "steer.queued"]);
  expect(session.tracing).toBeNull();
});

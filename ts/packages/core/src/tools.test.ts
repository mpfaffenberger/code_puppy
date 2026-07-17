import { expect, test } from "bun:test";
import { computeEditDiff } from "./tools";

test("computeEditDiff: correct counts, line numbers, del-then-add", () => {
  const file = "line one\nline two\nsay hello now\nline four";
  const d = computeEditDiff("demo.txt", file, "say hello now", "say hello world now\nand then say goodbye");
  expect(d.action).toBe("update");
  expect(d.removed).toBe(1);
  expect(d.added).toBe(2);
  expect(d.lines[0]).toEqual({ type: "del", line: 3, text: "say hello now" });
  expect(d.lines[1]!.type).toBe("add");
  expect(d.lines[1]!.line).toBe(3);
  expect(d.truncated).toBe(false);
});

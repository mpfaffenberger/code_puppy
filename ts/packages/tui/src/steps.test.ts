import { expect, test } from "bun:test";
import { labelForGroup } from "./steps";

test("uniform groups get specific labels", () => {
  expect(labelForGroup(["$ ls", "$ pwd", "$ git status"])).toBe("Ran 3 shell commands");
  expect(labelForGroup(["read a.ts", "read b.ts"])).toBe("Ran 2 file reads");
  expect(labelForGroup(["$ ls"])).toBe("Ran 1 shell command");
});

test("mixed groups fall back to tool calls", () => {
  expect(labelForGroup(["$ ls", "read a.ts", "grep 'x' — 3 matches"])).toBe("Ran 3 tool calls");
  expect(labelForGroup([])).toBe("");
});

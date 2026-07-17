import { expect, test } from "bun:test";
import { transcriptToMarkdown } from "./index";

test("transcriptToMarkdown covers every item kind", () => {
  const md = transcriptToMarkdown(
    [
      { id: 1, kind: "user", text: "build the thing" },
      { id: 2, kind: "narration", text: "Setting up first." },
      { id: 3, kind: "toolblock", label: "$ bun test", preview: ["exit 0", "22 pass"], hiddenLines: 4 },
      {
        id: 4, kind: "diff", path: "src/a.ts", action: "update", added: 1, removed: 1,
        lines: [ { type: "del", line: 3, text: "old" }, { type: "add", line: 3, text: "new" } ],
        truncated: false,
      },
      { id: 5, kind: "info", text: "Ran 2 tool calls" },
      { id: 6, kind: "response", text: "## Done\nAll green." },
    ] as never,
    "abcdef1234",
  );
  expect(md).toContain("# Mist session abcdef12");
  expect(md).toContain("## ❯ build the thing");
  expect(md).toContain("$ bun test");
  expect(md).toContain("… +4 lines");
  expect(md).toContain("```diff");
  expect(md).toContain("- old");
  expect(md).toContain("+ new");
  expect(md).toContain("**Update: src/a.ts** (+1/-1)");
  expect(md).toContain("> Ran 2 tool calls");
  expect(md).toContain("All green.");
});

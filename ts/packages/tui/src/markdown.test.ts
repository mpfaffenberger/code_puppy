import { expect, test } from "bun:test";
import { parseTable, tableIsCompact } from "./markdown";

test("parseTable: header + separator + rows", () => {
  const t = parseTable([
    "| # | Gap | What Codex has |",
    "|---|-----|----------------|",
    "| 1 | OS-level sandboxing | Platform sandboxes that constrain every tool exec |",
    "| 2 | Exec policy engine | A declarative rule DSL |",
  ]);
  expect(t).not.toBeNull();
  expect(t!.headers).toEqual(["#", "Gap", "What Codex has"]);
  expect(t!.rows.length).toBe(2);
  expect(t!.rows[0]![1]).toBe("OS-level sandboxing");
});

test("prose-heavy tables are stacked, compact ones are grids", () => {
  const prose = parseTable([
    "| # | Gap | Detail |",
    "|---|---|---|",
    "| 1 | Sandboxing | A very long prose cell describing platform sandboxes with policies and much more text |",
  ])!;
  expect(tableIsCompact(prose)).toBe(false);
  const compact = parseTable([
    "| name | status |",
    "|------|--------|",
    "| core | done |",
    "| tui | active |",
  ])!;
  expect(tableIsCompact(compact)).toBe(true);
});

test("non-tables are rejected", () => {
  expect(parseTable(["| just one line |"])).toBeNull();
  expect(parseTable(["|a|b|", "| not separator |"])).toBeNull();
});

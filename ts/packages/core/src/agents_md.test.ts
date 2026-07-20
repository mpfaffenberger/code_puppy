import { expect, test } from "bun:test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { discoverProjectDocs } from "./agents_md";

async function repo(base: string, layout: Record<string, string>): Promise<void> {
  await mkdir(join(base, ".git"), { recursive: true });
  for (const [rel, body] of Object.entries(layout)) {
    const path = join(base, rel);
    await mkdir(join(path, ".."), { recursive: true });
    await Bun.write(path, body);
  }
}

test("discovery: root-first chain, deeper files later (override by recency)", async () => {
  const base = `/tmp/mist-agents-${Date.now()}`;
  await repo(base, {
    "AGENTS.md": "ROOT RULES",
    "pkg/AGENTS.md": "PKG RULES",
    "pkg/deep/AGENTS.md": "DEEP RULES",
  });
  const docs = await discoverProjectDocs(join(base, "pkg", "deep"), "/nonexistent");
  expect(docs.files.length).toBe(3);
  const [a, b, c] = [docs.text.indexOf("ROOT RULES"), docs.text.indexOf("PKG RULES"), docs.text.indexOf("DEEP RULES")];
  expect(a).toBeGreaterThanOrEqual(0);
  expect(a).toBeLessThan(b);
  expect(b).toBeLessThan(c);
});

test("discovery: MIST.md wins over AGENTS.md per level; no repo root → cwd only", async () => {
  const base = `/tmp/mist-agents-alias-${Date.now()}`;
  await repo(base, { "AGENTS.md": "AGENTS BODY", "MIST.md": "MIST BODY" });
  const docs = await discoverProjectDocs(base, "/nonexistent");
  expect(docs.text).toContain("MIST BODY");
  expect(docs.text).not.toContain("AGENTS BODY");

  // Directory with no .git anywhere meaningful and no docs → empty.
  const bare = `/tmp/mist-agents-bare-${Date.now()}`;
  await mkdir(bare, { recursive: true });
  const none = await discoverProjectDocs(bare, "/nonexistent");
  expect(none.text).toBe("");
  expect(none.files).toEqual([]);
});

test("discovery: global doc leads the chain; 32 KiB cap truncates", async () => {
  const base = `/tmp/mist-agents-glob-${Date.now()}`;
  await repo(base, { "AGENTS.md": "x".repeat(40 * 1024) });
  const globalPath = join(base, "global-agents.md");
  await Bun.write(globalPath, "GLOBAL PREFS");
  const docs = await discoverProjectDocs(base, globalPath);
  expect(docs.text.indexOf("GLOBAL PREFS")).toBeGreaterThanOrEqual(0);
  expect(docs.text.indexOf("GLOBAL PREFS")).toBeLessThan(docs.text.indexOf("xxx"));
  expect(docs.text).toContain("truncated at 32 KiB budget");
  expect(docs.text.length).toBeLessThan(33 * 1024 + 200);
});

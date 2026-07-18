/**
 * Config surface tests: /set /show + history surgery (pop/prune/truncate).
 * Uses a temp mist.cfg so we never touch the user's real config.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  readConfig,
  getConfig,
  setConfig,
  mistCfgPath,
  SETTING_DEFS,
} from "./config";

let tmpHome: string;
let origHome: string | undefined;

beforeEach(() => {
  tmpHome = mkdtempSync(join(tmpdir(), "mist-cfg-test-"));
  origHome = process.env.HOME;
  process.env.HOME = tmpHome;
});

afterEach(() => {
  process.env.HOME = origHome;
});

describe("config layer (mist.cfg)", () => {
  test("setConfig + getConfig round-trip a key", async () => {
    await setConfig("verbosity", "verbose");
    expect(await getConfig("verbosity")).toBe("verbose");
  });

  test("setConfig preserves existing keys and creates the file", async () => {
    await setConfig("model", "claude-sonnet-4");
    await setConfig("verbosity", "quiet");
    const cfg = await readConfig();
    expect(cfg.model).toBe("claude-sonnet-4");
    expect(cfg.verbosity).toBe("quiet");
  });

  test("setConfig updates an existing key in place", async () => {
    await setConfig("temperature", "0.5");
    await setConfig("temperature", "0.9");
    const cfg = await readConfig();
    expect(cfg.temperature).toBe("0.9");
    expect(Object.keys(cfg).filter((k) => k === "temperature")).toHaveLength(1);
  });

  test("getConfig returns undefined for missing keys", async () => {
    expect(await getConfig("nonexistent")).toBeUndefined();
  });

  test("readConfig returns {} for missing file", async () => {
    const cfg = await readConfig();
    expect(cfg).toEqual({});
  });

  test("mistCfgPath points to ~/.mist/mist.cfg", () => {
    expect(mistCfgPath()).toBe(join(tmpHome, ".mist", "mist.cfg"));
  });

  test("SETTING_DEFS covers the documented keys", () => {
    const keys = SETTING_DEFS.map((s) => s.key);
    expect(keys).toContain("verbosity");
    expect(keys).toContain("reasoning");
    expect(keys).toContain("temperature");
    expect(keys).toContain("max_tokens");
    expect(keys).toContain("auto_compact_at");
  });

  test("SETTING_DEFS validators reject invalid values", () => {
    const verbosity = SETTING_DEFS.find((s) => s.key === "verbosity")!;
    expect(verbosity.validate?.("banana")).toBeTruthy();
    expect(verbosity.validate?.("quiet")).toBeNull();

    const temp = SETTING_DEFS.find((s) => s.key === "temperature")!;
    expect(temp.validate?.("3.5")).toBeTruthy();
    expect(temp.validate?.("1.0")).toBeNull();

    const reasoning = SETTING_DEFS.find((s) => s.key === "reasoning")!;
    expect(reasoning.validate?.("max")).toBeTruthy();
    expect(reasoning.validate?.("high")).toBeNull();
  });
});

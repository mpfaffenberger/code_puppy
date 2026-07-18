/**
 * Unit tests for completion sources and readline helpers.
 */

import { describe, expect, test } from "bun:test";
import {
  completionsFor,
  fileCompletions,
  isShellPassthrough,
  shellCommand,
} from "./completions";

const COMMANDS = [
  "help", "theme", "model", "resume", "sessions", "compact", "cd", "set",
  "show", "reasoning", "verbosity", "pop", "prune", "truncate", "mcp", "quit",
];

describe("slash-command completions", () => {
  test("prefix match: /mo → /model", () => {
    const sugs = completionsFor({
      line: "/mo",
      cursor: 3,
      cwd: "/tmp",
      commands: COMMANDS,
    });
    const labels = sugs.map((s) => s.label);
    expect(labels).toContain("/model");
  });

  test("empty prefix lists all commands", () => {
    const sugs = completionsFor({
      line: "/",
      cursor: 1,
      cwd: "/tmp",
      commands: COMMANDS,
    });
    expect(sugs.length).toBeGreaterThan(5);
  });

  test("no match returns empty", () => {
    const sugs = completionsFor({
      line: "/zzz",
      cursor: 4,
      cwd: "/tmp",
      commands: COMMANDS,
    });
    expect(sugs).toEqual([]);
  });

  test("slash not at start → no command completion", () => {
    const sugs = completionsFor({
      line: "run /mo",
      cursor: 7,
      cwd: "/tmp",
      commands: COMMANDS,
    });
    expect(sugs).toEqual([]);
  });
});

describe("file completions", () => {
  test("lists files in the test fixture dir", () => {
    // Use the ts/ dir itself as a fixture.
    const sugs = fileCompletions(process.cwd(), "");
    const labels = sugs.map((s) => s.label);
    expect(labels).toContain("package.json");
  });

  test("@trigger in token produces file suggestions", () => {
    const sugs = completionsFor({
      line: "read @pack",
      cursor: 10,
      cwd: process.cwd(),
      commands: COMMANDS,
    });
    const labels = sugs.map((s) => s.label);
    expect(labels.some((l) => l.includes("package"))).toBe(true);
  });

  test("ignores node_modules and dist", () => {
    const sugs = fileCompletions(process.cwd(), "");
    const labels = sugs.map((s) => s.label);
    expect(labels).not.toContain("node_modules");
  });
});

describe("shell passthrough", () => {
  test("detects !cmd", () => {
    expect(isShellPassthrough("!ls -la")).toBe(true);
    expect(isShellPassthrough("  !git status")).toBe(true);
    expect(isShellPassthrough("ls")).toBe(false);
  });

  test("extracts command", () => {
    expect(shellCommand("!ls -la")).toBe("ls -la");
    expect(shellCommand("  !git status")).toBe("git status");
  });
});

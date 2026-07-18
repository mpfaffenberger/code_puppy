/**
 * History surgery tests: popLastTurn, pruneHistory, truncateHistory.
 * Verifies the exact message-count semantics the TUI /pop /prune /truncate
 * commands surface to the user.
 */

import { describe, expect, test } from "bun:test";
import { MistEngine } from "./agent";
import type { ChatMessage } from "./models";

function hist(...msgs: { role: "user" | "assistant"; content: string }[]): ChatMessage[] {
  return msgs as ChatMessage[];
}

describe("history surgery", () => {
  test("popLastTurn removes the last user turn + reply", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(
      hist(
        { role: "user", content: "first" },
        { role: "assistant", content: "reply1" },
        { role: "user", content: "second" },
        { role: "assistant", content: "reply2" },
      ),
    );
    const removed = e.popLastTurn();
    expect(removed).toBe(2);
    expect(e.exportHistory()).toHaveLength(2);
    expect(e.exportHistory()[1]!.role).toBe("assistant");
  });

  test("popLastTurn returns 0 when history is empty", () => {
    const e = new MistEngine("/tmp");
    expect(e.popLastTurn()).toBe(0);
  });

  test("popLastTurn returns 0 when no user message exists", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(hist({ role: "assistant", content: "orphan" }));
    expect(e.popLastTurn()).toBe(0);
    expect(e.exportHistory()).toHaveLength(1);
  });

  test("pruneHistory keeps only the last N turns", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(
      hist(
        { role: "user", content: "t1" },
        { role: "assistant", content: "r1" },
        { role: "user", content: "t2" },
        { role: "assistant", content: "r2" },
        { role: "user", content: "t3" },
        { role: "assistant", content: "r3" },
      ),
    );
    const removed = e.pruneHistory(1);
    expect(removed).toBe(4);
    expect(e.exportHistory()).toHaveLength(2);
    expect((e.exportHistory()[0] as { content: string }).content).toBe("t3");
  });

  test("pruneHistory(0) is a refused no-op (wiping everything was a footgun)", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(
      hist(
        { role: "user", content: "a" },
        { role: "assistant", content: "b" },
      ),
    );
    expect(e.pruneHistory(0)).toBe(0);
    expect(e.exportHistory()).toHaveLength(2);
  });

  test("turn boundaries skip tool_results, steers, and auto-continue nudges", () => {
    const e = new MistEngine("/tmp");
    // One real turn with tool traffic, then a second real turn.
    e.loadHistory([
      { role: "user", content: "real turn one" },
      {
        role: "assistant",
        content: [
          { type: "text", text: "working" },
          { type: "tool_use", id: "t1", name: "shell", input: {} },
        ],
      },
      { role: "user", content: [{ type: "tool_result", tool_use_id: "t1", content: "out" }] },
      { role: "user", content: "[steer — freshest user intent, adjust immediately] hurry" },
      { role: "user", content: "[auto-continue] keep going" },
      { role: "assistant", content: [{ type: "text", text: "done one" }] },
      { role: "user", content: "real turn two" },
      { role: "assistant", content: [{ type: "text", text: "done two" }] },
    ] as ChatMessage[]);

    // /pop removes ONLY turn two (2 messages), not from the tool_result.
    expect(e.popLastTurn()).toBe(2);
    expect(e.exportHistory()).toHaveLength(6);
    // History still starts at the real prompt and ends with the assistant.
    expect((e.exportHistory()[0] as { content: string }).content).toBe("real turn one");

    // /prune 1 keeps the whole remaining turn intact — tool traffic included.
    expect(e.pruneHistory(1)).toBe(0); // only one genuine turn left
    expect(e.exportHistory()).toHaveLength(6);
  });

  test("pruneHistory never leaves an orphaned tool_result at the head", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory([
      { role: "user", content: "turn one" },
      { role: "assistant", content: [{ type: "tool_use", id: "a", name: "shell", input: {} }] },
      { role: "user", content: [{ type: "tool_result", tool_use_id: "a", content: "x" }] },
      { role: "assistant", content: [{ type: "text", text: "r1" }] },
      { role: "user", content: "turn two" },
      { role: "assistant", content: [{ type: "text", text: "r2" }] },
    ] as ChatMessage[]);
    expect(e.pruneHistory(1)).toBe(4); // drops all of turn one, atomically
    const head = e.exportHistory()[0]!;
    expect(head.role).toBe("user");
    expect(typeof head.content).toBe("string"); // a real prompt, not a tool_result
  });

  test("pruneHistory does nothing when already within limit", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(hist({ role: "user", content: "only" }));
    expect(e.pruneHistory(5)).toBe(0);
    expect(e.exportHistory()).toHaveLength(1);
  });

  test("truncateHistory drops oldest until under budget", () => {
    const e = new MistEngine("/tmp");
    // Each message ~10 chars ~4 tokens. Load several to exceed a small budget.
    e.loadHistory(
      hist(
        { role: "user", content: "0123456789".repeat(10) }, // ~40 tok
        { role: "assistant", content: "0123456789".repeat(10) },
        { role: "user", content: "0123456789".repeat(10) },
        { role: "assistant", content: "recent" },
      ),
    );
    const before = e.exportHistory().length;
    const removed = e.truncateHistory(10); // tiny budget → keep only last 1-2
    expect(removed).toBeGreaterThan(0);
    expect(e.exportHistory().length).toBeLessThan(before);
    expect(e.exportHistory().length).toBeGreaterThanOrEqual(1);
  });

  test("truncateHistory keeps at least one message", () => {
    const e = new MistEngine("/tmp");
    e.loadHistory(
      hist({ role: "user", content: "short" }, { role: "assistant", content: "ok" }),
    );
    e.truncateHistory(1);
    expect(e.exportHistory().length).toBeGreaterThanOrEqual(1);
  });
});

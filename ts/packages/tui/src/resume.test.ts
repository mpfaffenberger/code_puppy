import { expect, test } from "bun:test";
import { historyTailItems } from "./index";
import type { ChatMessage } from "@mist/core";

const HISTORY: ChatMessage[] = [
  { role: "user", content: "first question" },
  { role: "assistant", content: [{ type: "text", text: "answer one" }] },
  { role: "user", content: "second question" },
  {
    role: "assistant",
    content: [
      { type: "text", text: "working on it" },
      { type: "tool_use", id: "t1", name: "shell", input: {} },
      { type: "tool_use", id: "t2", name: "grep", input: {} },
    ],
  },
  {
    role: "user",
    content: [
      { type: "tool_result", tool_use_id: "t1", content: "out1" },
      { type: "tool_result", tool_use_id: "t2", content: "out2" },
    ],
  },
  { role: "assistant", content: [{ type: "text", text: "final answer" }] },
  { role: "user", content: "[steer — freshest user intent, adjust immediately] hurry up" },
  { role: "user", content: "[auto-continue] Your plan still has pending items." },
];

test("historyTailItems: chronological tail, tools collapsed, plumbing hidden", () => {
  const items = historyTailItems(HISTORY, 3) as { kind: string; text?: string }[];
  const shape = items.map((i) => `${i.kind}:${i.text ?? ""}`);
  expect(shape).toEqual([
    "info:— earlier in this session —",
    "user:first question",
    "response:answer one",
    "user:second question",
    "narration:working on it",
    "info:⋯ ran 2 tool calls",
    "response:final answer",
    "user:hurry up", // steer prefix stripped, auto-continue hidden
  ]);
});

test("historyTailItems: respects maxTurns and empty history", () => {
  const items = historyTailItems(HISTORY, 1) as { kind: string; text?: string }[];
  // Only the newest user turn (the steer) and what followed it.
  expect(items.map((i) => i.kind)).toEqual(["info", "user"]);
  expect(historyTailItems([], 3)).toEqual([]);
});

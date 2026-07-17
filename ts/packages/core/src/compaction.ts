/**
 * Context compaction — ported from the Python engine's battle-tested design
 * (code_puppy/agents/_compaction.py + _history.py):
 *
 * 1. **Tool-result clearing** (cheapest, every turn): old bulky tool_result
 *    payloads are replaced with a short stub once the model has consumed
 *    them; the most recent K stay verbatim. Pairing is preserved (only the
 *    content string changes).
 * 2. **Summarization compaction** (on demand via /compact, or automatically
 *    past a token threshold): older conversation is replaced by a single
 *    structured summary message; a recent tail is protected verbatim. The
 *    split only happens at *real user turn boundaries* (role=user with
 *    string content), which guarantees tool_use/tool_result pairs are never
 *    severed.
 */

import type { ChatMessage } from "./anthropic";

/** Same dirt-simple heuristic the Python engine uses: chars / 2.5. */
export function estimateTokens(messages: ChatMessage[]): number {
  let chars = 0;
  for (const m of messages) {
    chars += typeof m.content === "string" ? m.content.length : JSON.stringify(m.content).length;
  }
  return Math.max(1, Math.floor(chars / 2.5));
}

const CLEARED_PREFIX = "[tool result cleared";

export interface ClearOptions {
  keepRecent?: number; // most recent tool_results kept verbatim
  minChars?: number; // only clear payloads bigger than this
}

/** Replace old bulky tool_result contents with stubs. Idempotent. */
export function clearStaleToolResults(
  messages: ChatMessage[],
  { keepRecent = 4, minChars = 2000 }: ClearOptions = {},
): { messages: ChatMessage[]; cleared: number } {
  // Locate every tool_result block: [messageIndex, blockIndex]
  const locations: [number, number][] = [];
  messages.forEach((m, mi) => {
    if (!Array.isArray(m.content)) return;
    m.content.forEach((b, bi) => {
      if (b.type === "tool_result") locations.push([mi, bi]);
    });
  });
  if (locations.length <= keepRecent) return { messages, cleared: 0 };

  const protectedSet = new Set(locations.slice(-keepRecent).map(([a, b]) => `${a}:${b}`));
  let cleared = 0;
  const out = messages.map((m, mi) => {
    if (!Array.isArray(m.content)) return m;
    let changed = false;
    const content = m.content.map((b, bi) => {
      if (
        b.type !== "tool_result" ||
        protectedSet.has(`${mi}:${bi}`) ||
        typeof b.content !== "string" ||
        b.content.length < minChars ||
        b.content.startsWith(CLEARED_PREFIX)
      ) {
        return b;
      }
      changed = true;
      cleared += 1;
      return {
        ...b,
        content: `${CLEARED_PREFIX} to save context — ~${Math.floor(b.content.length / 2.5)} tokens removed. Re-run the tool if needed.]`,
      };
    });
    return changed ? { ...m, content } : m;
  });
  return { messages: out, cleared };
}

export const SUMMARIZATION_PROMPT = `Summarize this conversation log so the agent can keep working without re-deriving context. Preserve everything needed to continue. Cover, where present:
- GOAL: the user's original task and any restated intent.
- CONSTRAINTS: requirements, preferences, and instructions still in force.
- CHANGED FILES: files created/edited/deleted and the gist of each change.
- DECISIONS: choices made and the reasoning behind them.
- FAILED ATTEMPTS: approaches tried that did not work, so they aren't repeated.
- VERIFICATION: what was tested/run, and whether it passed, failed, or was skipped.
- NEXT ACTION: the immediate next step that was pending.
Do not invent verification results or claim success the log does not show. Use a concise bulleted list.`;

/**
 * Split history for compaction: everything before the chosen user-turn
 * boundary gets summarized; the tail stays verbatim. Returns null when
 * there's no safe/beneficial split (history too small or no boundary).
 */
export function splitForCompaction(
  messages: ChatMessage[],
  protectedTokens = 8_000,
): { toSummarize: ChatMessage[]; tail: ChatMessage[] } | null {
  if (messages.length < 4) return null;
  // Real user turn boundaries: role=user with plain string content.
  const boundaries: number[] = [];
  messages.forEach((m, i) => {
    if (i > 0 && m.role === "user" && typeof m.content === "string") boundaries.push(i);
  });
  if (!boundaries.length) return null;
  // Choose the latest boundary that keeps the tail under protectedTokens…
  let chosen = -1;
  for (const b of boundaries) {
    if (estimateTokens(messages.slice(b)) <= protectedTokens) {
      chosen = b;
      break; // boundaries ascend; the first fitting one keeps the most tail
    }
  }
  // …or, if even the last boundary's tail is huge, use the last boundary.
  if (chosen === -1) chosen = boundaries[boundaries.length - 1]!;
  if (chosen <= 1) return null; // nothing meaningful to summarize
  return { toSummarize: messages.slice(0, chosen), tail: messages.slice(chosen) };
}

/** Render messages into a plain-text log for the summarizer. */
export function renderLogForSummary(messages: ChatMessage[]): string {
  const parts: string[] = [];
  for (const m of messages) {
    if (typeof m.content === "string") {
      parts.push(`${m.role.toUpperCase()}: ${m.content}`);
      continue;
    }
    for (const b of m.content) {
      if (b.type === "text") parts.push(`ASSISTANT: ${b.text}`);
      else if (b.type === "tool_use")
        parts.push(`TOOL_CALL ${b.name}: ${JSON.stringify(b.input).slice(0, 300)}`);
      else if (b.type === "tool_result")
        parts.push(`TOOL_RESULT: ${String(b.content).slice(0, 500)}`);
    }
  }
  return parts.join("\n").slice(0, 120_000);
}

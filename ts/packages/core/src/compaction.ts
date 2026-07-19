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

/**
 * Supersession dedup: a newer read of the same file makes older reads stale
 * SEMANTICALLY, regardless of age — the newest read is the truth (the older
 * bytes may literally be wrong after edits). Evicts the older result bodies.
 *
 * Rules (conservative — supersession must be certain):
 * - a whole-file read (no start_line/num_lines) supersedes EVERY earlier
 *   read of that path (any range is contained in it)
 * - an identical-input read supersedes earlier identical reads
 * - different ranges of the same path do NOT supersede each other
 *
 * Cache discipline matches clearStaleToolResults: deterministic stub (bytes
 * depend only on the path), monotonic (once cleared, never touched again),
 * and small payloads are left alone (churn would cost more than it saves).
 */
export function dedupeSupersededReads(
  messages: ChatMessage[],
  { minChars = 2000 }: { minChars?: number } = {},
): { messages: ChatMessage[]; cleared: number } {
  // Collect read_file tool_use blocks in history order.
  const reads: { id: string; path: string; whole: boolean; inputKey: string }[] = [];
  for (const m of messages) {
    if (m.role !== "assistant" || !Array.isArray(m.content)) continue;
    for (const b of m.content) {
      if (b.type !== "tool_use" || b.name !== "read_file") continue;
      const input = (b.input ?? {}) as Record<string, unknown>;
      const path = typeof input["path"] === "string" ? input["path"] : "";
      if (!path) continue;
      reads.push({
        id: b.id,
        path,
        whole: input["start_line"] === undefined && input["num_lines"] === undefined,
        inputKey: JSON.stringify([path, input["start_line"], input["num_lines"]]),
      });
    }
  }
  // A read is superseded if any LATER read is a whole-file read of the same
  // path, or has identical input.
  const superseded = new Map<string, string>(); // tool_use id → path
  for (let i = 0; i < reads.length; i++) {
    const r = reads[i]!;
    for (let j = i + 1; j < reads.length; j++) {
      const later = reads[j]!;
      if (later.path !== r.path) continue;
      if (later.whole || later.inputKey === r.inputKey) {
        superseded.set(r.id, r.path);
        break;
      }
    }
  }
  if (superseded.size === 0) return { messages, cleared: 0 };

  let cleared = 0;
  const out = messages.map((m) => {
    if (!Array.isArray(m.content)) return m;
    let changed = false;
    const content = m.content.map((b) => {
      if (
        b.type !== "tool_result" ||
        !superseded.has(b.tool_use_id) ||
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
        content: `${CLEARED_PREFIX} — superseded by a newer read of ${superseded.get(b.tool_use_id)}. Re-run the tool if needed.]`,
      };
    });
    return changed ? { ...m, content } : m;
  });
  return { messages: out, cleared };
}

export interface ClearOptions {
  keepRecent?: number; // most recent tool_results kept verbatim
  minChars?: number; // only clear payloads bigger than this
  /** Plan only: report what WOULD be cleared without touching messages. */
  dryRun?: boolean;
}

export interface ClearResult {
  messages: ChatMessage[];
  cleared: number;
  /** Chars of payload that clearing removes (savings estimate). */
  savedChars: number;
  /** Chars from the FIRST cleared block's message to the end of history —
   *  the region a prompt-cache prefix bust would force to re-cache. */
  tailChars: number;
}

/** Replace old bulky tool_result contents with stubs. Idempotent. */
export function clearStaleToolResults(
  messages: ChatMessage[],
  { keepRecent = 4, minChars = 2000, dryRun = false }: ClearOptions = {},
): ClearResult {
  // Locate every tool_result block: [messageIndex, blockIndex]
  const locations: [number, number][] = [];
  messages.forEach((m, mi) => {
    if (!Array.isArray(m.content)) return;
    m.content.forEach((b, bi) => {
      if (b.type === "tool_result") locations.push([mi, bi]);
    });
  });
  if (locations.length <= keepRecent) return { messages, cleared: 0, savedChars: 0, tailChars: 0 };

  const protectedSet = new Set(locations.slice(-keepRecent).map(([a, b]) => `${a}:${b}`));
  // Plan pass: which blocks qualify, and what the clearing costs/saves.
  const clearSet = new Set<string>();
  let savedChars = 0;
  let firstMi = -1;
  messages.forEach((m, mi) => {
    if (!Array.isArray(m.content)) return;
    m.content.forEach((b, bi) => {
      if (
        b.type !== "tool_result" ||
        protectedSet.has(`${mi}:${bi}`) ||
        typeof b.content !== "string" ||
        b.content.length < minChars ||
        b.content.startsWith(CLEARED_PREFIX)
      ) {
        return;
      }
      clearSet.add(`${mi}:${bi}`);
      savedChars += b.content.length;
      if (firstMi < 0) firstMi = mi;
    });
  });
  if (clearSet.size === 0) return { messages, cleared: 0, savedChars: 0, tailChars: 0 };
  let tailChars = 0;
  for (let mi = firstMi; mi < messages.length; mi++) {
    const c = messages[mi]!.content;
    tailChars += typeof c === "string" ? c.length : JSON.stringify(c).length;
  }
  if (dryRun) return { messages, cleared: clearSet.size, savedChars, tailChars };

  const out = messages.map((m, mi) => {
    if (!Array.isArray(m.content)) return m;
    let changed = false;
    const content = m.content.map((b, bi) => {
      if (!clearSet.has(`${mi}:${bi}`) || b.type !== "tool_result" || typeof b.content !== "string")
        return b;
      changed = true;
      return {
        ...b,
        content: `${CLEARED_PREFIX} to save context — ~${Math.floor(b.content.length / 2.5)} tokens removed. Re-run the tool if needed.]`,
      };
    });
    return changed ? { ...m, content } : m;
  });
  return { messages: out, cleared: clearSet.size, savedChars, tailChars };
}

/**
 * Adaptive hygiene: should the stale-result sweep run NOW, or is deferring
 * cheaper? Uses the harness's own /lens observations — this is the runtime
 * break-even from the caching analysis, computed with live signals instead
 * of assumptions.
 *
 * Economics (cache read ≈ 0.1x, cache write ≈ 1.25x input price):
 * - clearing saves ~0.1 × savedTokens on EVERY future request
 * - but busts the prefix at the first cleared block: ~1.25 × tailTokens once
 * Clear when expected next-turn savings beat the bust cost. Always clear
 * when the endpoint shows no cache activity (nothing to protect) or the
 * cache is likely cold (idle past TTL — the bust is free).
 */
export interface HygieneSignals {
  /** Endpoint demonstrated real cache hits in recent turns. */
  cacheLive: boolean;
  /** Observed average model requests per turn (savings multiplier). */
  avgRequestsPerTurn: number;
  /** Idle past the provider cache TTL (or first turn) — bust costs nothing. */
  cacheLikelyCold: boolean;
}

export function staleClearWorthIt(
  plan: { savedChars: number; tailChars: number },
  sig: HygieneSignals,
): { clear: boolean; reason: string } {
  if (!sig.cacheLive) return { clear: true, reason: "no cache activity on this endpoint" };
  if (sig.cacheLikelyCold) return { clear: true, reason: "cache likely cold — clearing is free" };
  const savedTok = Math.round(plan.savedChars / 2.5);
  const tailTok = Math.round(plan.tailChars / 2.5);
  const perTurnSavings = Math.round(0.1 * savedTok * Math.max(1, sig.avgRequestsPerTurn));
  const bustCost = Math.round(1.25 * tailTok);
  return perTurnSavings > bustCost
    ? {
        clear: true,
        reason: `saves ~${perTurnSavings} tok-eq/turn vs ~${bustCost} one-time bust`,
      }
    : {
        clear: false,
        reason: `deferred — bust ~${bustCost} tok-eq > ~${perTurnSavings}/turn savings (cache live)`,
      };
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

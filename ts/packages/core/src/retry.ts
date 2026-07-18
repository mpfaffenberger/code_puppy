/**
 * Transient-failure retries for model calls — Claude Code style.
 *
 * Wraps any leaf ModelClient. Retryable failures (429/5xx/529 overloaded,
 * network drops, provider "overloaded" stream errors) back off exponentially
 * with jitter and re-send the SAME request; the UI is told via onRetry so the
 * wait is visible instead of a silent stall.
 *
 * Safety rule: NEVER retry once visible output has streamed to the UI —
 * a re-send would duplicate text the user already read. Those errors
 * surface immediately (the turn is resumable, nothing is lost).
 *
 * Knobs: MIST_RETRIES (default 5, 0 disables), MIST_RETRY_BASE_MS
 * (default 1000; doubles per attempt, capped at 30s, ±25% jitter).
 */

import type { ChatMessage, ModelClient, StreamCallbacks, ToolSpec, TurnResult } from "./models";

const RETRYABLE_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504, 529]);

export function isRetryableError(err: unknown): boolean {
  const msg = String((err as Error | undefined)?.message ?? err ?? "");
  const http = msg.match(/HTTP (\d{3})/);
  if (http) return RETRYABLE_STATUS.has(Number(http[1]));
  if (/overloaded|rate.?limit|too many requests|server had an error/i.test(msg)) return true;
  // Network-level failures (fetch throws before any HTTP status exists).
  return /fetch failed|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EPIPE|socket|network|terminated/i.test(
    msg,
  );
}

export function maxRetries(): number {
  const n = Number(process.env.MIST_RETRIES ?? 5);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 5;
}

/** attempt is 1-based; exponential with cap + ±25% jitter. */
export function retryDelayMs(attempt: number): number {
  const base = Number(process.env.MIST_RETRY_BASE_MS ?? 1000) || 1000;
  const exp = Math.min(base * 2 ** (attempt - 1), 30_000);
  const jitter = 0.75 + Math.random() * 0.5;
  return Math.round(exp * jitter);
}

const shortReason = (err: unknown): string =>
  String((err as Error | undefined)?.message ?? err ?? "unknown error")
    .replace(/\s+/g, " ")
    .slice(0, 120);

export class RetryingClient implements ModelClient {
  constructor(private inner: ModelClient) {}

  async stream(
    system: string,
    messages: ChatMessage[],
    tools: ToolSpec[],
    cb: StreamCallbacks,
    maxTokens?: number,
  ): Promise<TurnResult> {
    const retries = maxRetries();
    let emitted = false;
    // Track visible output only where a listener exists — headless calls
    // (title gen, summarizer) have no UI to duplicate, so they may retry
    // even after a mid-stream failure.
    const guarded: StreamCallbacks = { ...cb };
    if (cb.onTextDelta) {
      const orig = cb.onTextDelta;
      guarded.onTextDelta = (t) => {
        emitted = true;
        orig(t);
      };
    }
    if (cb.onToolUse) {
      const orig = cb.onToolUse;
      guarded.onToolUse = (n) => {
        emitted = true;
        orig(n);
      };
    }

    for (let attempt = 0; ; attempt++) {
      try {
        return await this.inner.stream(system, messages, tools, guarded, maxTokens);
      } catch (err) {
        if (emitted || attempt >= retries || !isRetryableError(err)) throw err;
        const delayMs = retryDelayMs(attempt + 1);
        cb.onRetry?.(attempt + 1, retries, delayMs, shortReason(err));
        await Bun.sleep(delayMs);
      }
    }
  }
}

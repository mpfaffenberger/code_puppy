/**
 * Round-robin wrapper: cycles through N underlying ModelClients, advancing to
 * the next after every `rotateEvery` requests. Mirrors Python's
 * `RoundRobinModel` — distribution, NOT failover (errors propagate; no retry
 * on the next candidate). Used to spread load across rate-limited endpoints.
 *
 * Configured via a `round_robin` model_type whose ModelDef carries a list of
 * candidate model names; the factory builds each child and wraps them here.
 */

import type { ModelClient, StreamCallbacks, ChatMessage, ToolSpec, TurnResult } from "./models";

export interface RoundRobinOptions {
  rotateEvery?: number;
}

export class RoundRobinClient implements ModelClient {
  private index = 0;
  private count = 0;
  private readonly rotateEvery: number;

  constructor(private readonly clients: ModelClient[], opts: RoundRobinOptions = {}) {
    if (clients.length === 0) throw new Error("RoundRobinClient needs at least one client");
    const re = opts.rotateEvery ?? 1;
    if (re < 1) throw new Error("rotateEvery must be >= 1");
    this.rotateEvery = re;
  }

  get modelNames(): string {
    return this.clients.map((c) => (c as any).model ?? "?").join(",");
  }

  private next(): ModelClient {
    const client = this.clients[this.index]!;
    this.count += 1;
    if (this.count >= this.rotateEvery) {
      this.index = (this.index + 1) % this.clients.length;
      this.count = 0;
    }
    return client;
  }

  async stream(
    system: string,
    messages: ChatMessage[],
    tools: ToolSpec[],
    cb: StreamCallbacks = {},
    maxTokens?: number,
  ): Promise<TurnResult> {
    // Distribution, not failover — let errors propagate (Python parity).
    return this.next().stream(system, messages, tools, cb, maxTokens);
  }
}

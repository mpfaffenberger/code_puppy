/**
 * Round-robin wrapper: verifies rotation every N requests and that errors
 * propagate (distribution, not failover — Python parity).
 */

import { describe, expect, test } from "bun:test";
import { RoundRobinClient } from "./round_robin";
import { configFromDef, createModelClient } from "./models";
import type { ChatMessage, ModelClient, ModelResolver, ToolSpec, TurnResult } from "./models";

function fakeClient(name: string, calls: string[]): ModelClient {
  return {
    async stream(
      _s: string,
      _m: ChatMessage[],
      _t: ToolSpec[],
    ): Promise<TurnResult> {
      calls.push(name);
      return {
        text: name,
        thinkingMs: 0,
        toolUses: [],
        stopReason: "stop",
        inputTokens: 1,
        outputTokens: 1,
      };
    },
  };
}

describe("RoundRobinClient", () => {
  test("rotates every request by default (rotateEvery=1)", async () => {
    const calls: string[] = [];
    const rr = new RoundRobinClient([
      fakeClient("A", calls),
      fakeClient("B", calls),
      fakeClient("C", calls),
    ]);
    for (let i = 0; i < 6; i++) await rr.stream("s", [], []);
    expect(calls).toEqual(["A", "B", "C", "A", "B", "C"]);
  });

  test("respects rotateEvery=2", async () => {
    const calls: string[] = [];
    const rr = new RoundRobinClient(
      [fakeClient("A", calls), fakeClient("B", calls)],
      { rotateEvery: 2 },
    );
    for (let i = 0; i < 6; i++) await rr.stream("s", [], []);
    expect(calls).toEqual(["A", "A", "B", "B", "A", "A"]);
  });

  test("wraps around the candidate list", async () => {
    const calls: string[] = [];
    const rr = new RoundRobinClient(
      [fakeClient("X", calls), fakeClient("Y", calls)],
      { rotateEvery: 1 },
    );
    for (let i = 0; i < 5; i++) await rr.stream("s", [], []);
    expect(calls).toEqual(["X", "Y", "X", "Y", "X"]);
  });

  test("rejects empty candidate list and rotateEvery < 1", () => {
    expect(() => new RoundRobinClient([])).toThrow("at least one");
    expect(() => new RoundRobinClient([fakeClient("A", [])], { rotateEvery: 0 })).toThrow(">= 1");
  });

  test("factory path: configFromDef + createModelClient reach RoundRobinClient", async () => {
    // Regression: configFromDef used to throw 'no endpoint configured' for
    // round_robin defs (no custom_endpoint, no default base) BEFORE the
    // factory's round_robin branch could run — the feature was unreachable.
    const registry: Record<string, { name: string; type: string; custom_endpoint?: { url: string; api_key?: string }; models?: string[]; rotate_every?: number }> = {
      m1: { name: "m1", type: "custom_anthropic", custom_endpoint: { url: "http://127.0.0.1:1", api_key: "x" } },
      m2: { name: "m2", type: "custom_anthropic", custom_endpoint: { url: "http://127.0.0.1:2", api_key: "x" } },
      rr: { name: "rr", type: "round_robin", models: ["m1", "m2"], rotate_every: 5 },
    };
    const resolve: ModelResolver = async (n) => createModelClient(configFromDef(registry[n]!), resolve);
    const client = await createModelClient(configFromDef(registry["rr"]!), resolve);
    expect(client).toBeInstanceOf(RoundRobinClient);
    expect((client as RoundRobinClient).modelNames.split(",").length).toBe(2);
  });

  test("propagates errors (distribution, not failover)", async () => {
    const bad: ModelClient = {
      async stream(): Promise<TurnResult> {
        throw new Error("429 rate limited");
      },
    };
    const good = fakeClient("good", []);
    const rr = new RoundRobinClient([bad, good]);
    expect(rr.stream("s", [], [])).rejects.toThrow("429");
  });
});

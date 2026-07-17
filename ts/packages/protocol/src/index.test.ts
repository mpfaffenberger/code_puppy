import { describe, expect, test } from "bun:test";
import { EventEnvelopeSchema, parseEnvelope } from "./index";

describe("EventEnvelope", () => {
  test("parses a well-formed envelope (as emitted by code_puppy/events.py)", () => {
    const env = parseEnvelope(
      JSON.stringify({
        schema_version: 1,
        sequence: 3,
        type: "agent_response",
        session_id: "abc-123",
        timestamp: "2026-07-16T12:00:00+00:00",
        data: { text: "hello" },
      }),
    );
    expect(env.sequence).toBe(3);
    expect(env.type).toBe("agent_response");
    expect(env.timestamp instanceof Date).toBe(true);
    expect(env.data["text"]).toBe("hello");
  });

  test("defaults schema_version to 1 and data to {}", () => {
    const env = EventEnvelopeSchema.parse({
      sequence: 1,
      type: "lifecycle",
      session_id: "s",
      timestamp: "2026-07-16T12:00:00Z",
    });
    expect(env.schema_version).toBe(1);
    expect(env.data).toEqual({});
  });

  test("rejects invalid sequence (Python side enforces ge=1)", () => {
    expect(() =>
      EventEnvelopeSchema.parse({
        sequence: 0,
        type: "x",
        session_id: "s",
        timestamp: "2026-07-16T12:00:00Z",
      }),
    ).toThrow();
  });
});

/**
 * @mist/protocol — the wire contract between Mist front-ends and engines.
 *
 * Ported from `code_puppy/events.py` (`EventEnvelope`). This package is the
 * migration seam (docs/BUN_MIGRATION_PLAN.md §1): the Bun TUI speaks this
 * envelope to the Python engine's `mist --serve` today, and to the Bun engine
 * later. Changes here are breaking-change territory — mirror the Python side
 * (schema_version bump) or don't make them.
 */

import { z } from "zod";

/**
 * Stable public envelope around internal messages and lifecycle events.
 * Mirrors Python: schema_version >= 1, sequence >= 1 (monotonic per session),
 * ISO-8601 UTC timestamp, free-form `data` payload keyed by `type`.
 */
export const EventEnvelopeSchema = z.object({
  schema_version: z.number().int().min(1).default(1),
  sequence: z.number().int().min(1),
  type: z.string(),
  session_id: z.string(),
  timestamp: z.coerce.date(),
  data: z.record(z.unknown()).default({}),
});

export type EventEnvelope = z.infer<typeof EventEnvelopeSchema>;

/** Parse one SSE `data:` payload (or any JSON string) into an envelope. */
export function parseEnvelope(json: string): EventEnvelope {
  return EventEnvelopeSchema.parse(JSON.parse(json));
}

/** Session record shape returned by the HTTP API (subset we rely on). */
export const SessionRecordSchema = z.object({
  id: z.string(),
  agent_name: z.string().optional(),
  status: z.string().optional(),
});
export type SessionRecord = z.infer<typeof SessionRecordSchema>;

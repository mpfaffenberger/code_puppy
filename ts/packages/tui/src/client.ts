/**
 * MistClient — thin session client over the EventEnvelope HTTP/SSE API.
 *
 * Engine-agnostic on purpose: Phase 1 points it at the Python engine
 * (`mist --serve`); Phase 2 points it at the Bun engine. The TUI never knows
 * the difference — that's the strangler seam.
 */

import { EventEnvelopeSchema, SessionRecordSchema } from "@mist/protocol";
import type { EventEnvelope, SessionRecord } from "@mist/protocol";

export class MistClient {
  private headers: Record<string, string> = {};

  constructor(readonly base: string = process.env.MIST_SERVER ?? "http://127.0.0.1:4096") {}

  async connect(token?: string): Promise<void> {
    const t =
      token ??
      (await Bun.file(`${process.env.HOME}/.mist/server.json`)
        .json()
        .then((c) => c.token as string));
    this.headers = { Authorization: `Bearer ${t}`, "Content-Type": "application/json" };
  }

  async createSession(): Promise<SessionRecord> {
    const res = await fetch(`${this.base}/session`, {
      method: "POST",
      headers: this.headers,
      body: "{}",
    });
    if (!res.ok) throw new Error(`create session: HTTP ${res.status}`);
    return SessionRecordSchema.parse(await res.json());
  }

  async submit(sessionId: string, prompt: string): Promise<void> {
    const res = await fetch(`${this.base}/session/${sessionId}/message`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) throw new Error(`submit: HTTP ${res.status}`);
  }

  async interrupt(sessionId: string): Promise<void> {
    await fetch(`${this.base}/session/${sessionId}/interrupt`, {
      method: "POST",
      headers: this.headers,
    });
  }

  /**
   * Subscribe to the session's SSE stream; invokes `onEvent` per envelope.
   * Returns a cancel function. Reconnects once on transient stream errors
   * using Last-Event-ID so no envelopes are lost.
   */
  subscribe(
    sessionId: string,
    onEvent: (env: EventEnvelope) => void,
    onError: (err: Error) => void,
  ): () => void {
    let cancelled = false;
    let lastId = 0;

    const run = async (attempt: number): Promise<void> => {
      try {
        const res = await fetch(`${this.base}/session/${sessionId}/events`, {
          headers: { ...this.headers, "Last-Event-ID": String(lastId || "") },
        });
        if (!res.ok || !res.body) throw new Error(`events: HTTP ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const frames = buf.split("\n\n");
          buf = frames.pop() ?? "";
          for (const frame of frames) {
            const data = frame
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trim())
              .join("");
            if (!data) continue;
            try {
              const env = EventEnvelopeSchema.parse(JSON.parse(data));
              lastId = env.sequence;
              onEvent(env);
            } catch {
              /* SSE comments / keepalives — not envelopes */
            }
          }
        }
      } catch (err) {
        if (!cancelled && attempt < 1) return run(attempt + 1);
        if (!cancelled) onError(err as Error);
      }
    };
    void run(0);
    return () => {
      cancelled = true;
    };
  }
}

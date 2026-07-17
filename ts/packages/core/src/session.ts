/**
 * EngineSession — bridges the MistEngine loop to the EventEnvelope protocol,
 * in-process. Implements the same client surface as the HTTP MistClient
 * (createSession / submit / subscribe / interrupt), so the TUI runs fully
 * self-contained in one binary — the strangler seam's final form.
 */

import type { EventEnvelope } from "@mist/protocol";
import { MistEngine } from "./agent";

type Listener = (env: EventEnvelope) => void;

export class EngineSession {
  readonly id = crypto.randomUUID().replaceAll("-", "");
  private engine: MistEngine;
  private sequence = 0;
  private listeners = new Set<Listener>();
  private buffer: EventEnvelope[] = [];

  constructor(cwd: string = process.cwd()) {
    this.engine = new MistEngine(cwd);
    this.emit("session.created", { agent_name: "mist" });
  }

  private emit(type: string, data: Record<string, unknown>): void {
    const env: EventEnvelope = {
      schema_version: 1,
      sequence: ++this.sequence,
      type,
      session_id: this.id,
      timestamp: new Date(),
      data,
    };
    this.buffer.push(env);
    for (const l of this.listeners) l(env);
  }

  subscribe(onEvent: Listener): () => void {
    for (const env of this.buffer) onEvent(env); // replay, like Last-Event-ID
    this.listeners.add(onEvent);
    return () => this.listeners.delete(onEvent);
  }

  async submit(prompt: string): Promise<void> {
    this.emit("session.running", { prompt });
    try {
      const turn = await this.engine.runTurn(prompt, {
        onTextDelta: (delta) => this.emit("text.delta", { delta }),
        onStep: (label) => this.emit("step", { label }),
        onUsage: (input_tokens, output_tokens) =>
          this.emit("usage", { input_tokens, output_tokens }),
      });
      if (turn.finalText.trim()) {
        this.emit("AgentResponseMessage", { content: turn.finalText });
      }
      this.emit("session.idle", {});
    } catch (err) {
      this.emit("session.error", { error: (err as Error).message });
      this.emit("session.idle", {});
    }
  }
}

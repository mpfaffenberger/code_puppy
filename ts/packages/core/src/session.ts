/**
 * EngineSession — bridges the MistEngine loop to the EventEnvelope protocol,
 * in-process. Implements the same client surface as the HTTP MistClient
 * (createSession / submit / subscribe / interrupt), so the TUI runs fully
 * self-contained in one binary — the strangler seam's final form.
 */

import type { EventEnvelope } from "@mist/protocol";
import { MistEngine } from "./agent";
import { SessionStore } from "./store";
import type { StoredSession } from "./store";

type Listener = (env: EventEnvelope) => void;

export class EngineSession {
  readonly id: string;
  private engine: MistEngine;
  private sequence = 0;
  private listeners = new Set<Listener>();
  private buffer: EventEnvelope[] = [];
  private store: SessionStore;
  private persistedCount = 0;
  private created: boolean;

  constructor(cwd: string = process.cwd(), resume?: StoredSession) {
    this.engine = new MistEngine(cwd);
    this.store = new SessionStore(cwd);
    if (resume) {
      this.id = resume.meta.id;
      this.created = true;
      this.engine.loadHistory(resume.messages);
      this.engine.plan = resume.plan;
      this.persistedCount = resume.messages.length;
      this.emit("session.created", { agent_name: "mist" });
      this.emit("session.resumed", {
        title: resume.meta.title,
        messages: resume.messages.length,
        created_at: resume.meta.created_at,
      });
      if (resume.plan.length) this.emit("plan.updated", { items: resume.plan });
    } else {
      this.id = crypto.randomUUID().replaceAll("-", "");
      this.created = false;
      this.emit("session.created", { agent_name: "mist" });
    }
  }

  private userNamed = false;
  private autoTitled = false;

  /** Rename this session (the /rename command); sticks for /resume. */
  async rename(title: string): Promise<void> {
    const clean = title.trim();
    if (!clean) return;
    this.userNamed = true;
    const ok = this.created ? await this.store.rename(this.id, clean) : false;
    if (!ok && !this.created) {
      // Session not persisted yet — create it now under the chosen name.
      await this.store.create(this.id, clean);
      this.created = true;
    }
    this.emit("session.renamed", { title: clean, auto: false });
  }

  /**
   * One-shot: replace the raw first-prompt title with a short generated name
   * (skipped once the user has named the session themselves).
   */
  private async autoTitle(firstPrompt: string): Promise<void> {
    if (this.userNamed || this.autoTitled) return;
    this.autoTitled = true;
    const title = await this.engine.generateTitle(firstPrompt);
    if (!title || this.userNamed) return;
    const ok = await this.store.rename(this.id, title);
    if (ok) this.emit("session.renamed", { title, auto: true });
  }

  /** Persist any history the store hasn't seen yet (after each turn). */
  private async persist(): Promise<void> {
    try {
      const history = this.engine.exportHistory();
      if (!this.created) {
        const firstUser = history.find((m) => m.role === "user");
        const raw = typeof firstUser?.content === "string" ? firstUser.content : "(tool session)";
        await this.store.create(this.id, raw);
        this.created = true;
        // Upgrade the raw prompt to a generated name in the background.
        if (typeof firstUser?.content === "string") void this.autoTitle(firstUser.content);
      }
      if (history.length > this.persistedCount) {
        await this.store.appendMessages(this.id, history.slice(this.persistedCount));
        this.persistedCount = history.length;
      }
      await this.store.snapshotPlan(this.id, this.engine.plan);
    } catch {
      /* persistence must never break the session */
    }
  }

  private traceSink: import("bun").FileSink | null = null;
  private tracePath: string | null = null;
  private traceCount = 0;

  /** Start recording every envelope to a JSONL trace (for replay debugging). */
  startTrace(path?: string): string {
    const file = path ?? `${process.env.HOME}/.mist/traces/${this.id.slice(0, 8)}-${Date.now()}.jsonl`;
    Bun.spawnSync(["mkdir", "-p", file.slice(0, file.lastIndexOf("/"))]);
    this.traceSink = Bun.file(file).writer();
    this.tracePath = file;
    this.traceCount = 0;
    // replay context: everything already buffered lands in the trace too
    for (const env of this.buffer) this.writeTrace(env);
    return file;
  }

  /** Stop recording; returns {path, events}. */
  stopTrace(): { path: string; events: number } | null {
    if (!this.traceSink || !this.tracePath) return null;
    void this.traceSink.end();
    const out = { path: this.tracePath, events: this.traceCount };
    this.traceSink = null;
    this.tracePath = null;
    return out;
  }

  get tracing(): string | null {
    return this.tracePath;
  }

  private writeTrace(env: EventEnvelope): void {
    if (!this.traceSink) return;
    this.traceSink.write(`${JSON.stringify(env)}\n`);
    this.traceCount += 1;
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
    this.writeTrace(env);
    for (const l of this.listeners) l(env);
  }

  subscribe(onEvent: Listener): () => void {
    for (const env of this.buffer) onEvent(env); // replay, like Last-Event-ID
    this.listeners.add(onEvent);
    return () => this.listeners.delete(onEvent);
  }

  /** Manual compaction (the /compact command). */
  async compact(): Promise<void> {
    try {
      const r = await this.engine.compact();
      if (r) {
        this.emit("context.compacted", {
          before_tokens: r.beforeTokens,
          after_tokens: r.afterTokens,
          summarized: r.summarized,
        });
      } else {
        this.emit("context.compacted", { before_tokens: 0, after_tokens: 0, summarized: 0 });
      }
    } catch (err) {
      this.emit("session.error", { error: `compact failed: ${(err as Error).message}` });
    }
  }

  contextTokens(): number {
    return this.engine.estimateContextTokens();
  }

  historyLength(): number {
    return this.engine.exportHistory().length;
  }

  exportHistory() {
    return this.engine.exportHistory();
  }

  /** Switch models mid-session (next request onward). */
  setModel(name: string): void {
    this.engine.setModel(name);
  }

  /** Nudge the running turn; injected before the model's next request. */
  steer(text: string): void {
    this.engine.queueSteer(text);
    this.emit("steer.queued", { text });
  }

  private pendingAnswer: ((answer: string) => void) | null = null;

  /** Answer the currently pending ask_user question (no-op if none). */
  answer(text: string): void {
    const resolve = this.pendingAnswer;
    this.pendingAnswer = null;
    resolve?.(text);
  }

  async submit(prompt: string): Promise<void> {
    this.emit("session.running", { prompt });
    try {
      const turn = await this.engine.runTurn(prompt, {
        onTextDelta: (delta) => this.emit("text.delta", { delta }),
        onStep: (label) => this.emit("step", { label }),
        onUsage: (input_tokens, output_tokens) =>
          this.emit("usage", { input_tokens, output_tokens }),
        onPlan: (items) => this.emit("plan.updated", { items }),
        onSavings: (tokens_saved) => this.emit("headroom.saved", { tokens_saved }),
        onNarration: (text) => this.emit("narration", { text }),
        onDiff: (diff) => this.emit("file.edited", { ...diff }),
        onToolDone: (label, preview, hidden_lines) =>
          this.emit("step.done", { label, preview, hidden_lines }),
        onThought: (ms) => this.emit("thought", { ms }),
        onCompacted: (r) =>
          this.emit("context.compacted", {
            before_tokens: r.beforeTokens,
            after_tokens: r.afterTokens,
            summarized: r.summarized,
          }),
        onQuestion: (question, options) =>
          new Promise<string>((resolve) => {
            this.pendingAnswer = resolve;
            this.emit("question.asked", { question, options });
          }),
      });
      if (turn.finalText.trim()) {
        this.emit("AgentResponseMessage", { content: turn.finalText });
      }
      await this.persist();
      this.emit("session.idle", {});
    } catch (err) {
      this.emit("session.error", { error: (err as Error).message });
      await this.persist();
      this.emit("session.idle", {});
    }
  }
}

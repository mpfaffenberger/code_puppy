/**
 * Session persistence — Claude Code / codex style.
 *
 * Layout: `~/.mist/ts-sessions/<project-slug>/<session-id>.jsonl`, append-only
 * JSONL. First line is meta; subsequent lines are history messages (and
 * occasional plan snapshots). Sessions are grouped per project directory
 * (slugged cwd), so `--continue` resumes the latest session *for this
 * project*, exactly like Claude Code.
 *
 * Line shapes:
 *   {"kind":"meta","id":…,"cwd":…,"created_at":…,"title":…}
 *   {"kind":"message","message":{role, content}}
 *   {"kind":"plan","items":[…]}          // latest snapshot wins on resume
 *   {"kind":"lens","turn":{…}}           // one per completed turn (/lens survives resume)
 */

import { mkdir, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ChatMessage } from "./anthropic";
import type { TurnLens } from "./lens";
import type { PlanItem } from "./plan";

export interface SessionMeta {
  id: string;
  cwd: string;
  created_at: string;
  updated_at?: string;
  title: string;
}

export interface StoredSession {
  meta: SessionMeta;
  messages: ChatMessage[];
  plan: PlanItem[];
  /** Lens ledger turns, oldest → newest (capped to the engine's 50). */
  lensTurns: TurnLens[];
}

export function projectSlug(cwd: string): string {
  return cwd.replaceAll("/", "-").replace(/^-/, "-");
}

function root(): string {
  return process.env.MIST_SESSIONS_DIR ?? join(homedir(), ".mist", "ts-sessions");
}

function dirFor(cwd: string): string {
  return join(root(), projectSlug(cwd));
}

function fileFor(cwd: string, id: string): string {
  return join(dirFor(cwd), `${id}.jsonl`);
}

export class SessionStore {
  constructor(readonly cwd: string) {}

  async create(id: string, title: string): Promise<void> {
    await mkdir(dirFor(this.cwd), { recursive: true });
    const meta: SessionMeta = {
      id,
      cwd: this.cwd,
      created_at: new Date().toISOString(),
      title: title.slice(0, 80),
    };
    await Bun.write(fileFor(this.cwd, id), `${JSON.stringify({ kind: "meta", ...meta })}\n`);
  }

  private async append(id: string, line: Record<string, unknown>): Promise<void> {
    const path = fileFor(this.cwd, id);
    const existing = await Bun.file(path)
      .text()
      .catch(() => "");
    await Bun.write(path, existing + `${JSON.stringify(line)}\n`);
  }

  /** Rewrite the meta line with a new title (the /rename command + auto-titling). */
  async rename(id: string, title: string): Promise<boolean> {
    const path = fileFor(this.cwd, id);
    const text = await Bun.file(path)
      .text()
      .catch(() => "");
    if (!text) return false;
    const lines = text.split("\n");
    let meta: SessionMeta;
    try {
      const obj = JSON.parse(lines[0] ?? "") as Record<string, unknown>;
      if (obj["kind"] !== "meta") return false;
      meta = obj as unknown as SessionMeta;
    } catch {
      return false;
    }
    meta.title = title.slice(0, 80);
    meta.updated_at = new Date().toISOString();
    lines[0] = JSON.stringify({ kind: "meta", ...meta });
    await Bun.write(path, lines.join("\n"));
    return true;
  }

  async appendMessages(id: string, messages: ChatMessage[]): Promise<void> {
    for (const message of messages) {
      await this.append(id, { kind: "message", message });
    }
  }

  async snapshotPlan(id: string, items: PlanItem[]): Promise<void> {
    if (items.length) await this.append(id, { kind: "plan", items });
  }

  async appendLensTurn(id: string, turn: TurnLens): Promise<void> {
    await this.append(id, { kind: "lens", turn });
  }

  async load(id: string): Promise<StoredSession | null> {
    const text = await Bun.file(fileFor(this.cwd, id))
      .text()
      .catch(() => "");
    if (!text) return null;
    let meta: SessionMeta | null = null;
    const messages: ChatMessage[] = [];
    let plan: PlanItem[] = [];
    const lensTurns: TurnLens[] = [];
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      try {
        const obj = JSON.parse(line) as Record<string, unknown>;
        if (obj["kind"] === "meta") meta = obj as unknown as SessionMeta;
        else if (obj["kind"] === "message") messages.push(obj["message"] as ChatMessage);
        else if (obj["kind"] === "plan" && Array.isArray(obj["items"]))
          plan = obj["items"] as PlanItem[];
        else if (obj["kind"] === "lens" && obj["turn"]) lensTurns.push(obj["turn"] as TurnLens);
      } catch {
        /* skip corrupt line — resume what we can */
      }
    }
    return meta ? { meta, messages, plan, lensTurns: lensTurns.slice(-50) } : null;
  }

  /** Sessions for this project, newest first (by file mtime). */
  async list(): Promise<SessionMeta[]> {
    const dir = dirFor(this.cwd);
    let names: string[] = [];
    try {
      names = (await readdir(dir)).filter((n) => n.endsWith(".jsonl"));
    } catch {
      return [];
    }
    const metas: (SessionMeta & { mtime: number })[] = [];
    for (const name of names) {
      const path = join(dir, name);
      const file = Bun.file(path);
      const first = (await file.text().catch(() => "")).split("\n", 1)[0] ?? "";
      try {
        const obj = JSON.parse(first) as Record<string, unknown>;
        if (obj["kind"] === "meta") {
          metas.push({ ...(obj as unknown as SessionMeta), mtime: file.lastModified });
        }
      } catch {
        /* unreadable session file — skip */
      }
    }
    metas.sort((a, b) => b.mtime - a.mtime);
    return metas.map(({ mtime: _m, ...meta }) => meta);
  }

  async latest(): Promise<SessionMeta | null> {
    return (await this.list())[0] ?? null;
  }
}

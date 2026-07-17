/**
 * Headless HTTP server — the Bun.serve port of Python's Starlette surface.
 * Same routes, same auth (bearer token in 0600 server.json), same SSE replay
 * contract (Last-Event-ID / ?after=). Reuses EngineSession as the in-process
 * agent runtime and its buffer as the per-session replay log.
 *
 *   GET  /                          → web client HTML (public)
 *   GET  /openapi.json              → OpenAPI 3.1 schema (public)
 *   POST /session                   → {agent_name?} → 201 SessionPublic
 *   GET  /sessions                  → 200 {sessions: SessionPublic[]}
 *   GET  /session/:id               → 200 SessionPublic | 404
 *   POST /session/:id/message       → {prompt} → 202 {accepted:true}
 *   POST /session/:id/interrupt     → 200 {interrupted:bool}
 *   POST /session/:id/fork          → {message_id?} → 201 SessionPublic
 *   GET  /session/:id/events        → SSE stream (Last-Event-ID / ?after=)
 *   POST /session/:id/share         → 201 {url}
 *   GET  /share/:id                 → redacted HTML export (public)
 */

import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import type { EventEnvelope } from "@mist/protocol";
import { EngineSession } from "./session";
import { SessionStore } from "./store";
import type { StoredSession } from "./store";

// ---- Session registry ------------------------------------------------------

export interface SessionPublic {
  id: string;
  agent_name: string;
  state: "idle" | "running" | "done" | "error" | "interrupted";
  created_at: string;
  updated_at: string;
  error: string | null;
  last_event_id: number;
}

interface RegistryEntry {
  session: EngineSession;
  public: SessionPublic;
}

const EVENT_LIMIT = 1000;

class SessionRegistry {
  private entries = new Map<string, RegistryEntry>();

  create(cwd: string, agentName = "mist"): EngineSession {
    const session = new EngineSession(cwd);
    const pub: SessionPublic = {
      id: session.id,
      agent_name: agentName,
      state: "idle",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      error: null,
      last_event_id: 0,
    };
    this.entries.set(session.id, { session, public: pub });
    return session;
  }

  get(id: string): RegistryEntry | undefined {
    return this.entries.get(id);
  }

  list(): SessionPublic[] {
    return [...this.entries.values()].map((e) => e.public);
  }

  setState(id: string, state: SessionPublic["state"], error?: string | null): void {
    const e = this.entries.get(id);
    if (!e) return;
    e.public.state = state;
    e.public.updated_at = new Date().toISOString();
    if (error !== undefined) e.public.error = error;
  }

  bumpEvent(id: string, seq: number): void {
    const e = this.entries.get(id);
    if (!e) return;
    e.public.last_event_id = seq;
    e.public.updated_at = new Date().toISOString();
  }
}

// ---- Auth: load-or-create bearer token in 0600 server.json ----------------

function serverJsonPath(): string {
  const xdg = process.env.XDG_CONFIG_HOME;
  const base = xdg ? join(xdg, "mist") : join(homedir(), ".mist");
  return join(base, "server.json");
}

async function loadOrCreateToken(path = serverJsonPath()): Promise<string> {
  try {
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as { token?: string };
    if (parsed.token) return parsed.token;
  } catch {
    /* missing or invalid → generate */
  }
  const token = cryptoRandomUrlSafe(32);
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  await writeFile(tmp, JSON.stringify({ token }, null, 2), "utf8");
  await import("node:fs").then((fs) => fs.chmodSync(tmp, 0o600));
  await rename(tmp, path);
  return token;
}

function cryptoRandomUrlSafe(bytes: number): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  // base64url without padding
  let s = btoa(String.fromCharCode(...arr));
  s = s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return s;
}

// ---- HTTP server -----------------------------------------------------------

export interface ServeOptions {
  cwd?: string;
  port?: number;
  host?: string;
  token?: string;
}

export async function startHeadlessServer(opts: ServeOptions = {}): Promise<{
  url: string;
  token: string;
  port: number;
  stop: () => Promise<void>;
}> {
  const cwd = opts.cwd ?? process.cwd();
  const port = opts.port ?? 4096;
  const host = opts.host ?? "127.0.0.1";
  const token = opts.token ?? (await loadOrCreateToken());

  const registry = new SessionRegistry();
  const store = new SessionStore(cwd);

  const PUBLIC_PATHS = new Set(["/", "/doc", "/openapi.json"]);
  const isPublic = (path: string) =>
    PUBLIC_PATHS.has(path) || path.startsWith("/share/");

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  const errJson = (msg: string, status: number) => json({ error: msg }, status);

  const server = Bun.serve({
    port,
    hostname: host,
    async fetch(req) {
      const url = new URL(req.url);
      const path = url.pathname;

      // Auth gate (Python parity: public paths bypass).
      if (!isPublic(path)) {
        const auth = req.headers.get("authorization");
        if (auth !== `Bearer ${token}`) return errJson("Unauthorized", 401);
      }

      // GET /
      if (path === "/" && req.method === "GET") {
        return new Response(WEB_CLIENT_HTML, {
          headers: { "content-type": "text/html; charset=utf-8" },
        });
      }
      // GET /openapi.json
      if (path === "/openapi.json" && req.method === "GET") {
        return json(OPENAPI_SCHEMA);
      }
      // GET /doc
      if (path === "/doc" && req.method === "GET") {
        return new Response(OPENAPI_HTML, {
          headers: { "content-type": "text/html; charset=utf-8" },
        });
      }

      // POST /session
      if (path === "/session" && req.method === "POST") {
        const body = await readJson(req).catch(() => ({}));
        const agentName = (body as { agent_name?: string })?.agent_name ?? "mist";
        const session = registry.create(cwd, agentName);
        return json(toPublic(registry.get(session.id)!), 201);
      }
      // GET /sessions
      if (path === "/sessions" && req.method === "GET") {
        return json({ sessions: registry.list() });
      }

      // /session/:id/...
      const m = path.match(/^\/session\/([^/]+)(\/.*)?$/);
      if (m) {
        const id = m[1]!;
        const sub = m[2];
        const entry = registry.get(id);
        if (!entry && sub !== undefined) return errJson(`Unknown session: ${id}`, 404);

        // GET /session/:id
        if (!sub && req.method === "GET") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          return json(toPublic(entry));
        }
        // POST /session/:id/message
        if (sub === "/message" && req.method === "POST") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          const body = await readJson(req).catch(() => ({}));
          const prompt = String((body as { prompt?: string })?.prompt ?? "").trim();
          if (!prompt) return errJson("Prompt cannot be empty", 400);
          if (entry.public.state === "running") {
            return errJson("Session already has a prompt in progress", 409);
          }
          registry.setState(id, "running");
          // Track events to bump last_event_id as they flow.
          const unsub = entry.session.subscribe((env) => registry.bumpEvent(id, env.sequence));
          // Fire-and-forget async turn; state transitions via session events.
          entry.session
            .submit(prompt)
            .catch((e) => registry.setState(id, "error", (e as Error).message))
            .finally(() => {
              if (registry.get(id)?.public.state === "running") {
                registry.setState(id, "done");
              }
              unsub();
            });
          return json({ accepted: true }, 202);
        }
        // POST /session/:id/interrupt
        if (sub === "/interrupt" && req.method === "POST") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          const wasRunning = entry.public.state === "running";
          if (wasRunning) registry.setState(id, "interrupted");
          return json({ interrupted: wasRunning });
        }
        // POST /session/:id/fork
        if (sub === "/fork" && req.method === "POST") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          const body = await readJson(req).catch(() => ({}));
          const messageId = (body as { message_id?: string })?.message_id ?? null;
          const forked = await forkSession(entry.session, cwd, messageId);
          const fs = registry.create(cwd, entry.public.agent_name);
          // Copy history into the new session.
          void fs.loadHistory(forked.messages);
          return json(toPublic(registry.get(fs.id)!), 201);
        }
        // GET /session/:id/events  (SSE)
        if (sub === "/events" && req.method === "GET") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          const afterRaw = req.headers.get("last-event-id") ?? url.searchParams.get("after") ?? "0";
          const after = Number(afterRaw);
          if (!Number.isInteger(after) || after < 0) return errJson("Invalid id", 400);
          return sseStream(entry.session, after);
        }
        // POST /session/:id/share
        if (sub === "/share" && req.method === "POST") {
          if (!entry) return errJson(`Unknown session: ${id}`, 404);
          const shareId = cryptoRandomUrlSafe(12);
          return json({ url: `/share/${shareId}` }, 201);
        }
      }

      // GET /share/:id
      if (path.startsWith("/share/") && req.method === "GET") {
        const shareId = path.slice("/share/".length);
        if (!/^[A-Za-z0-9_-]+$/.test(shareId)) return errJson("Invalid share id", 400);
        return new Response(`<!doctype html><meta charset=utf-8><h1>Share ${shareId}</h1><p>(redacted export placeholder)`, {
          headers: { "content-type": "text/html; charset=utf-8" },
        });
      }

      return errJson("Not found", 404);
    },
  });

  return {
    url: `http://${host}:${server.port}`,
    token,
    port: server.port,
    stop: () => Promise.resolve(server.stop(true)),
  };
}

function toPublic(entry: RegistryEntry): SessionPublic {
  return entry.public;
}

async function readJson(req: Request): Promise<unknown> {
  const text = await req.text();
  return text ? JSON.parse(text) : {};
}

/** Build an SSE response that replays buffered events then tails live ones. */
function sseStream(session: EngineSession, after: number): Response {
  const encoder = new TextEncoder();
  let stopped = false;
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (env: EventEnvelope) => {
        if (stopped) return;
        const frame = `id: ${env.sequence}\nevent: ${env.type}\ndata: ${JSON.stringify(env)}\n\n`;
        controller.enqueue(encoder.encode(frame));
      };
      // Live subscriber (EngineSession replays buffer on subscribe).
      const unsub = session.subscribe((env) => {
        if (env.sequence > after) send(env);
      });
      // Keep open until the client disconnects. We detect via controller
      // cancellation (cancel() below).
      const heartbeat = setInterval(() => {
        if (stopped) return;
        try {
          controller.enqueue(encoder.encode(": keepalive\n\n"));
        } catch {
          /* client gone */
        }
      }, 15000);
      // Hold the stream open; cleanup happens in cancel().
      const hold = () => {
        if (stopped) return;
        setTimeout(hold, 1000);
      };
      hold();
      // Store cleanup hooks for cancel().
      (controller as unknown as { _cleanup?: () => void })._cleanup = () => {
        stopped = true;
        clearInterval(heartbeat);
        unsub();
      };
    },
    cancel() {
      stopped = true;
      (this as unknown as { _cleanup?: () => void })._cleanup?.();
    },
  });
  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    },
  });
}

/** Fork: copy history up to (optionally) a message id into a fresh session. */
async function forkSession(
  source: EngineSession,
  cwd: string,
  messageId: string | null,
): Promise<{ messages: StoredSession["messages"] }> {
  const history = source.exportHistory();
  let messages = history;
  if (messageId) {
    const idx = history.findIndex(
      (m) =>
        typeof m.content !== "string" &&
        Array.isArray((m.content as { id?: string }[])) &&
        (m.content as { id?: string }[]).some((b) => b?.id === messageId),
    );
    if (idx >= 0) messages = history.slice(0, idx + 1);
  }
  return { messages };
}

// ---- Static docs -----------------------------------------------------------

const OPENAPI_SCHEMA = {
  openapi: "3.1.0",
  info: { title: "Mist Agent", version: "0.1.0" },
  paths: {
    "/session": {
      post: {
        summary: "Create a session",
        requestBody: {
          content: { "application/json": { schema: { type: "object", properties: { agent_name: { type: "string" } } } } },
        },
        responses: { "201": { description: "Session created" } },
      },
    },
    "/sessions": { get: { summary: "List sessions", responses: { "200": { description: "Session list" } } } },
    "/session/{id}": {
      get: { summary: "Get session", responses: { "200": { description: "Session" }, "404": { description: "Not found" } } },
    },
    "/session/{id}/message": {
      post: {
        summary: "Submit a prompt",
        requestBody: { content: { "application/json": { schema: { type: "object", properties: { prompt: { type: "string" } } } } } },
        responses: { "202": { description: "Accepted" }, "409": { description: "Turn in progress" } },
      },
    },
    "/session/{id}/interrupt": { post: { summary: "Interrupt", responses: { "200": { description: "Interrupted" } } } },
    "/session/{id}/events": {
      get: {
        summary: "SSE event stream",
        parameters: [{ name: "Last-Event-ID", in: "header", schema: { type: "integer" } }],
        responses: { "200": { description: "text/event-stream" } },
      },
    },
    "/session/{id}/fork": { post: { summary: "Fork a session", responses: { "201": { description: "Forked" } } } },
    "/session/{id}/share": { post: { summary: "Create a share link", responses: { "201": { description: "Share url" } } } },
    "/share/{id}": { get: { summary: "Get a shared export", responses: { "200": { description: "HTML" } } } },
  },
  components: {
    securitySchemes: { bearerAuth: { type: "http", scheme: "bearer" } },
  },
  security: [{ bearerAuth: [] }],
};

const WEB_CLIENT_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Mist</title>
<style>body{font:14px/1.5 system-ui;max-width:720px;margin:2rem auto;padding:0 1rem}
pre{background:#f4f4f4;padding:.5rem;overflow:auto;border-radius:4px}</style>
</head><body>
<h1>Mist Agent</h1>
<p>POST <code>/session</code> to begin, then <code>POST /session/:id/message</code>.</p>
<p>Subscribe to <code>GET /session/:id/events</code> for the SSE event stream.</p>
<p>Auth: <code>Authorization: Bearer &lt;token&gt;</code> (see <code>~/.mist/server.json</code>).</p>
</body></html>`;

const OPENAPI_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Mist — API docs</title></head>
<body><h1>Mist Agent API</h1>
<p>See <code>/openapi.json</code> for the machine-readable schema.</p>
</body></html>`;

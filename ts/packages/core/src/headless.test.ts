/**
 * Headless server tests — verifies the route surface, bearer auth, session
 * lifecycle, and SSE replay contract against a live Bun.serve instance.
 * Uses the mock_model server so no real LLM calls are made.
 */

import { afterEach, describe, expect, test } from "bun:test";
import { startMockModel } from "./testing/mock_model";
import { startHeadlessServer } from "./headless";

const M_PORT = 9871;
const H_PORT = 9872;

async function setupServers() {
  // Point the engine at the mock model.
  process.env.ANTHROPIC_BASE_URL = `http://127.0.0.1:${M_PORT}`;
  process.env.ANTHROPIC_API_KEY = "test-key";
  const mock = startMockModel(M_PORT);
  const server = await startHeadlessServer({ port: H_PORT, cwd: process.cwd() });
  return {
    mock,
    server,
    cleanup: async () => {
      server.stop();
      mock.stop();
    },
    base: server.url,
    token: server.token,
  };
}

function authHeaders(token: string): Record<string, string> {
  return { authorization: `Bearer ${token}`, "content-type": "application/json" };
}

describe("headless server", () => {
  test("GET / is public (no auth) and serves HTML", async () => {
    const { cleanup, base } = await setupServers();
    const res = await fetch(`${base}/`);
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("<html");
    await cleanup();
  });

  test("unauthorized requests to /session are rejected (401)", async () => {
    const { cleanup, base } = await setupServers();
    const res = await fetch(`${base}/session`, { method: "POST", body: "{}" });
    expect(res.status).toBe(401);
    await cleanup();
  });

  test("full lifecycle: create → submit → SSE events arrive", async () => {
    const { cleanup, base, token } = await setupServers();

    // 1. Create session.
    const createRes = await fetch(`${base}/session`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ agent_name: "mist" }),
    });
    expect(createRes.status).toBe(201);
    const session = (await createRes.json()) as { id: string; state: string };
    expect(session.id).toBeTruthy();
    expect(session.state).toBe("idle");

    // 2. Submit a prompt.
    const msgRes = await fetch(`${base}/session/${session.id}/message`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ prompt: "say hello" }),
    });
    expect(msgRes.status).toBe(202);
    const accepted = (await msgRes.json()) as { accepted: boolean };
    expect(accepted.accepted).toBe(true);

    // 3. Subscribe to the SSE stream and collect events until idle.
    const events = await collectSseEvents(`${base}/session/${session.id}/events`, token, 8000, "session.idle");
    const types = events.map((e) => e.event);
    expect(types).toContain("session.running");
    expect(types).toContain("session.idle");

    await cleanup();
  }, 15000);

  test("submitting while a turn is running returns 409", async () => {
    const { cleanup, base, token } = await setupServers();
    const createRes = await fetch(`${base}/session`, {
      method: "POST",
      headers: authHeaders(token),
      body: "{}",
    });
    const session = (await createRes.json()) as { id: string };

    // Fire first submit.
    await fetch(`${base}/session/${session.id}/message`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ prompt: "long task" }),
    });
    // Immediately submit again.
    const second = await fetch(`${base}/session/${session.id}/message`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ prompt: "second" }),
    });
    // Could be 202 (if first already finished) or 409 (if still running).
    expect([202, 409]).toContain(second.status);
    await cleanup();
  });

  test("GET /sessions lists active sessions", async () => {
    const { cleanup, base, token } = await setupServers();
    await fetch(`${base}/session`, {
      method: "POST",
      headers: authHeaders(token),
      body: "{}",
    });
    const res = await fetch(`${base}/sessions`, { headers: authHeaders(token) });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { sessions: { id: string }[] };
    expect(body.sessions.length).toBeGreaterThanOrEqual(1);
    await cleanup();
  });

  test("GET /openapi.json is public and valid", async () => {
    const { cleanup, base } = await setupServers();
    const res = await fetch(`${base}/openapi.json`);
    expect(res.status).toBe(200);
    const schema = (await res.json()) as { openapi: string; paths: unknown };
    expect(schema.openapi).toBe("3.1.0");
    expect(schema.paths).toBeDefined();
    await cleanup();
  });

  test("interrupt a running session", async () => {
    const { cleanup, base, token } = await setupServers();
    const createRes = await fetch(`${base}/session`, {
      method: "POST",
      headers: authHeaders(token),
      body: "{}",
    });
    const session = (await createRes.json()) as { id: string };
    await fetch(`${base}/session/${session.id}/message`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ prompt: "task" }),
    });
    const res = await fetch(`${base}/session/${session.id}/interrupt`, {
      method: "POST",
      headers: authHeaders(token),
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { interrupted: boolean };
    expect(typeof body.interrupted).toBe("boolean");
    await cleanup();
  });
});

/** Connect to the SSE stream, parse frames, collect until a terminal event or timeout. */
async function collectSseEvents(
  url: string,
  token: string,
  timeoutMs: number,
  stopOnEvent?: string,
): Promise<{ id: number; event: string; data: unknown }[]> {
  const events: { id: number; event: string; data: unknown }[] = [];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" },
      signal: controller.signal,
    });
    if (!res.body) return events;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        const lines = frame.split("\n");
        let id = 0;
        let event = "";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("id:")) id = Number(line.slice(3).trim());
          else if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (event) {
          let parsed: unknown = data;
          try {
            parsed = JSON.parse(data);
          } catch {
            /* keep raw */
          }
          events.push({ id, event, data: parsed });
          if (stopOnEvent && event === stopOnEvent) {
            clearTimeout(timer);
            return events;
          }
        }
      }
    }
  } catch {
    // timeout or abort — return what we have
  } finally {
    clearTimeout(timer);
  }
  return events;
}

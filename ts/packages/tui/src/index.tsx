/**
 * @mist/tui — Phase 1 spike (docs/BUN_MIGRATION_PLAN.md §2, Phase 1).
 *
 * Go/no-go question this answers: can Ink deliver Mist's Option B UX —
 * transcript scrolling above a pinned, always-animating footer — against the
 * live Python engine (`mist --serve`)?
 *
 * Ink's `<Static>` renders completed items once, above the dynamic region,
 * and never repaints them — the exact print-above-Live semantics the Python
 * TUI needed custom plumbing for. The dynamic region below is the footer.
 *
 * Usage:  bun run src/index.tsx "your prompt"
 * Exits on q / Ctrl+C, or ~10s after the last event (headless testing).
 */

import { Box, Static, Text, render, useApp, useInput } from "ink";
import { useEffect, useRef, useState } from "react";
import { EventEnvelopeSchema, SessionRecordSchema } from "@mist/protocol";
import type { EventEnvelope } from "@mist/protocol";

const BASE = process.env.MIST_SERVER ?? "http://127.0.0.1:4096";
const SPARKLE = ["⡡⠊⢔⠡", "⠊⡰⡡⡘", "⢔⢅⠈⢢", "⡁⢂⠆⡍", "⢔⠨⢑⢐", "⠨⡑⡠⠊"];
const BREATHE = ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"];

async function authHeaders(): Promise<Record<string, string>> {
  const cfg = await Bun.file(`${process.env.HOME}/.mist/server.json`).json();
  return { Authorization: `Bearer ${cfg.token}`, "Content-Type": "application/json" };
}

function summarize(env: EventEnvelope): string {
  const d = env.data as Record<string, unknown>;
  const text =
    (typeof d["text"] === "string" && d["text"]) ||
    (typeof d["content"] === "string" && d["content"]) ||
    (typeof d["message"] === "string" && d["message"]) ||
    "";
  const body = text ? text : JSON.stringify(d).slice(0, 100);
  return body.length > 400 ? `${body.slice(0, 399)}…` : body;
}

function App({ prompt }: { prompt: string }) {
  const { exit } = useApp();
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [status, setStatus] = useState("connecting");
  const [frame, setFrame] = useState(0);
  const lastEventAt = useRef(Date.now());

  useInput((input) => {
    if (input === "q") exit();
  });

  // Footer heartbeat — animates regardless of stream activity (the whole
  // point: liveliness is owned by the render loop, not the byte stream).
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => f + 1), 120);
    return () => clearInterval(id);
  }, []);

  // Idle auto-exit so the spike is drivable headlessly (tmux harness).
  useEffect(() => {
    const id = setInterval(() => {
      if (events.length > 0 && Date.now() - lastEventAt.current > 10_000) exit();
    }, 1000);
    return () => clearInterval(id);
  }, [events.length, exit]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const H = await authHeaders();
      const sRes = await fetch(`${BASE}/session`, { method: "POST", headers: H, body: "{}" });
      const session = SessionRecordSchema.parse(await sRes.json());
      setStatus(`session ${session.id.slice(0, 8)} · working`);
      await fetch(`${BASE}/session/${session.id}/message`, {
        method: "POST",
        headers: H,
        body: JSON.stringify({ prompt }),
      });
      const eRes = await fetch(`${BASE}/session/${session.id}/events`, { headers: H });
      const reader = eRes.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (!cancelled) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const chunks = buf.split("\n\n");
        buf = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const data = chunk
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trim())
            .join("");
          if (!data) continue;
          try {
            const env = EventEnvelopeSchema.parse(JSON.parse(data));
            lastEventAt.current = Date.now();
            setEvents((prev) => [...prev, env]);
          } catch {
            // Non-envelope SSE noise (comments/heartbeats) — ignore.
          }
        }
      }
    })().catch((err) => setStatus(`error: ${err.message}`));
    return () => {
      cancelled = true;
    };
  }, [prompt]);

  return (
    <Box flexDirection="column">
      {/* Transcript: rendered once, scrolls away above — Ink's print-above. */}
      <Static items={events}>
        {(env, i) => (
          <Box key={`${env.sequence}-${i}`} flexDirection="row" gap={1}>
            <Text color="yellow" dimColor>
              [{env.type}]
            </Text>
            <Text>{summarize(env)}</Text>
          </Box>
        )}
      </Static>
      {/* Pinned footer: heartbeat + sparkle + status, always animating. */}
      <Box marginTop={1}>
        <Text color="cyan" bold>
          {BREATHE[frame % BREATHE.length]} {SPARKLE[frame % SPARKLE.length]} Mist · {status} ·{" "}
          {events.length} events · q to quit
        </Text>
      </Box>
    </Box>
  );
}

const prompt = process.argv.slice(2).join(" ") || "Reply with exactly: pong";
render(<App prompt={prompt} />);

/**
 * Mist TUI — Phase 1 (docs/BUN_MIGRATION_PLAN.md).
 *
 * Polished Ink front-end speaking the EventEnvelope protocol to any engine
 * (Python `mist --serve` today, Bun engine next). Layout:
 *
 *   ◆ Mist  — brand lockup (pastel gradient) + session/engine info
 *   transcript (Ink <Static>: user prompts, ✓ step rows, markdown answers)
 *   input box (idle)  /  animated status line (busy)
 *
 * Headless/demo mode: `bun run src/index.tsx "prompt"` submits argv and exits
 * shortly after the turn completes (tmux-harness friendly). Interactive mode:
 * no argv → REPL loop; Esc interrupts a busy turn; Ctrl+C exits.
 */

import { Box, Static, Text, render, useApp, useInput } from "ink";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { classifyEvent } from "@mist/protocol";
import type { EventEnvelope } from "@mist/protocol";
import { MistClient } from "./client";
import { Markdown } from "./markdown";
import { HEARTBEAT, SPARKLE, rampColor, theme } from "./theme";

type Item =
  | { id: number; kind: "user"; text: string }
  | { id: number; kind: "step"; text: string }
  | { id: number; kind: "info"; text: string }
  | { id: number; kind: "error"; text: string }
  | { id: number; kind: "response"; text: string };

let nextId = 1;
const item = (kind: Item["kind"], text: string): Item => ({ id: nextId++, kind, text });

function Brand({ engine, session }: { engine: string; session: string }) {
  const word = "Mist";
  return (
    <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
      <Text>
        <Text color={theme.accent}>◆ </Text>
        {[...word].map((ch, i) => (
          <Text key={`b${i}`} bold color={rampColor(i, word.length)}>
            {ch}
          </Text>
        ))}
        <Text color={theme.dim}> — coding agent</Text>
      </Text>
      <Text color={theme.dim}>
        {session ? `session ${session.slice(0, 8)} · ` : ""}
        {engine}
      </Text>
    </Box>
  );
}

function TranscriptItem({ it }: { it: Item }) {
  switch (it.kind) {
    case "user":
      return (
        <Box marginTop={1}>
          <Text bold color={theme.user}>
            ❯ {it.text}
          </Text>
        </Box>
      );
    case "step":
      return (
        <Text color={theme.dim}>
          {"  "}
          <Text color={theme.success}>✓</Text> {it.text}
        </Text>
      );
    case "info":
      return (
        <Text color={theme.dim} dimColor>
          {"  "}
          {it.text}
        </Text>
      );
    case "error":
      return (
        <Text color={theme.error} bold>
          {"  ✗ "}
          {it.text}
        </Text>
      );
    case "response":
      return (
        <Box flexDirection="column" marginTop={1} paddingLeft={0}>
          <Markdown source={it.text} />
        </Box>
      );
  }
}

function App({ initialPrompt }: { initialPrompt?: string }) {
  const { exit } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [frame, setFrame] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [engine] = useState("engine: python");
  const [sessionId, setSessionId] = useState("");
  const [fatal, setFatal] = useState("");
  const clientRef = useRef<MistClient | null>(null);
  const headless = Boolean(initialPrompt);
  const idleExitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const push = useCallback((...xs: Item[]) => setItems((p) => [...p, ...xs]), []);

  // Animation clock (footer only re-renders the dynamic region — cheap).
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => f + 1), 110);
    return () => clearInterval(id);
  }, []);

  const handleEnvelope = useCallback(
    (env: EventEnvelope) => {
      const ev = classifyEvent(env);
      switch (ev.kind) {
        case "session_running":
          setBusy(true);
          setStartedAt(Date.now());
          setStepCount(0);
          break;
        case "shell_start":
          setStepCount((n) => n + 1);
          push(item("step", ev.command.length > 90 ? `${ev.command.slice(0, 89)}…` : ev.command));
          break;
        case "file_read":
          setStepCount((n) => n + 1);
          push(item("step", `read ${ev.path}`));
          break;
        case "file_diff":
          setStepCount((n) => n + 1);
          push(item("step", `edited ${ev.path}`));
          break;
        case "grep_result":
          setStepCount((n) => n + 1);
          push(item("step", `grep — ${ev.totalMatches} matches`));
          break;
        case "subagent_invocation":
          setStepCount((n) => n + 1);
          push(item("step", `delegated to ${ev.agentName}`));
          break;
        case "agent_response":
          if (ev.content.trim()) push(item("response", ev.content));
          break;
        case "session_error":
          push(item("error", ev.error));
          break;
        case "session_idle":
        case "session_interrupted":
          setBusy(false);
          setStartedAt(null);
          if (headless) {
            if (idleExitTimer.current) clearTimeout(idleExitTimer.current);
            idleExitTimer.current = setTimeout(() => exit(), 1500);
          }
          break;
        default:
          break; // shell lines, reasoning, misc info stay out of the transcript — signal over noise
      }
    },
    [exit, headless, push],
  );

  // Bootstrap: connect, create session, subscribe, optionally submit argv.
  useEffect(() => {
    let cancel: (() => void) | undefined;
    (async () => {
      try {
        const client = new MistClient();
        await client.connect();
        clientRef.current = client;
        const session = await client.createSession();
        setSessionId(session.id);
        cancel = client.subscribe(session.id, handleEnvelope, (err) =>
          setFatal(`stream error: ${err.message}`),
        );
        if (initialPrompt) {
          push(item("user", initialPrompt));
          setBusy(true);
          setStartedAt(Date.now());
          await client.submit(session.id, initialPrompt);
        }
      } catch (err) {
        setFatal((err as Error).message);
      }
    })();
    return () => cancel?.();
  }, [handleEnvelope, initialPrompt, push]);

  const submit = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || busy || !clientRef.current || !sessionId) return;
    setInput("");
    push(item("user", prompt));
    setBusy(true);
    setStartedAt(Date.now());
    try {
      await clientRef.current.submit(sessionId, prompt);
    } catch (err) {
      push(item("error", (err as Error).message));
      setBusy(false);
    }
  }, [busy, input, push, sessionId]);

  useInput((ch, key) => {
    if (key.ctrl && ch === "c") exit();
    if (busy) {
      if (key.escape && clientRef.current && sessionId) {
        void clientRef.current.interrupt(sessionId);
      }
      return;
    }
    if (key.return) {
      void submit();
      return;
    }
    if (key.backspace || key.delete) {
      setInput((s) => s.slice(0, -1));
      return;
    }
    if (key.ctrl && ch === "u") {
      setInput("");
      return;
    }
    if (ch && !key.ctrl && !key.meta && !key.escape) setInput((s) => s + ch);
  });

  const elapsed = startedAt ? Math.floor((Date.now() - startedAt) / 1000) : 0;

  return (
    <Box flexDirection="column" paddingX={1}>
      <Static items={[{ id: 0, kind: "brand" } as unknown as Item, ...items]}>
        {(it) =>
          (it as unknown as { kind: string }).kind === "brand" ? (
            <Brand key="brand" engine={engine} session={sessionId} />
          ) : (
            <TranscriptItem key={it.id} it={it} />
          )
        }
      </Static>

      {fatal ? (
        <Box marginTop={1}>
          <Text color={theme.error} bold>
            ✗ {fatal}
          </Text>
        </Box>
      ) : busy ? (
        <Box marginTop={1}>
          <Text color={theme.brand} bold>
            {HEARTBEAT[frame % HEARTBEAT.length]} {SPARKLE[frame % SPARKLE.length]}{" "}
          </Text>
          <Text color={theme.dim}>
            working · {elapsed}s · {stepCount} step{stepCount === 1 ? "" : "s"}
            {"  "}
          </Text>
          <Text color={theme.dim} dimColor>
            esc to interrupt
          </Text>
        </Box>
      ) : (
        <Box
          borderStyle="round"
          borderColor={theme.border}
          paddingX={1}
          marginTop={1}
          flexDirection="row"
        >
          <Text color={theme.accent} bold>
            ❯{" "}
          </Text>
          <Text>
            {input}
            <Text color={theme.brand}>█</Text>
          </Text>
        </Box>
      )}
      {!fatal && !busy && (
        <Text color={theme.dim} dimColor>
          {"  "}enter to send · ctrl+c to quit
        </Text>
      )}
    </Box>
  );
}

const argvPrompt = process.argv.slice(2).join(" ").trim();
render(<App initialPrompt={argvPrompt || undefined} />);

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
import { EngineSession, SessionStore, getConfiguredModelName, listModelNames, persistModelChoice } from "@mist/core";
import type { SessionMeta, StoredSession } from "@mist/core";
import { MistClient } from "./client";
import { Markdown } from "./markdown";
import { HEARTBEAT, SPARKLE, THEMES, applyTheme, loadPersistedTheme, persistTheme, rampColor, theme } from "./theme";

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
    <Box flexDirection="row" marginBottom={1}>
      <Text>
        <Text color={theme.accent}>◆ </Text>
        {[...word].map((ch, i) => (
          <Text key={`b${i}`} bold color={rampColor(i, word.length)}>
            {ch}
          </Text>
        ))}
        <Text color={theme.dim}> — coding agent · </Text>
        <Text color={theme.dim}>
          {session ? `session ${session.slice(0, 8)} · ` : ""}
          {engine}
        </Text>
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

function App({ initialPrompt, resume }: { initialPrompt?: string; resume?: StoredSession }) {
  const { exit } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [frame, setFrame] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [engine] = useState(process.env.MIST_ENGINE === "python" ? "engine: python" : "engine: bun");
  const [stream, setStream] = useState("");
  const [tokens, setTokens] = useState(0);
  const [plan, setPlan] = useState<{ id: string; title: string; status: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [saved, setSaved] = useState(0);
  const [, setThemeTick] = useState(0);
  const [picker, setPicker] = useState<SessionMeta[] | null>(null);
  const [pickerIndex, setPickerIndex] = useState(0);
  const sessionRef = useRef<EngineSession | null>(null);
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
        case "text_delta":
          setStream((t) => t + ev.delta);
          break;
        case "step":
          setStepCount((n) => n + 1);
          push(item("step", ev.label));
          break;
        case "usage":
          setTokens((t) => t + ev.inputTokens + ev.outputTokens);
          break;
        case "plan_updated":
          setPlan(ev.items);
          break;
        case "question_asked":
          setQuestion(ev.question);
          setInput("");
          break;
        case "session_resumed":
          push(item("info", `↺ resumed “${ev.title}” · ${ev.messages} messages · started ${ev.createdAt.slice(0, 10)}`));
          break;
        case "steer_queued":
          push(item("info", `↪ steered: ${ev.text}`));
          break;
        case "headroom_saved":
          setSaved((t) => t + ev.tokensSaved);
          break;
        case "agent_response":
          setStream("");
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
        if (process.env.MIST_ENGINE !== "python") {
          // Self-contained mode: the Bun engine runs in-process. No server.
          const session = new EngineSession(process.cwd(), resume);
          sessionRef.current = session;
          setSessionId(session.id);
          cancel = session.subscribe(handleEnvelope);
          clientRef.current = {
            submit: (_id: string, prompt: string) => session.submit(prompt),
            interrupt: async () => {},
          } as unknown as MistClient;
          if (resume) {
            // Replay the tail of the conversation so the user sees where
            // they left off (codex/Claude Code resume behavior, condensed).
            const lastUser = [...resume.messages].reverse().find(
              (m) => m.role === "user" && typeof m.content === "string",
            );
            if (lastUser) push(item("user", String(lastUser.content)));
            const lastAssistant = [...resume.messages].reverse().find(
              (m) => m.role === "assistant",
            );
            if (lastAssistant) {
              const text = Array.isArray(lastAssistant.content)
                ? lastAssistant.content
                    .map((b) => (b.type === "text" ? b.text : ""))
                    .join("")
                : String(lastAssistant.content);
              if (text.trim()) push(item("response", text));
            }
          }
          if (initialPrompt) {
            push(item("user", initialPrompt));
            setBusy(true);
            setStartedAt(Date.now());
            void session.submit(initialPrompt);
          }
          return;
        }
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

  const resumeIntoSession = useCallback(
    (stored: StoredSession) => {
      const fresh = new EngineSession(process.cwd(), stored);
      sessionRef.current = fresh;
      setSessionId(fresh.id);
      fresh.subscribe(handleEnvelope);
      clientRef.current = {
        submit: (_id: string, prompt: string) => fresh.submit(prompt),
        interrupt: async () => {},
      } as unknown as MistClient;
      const lastUser = [...stored.messages].reverse().find(
        (m) => m.role === "user" && typeof m.content === "string",
      );
      if (lastUser) push(item("user", String(lastUser.content)));
      const lastAssistant = [...stored.messages].reverse().find((m) => m.role === "assistant");
      if (lastAssistant) {
        const text = Array.isArray(lastAssistant.content)
          ? lastAssistant.content.map((b) => (b.type === "text" ? b.text : "")).join("")
          : String(lastAssistant.content);
        if (text.trim()) push(item("response", text));
      }
    },
    [handleEnvelope, push],
  );

  const runCommand = useCallback(
    async (line: string) => {
      const [cmd = "", ...rest] = line.slice(1).trim().split(/\s+/);
      const arg = rest.join(" ").trim();
      const say = (text: string) => push(item("info", text));
      switch (cmd.toLowerCase()) {
        case "help":
          say("commands: /help /resume /theme /model /sessions /new(/clear) /tools /status /dump_context /quit");
          say("keys: Enter send · type+Enter while busy = steer · Esc interrupt · Ctrl+C quit");
          say("flags: -c continue · -r <id> resume · --sessions · MIST_HEADROOM=1");
          break;
        case "theme": {
          if (!arg) {
            say(`themes: ${Object.keys(THEMES).join(" · ")} (current: ${theme.name})`);
            break;
          }
          if (applyTheme(arg)) {
            await persistTheme(arg);
            setThemeTick((t) => t + 1);
            say(`theme → ${arg}`);
          } else {
            say(`unknown theme '${arg}' — try: ${Object.keys(THEMES).join(", ")}`);
          }
          break;
        }
        case "model": {
          if (!arg) {
            const current = await getConfiguredModelName();
            const names = await listModelNames();
            say(`model: ${current} · available: ${names.slice(0, 10).join(", ")}`);
            break;
          }
          const names = await listModelNames();
          if (!names.includes(arg)) {
            say(`unknown model '${arg}' — see /model for the list`);
            break;
          }
          sessionRef.current?.setModel(arg);
          await persistModelChoice(arg);
          say(`model → ${arg} (persisted; applies from the next request)`);
          break;
        }
        case "resume": {
          const list = await new SessionStore(process.cwd()).list();
          if (!list.length) {
            say("(no saved sessions for this directory)");
            break;
          }
          setPicker(list.slice(0, 15));
          setPickerIndex(0);
          break;
        }
        case "sessions": {
          const list = await new SessionStore(process.cwd()).list();
          if (!list.length) say("(no saved sessions for this directory)");
          for (const m of list.slice(0, 8)) {
            say(`${m.id.slice(0, 8)} · ${m.created_at.slice(0, 16).replace("T", " ")} · ${m.title}`);
          }
          if (list.length) say("resume with: mist-ts -r <id>");
          break;
        }
        case "tools": {
          say("tools: read_file (ranged) · create_file · replace_in_file (exact-match) · list_files · grep · shell (guarded)");
          say("engine: update_plan (live plan) · ask_user (clarifying questions)");
          break;
        }
        case "status": {
          const model = await getConfiguredModelName();
          const hist = sessionRef.current ? sessionRef.current.historyLength() : 0;
          say(`session ${sessionId.slice(0, 8)} · model ${model} · ${hist} messages · ${tokens.toLocaleString()} tok this run${saved ? ` · ↓${saved} saved` : ""}`);
          say(`theme ${theme.name} · cwd ${process.cwd()}`);
          break;
        }
        case "dump_context": {
          const path = `/tmp/mist-context-${sessionId.slice(0, 8)}.json`;
          const history = sessionRef.current ? sessionRef.current.exportHistory() : [];
          await Bun.write(path, JSON.stringify(history, null, 2));
          say(`context (${history.length} messages) → ${path}`);
          break;
        }
        case "clear":
        case "new": {
          const fresh = new EngineSession(process.cwd());
          sessionRef.current = fresh;
          setSessionId(fresh.id);
          fresh.subscribe(handleEnvelope);
          clientRef.current = {
            submit: (_id: string, prompt: string) => fresh.submit(prompt),
            interrupt: async () => {},
          } as unknown as MistClient;
          setPlan([]);
          say("— new session —");
          break;
        }
        case "quit":
        case "exit":
        case "q":
          exit();
          break;
        default:
          say(`unknown command /${cmd} — try /help`);
      }
    },
    [exit, handleEnvelope, push, saved, sessionId, tokens],
  );

  const submit = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || busy) return;
    if (prompt.startsWith("/")) {
      setInput("");
      push(item("user", prompt));
      await runCommand(prompt);
      return;
    }
    if (!clientRef.current || !sessionId) return;
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
  }, [busy, input, push, runCommand, sessionId]);

  useInput((ch, key) => {
    if (key.ctrl && ch === "c") exit();
    if (picker) {
      if (key.escape) {
        setPicker(null);
        return;
      }
      if (key.upArrow) {
        setPickerIndex((i) => (i - 1 + picker.length) % picker.length);
        return;
      }
      if (key.downArrow) {
        setPickerIndex((i) => (i + 1) % picker.length);
        return;
      }
      const digit = ch >= "1" && ch <= "9" ? Number(ch) - 1 : -1;
      if (digit >= 0 && digit < picker.length) {
        setPickerIndex(digit);
      }
      if (key.return || (digit >= 0 && digit < picker.length)) {
        const chosen = picker[key.return ? pickerIndex : digit];
        setPicker(null);
        if (chosen) {
          void new SessionStore(process.cwd()).load(chosen.id).then((stored) => {
            if (stored) resumeIntoSession(stored);
            else push(item("error", `could not load session ${chosen.id.slice(0, 8)}`));
          });
        }
        return;
      }
      return;
    }
    if (question) {
      // Answer mode: the agent asked a clarifying question.
      if (key.return) {
        const answer = input.trim();
        setInput("");
        setQuestion("");
        push(item("info", `❓ ${question}`), item("user", answer || "(no answer)"));
        sessionRef.current?.answer(answer || "(no answer — use your judgment)");
        return;
      }
      if (key.backspace || key.delete) { setInput((s) => s.slice(0, -1)); return; }
      if (ch && !key.ctrl && !key.meta && !key.escape) setInput((s) => s + ch);
      return;
    }
    if (busy) {
      if (key.escape && clientRef.current && sessionId) {
        void clientRef.current.interrupt(sessionId);
        return;
      }
      // Steering: type while the agent works; Enter queues the nudge.
      if (key.return) {
        const steer = input.trim();
        setInput("");
        if (steer) sessionRef.current?.steer(steer);
        return;
      }
      if (key.backspace || key.delete) { setInput((s) => s.slice(0, -1)); return; }
      if (ch && !key.ctrl && !key.meta && !key.escape) setInput((s) => s + ch);
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
      ) : picker ? (
        <Box flexDirection="column" marginTop={1}>
          <Box borderStyle="round" borderColor={theme.accent} paddingX={1} flexDirection="column">
            <Text color={theme.accent} bold>
              ↺ Resume a session
            </Text>
            {picker.map((m, i) => (
              <Text key={m.id} color={i === pickerIndex ? theme.brand : theme.dim} bold={i === pickerIndex}>
                {i === pickerIndex ? "▸ " : "  "}
                {i + 1}. {m.created_at.slice(0, 16).replace("T", " ")} · {m.title}
              </Text>
            ))}
          </Box>
          <Text color={theme.dim} dimColor>
            {"  "}↑/↓ or 1-9 select · enter resume · esc cancel
          </Text>
        </Box>
      ) : question ? (
        <Box flexDirection="column" marginTop={1}>
          <Box borderStyle="round" borderColor={theme.accent} paddingX={1} flexDirection="column">
            <Text color={theme.accent} bold>
              ❓ {question}
            </Text>
            <Text>
              <Text color={theme.accent} bold>{"❯ "}</Text>
              {input}
              <Text color={theme.brand}>█</Text>
            </Text>
          </Box>
          <Text color={theme.dim} dimColor>
            {"  "}enter to answer
          </Text>
        </Box>
      ) : busy ? (
        <Box flexDirection="column" marginTop={1}>
          {plan.length ? (
            <Box flexDirection="column" marginBottom={1} borderStyle="round" borderColor={theme.border} paddingX={1}>
              <Text color={theme.dim} bold>Plan</Text>
              {plan.map((it) => (
                <Text key={it.id} color={it.status === "active" ? theme.brand : theme.dim}>
                  {it.status === "done" ? "✓ " : it.status === "active" ? "▸ " : it.status === "skipped" ? "⊘ " : "○ "}
                  {it.title}
                </Text>
              ))}
            </Box>
          ) : null}
          {stream ? (
            <Box flexDirection="column" marginBottom={1}>
              <Markdown source={stream} />
            </Box>
          ) : null}
          <Box>
          <Text color={theme.brand} bold>
            {HEARTBEAT[frame % HEARTBEAT.length]} {SPARKLE[frame % SPARKLE.length]}{" "}
          </Text>
          <Text color={theme.dim}>
            working · {elapsed}s · {stepCount} step{stepCount === 1 ? "" : "s"}{tokens ? ` · ${tokens.toLocaleString()} tok` : ""}{saved ? ` · ↓${saved.toLocaleString()} saved` : ""}
            {"  "}
          </Text>
          <Text color={theme.dim} dimColor>
            esc interrupt · type+enter to steer
          </Text>
          </Box>
          {input ? (
            <Text color={theme.user}>
              {"  ↪ "}
              {input}
              <Text color={theme.brand}>█</Text>
            </Text>
          ) : null}
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
          {"  "}
          {input.startsWith("/")
            ? "/help · /resume · /theme · /model · /sessions · /new · /quit"
            : "enter to send · / for commands · ctrl+c to quit"}
        </Text>
      )}
    </Box>
  );
}

const VERSION = "0.1.0";

const HELP = `mist-ts ${VERSION} — Mist coding agent (Bun engine)

Usage:
  mist-ts                     interactive session (new)
  mist-ts "task"              one-shot: run the task and exit
  mist-ts -c | --continue     resume the latest session for this directory
  mist-ts -r <id> | --resume  resume a specific session (id prefix ok)
  mist-ts --sessions          list saved sessions for this directory
  mist-ts --help | --version

While the agent works: type + Enter to steer it; Esc interrupts; Ctrl+C quits.
Config: ~/.mist/mist.cfg (model), ~/.mist/extra_models.json (endpoints),
.mist/hooks.json (project intent + tool guardrails), MIST_HEADROOM=1 (token
compression).`;

async function main(): Promise<void> {
  await loadPersistedTheme();
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    console.log(HELP);
    return;
  }
  if (args.includes("--version") || args.includes("-v")) {
    console.log(VERSION);
    return;
  }
  const store = new SessionStore(process.cwd());
  if (args.includes("--sessions")) {
    const sessions = await store.list();
    if (!sessions.length) console.log("(no saved sessions for this directory)");
    for (const s of sessions) {
      console.log(`${s.id.slice(0, 8)}  ${s.created_at.slice(0, 16).replace("T", " ")}  ${s.title}`);
    }
    return;
  }

  let resume: StoredSession | undefined;
  const rest: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === "-c" || a === "--continue") {
      const latest = await store.latest();
      if (!latest) {
        console.log("no session to continue in this directory — starting fresh");
      } else {
        resume = (await store.load(latest.id)) ?? undefined;
      }
    } else if (a === "-r" || a === "--resume") {
      const idArg = args[++i];
      if (!idArg) {
        console.error("--resume needs a session id (see --sessions)");
        process.exit(1);
      }
      const match = (await store.list()).find((s) => s.id.startsWith(idArg));
      if (!match) {
        console.error(`no session matching '${idArg}' (see --sessions)`);
        process.exit(1);
      }
      resume = (await store.load(match.id)) ?? undefined;
    } else {
      rest.push(a);
    }
  }
  const argvPrompt = rest.join(" ").trim();
  render(<App initialPrompt={argvPrompt || undefined} resume={resume} />);
}

void main();

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
import { labelForGroup } from "./steps";
import { pickVerb } from "./spinnerVerbs";
import type { VerbContext } from "./spinnerVerbs";
import { Markdown } from "./markdown";
import { SPARKLE, THEMES, applyTheme, loadPersistedTheme, persistTheme, rampColor, theme } from "./theme";

type Item =
  | { id: number; kind: "user"; text: string }
  | { id: number; kind: "step"; text: string }
  | { id: number; kind: "info"; text: string }
  | { id: number; kind: "error"; text: string }
  | { id: number; kind: "response"; text: string }
  | { id: number; kind: "narration"; text: string }
  | { id: number; kind: "toolblock"; label: string; preview: string[]; hiddenLines: number }
  | {
      id: number;
      kind: "diff";
      path: string;
      action: "update" | "create";
      added: number;
      removed: number;
      lines: { type: "add" | "del"; line: number; text: string }[];
      truncated: boolean;
    };

let nextId = 1;
const item = (kind: "user" | "step" | "info" | "error" | "response" | "narration", text: string): Item =>
  ({ id: nextId++, kind, text }) as Item;
const diffItem = (d: Omit<Extract<Item, { kind: "diff" }>, "id" | "kind">): Item =>
  ({ id: nextId++, kind: "diff", ...d }) as Item;
const toolBlockItem = (label: string, preview: string[], hiddenLines: number): Item =>
  ({ id: nextId++, kind: "toolblock", label, preview, hiddenLines }) as Item;

/** Serialize the transcript to shareable markdown (the /record command). */
export function transcriptToMarkdown(items: Item[], sessionId: string): string {
  const out: string[] = [`# Mist session ${sessionId.slice(0, 8)}`, ""];
  for (const it of items) {
    switch (it.kind) {
      case "user":
        out.push(`## \u276f ${it.text}`, "");
        break;
      case "narration":
      case "response":
        out.push(it.text, "");
        break;
      case "toolblock": {
        const body = [it.label, ...it.preview];
        if (it.hiddenLines) body.push(`\u2026 +${it.hiddenLines} lines`);
        out.push("```", ...body, "```", "");
        break;
      }
      case "diff":
        out.push(
          `**${it.action === "create" ? "Create" : "Update"}: ${it.path}** (+${it.added}/-${it.removed})`,
          "```diff",
          ...it.lines.map((l) => `${l.type === "add" ? "+" : "-"} ${l.text}`),
          "```",
          "",
        );
        break;
      case "step":
      case "info":
        out.push(`> ${it.text}`, "");
        break;
      case "error":
        out.push(`> \u26a0\ufe0f ${it.text}`, "");
        break;
    }
  }
  return out.filter((l, i, a) => !(l === "" && a[i - 1] === "")).join("\n");
}

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
    case "toolblock":
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color={theme.success}>● </Text>
            <Text bold>shell</Text>
            <Text color={theme.dim}>(</Text>
            <Text color={theme.code}>{it.label.length > 100 ? `${it.label.slice(0, 99)}…` : it.label}</Text>
            <Text color={theme.dim}>)</Text>
          </Text>
          {it.preview.map((l, i) => (
            <Text key={`tb${it.id}-${i}`} color={theme.dim}>
              {"  ⌙ "}
              {l}
            </Text>
          ))}
          {it.hiddenLines > 0 ? (
            <Text color={theme.dim} dimColor>
              {"    … +"}
              {it.hiddenLines} line{it.hiddenLines === 1 ? "" : "s"} (/steps to expand)
            </Text>
          ) : null}
        </Box>
      );
    case "narration":
      return (
        <Box flexDirection="row" marginTop={1}>
          <Text color={theme.accent}>● </Text>
          <Box flexDirection="column" flexGrow={1}>
            <Markdown source={it.text} />
          </Box>
        </Box>
      );
    case "diff":
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color={theme.success}>● </Text>
            <Text bold>{it.action === "create" ? "Create" : "Update"}(</Text>
            <Text color={theme.path}>{it.path}</Text>
            <Text bold>)</Text>
          </Text>
          <Text color={theme.dim}>
            {"  "}Added {it.added} line{it.added === 1 ? "" : "s"}
            {it.removed ? `, removed ${it.removed} line${it.removed === 1 ? "" : "s"}` : ""}
          </Text>
          {it.lines.map((l, i) => (
            <Text key={`dl${it.id}-${i}`} backgroundColor={l.type === "add" ? "#12351a" : "#3a1518"}>
              <Text color={theme.dim}>{String(l.line).padStart(5)} </Text>
              <Text color={l.type === "add" ? "#7ddf8a" : "#ff8f8f"}>{l.type === "add" ? "+ " : "- "}{l.text}</Text>
            </Text>
          ))}
          {it.truncated ? (
            <Text color={theme.dim} dimColor>{"      …diff truncated"}</Text>
          ) : null}
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
  const startedAtRef = useRef<number | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [engine] = useState(process.env.MIST_ENGINE === "python" ? "engine: python" : "engine: bun");
  const [stream, setStream] = useState("");
  const [tokens, setTokens] = useState(0);
  const [plan, setPlan] = useState<{ id: string; title: string; status: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [saved, setSaved] = useState(0);
  const [, setThemeTick] = useState(0);
  const [picker, setPicker] = useState<SessionMeta[] | null>(null);
  // Generic modal menu (help browser, theme/model choosers): ↑/↓ + Enter,
  // Esc closes, 1-9 quick-select. `action` is a slash-command line to run.
  const [menu, setMenu] = useState<{
    title: string;
    rows: { label: string; desc?: string; action: string }[];
  } | null>(null);
  const [menuIndex, setMenuIndex] = useState(0);
  const [planVisible, setPlanVisible] = useState(true);
  // Input history (↑/↓ recall, shell-style), persisted across sessions.
  const historyRef = useRef<string[]>([]);
  const histIndex = useRef<number | null>(null);
  const draftRef = useRef("");
  const [recentSteps, setRecentSteps] = useState<string[]>([]);
  const [narration, setNarration] = useState("");
  const [verb, setVerb] = useState("Working");
  const verbContext = useRef<VerbContext>("general");

  const noteActivity = useCallback((label: string) => {
    const next: VerbContext = label.startsWith("$")
      ? "shell"
      : label.startsWith("edited") || label.startsWith("created")
        ? "edit"
        : label.startsWith("read") || label.startsWith("listed") || label.startsWith("grep")
          ? "study"
          : "general";
    if (next !== verbContext.current) {
      verbContext.current = next;
      setVerb((v) => pickVerb(v, next)); // switch flavor with the work
    }
  }, []);
  const stepLog = useRef<string[]>([]);
  const lastStepLog = useRef<string[]>([]);
  const stepGroup = useRef<string[]>([]);
  const [pickerIndex, setPickerIndex] = useState(0);
  const sessionRef = useRef<EngineSession | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [fatal, setFatal] = useState("");
  const clientRef = useRef<MistClient | null>(null);
  const headless = Boolean(initialPrompt);
  const idleExitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const push = useCallback((...xs: Item[]) => setItems((p) => [...p, ...xs]), []);

  // Steps show live (rolling last 3) while working, then collapse to one
  // summary line in the transcript — codex-style granularity. /steps expands.
  const addStep = useCallback((label: string) => {
    noteActivity(label);
    setStepCount((n) => n + 1);
    stepLog.current.push(label);
    setRecentSteps([...stepLog.current.slice(-3)]);
    // Hook blocks are exceptions — they must survive in the transcript.
    if (label.includes("blocked by hook")) push(item("error", label));
  }, [noteActivity, push]);

  /** Collapse the pending tool group into one dim "Ran N …" line. */
  const flushStepGroup = useCallback(() => {
    if (!stepGroup.current.length) return;
    push(item("info", labelForGroup(stepGroup.current)));
    stepGroup.current = [];
    setRecentSteps([]);
  }, [push]);

  // Rotate the whimsical verb every ~10s while working.
  useEffect(() => {
    if (!busy) return;
    const id = setInterval(() => setVerb((v) => pickVerb(v, verbContext.current)), 10_000);
    return () => clearInterval(id);
  }, [busy]);

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
          verbContext.current = "general";
          setVerb((v) => pickVerb(v, "general"));
          setBusy(true);
          setStartedAt(Date.now());
          startedAtRef.current = Date.now();
          setStepCount(0);
          stepLog.current = [];
          setRecentSteps([]);
          setNarration("");
          break;
        case "shell_start":
          addStep(ev.command.length > 90 ? `${ev.command.slice(0, 89)}…` : ev.command);
          break;
        case "file_read":
          addStep(`read ${ev.path}`);
          break;
        case "file_diff":
          addStep(`edited ${ev.path}`);
          break;
        case "grep_result":
          addStep(`grep — ${ev.totalMatches} matches`);
          break;
        case "subagent_invocation":
          addStep(`delegated to ${ev.agentName}`);
          break;
        case "text_delta":
          setStream((t) => t + ev.delta);
          break;
        case "toolblock":
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color={theme.success}>● </Text>
            <Text bold>shell</Text>
            <Text color={theme.dim}>(</Text>
            <Text color={theme.code}>{it.label.length > 100 ? `${it.label.slice(0, 99)}…` : it.label}</Text>
            <Text color={theme.dim}>)</Text>
          </Text>
          {it.preview.map((l, i) => (
            <Text key={`tb${it.id}-${i}`} color={theme.dim}>
              {"  ⌙ "}
              {l}
            </Text>
          ))}
          {it.hiddenLines > 0 ? (
            <Text color={theme.dim} dimColor>
              {"    … +"}
              {it.hiddenLines} line{it.hiddenLines === 1 ? "" : "s"} (/steps to expand)
            </Text>
          ) : null}
        </Box>
      );
        case "step_done": {
          if (ev.label.startsWith("$")) {
            flushStepGroup();
            push(toolBlockItem(ev.label, ev.preview, ev.hiddenLines));
          } else if (!ev.label.startsWith("edited") && !ev.label.startsWith("created")) {
            stepGroup.current.push(ev.label); // quiet ops collapse to Ran-N
          }
          break;
        }
        case "thought":
          push(item("info", `Thought for ${Math.max(1, Math.round(ev.ms / 1000))}s`));
          break;
        case "narration": {
          flushStepGroup();
          if (ev.text.trim()) push(item("narration", ev.text.trim()));
          setStream("");
          setNarration("");
          break;
        }
        case "step":
          addStep(ev.label);
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
        case "file_edited":
          push(diffItem({ path: ev.path, action: ev.action, added: ev.added, removed: ev.removed, lines: ev.lines, truncated: ev.truncated }));
          break;
        case "context_compacted":
          push(item("info",
            ev.summarized
              ? `⇣ compacted: ${ev.beforeTokens.toLocaleString()} → ${ev.afterTokens.toLocaleString()} tok (${ev.summarized} messages summarized)`
              : "⇣ nothing to compact yet",
          ));
          break;
        case "headroom_saved":
          setSaved((t) => t + ev.tokensSaved);
          break;
        case "agent_response":
          setStream("");
          setNarration("");
          if (ev.content.trim()) push(item("response", ev.content));
          break;
        case "session_error":
          push(item("error", ev.error));
          break;
        case "session_idle":
        case "session_interrupted":
          flushStepGroup();
          if (stepLog.current.length) {
            lastStepLog.current = [...stepLog.current];
            stepLog.current = [];
          }
          setRecentSteps([]);
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
    [addStep, exit, flushStepGroup, headless, push],
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
            startedAtRef.current = Date.now();
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
        case "help": {
          setMenuIndex(0);
          setMenu({
            title: "Help — commands (↑/↓ · enter run · esc close)",
            rows: [
              { label: "/resume", desc: "pick a previous session to resume", action: "/resume" },
              { label: "/sessions", desc: "list saved sessions for this directory", action: "/sessions" },
              { label: "/new", desc: "start a fresh conversation (alias /clear)", action: "/new" },
              { label: "/compact", desc: "summarize older context to free tokens", action: "/compact" },
              { label: "/steps", desc: "expand the last turn's collapsed tool calls", action: "/steps" },
              { label: "/theme", desc: "switch themes — opens a chooser", action: "/theme" },
              { label: "/model", desc: "switch the model — opens a chooser", action: "/model" },
              { label: "/tools", desc: "list the agent's tools", action: "/tools" },
              { label: "/status", desc: "session, model, context tokens, theme, cwd", action: "/status" },
              { label: "/record", desc: "export the session transcript to markdown", action: "/record" },
              { label: "/dump_context", desc: "write conversation history to /tmp", action: "/dump_context" },
              { label: "/quit", desc: "leave mist-ts (aliases /exit, /q)", action: "/quit" },
            ],
          });
          say("keys: Enter send · type+Enter while busy = steer · Esc interrupt · ctrl+t toggle tasks · ↑/↓ history");
          say("flags: -c continue · -r <id> resume · --sessions · --help  |  env: MIST_HEADROOM=1 · MIST_COMPACT_AT · MIST_MODEL");
          break;
        }
        case "theme": {
          if (!arg) {
            setMenuIndex(0);
            setMenu({
              title: "Choose a theme (↑/↓ · enter apply · esc close)",
              rows: Object.keys(THEMES).map((name) => ({
                label: name === theme.name ? `${name} (current)` : name,
                action: `/theme ${name}`,
              })),
            });
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
            setMenuIndex(0);
            setMenu({
              title: "Choose a model (↑/↓ · enter apply · esc close)",
              rows: names.slice(0, 15).map((name) => ({
                label: name === current ? `${name} (current)` : name,
                action: `/model ${name}`,
              })),
            });
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
        case "compact": {
          say("compacting…");
          await sessionRef.current?.compact();
          break;
        }
        case "steps": {
          if (!lastStepLog.current.length) {
            say("(no tool calls recorded for the last turn)");
            break;
          }
          for (const label of lastStepLog.current) say(`✓ ${label}`);
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
          const ctxTok = sessionRef.current ? sessionRef.current.contextTokens() : 0;
          say(`session ${sessionId.slice(0, 8)} · model ${model} · ${hist} messages · ~${ctxTok.toLocaleString()} tok in context · ${tokens.toLocaleString()} tok this run${saved ? ` · ↓${saved} saved` : ""}`);
          say(`theme ${theme.name} · cwd ${process.cwd()}`);
          break;
        }
        case "record":
        case "export": {
          const file = arg || `mist-session-${sessionId.slice(0, 8)}.md`;
          const md = transcriptToMarkdown(items, sessionId);
          await Bun.write(file, md);
          say(`transcript (${items.length} entries) \u2192 ${file}`);
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
    [exit, handleEnvelope, items, push, saved, sessionId, tokens],
  );

  const submit = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || busy) return;
    if (prompt.startsWith("/")) {
      setInput("");
      recordHistory(prompt);
      push(item("user", prompt));
      await runCommand(prompt);
      return;
    }
    if (!clientRef.current || !sessionId) return;
    setInput("");
    recordHistory(prompt);
    push(item("user", prompt));
    setBusy(true);
    setStartedAt(Date.now());
    startedAtRef.current = Date.now();
    try {
      await clientRef.current.submit(sessionId, prompt);
    } catch (err) {
      push(item("error", (err as Error).message));
      setBusy(false);
    }
  }, [busy, input, push, runCommand, sessionId]);

  // Load persisted input history once.
  useEffect(() => {
    (async () => {
      try {
        const path = process.env.MIST_TS_HISTORY ?? `${process.env.HOME}/.mist/ts-history`;
        const text = await Bun.file(path).text();
        historyRef.current = text.split("\n").filter((l) => l.trim()).slice(-1000);
      } catch {
        /* no history yet */
      }
    })();
  }, []);

  const recordHistory = useCallback((entry: string) => {
    const trimmed = entry.trim();
    if (!trimmed) return;
    const hist = historyRef.current;
    if (hist[hist.length - 1] !== trimmed) hist.push(trimmed);
    if (hist.length > 1000) historyRef.current = hist.slice(-1000);
    histIndex.current = null;
    const path = process.env.MIST_TS_HISTORY ?? `${process.env.HOME}/.mist/ts-history`;
    void Bun.write(path, historyRef.current.join("\n") + "\n").catch(() => {});
  }, []);

  /** ↑/↓ history navigation. Returns true if the key was consumed. */
  const historyNav = useCallback(
    (key: { upArrow: boolean; downArrow: boolean }): boolean => {
      const hist = historyRef.current;
      if (key.upArrow) {
        if (!hist.length) return true;
        if (histIndex.current === null) {
          draftRef.current = "";
          histIndex.current = hist.length - 1;
        } else if (histIndex.current > 0) {
          histIndex.current -= 1;
        }
        setInput(hist[histIndex.current] ?? "");
        return true;
      }
      if (key.downArrow) {
        if (histIndex.current === null) return true;
        histIndex.current += 1;
        if (histIndex.current > hist.length - 1) {
          histIndex.current = null;
          setInput(draftRef.current);
        } else {
          setInput(hist[histIndex.current] ?? "");
        }
        return true;
      }
      return false;
    },
    [],
  );

  useInput((ch, key) => {
    if (key.ctrl && ch === "c") exit();
    if (key.ctrl && ch === "t") {
      setPlanVisible((v) => !v);
      return;
    }
    if (menu) {
      if (key.escape) {
        setMenu(null);
        return;
      }
      if (key.upArrow) {
        setMenuIndex((i) => (i - 1 + menu.rows.length) % menu.rows.length);
        return;
      }
      if (key.downArrow) {
        setMenuIndex((i) => (i + 1) % menu.rows.length);
        return;
      }
      const digit = ch >= "1" && ch <= "9" ? Number(ch) - 1 : -1;
      if (key.return || (digit >= 0 && digit < menu.rows.length)) {
        const row = menu.rows[key.return ? menuIndex : digit];
        setMenu(null);
        if (row) void runCommand(row.action);
        return;
      }
      return;
    }
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
      if (historyNav(key)) return;
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
      if (historyNav(key)) return;
      if (key.return) {
        const steer = input.trim();
        setInput("");
        if (steer) {
          recordHistory(steer);
          sessionRef.current?.steer(steer);
        }
        return;
      }
      if (key.backspace || key.delete) { setInput((s) => s.slice(0, -1)); return; }
      if (ch && !key.ctrl && !key.meta && !key.escape) setInput((s) => s + ch);
      return;
    }
    if (historyNav(key)) return;
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
    if (ch && !key.ctrl && !key.meta && !key.escape) {
      histIndex.current = null;
      setInput((s) => {
        const next = s + ch;
        draftRef.current = next;
        return next;
      });
    }
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
      ) : menu ? (
        <Box flexDirection="column" marginTop={1}>
          <Box borderStyle="round" borderColor={theme.accent} paddingX={1} flexDirection="column">
            <Text color={theme.accent} bold>
              {menu.title}
            </Text>
            {menu.rows.map((row, i) => (
              <Box key={row.action} flexDirection="column">
                <Text color={i === menuIndex ? theme.brand : theme.text} bold={i === menuIndex}>
                  {i === menuIndex ? "❯ " : "  "}
                  {row.label}
                </Text>
                {row.desc ? (
                  <Text color={theme.dim}>
                    {"    "}
                    {row.desc}
                  </Text>
                ) : null}
              </Box>
            ))}
          </Box>
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
          {plan.length && planVisible ? (
            <Box flexDirection="column" marginBottom={1} paddingLeft={1}>
              {plan.map((it, i) => (
                <Text
                  key={it.id}
                  color={it.status === "active" ? theme.brand : theme.dim}
                  bold={it.status === "active"}
                  strikethrough={it.status === "skipped"}
                  dimColor={it.status === "done"}
                >
                  {"⌙ "}
                  {it.status === "done" ? "☑" : it.status === "skipped" ? "☒" : "☐"}
                  {" #"}
                  {i + 1} {it.title}
                </Text>
              ))}
            </Box>
          ) : null}
          {recentSteps.length ? (
            <Box flexDirection="column" marginBottom={0}>
              {recentSteps.map((label, i) => (
                <Text key={`rs${i}`} color={theme.dim} dimColor={i < recentSteps.length - 1}>
                  {"  "}
                  <Text color={theme.success}>✓</Text> {label}
                </Text>
              ))}
            </Box>
          ) : null}
          {narration && !stream ? (
            <Text color={theme.dim} italic>
              {"  ⋯ "}
              {narration}
            </Text>
          ) : null}
          {stream ? (
            <Text color={theme.dim} italic>
              {"  ⋯ "}
              {(() => {
                const lines = stream.split("\n").filter((l) => l.trim());
                const tail = lines[lines.length - 1] ?? "";
                return tail.length > 110 ? `${tail.slice(0, 109)}…` : tail;
              })()}
            </Text>
          ) : null}
          <Box>
          <Text color={theme.brand} bold>
            {SPARKLE[frame % SPARKLE.length]}{" "}
          </Text>
          <Text color={theme.dim}>
            {verb}… · {elapsed}s · {stepCount} step{stepCount === 1 ? "" : "s"}{tokens ? ` · ${tokens.toLocaleString()} tok` : ""}{saved ? ` · ↓${saved.toLocaleString()} saved` : ""}
            {"  "}
          </Text>
          <Text color={theme.dim} dimColor>
            esc interrupt · type+enter to steer{plan.length ? ` · ctrl+t to ${planVisible ? "hide" : "show"} tasks` : ""}
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

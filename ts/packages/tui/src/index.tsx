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
import { EngineSession, INIT_PROMPT, SessionStore, getConfiguredModelName, getModelDef, lensTotals, listModelNames, persistModelChoice, renderLensHtml } from "@mist/core";
import { readConfig, getConfig, setConfig, SETTING_DEFS } from "@mist/core";
import type { ChatMessage, SessionMeta, StoredSession } from "@mist/core";
import { MistClient } from "./client";
import { labelForGroup } from "./steps";
import { pickVerb } from "./spinnerVerbs";
import type { VerbContext } from "./spinnerVerbs";
import { Markdown } from "./markdown";
import { Mascot } from "./mascot";
import { SPINNERS } from "./spinners";
import type { Spinner } from "./spinners";
import { THEMES, applyTheme, loadPersistedTheme, persistTheme, rampColor, theme } from "./theme";
import { useReadline } from "./readline";
import { completionsFor, isShellPassthrough, shellCommand, type Suggestion } from "./completions";

/** Canonical slash-command list — drives Tab completion and the /help rows. */
const COMMAND_NAMES = [
  "help", "theme", "model", "resume", "sessions", "rename", "new", "clear",
  "compact", "steps", "tools", "status", "record", "export", "dump_context",
  "quit", "exit", "q", "set", "show", "cd", "reasoning", "verbosity",
  "pop", "prune", "truncate", "mcp", "lens",
];

type Item =
  | { id: number; kind: "user"; text: string }
  | { id: number; kind: "step"; text: string }
  | { id: number; kind: "info"; text: string }
  | { id: number; kind: "error"; text: string }
  | { id: number; kind: "response"; text: string }
  | { id: number; kind: "narration"; text: string }
  | { id: number; kind: "toolblock"; label: string; preview: string[]; hiddenLines: number; tool?: string }
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
const toolBlockItem = (label: string, preview: string[], hiddenLines: number, tool = "shell"): Item =>
  ({ id: nextId++, kind: "toolblock", label, preview, hiddenLines, tool }) as Item;

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

/**
 * Condensed replay of the last few exchanges for session resume: user prompts
 * and assistant text verbatim, tool activity collapsed to one dim count line.
 * Steer prefixes are stripped; auto-continue nudges and compaction summaries
 * are engine plumbing and stay hidden.
 */
export function historyTailItems(messages: ChatMessage[], maxTurns = 3): Item[] {
  const out: Item[] = [];
  let userTurns = 0;
  let skippedTools = 0;
  const flushToolCount = () => {
    if (skippedTools > 0) {
      out.push(item("info", `⋯ ran ${skippedTools} tool call${skippedTools === 1 ? "" : "s"}`));
      skippedTools = 0;
    }
  };
  for (let i = messages.length - 1; i >= 0 && userTurns < maxTurns; i--) {
    const m = messages[i]!;
    if (m.role === "user") {
      // tool_result carriers: the calls are counted from the tool_use side.
      if (typeof m.content !== "string") continue;
      if (m.content.startsWith("[auto-continue]") || m.content.startsWith("[conversation summary")) continue;
      flushToolCount();
      out.push(item("user", m.content.replace(/^\[steer[^\]]*\]\s*/, "")));
      userTurns += 1;
    } else {
      const blocks = Array.isArray(m.content) ? m.content : [];
      const text =
        typeof m.content === "string"
          ? m.content
          : blocks.filter((b) => b.type === "text").map((b) => (b as { text: string }).text).join("");
      const toolCount = blocks.filter((b) => b.type === "tool_use").length;
      skippedTools += toolCount;
      if (text.trim()) {
        flushToolCount();
        // Text alongside tool calls was live-rendered as ● narration.
        out.push(item(toolCount > 0 ? "narration" : "response", text));
      }
    }
  }
  if (out.length === 0) return [];
  flushToolCount();
  out.push(item("info", "— earlier in this session —"));
  return out.reverse();
}

function Wordmark() {
  const word = "Mist";
  return (
    <Text>
      <Text color={theme.accent}>◆ </Text>
      {[...word].map((ch, i) => (
        <Text key={`b${i}`} bold color={rampColor(i, word.length)}>
          {ch}
        </Text>
      ))}
    </Text>
  );
}

function Brand({ engine, session }: { engine: string; session: string }) {
  return (
    <Box flexDirection="row" marginBottom={1}>
      <Text>
        <Wordmark />
        <Text color={theme.dim}> — coding agent · </Text>
        <Text color={theme.dim}>
          {session ? `session ${session.slice(0, 8)} · ` : ""}
          {engine}
        </Text>
      </Text>
    </Box>
  );
}

export interface BannerInfo {
  model: string;
  latestTitle: string | null;
}

/**
 * Input box with the session name embedded in the top border, right-aligned —
 * Claude-Code style:  ╭──────────── session-name ──╮
 */
function InputFrame({ title, marginTop = 0, children }: { title: string; marginTop?: number; children: React.ReactNode }) {
  const w = Math.max(24, (process.stdout.columns ?? 80) - 2);
  const label = title ? ` ${title.length > 32 ? `${title.slice(0, 31)}…` : title} ` : "";
  const left = Math.max(0, w - 2 - label.length - (label ? 2 : 0));
  return (
    <Box flexDirection="column" marginTop={marginTop} width={w}>
      <Text color={theme.border}>
        ╭{"─".repeat(left)}
        {label ? <Text color={theme.accent}>{label}</Text> : null}
        {label ? "──" : ""}╮
      </Text>
      <Box
        borderStyle="round"
        borderColor={theme.border}
        borderTop={false}
        paddingX={1}
        flexDirection="row"
        width={w}
      >
        {children}
      </Box>
    </Box>
  );
}

/** Claude-Code-style welcome banner: Misty + session facts + tips. */
function Banner({ session, info }: { session: string; info: BannerInfo }) {
  const rawUser = process.env.USER || process.env.USERNAME || "friend";
  const user = rawUser.charAt(0).toUpperCase() + rawUser.slice(1);
  const home = process.env.HOME ?? "";
  const cwdFull = home && process.cwd().startsWith(home) ? process.cwd().replace(home, "~") : process.cwd();
  const cwd = cwdFull.length > 52 ? `…${cwdFull.slice(-51)}` : cwdFull;
  const cols = process.stdout.columns ?? 80;
  const wide = cols >= 92;
  const boxWidth = Math.min(cols - 2, 96);
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box width={boxWidth} borderStyle="round" borderColor={theme.border} flexDirection="row" paddingX={2}>
        <Box flexDirection="column" flexGrow={1}>
          <Text>
            <Wordmark />
            <Text color={theme.dim}> v{VERSION}</Text>
          </Text>
          <Box flexDirection="column" alignItems="center">
            <Text bold color={theme.text}>
              Welcome back, {user}!
            </Text>
            <Box marginTop={1}>
              <Mascot />
            </Box>
            <Box marginTop={1}>
              <Text color={theme.dim}>
                {info.model}
                {session ? ` · session ${session.slice(0, 8)}` : ""}
              </Text>
            </Box>
            <Text color={theme.dim}>{cwd}</Text>
          </Box>
        </Box>
        {wide ? (
          <Box flexDirection="column" marginLeft={2} paddingLeft={2} width={34} flexShrink={0} borderStyle="single" borderColor={theme.border} borderTop={false} borderBottom={false} borderRight={false}>
            <Text bold color={theme.accent}>
              Tips for getting started
            </Text>
            <Text color={theme.dim}>/help — browse every command</Text>
            <Text color={theme.dim}>/theme — pick a breathing style</Text>
            <Text color={theme.dim}>type while it works to steer</Text>
            <Box marginTop={1} flexDirection="column">
              <Text bold color={theme.accent}>
                Recent activity
              </Text>
              {info.latestTitle ? (
                <>
                  <Text color={theme.dim}>{info.latestTitle.length > 30 ? `${info.latestTitle.slice(0, 29)}…` : info.latestTitle}</Text>
                  <Text color={theme.dim}>resume it with /resume</Text>
                </>
              ) : (
                <Text color={theme.dim}>No recent activity</Text>
              )}
            </Box>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

function TranscriptItem({ it }: { it: Item }) {
  switch (it.kind) {
    case "user":
      return (
        <Box marginTop={1}>
          <Text bold color={theme.user} backgroundColor={theme.userBg}>
            {" ❯ "}
            {it.text}
            {" "}
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
      // Explicit width: nested inline <Text> (bold/code spans) can defeat
      // Ink's wrap measurement inside <Static>, hard-wrapping mid-word at the
      // terminal edge (the 'compil/e' artifact) — pin the column like narration.
      return (
        <Box flexDirection="column" marginTop={1} width={Math.max(20, (process.stdout.columns ?? 80) - 3)}>
          <Markdown source={it.text} />
        </Box>
      );
    case "toolblock":
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color={theme.success}>● </Text>
            <Text bold>{it.tool ?? "shell"}</Text>
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
      // Explicit width: inside <Static>, a flexGrow child next to the ● can
      // overflow the terminal and hard-wrap at column 0 — pin the text column.
      return (
        <Box flexDirection="row" marginTop={1}>
          <Text color={theme.accent}>● </Text>
          <Box flexDirection="column" width={Math.max(20, (process.stdout.columns ?? 80) - 5)}>
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

function App({ initialPrompt, resume, banner }: { initialPrompt?: string; resume?: StoredSession; banner?: BannerInfo }) {
  const { exit } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  // Completion popup: candidates + the anchor/tail of the token being
  // completed, captured at first Tab so cycling replaces the right span.
  const [suggestions, setSuggestions] = useState<{
    list: Suggestion[];
    index: number;
    anchor: number;
    tail: string;
  } | null>(null);
  const [frame, setFrame] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [engine] = useState(process.env.MIST_ENGINE === "python" ? "engine: python" : "engine: bun");
  const [stream, setStream] = useState("");
  const [tokens, setTokens] = useState(0);
  // Live context size = the LAST request's real prompt tokens (what the
  // model actually holds), vs cumulative `tokens` which re-bills the whole
  // history every request and balloons misleadingly while working.
  const [ctxTokens, setCtxTokens] = useState(0);
  const [ctxLimit, setCtxLimit] = useState(0);
  const [plan, setPlan] = useState<{ id: string; title: string; status: string }[]>([]);
  // Clarifying question (ask_user): optional arrow-key options + free text.
  const [question, setQuestion] = useState<{ text: string; options: string[] } | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [questionCustom, setQuestionCustom] = useState(false);
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
  // Glyph set follows the verb context — a distinctive spinner per activity
  // (scan while reading, fillsweep while editing, cascade while executing).
  const [spinner, setSpinner] = useState<Spinner>(SPINNERS.general);

  // Cursor-aware input line for idle mode (replaces append-only setInput).
  // Gives us Ctrl+A/E/K/U/W, ←/→, Alt+B/F word jumps, Ctrl+R reverse search,
  // Alt+M/Ctrl+J multiline, and ↑/↓ history with draft preservation.
  // rlValueRef breaks the circular dep between rlHistoryNav (callback) and rl.
  const rlValueRef = useRef("");
  const rlHistoryNav = useCallback((direction: "up" | "down"): string | undefined => {
    const hist = historyRef.current;
    if (direction === "up") {
      if (!hist.length) return undefined;
      if (histIndex.current === null) {
        draftRef.current = rlValueRef.current;
        histIndex.current = hist.length - 1;
      } else if (histIndex.current > 0) {
        histIndex.current -= 1;
      }
      return hist[histIndex.current];
    }
    if (histIndex.current === null) return undefined;
    histIndex.current += 1;
    if (histIndex.current > hist.length - 1) {
      histIndex.current = null;
      return draftRef.current;
    }
    return hist[histIndex.current];
  }, []);
  const rl = useReadline({ onHistoryNav: rlHistoryNav });
  rlValueRef.current = rl.handle.state.value; // keep ref fresh for history nav

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
      setSpinner(SPINNERS[next]);
    }
  }, []);
  const stepLog = useRef<string[]>([]);
  const lastStepLog = useRef<string[]>([]);
  const stepGroup = useRef<string[]>([]);
  const [pickerIndex, setPickerIndex] = useState(0);
  const sessionRef = useRef<EngineSession | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [sessionTitle, setSessionTitle] = useState("");
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

  // Context-window ceiling for the gauge under the input box. Re-resolved
  // when a turn starts so mid-session /model switches are picked up.
  useEffect(() => {
    void (async () => {
      try {
        const def = await getModelDef(await getConfiguredModelName());
        setCtxLimit(def?.context_length ?? 0);
      } catch {
        setCtxLimit(0);
      }
    })();
  }, [busy]);

  // Animation clock at the active spinner's native pace — pacing is part of
  // the character (footer only re-renders the dynamic region — cheap).
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => f + 1), spinner.interval);
    return () => clearInterval(id);
  }, [spinner]);

  const handleEnvelope = useCallback(
    (env: EventEnvelope) => {
      const ev = classifyEvent(env);
      switch (ev.kind) {
        case "session_running":
          verbContext.current = "general";
          setVerb((v) => pickVerb(v, "general"));
          setSpinner(SPINNERS.general);
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
        case "subagent_started": {
          flushStepGroup();
          const brief = ev.task.length > 70 ? `${ev.task.slice(0, 69)}…` : ev.task;
          push(toolBlockItem(brief, [], 0, `◇ subagent “${ev.label}”`));
          break;
        }
        case "subagent_step":
          addStep(`[${ev.label}] ${ev.step}`);
          break;
        case "subagent_done": {
          const lines = ev.report.split("\n").filter((l) => l.trim());
          const preview = lines.slice(0, 2).map((l) => (l.length > 90 ? `${l.slice(0, 89)}…` : l));
          push(
            toolBlockItem(
              `${ev.steps} step${ev.steps === 1 ? "" : "s"}`,
              preview,
              Math.max(0, lines.length - preview.length),
              `◇ ${ev.label} done`,
            ),
          );
          setRecentSteps([]);
          break;
        }
        case "subagent_error":
          push(item("error", `subagent “${ev.label}” failed: ${ev.error}`));
          break;
        case "mcp_status": {
          if (ev.started.length) push(item("info", `⚡ mcp: started ${ev.started.join(", ")}`));
          for (const f of ev.failed) push(item("error", `mcp: ${f}`));
          break;
        }
        case "text_delta":
          setStream((t) => t + ev.delta);
          break;
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
        case "model_retry":
          push(
            item(
              "info",
              `⚠ API error (${ev.reason}) — retrying in ${Math.max(1, Math.round(ev.delayMs / 1000))}s (attempt ${ev.attempt}/${ev.maxAttempts})`,
            ),
          );
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
          setCtxTokens(ev.inputTokens); // latest prompt size = live context
          break;
        case "plan_updated":
          setPlan(ev.items);
          break;
        case "question_asked":
          setQuestion({ text: ev.question, options: ev.options });
          setQuestionIndex(0);
          setQuestionCustom(ev.options.length === 0);
          rl.handle.reset();
          break;
        case "session_resumed":
          setSessionTitle(ev.title);
          push(item("info", `↺ resumed “${ev.title}” · ${ev.messages} messages · started ${ev.createdAt.slice(0, 10)}`));
          setCtxTokens(sessionRef.current?.contextTokens() ?? 0);
          break;
        case "session_renamed":
          setSessionTitle(ev.title);
          push(item("info", ev.auto ? `✎ session named “${ev.title}”` : `✎ session renamed to “${ev.title}”`));
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
          if (ev.afterTokens > 0) setCtxTokens(ev.afterTokens);
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
          // Replay the tail of the conversation BEFORE subscribing so the
          // "↺ resumed" line lands beneath the restored context.
          if (resume) push(...historyTailItems(resume.messages));
          cancel = session.subscribe(handleEnvelope);
          clientRef.current = {
            submit: (_id: string, prompt: string) => session.submit(prompt),
            interrupt: async () => {},
          } as unknown as MistClient;
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
      push(...historyTailItems(stored.messages));
      fresh.subscribe(handleEnvelope);
      clientRef.current = {
        submit: (_id: string, prompt: string) => fresh.submit(prompt),
        interrupt: async () => {},
      } as unknown as MistClient;
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
              { label: "/rename", desc: "name this session (auto-named from your first question otherwise)", action: "/rename" },
              { label: "/init", desc: "explore the repo and draft AGENTS.md (repository guidelines)", action: "/init" },
              { label: "/new", desc: "start a fresh conversation (alias /clear)", action: "/new" },
              { label: "/lens", desc: "explainability: tokens, tools, subagents — /lens html for the diagram", action: "/lens" },
              { label: "/compact", desc: "summarize older context to free tokens", action: "/compact" },
              { label: "/pop", desc: "remove the last turn from history", action: "/pop" },
              { label: "/prune", desc: "keep only the last N turns", action: "/prune" },
              { label: "/truncate", desc: "drop oldest messages to fit a token budget", action: "/truncate" },
              { label: "/set", desc: "adjust config (verbosity, reasoning, temperature, …)", action: "/set" },
              { label: "/show", desc: "show config values from mist.cfg", action: "/show" },
              { label: "/cd", desc: "change working directory", action: "/cd" },
              { label: "/reasoning", desc: "set reasoning effort (off·low·medium·high)", action: "/reasoning" },
              { label: "/verbosity", desc: "set output verbosity (quiet·normal·verbose)", action: "/verbosity" },
              { label: "/mcp", desc: "manage MCP servers (status·start·stop·restart)", action: "/mcp" },
              { label: "/theme", desc: "switch themes — opens a chooser", action: "/theme" },
              { label: "/model", desc: "switch the model — opens a chooser", action: "/model" },
              { label: "/tools", desc: "list the agent's tools", action: "/tools" },
              { label: "/status", desc: "session, model, context tokens, theme, cwd", action: "/status" },
              { label: "/record", desc: "toggle event-trace recording (jsonl, for debugging)", action: "/record" },
              { label: "/export", desc: "export the session transcript to markdown", action: "/export" },
              { label: "/dump_context", desc: "write conversation history to /tmp", action: "/dump_context" },
              { label: "/quit", desc: "leave mist (aliases /exit, /q)", action: "/quit" },
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
          if (list.length) say("resume with: mist -r <id>");
          break;
        }
        case "rename": {
          if (!arg) {
            say("usage: /rename <new name> — names this session in /resume and /sessions");
            break;
          }
          await sessionRef.current?.rename(arg);
          break;
        }
        case "init": {
          // Prompt-sugar, codex-style: submit a canned prompt and let the
          // model explore the repo and write AGENTS.md with ordinary tools
          // (hooks apply like any other write).
          if (!clientRef.current || !sessionId) break;
          say("✎ exploring the repo to draft AGENTS.md (200–400 words, injected into every future session)…");
          setBusy(true);
          setStartedAt(Date.now());
          startedAtRef.current = Date.now();
          try {
            await clientRef.current.submit(sessionId, INIT_PROMPT);
          } catch (err) {
            push(item("error", (err as Error).message));
            setBusy(false);
          }
          break;
        }
        case "lens": {
          const turns = sessionRef.current?.lens() ?? [];
          if (!turns.length) {
            say("(no turns recorded yet — run a prompt first)");
            break;
          }
          const sub = rest[0]?.toLowerCase();
          if (sub === "html") {
            const file = rest[1] || `mist-lens-${sessionId.slice(0, 8)}.html`;
            await Bun.write(file, renderLensHtml(turns, sessionId));
            say(`🔍 interactive lens report (${turns.length} turns) → ${file} — open in a browser`);
            break;
          }
          if (sub === "json") {
            const file = rest[1] || `mist-lens-${sessionId.slice(0, 8)}.json`;
            await Bun.write(file, JSON.stringify(turns, null, 2));
            say(`🔍 full lens ledger → ${file}`);
            break;
          }
          // Default: text summary of the LAST turn.
          const turn = turns[turns.length - 1]!;
          const t = lensTotals(turn);
          say(`🔍 lens — last turn: “${turn.prompt.slice(0, 60)}” (${Math.round(turn.ms / 1000)}s)`);
          say(`tokens: ${t.billedInputTokens.toLocaleString()} input (history×${t.requests} requests) · ${t.outputTokens.toLocaleString()} output (≈${t.estThinkingTokens.toLocaleString()} thinking) · context now ${t.finalContextTokens.toLocaleString()}`);
          if (t.cacheReadTokens || t.cacheWriteTokens) {
            const pct = t.billedInputTokens ? Math.round((t.cacheReadTokens / t.billedInputTokens) * 100) : 0;
            say(`cache: ${t.cacheReadTokens.toLocaleString()} read (~0.1x price) · ${t.cacheWriteTokens.toLocaleString()} written · ${pct}% of input served from cache`);
          } else {
            say(`cache: no activity — endpoint may not support prompt caching (MIST_CACHE=0 disables sending breakpoints)`);
          }
          say(`work: ${t.requests} model requests (${Math.round(t.modelMs / 1000)}s) · ${t.toolCalls} tool calls (${Math.round(t.toolMs / 1000)}s) · ${t.subagents} subagents${t.toolErrors ? ` · ${t.toolErrors} tool errors` : ""}${t.hookBlocks ? ` · ${t.hookBlocks} hook blocks` : ""}`);
          if (turn.hygiene) {
            const h = turn.hygiene;
            const dedupe = `${h.dedupedReads} superseded read${h.dedupedReads === 1 ? "" : "s"} evicted${h.dedupedDeferred ? ` (${h.dedupedDeferred} deferred — deep in warm cache)` : ""}`;
            say(`hygiene: ${dedupe} · ${h.staleDeferred ? `stale-clear deferred` : `${h.staleCleared} stale result${h.staleCleared === 1 ? "" : "s"} cleared`}${h.note ? ` — ${h.note}` : ""}`);
          }
          if (turn.autoContinues || turn.capHit || turn.compactions.length) {
            say(`events: ${[turn.autoContinues ? `⟳ ${turn.autoContinues} auto-continue` : "", turn.capHit ? "⏸ cap hit" : "", ...turn.compactions.map((c) => `⇣ compacted ${c.beforeTokens.toLocaleString()}→${c.afterTokens.toLocaleString()}`)].filter(Boolean).join(" · ")}`);
          }
          // Top token-consuming requests + biggest tool outputs.
          const topReq = [...turn.requests].sort((a, b) => b.outputTokens - a.outputTokens)[0];
          if (topReq) say(`hottest request: #${topReq.index + 1} — out ${topReq.outputTokens.toLocaleString()} tok, ${topReq.toolCalls.length} tools, ${topReq.stopReason}`);
          const allTools = turn.requests.flatMap((r) => r.toolCalls);
          for (const c of [...allTools].sort((a, b) => b.outputChars - a.outputChars).slice(0, 3)) {
            say(`  ${c.isError ? "✗" : "·"} ${c.name}: ${c.label.slice(0, 60)} — ${c.outputChars.toLocaleString()} chars, ${c.ms}ms`);
          }
          for (const s of turn.subagents) {
            say(`  ◇ ${s.label}: ${s.steps} steps · in ${s.inputTokens.toLocaleString()} / out ${s.outputTokens.toLocaleString()} tok · ${Math.round(s.ms / 1000)}s${s.error ? ` · FAILED: ${s.error.slice(0, 60)}` : ""}`);
          }
          say("/lens html → interactive diagram · /lens json → full ledger (all turns, tool outputs)");
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
          say("engine: update_plan (live plan) · ask_user (clarifying questions) · invoke_subagent (parallel delegation, isolated context)");
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
        case "record": {
          const sess = sessionRef.current;
          if (!sess) break;
          if (sess.tracing) {
            const r = sess.stopTrace();
            if (r) say(`\u23f9 trace stopped \u2014 ${r.events} events \u2192 ${r.path}`);
          } else {
            const path = sess.startTrace(arg || undefined);
            say(`\u23fa trace recording \u2192 ${path} (run /record again to stop)`);
          }
          break;
        }
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
        case "set": {
          if (!arg) {
            // Interactive menu: show all settable keys with current values.
            const cfg = await readConfig();
            setMenuIndex(0);
            setMenu({
              title: "/set — adjust a config setting (↑/↓ · enter edit · esc close)",
              rows: SETTING_DEFS.map((s) => ({
                label: `${s.label} = ${cfg[s.key] ?? "(unset)"}`,
                desc: s.desc,
                action: `/set ${s.key}`,
              })),
            });
            break;
          }
          const [setKey, ...setRest] = arg.split(/\s+/);
          const setValue = setRest.join(" ").trim();
          if (!setValue) {
            // Show current value of one key.
            const v = await getConfig(setKey);
            say(v ? `${setKey} = ${v}` : `${setKey} is not set`);
            break;
          }
          const def = SETTING_DEFS.find((s) => s.key === setKey);
          if (def?.validate) {
            const err = def.validate(setValue);
            if (err) {
              say(`✗ ${setKey}: ${err}`);
              break;
            }
          }
          await setConfig(setKey, setValue);
          say(`✓ ${setKey} = ${setValue} (saved to ~/.mist/mist.cfg)`);
          break;
        }
        case "show": {
          if (!arg) {
            const cfg = await readConfig();
            const keys = Object.keys(cfg).sort();
            if (!keys.length) say("(mist.cfg is empty)");
            for (const k of keys) say(`${k} = ${cfg[k]}`);
          } else {
            const v = await getConfig(arg);
            say(v ? `${arg} = ${v}` : `${arg} is not set`);
          }
          break;
        }
        case "cd": {
          if (!arg) {
            say(`cwd: ${process.cwd()}`);
            break;
          }
          try {
            const resolved = arg.startsWith("/") ? arg : `${process.cwd()}/${arg}`;
            const stat = await Bun.file(resolved).exists() ? true : false;
            if (!stat) {
              say(`✗ not found: ${resolved}`);
              break;
            }
            process.chdir(resolved);
            say(`✓ cwd → ${process.cwd()}`);
          } catch (err) {
            say(`✗ ${(err as Error).message}`);
          }
          break;
        }
        case "reasoning": {
          if (!arg) {
            const v = (await getConfig("reasoning")) ?? "(unset)";
            say(`reasoning = ${v} (off · low · medium · high)`);
            break;
          }
          if (!["off", "low", "medium", "high"].includes(arg)) {
            say("✗ reasoning must be off · low · medium · high");
            break;
          }
          await setConfig("reasoning", arg);
          say(`✓ reasoning = ${arg}`);
          break;
        }
        case "verbosity": {
          if (!arg) {
            const v = (await getConfig("verbosity")) ?? "(unset)";
            say(`verbosity = ${v} (quiet · normal · verbose)`);
            break;
          }
          if (!["quiet", "normal", "verbose"].includes(arg)) {
            say("✗ verbosity must be quiet · normal · verbose");
            break;
          }
          await setConfig("verbosity", arg);
          say(`✓ verbosity = ${arg}`);
          break;
        }
        case "pop": {
          const removed = sessionRef.current?.popLastTurn() ?? 0;
          say(removed ? `↶ popped ${removed} message${removed === 1 ? "" : "s"} (last turn removed)` : "(nothing to pop — no user turn in history)");
          break;
        }
        case "prune": {
          const n = Number(arg);
          // N must be >= 1: /prune 0 used to silently wipe the whole history.
          if (!Number.isFinite(n) || n < 1) {
            say("usage: /prune <N> — keep only the last N turns (N ≥ 1; /new to start fresh)");
            break;
          }
          const removed = sessionRef.current?.pruneHistory(n) ?? 0;
          say(removed ? `✂ pruned ${removed} message${removed === 1 ? "" : "s"} (kept last ${n} turn${n === 1 ? "" : "s"})` : "(nothing to prune)");
          break;
        }
        case "truncate": {
          const budget = Number(arg);
          if (!Number.isFinite(budget) || budget <= 0) {
            say("usage: /truncate <token_budget> — drop oldest until under budget");
            break;
          }
          const removed = sessionRef.current?.truncateHistory(budget) ?? 0;
          say(removed ? `✂ truncated ${removed} message${removed === 1 ? "" : "s"} (budget: ${budget.toLocaleString()} tok)` : "(already under budget)");
          break;
        }
        case "mcp": {
          const mcpMgr = sessionRef.current?.mcp;
          if (!mcpMgr) {
            say("(MCP not initialized — add servers to ~/.mist/mcp_servers.json)");
            break;
          }
          const sub = rest[0]?.toLowerCase();
          if (sub === "start" && rest[1]) {
            try { await mcpMgr.start(rest[1]); say(`✓ started ${rest[1]}`); } catch (e) { say(`✗ ${(e as Error).message}`); }
            break;
          }
          if (sub === "stop" && rest[1]) {
            await mcpMgr.stop(rest[1]); say(`✓ stopped ${rest[1]}`); break;
          }
          if (sub === "restart" && rest[1]) {
            try { await mcpMgr.restart(rest[1]); say(`✓ restarted ${rest[1]}`); } catch (e) { say(`✗ ${(e as Error).message}`); }
            break;
          }
          // Default: list status.
          const statuses = mcpMgr.status();
          const configs = mcpMgr.configsList();
          if (!configs.length) { say("(no MCP servers configured in ~/.mist/mcp_servers.json)"); break; }
          for (const c of configs) {
            const s = statuses.find((s) => s.name === c.name);
            const glyph = s?.status === "running" ? "✓" : s?.status === "starting" ? "⏳" : s?.status === "error" ? "✗" : "○";
            say(`${glyph} ${c.name} (${c.type}) — ${s?.status ?? "stopped"}${s?.tools ? ` · ${s.tools} tool${s.tools === 1 ? "" : "s"}` : ""}${s?.restarts ? ` · ${s.restarts} restart${s.restarts === 1 ? "" : "s"}` : ""}`);
          }
          say("/mcp start|stop|restart <name>");
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
          setSessionTitle("");
          say("— new session —");
          break;
        }
        case "quit":
        case "exit":
        case "q":
          await sessionRef.current?.shutdown().catch(() => {});
          exit();
          break;
        default:
          say(`unknown command /${cmd} — try /help`);
      }
    },
    [exit, handleEnvelope, items, push, saved, sessionId, tokens],
  );

  // (Declared BEFORE submit — a later declaration put the useCallback dep
  // array in the temporal dead zone and crashed the first suggestions render.)
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

  const submit = useCallback(async () => {
    const prompt = rl.handle.state.value.trim();
    if (!prompt || busy) return;
    rl.handle.reset();
    setSuggestions(null);
    // !cmd → bare shell passthrough (runs locally, not through the agent).
    if (isShellPassthrough(prompt)) {
      const cmd = shellCommand(prompt);
      recordHistory(prompt);
      push(item("user", prompt));
      push(item("info", `$ ${cmd}`));
      try {
        const proc = Bun.spawn(["sh", "-c", cmd], { cwd: process.cwd(), stdout: "pipe", stderr: "pipe" });
        const [stdout, stderr] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text()]);
        const code = await proc.exited;
        const out = (stdout + (stderr ? `\n[stderr]\n${stderr}` : "")).trim();
        if (out) push(item("info", out.slice(0, 2000)));
        push(item("info", `[exit ${code}]`));
      } catch (err) {
        push(item("error", `shell failed: ${(err as Error).message}`));
      }
      return;
    }
    if (prompt.startsWith("/")) {
      recordHistory(prompt);
      push(item("user", prompt));
      await runCommand(prompt);
      return;
    }
    if (!clientRef.current || !sessionId) return;
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
  }, [busy, push, recordHistory, rl, runCommand, sessionId]);

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

  /** Anchor of the completion token at the cursor: for @path completions the
   * @ sign; for /cmd the token start. */
  const completionAnchor = (line: string, cursor: number): number => {
    let start = cursor;
    while (start > 0 && !/\s/.test(line[start - 1]!)) start -= 1;
    const atIdx = line.slice(start, cursor).lastIndexOf("@");
    return atIdx >= 0 ? start + atIdx : start;
  };

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
      const answerWith = (answer: string) => {
        rl.handle.reset();
        setQuestion(null);
        setQuestionCustom(false);
        push(item("info", `❓ ${question.text}`), item("user", answer || "(no answer)"));
        sessionRef.current?.answer(answer || "(no answer — use your judgment)");
      };
      const rows = question.options.length + 1; // options + "type my own"
      if (question.options.length && !questionCustom) {
        // Option mode: ↑/↓ + Enter (Claude-Code style); 1-9 quick-select;
        // typing any character drops straight into free-text.
        if (key.upArrow) { setQuestionIndex((i) => (i - 1 + rows) % rows); return; }
        if (key.downArrow) { setQuestionIndex((i) => (i + 1) % rows); return; }
        const digit = ch >= "1" && ch <= "9" ? Number(ch) - 1 : -1;
        if (digit >= 0 && digit < question.options.length) {
          answerWith(question.options[digit]!);
          return;
        }
        if (key.return) {
          if (questionIndex < question.options.length) answerWith(question.options[questionIndex]!);
          else setQuestionCustom(true);
          return;
        }
        if (ch && !key.ctrl && !key.meta && !key.escape && !key.tab) {
          setQuestionCustom(true);
          rl.handle.setValue(ch);
        }
        return;
      }
      // Free-text mode (no options, or the user chose to type their own) —
      // full readline editing, same buffer as everywhere else.
      if (key.escape && question.options.length) {
        setQuestionCustom(false);
        rl.handle.reset();
        return;
      }
      if (key.return) { answerWith(rl.handle.state.value.trim()); return; }
      rl.input(ch, key);
      return;
    }
    if (busy) {
      if (key.escape && clientRef.current && sessionId) {
        void clientRef.current.interrupt(sessionId);
        return;
      }
      // Steering: type while the agent works; Enter queues the nudge.
      // Same readline buffer as idle — editing + ↑/↓ history work here too.
      if (key.return) {
        const steer = rl.handle.state.value.trim();
        rl.handle.reset();
        if (steer) {
          recordHistory(steer);
          sessionRef.current?.steer(steer);
        }
        return;
      }
      rl.input(ch, key);
      return;
    }
    // Cursor-aware editing via readline hook (Ctrl+A/E/K/U/W, arrows, ↑/↓
    // history via rlHistoryNav — no pre-filtering, rl owns the buffer).
    if (rl.search.active) {
      // Ctrl+R reverse search: delegate fully, render the search overlay.
      rl.input(ch, key);
      return;
    }
    // Tab: open the completion popup, or cycle through its candidates. The
    // anchor + tail are captured at FIRST Tab so each cycle replaces exactly
    // the candidate span (the old line-comparison guard never matched).
    if (key.tab) {
      if (suggestions && suggestions.list.length > 0) {
        const next = (suggestions.index + 1) % suggestions.list.length;
        const sug = suggestions.list[next]!;
        const head = rl.handle.state.value.slice(0, suggestions.anchor);
        rl.handle.setValue(head + sug.replacement + suggestions.tail, suggestions.anchor + sug.replacement.length);
        setSuggestions({ ...suggestions, index: next });
        return;
      }
      const { value: line, cursor } = rl.handle.state;
      const list = completionsFor({ line, cursor, cwd: process.cwd(), commands: COMMAND_NAMES });
      if (list.length) {
        const anchor = completionAnchor(line, cursor);
        const tail = line.slice(cursor);
        const sug = list[0]!;
        rl.handle.setValue(line.slice(0, anchor) + sug.replacement + tail, anchor + sug.replacement.length);
        setSuggestions({ list, index: 0, anchor, tail });
      } else {
        setSuggestions(null);
      }
      return;
    }
    // Any other key: pass to readline; typing dismisses the popup.
    const consumed = rl.input(ch, key);
    if (consumed) {
      if (suggestions) setSuggestions(null);
      return;
    }
    if (key.return) {
      void submit();
      return;
    }
  });

  const elapsed = startedAt ? Math.floor((Date.now() - startedAt) / 1000) : 0;

  return (
    <Box flexDirection="column" paddingX={1}>
      <Static items={[{ id: 0, kind: "brand" } as unknown as Item, ...items]}>
        {(it) =>
          (it as unknown as { kind: string }).kind === "brand" ? (
            banner ? (
              <Banner key="brand" session={sessionId} info={banner} />
            ) : (
              <Brand key="brand" engine={engine} session={sessionId} />
            )
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
              ❓ {question.text}
            </Text>
            {question.options.length && !questionCustom ? (
              <>
                {question.options.map((opt, i) => (
                  <Text key={`qo${i}`} color={i === questionIndex ? theme.brand : theme.text} bold={i === questionIndex}>
                    {i === questionIndex ? "❯ " : "  "}
                    {i + 1}. {opt}
                  </Text>
                ))}
                <Text
                  color={questionIndex === question.options.length ? theme.brand : theme.dim}
                  bold={questionIndex === question.options.length}
                >
                  {questionIndex === question.options.length ? "❯ " : "  "}✎ type my own answer…
                </Text>
              </>
            ) : (
              <Text>
                <Text color={theme.accent} bold>{"❯ "}</Text>
                {rl.handle.state.value.slice(0, rl.handle.state.cursor)}
                <Text color={theme.brand}>▏</Text>
                {rl.handle.state.value.slice(rl.handle.state.cursor)}
              </Text>
            )}
          </Box>
          <Text color={theme.dim} dimColor>
            {"  "}
            {question.options.length && !questionCustom
              ? "↑/↓ or 1-9 select · enter confirm · or just start typing"
              : question.options.length
                ? "enter to answer · esc back to options"
                : "enter to answer"}
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
            {spinner.frames[frame % spinner.frames.length]}{" "}
          </Text>
          <Text color={theme.verb}>{verb}…</Text>
          <Text color={theme.dim}>
            {" "}· {elapsed}s · {stepCount} step{stepCount === 1 ? "" : "s"}{ctxTokens ? ` · ctx ${shortTok(ctxTokens)}` : ""}{saved ? ` · ↓${saved.toLocaleString()} saved` : ""}
            {"  "}
          </Text>
          <Text color={theme.dim} dimColor>
            esc to interrupt{plan.length ? ` · ctrl+t to ${planVisible ? "hide" : "show"} tasks` : ""}
          </Text>
          </Box>
          <InputFrame title={sessionTitle}>
            <Text color={rl.handle.state.value ? theme.accent : theme.dim} bold>
              ❯{" "}
            </Text>
            <Text color={rl.handle.state.value ? undefined : theme.dim}>
              {rl.handle.state.value.slice(0, rl.handle.state.cursor)}
              <Text color={theme.brand}>▏</Text>
              {rl.handle.state.value.slice(rl.handle.state.cursor)}
            </Text>
          </InputFrame>
          <Box width={Math.max(24, (process.stdout.columns ?? 80) - 2)} justifyContent="space-between">
            <Text color={theme.dim} dimColor>
              {"  "}type + enter to steer the agent mid-task
            </Text>
            <Text color={theme.dim} dimColor>
              {ctxGauge(ctxTokens, ctxLimit)}
            </Text>
          </Box>
        </Box>
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {rl.search.active ? (
            <Box flexDirection="column" marginBottom={1}>
              <Text color={theme.accent} bold>
                ↎ reverse-i-search: {rl.search.query || "(type to search)"}
              </Text>
              {rl.search.result ? (
                <Text color={theme.dim}>  {rl.search.result}</Text>
              ) : rl.search.query ? (
                <Text color={theme.dim}>  (no match)</Text>
              ) : null}
              <Text color={theme.dim} dimColor>  ctrl+r again to cycle · enter to accept · backspace to edit · esc to cancel</Text>
            </Box>
          ) : null}
          {suggestions && suggestions.list.length > 0 ? (
            <Box flexDirection="column" marginBottom={0}>
              {suggestions.list.map((sug, i) => (
                <Text key={`${sug.label}-${i}`} color={i === suggestions.index ? theme.brand : theme.dim} bold={i === suggestions.index}>
                  {i === suggestions.index ? "❯ " : "  "}
                  {sug.label}
                  {sug.detail ? <Text color={theme.dim}> — {sug.detail}</Text> : null}
                </Text>
              ))}
              <Text color={theme.dim} dimColor>  tab to cycle · enter to send</Text>
            </Box>
          ) : null}
          <InputFrame title={sessionTitle} marginTop={1}>
            <Text color={rl.handle.state.value ? theme.accent : theme.dim} bold>
              ❯{" "}
            </Text>
            <Text color={rl.handle.state.value ? undefined : theme.dim}>
              {rl.handle.state.value.slice(0, rl.handle.state.cursor)}
              <Text color={theme.brand}>▏</Text>
              {rl.handle.state.value.slice(rl.handle.state.cursor)}
            </Text>
          </InputFrame>
        </Box>
      )}
      {!fatal && !busy && (
        <Box width={Math.max(24, (process.stdout.columns ?? 80) - 2)} justifyContent="space-between">
          <Text color={theme.dim} dimColor>
            {"  "}
            {rl.handle.state.value.startsWith("/")
              ? "tab completes commands · enter to run"
              : isShellPassthrough(rl.handle.state.value)
                ? "enter to run as shell"
                : rl.search.active
                  ? "ctrl+r cycle · enter accept · esc cancel"
                  : "enter to send · / commands · ! shell · @ files · ctrl+r search · ctrl+t tasks"}
          </Text>
          <Text color={theme.dim} dimColor>
            {ctxGauge(ctxTokens, ctxLimit)}
          </Text>
        </Box>
      )}
    </Box>
  );
}

/** 84213 → "84.2k", 1000000 → "1.00m" — compact token figures. */
function shortTok(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}m`;
}

/** Bottom-right context gauge: real prompt size vs the model's window. */
function ctxGauge(ctx: number, limit: number): string {
  if (!ctx) return "";
  if (!limit) return `context ${shortTok(ctx)}`;
  const pct = Math.min(100, Math.round((ctx / limit) * 100));
  return `context ${shortTok(ctx)} / ${shortTok(limit)} (${pct}%)`;
}

const VERSION = "0.1.0";

const HELP = `mist ${VERSION} — Mist coding agent (Bun engine)

Usage:
  mist                        interactive session (new)
  mist "task"                 one-shot: run the task and exit
  mist -p "task"              one-shot (explicit --prompt form)
  mist -p "task" --output json   one-shot, emit one JSON envelope per line
  mist --serve [--port 4096] [--host 127.0.0.1]   headless HTTP/SSE server
  mist -c | --continue        resume the latest session for this directory
  mist -r <id> | --resume     resume a specific session (id prefix ok)
  mist --sessions             list saved sessions for this directory
  mist --export-training [f]  sessions → SFT JSONL (--format=openai,
                              --min-turns=N, --no-redact)
  mist --help | --version

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

  // --export-training: dump stored sessions as SFT-ready JSONL trajectories.
  if (args.includes("--export-training")) {
    const { exportTraining } = await import("@mist/core");
    const idx = args.indexOf("--export-training");
    const next = args[idx + 1];
    const outPath = next && !next.startsWith("--") ? next : `mist-training-${Date.now()}.jsonl`;
    const format = args.includes("--format=openai") ? "openai" as const : "anthropic" as const;
    const mt = args.find((a) => a.startsWith("--min-turns="));
    const minTurns = mt ? Math.max(1, Number(mt.split("=")[1])) : 1;
    const redact = !args.includes("--no-redact");
    const res = await exportTraining(process.cwd(), outPath, { format, minTurns, redact });
    console.log(
      `exported ${res.written} trajectories (${format}${redact ? ", secrets redacted" : ", RAW — review before sharing"}) → ${res.outPath}` +
        (res.skipped ? ` · ${res.skipped} skipped (< ${minTurns} turns)` : ""),
    );
    return;
  }

  // --serve: headless HTTP/SSE server (never renders the TUI).
  if (args.includes("--serve")) {
    const { startHeadlessServer } = await import("@mist/core");
    const portIdx = args.indexOf("--port");
    const hostIdx = args.indexOf("--host");
    const port = portIdx >= 0 ? Number(args[portIdx + 1]) : undefined;
    const host = hostIdx >= 0 ? args[hostIdx + 1] : undefined;
    const server = await startHeadlessServer({ cwd: process.cwd(), port, host });
    console.error(`mist --serve listening on ${server.url}`);
    console.error(`auth token: ${server.token}  (also in ~/.mist/server.json)`);
    return; // server keeps the process alive
  }

  // -p / --prompt with --output: headless one-shot (never renders the TUI).
  let explicitPrompt: string | undefined;
  let outputFormat: "json" | "text" | undefined;
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === "-p" || a === "--prompt") {
      explicitPrompt = args[++i];
    } else if (a === "--output") {
      const v = args[++i];
      if (v === "json" || v === "text") outputFormat = v;
      else {
        console.error(`--output must be 'json' or 'text' (got '${v}')`);
        process.exit(1);
      }
    }
  }
  if (explicitPrompt !== undefined || outputFormat) {
    const { runHeadless } = await import("@mist/core");
    const prompt = explicitPrompt ?? "";
    const res = await runHeadless(prompt, { cwd: process.cwd(), output: outputFormat });
    process.exit(res.exitCode);
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
  // Interactive launches get the full welcome banner; one-shot (argv) runs
  // keep the compact one-liner so scripted/tmux output stays clean.
  let banner: BannerInfo | undefined;
  if (!argvPrompt) {
    banner = {
      model: await getConfiguredModelName().catch(() => "no model configured"),
      latestTitle: resume?.meta.title ?? (await store.latest().catch(() => null))?.title ?? null,
    };
  }
  render(<App initialPrompt={argvPrompt || undefined} resume={resume} banner={banner} />);
}

void main();

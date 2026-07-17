/**
 * Typed views over the EventEnvelope stream.
 *
 * Taxonomy (from code_puppy/server/session_manager.py + messaging/messages.py):
 *  - Lifecycle events use dotted names: session.created / session.running /
 *    session.idle / session.interrupted / session.error / stream.lagged.
 *  - Bus messages arrive with `type` = the Python class name and
 *    `data` = the message's model_dump(). We type the fields we render.
 *
 * NOTE (Phase 1): the Python engine publishes the agent response as ONE
 * AgentResponseMessage at turn end; `session.idle` marks turn completion.
 * Token-level deltas arrive with the TS engine (Phase 2) as `text.delta`.
 */

import type { EventEnvelope } from "./index";

export type MistEvent =
  | { kind: "session_created"; agentName: string }
  | { kind: "session_running"; prompt: string }
  | { kind: "session_idle" }
  | { kind: "session_interrupted" }
  | { kind: "session_error"; error: string }
  | { kind: "agent_response"; content: string }
  | { kind: "agent_reasoning"; reasoning: string; nextSteps?: string }
  | { kind: "text"; level: string; text: string }
  | { kind: "shell_start"; command: string }
  | { kind: "shell_line"; line: string; stream: "stdout" | "stderr" }
  | { kind: "file_read"; path: string }
  | { kind: "file_diff"; path: string }
  | { kind: "grep_result"; totalMatches: number }
  | { kind: "subagent_invocation"; agentName: string; prompt: string }
  | { kind: "subagent_response"; agentName: string; response: string }
  | { kind: "text_delta"; delta: string } // TS engine (Phase 2) only
  | { kind: "other"; type: string };

const str = (v: unknown): string => (typeof v === "string" ? v : "");

export function classifyEvent(env: EventEnvelope): MistEvent {
  const d = env.data as Record<string, unknown>;
  switch (env.type) {
    case "session.created":
      return { kind: "session_created", agentName: str(d["agent_name"]) || "mist" };
    case "session.running":
      return { kind: "session_running", prompt: str(d["prompt"]) };
    case "session.idle":
      return { kind: "session_idle" };
    case "session.interrupted":
      return { kind: "session_interrupted" };
    case "session.error":
      return { kind: "session_error", error: str(d["error"]) };
    case "AgentResponseMessage":
      return { kind: "agent_response", content: str(d["content"]) };
    case "AgentReasoningMessage":
      return {
        kind: "agent_reasoning",
        reasoning: str(d["reasoning"]),
        nextSteps: str(d["next_steps"]) || undefined,
      };
    case "TextMessage":
      return { kind: "text", level: str(d["level"]) || "info", text: str(d["text"]) };
    case "ShellStartMessage":
      return { kind: "shell_start", command: str(d["command"]) };
    case "ShellLineMessage":
      return {
        kind: "shell_line",
        line: str(d["line"]),
        stream: d["stream"] === "stderr" ? "stderr" : "stdout",
      };
    case "FileContentMessage":
      return { kind: "file_read", path: str(d["path"]) };
    case "DiffMessage":
      return { kind: "file_diff", path: str(d["path"]) };
    case "GrepResultMessage":
      return {
        kind: "grep_result",
        totalMatches: typeof d["total_matches"] === "number" ? d["total_matches"] : 0,
      };
    case "SubAgentInvocationMessage":
      return {
        kind: "subagent_invocation",
        agentName: str(d["agent_name"]),
        prompt: str(d["prompt"]),
      };
    case "SubAgentResponseMessage":
      return {
        kind: "subagent_response",
        agentName: str(d["agent_name"]),
        response: str(d["response"]),
      };
    case "text.delta":
      return { kind: "text_delta", delta: str(d["delta"]) };
    default:
      return { kind: "other", type: env.type };
  }
}

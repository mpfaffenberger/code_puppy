/**
 * Streaming client for the OpenAI Chat Completions API (`/v1/chat/completions`
 * with `stream: true`), covering the OpenAI-compatible family: openai,
 * azure_openai, custom_openai, cerebras, openrouter, synthetic, zai_*,
 * chatgpt_oauth, copilot, minimax.
 *
 * The agent loop keeps an Anthropic-shaped history (its source of truth);
 * this client translates to/from the OpenAI wire format on each call:
 *
 *   - Anthropic `tool_use` block → OpenAI assistant `tool_calls[i]`
 *   - Anthropic `tool_result` block → OpenAI `role: "tool"` message
 *   - Anthropic `system` param → OpenAI `role: "system"` message
 *
 * Streamed tool calls arrive as deltas: the model emits a `tool_calls[].id`
 * and `function.name` on the first delta for index i, then streams
 * `function.arguments` (partial JSON) across subsequent deltas for that same
 * index. We accumulate per-index and JSON-parse at the end — same pattern as
 * the Anthropic client's `input_json_delta` handling.
 */

import type {
  ChatMessage,
  ContentBlock,
  ModelClient,
  StreamCallbacks,
  ToolSpec,
  TurnResult,
} from "./models";

// ---- OpenAI wire shapes (the subset we read/write) -------------------------

interface OAIFunctionSpec {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

interface OAIMessage {
  role: "system" | "user" | "assistant" | "tool";
  content?: string | null;
  tool_calls?: {
    id: string;
    type: "function";
    function: { name: string; arguments: string };
  }[];
  tool_call_id?: string;
}

interface OAIChoiceDelta {
  role?: string;
  content?: string | null;
  tool_calls?: {
    index: number;
    id?: string;
    function?: { name?: string; arguments?: string };
  }[];
}

interface OAIStreamChunk {
  choices?: {
    delta?: OAIChoiceDelta;
    finish_reason?: string | null;
  }[];
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

/** Reasoning models need max_completion_tokens and reject temperature. */
function isReasoningModel(model: string): boolean {
  return /^o\d|gpt-5/.test(model);
}

/** Early o1 previews reject reasoning_effort as well. */
function rejectsReasoningEffort(model: string): boolean {
  return /^o1(-preview|-mini)/.test(model);
}

export class OpenAIClient implements ModelClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly model: string,
    private readonly type: string,
  ) {}

  private resolvedUrl(): string {
    // configFromDef always resolves the base (defaultBaseForType is the single
    // source of truth); the literal here only covers direct construction.
    const base = (this.baseUrl || "https://api.openai.com/v1").replace(/\/$/, "");
    return `${base}/chat/completions`;
  }

  async stream(
    system: string,
    messages: ChatMessage[],
    tools: ToolSpec[],
    cb: StreamCallbacks = {},
    maxTokens = 8192,
  ): Promise<TurnResult> {
    const url = this.resolvedUrl();
    const body: Record<string, unknown> = {
      model: this.model,
      messages: this.translateHistory(system, messages),
      stream: true,
      stream_options: { include_usage: true },
    };
    if (tools.length) {
      body.tools = this.translateTools(tools);
    }
    if (isReasoningModel(this.model)) {
      // Reasoning models reject max_tokens (400) — they take max_completion_tokens
      // — and reject temperature; early o1 previews also reject reasoning_effort.
      body.max_completion_tokens = maxTokens;
      if (!rejectsReasoningEffort(this.model)) body.reasoning_effort = "medium";
    } else {
      body.max_tokens = maxTokens;
      body.temperature = 0;
    }

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${this.apiKey}`,
        ...(this.type === "openrouter" ? { "http-referer": "https://mist.local" } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "");
      throw new Error(`model call failed: HTTP ${res.status} ${text.slice(0, 300)}`);
    }

    const result: TurnResult = {
      text: "",
      thinkingMs: 0,
      toolUses: [],
      stopReason: "stop",
      inputTokens: 0,
      outputTokens: 0,
    };
    // Per-index tool-call accumulation (the model streams arguments in pieces).
    const toolAcc = new Map<
      number,
      { id: string; name: string; json: string; announced: boolean }
    >();

    let debugSink: import("bun").FileSink | null = null;
    const debugPath = process.env.MIST_DEBUG_STREAM;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const raw of lines) {
        const line = raw.trim();
        if (!line || !line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") continue;
        if (debugPath) {
          debugSink ??= Bun.file(debugPath).writer();
          debugSink.write(`${data}\n`);
        }
        let chunk: OAIStreamChunk;
        try {
          chunk = JSON.parse(data);
        } catch {
          continue;
        }
        // Mid-stream provider errors arrive as {"error":{...}} after 200 OK —
        // surface them; swallowing yields a silent blank turn (the 429 lesson).
        const errObj = (chunk as { error?: { message?: string } }).error;
        if (errObj) {
          throw new Error(
            `stream error: ${String(errObj.message ?? JSON.stringify(errObj)).slice(0, 300)}`,
          );
        }
        if (chunk.usage) {
          if (typeof chunk.usage.prompt_tokens === "number")
            result.inputTokens = chunk.usage.prompt_tokens;
          if (typeof chunk.usage.completion_tokens === "number")
            result.outputTokens = chunk.usage.completion_tokens;
          // o-series reasoning tokens are REAL usage (billed inside
          // completion_tokens) — surface them for /lens attribution.
          const details = (chunk.usage as { completion_tokens_details?: { reasoning_tokens?: number } })
            .completion_tokens_details;
          if (typeof details?.reasoning_tokens === "number")
            result.reasoningTokens = details.reasoning_tokens;
        }
        const choice = chunk.choices?.[0];
        if (!choice) continue;
        const delta = choice.delta;
        if (delta?.content) {
          const t = String(delta.content);
          result.text += t;
          cb.onTextDelta?.(t);
        }
        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
            const acc = toolAcc.get(tc.index) ?? {
              id: tc.id ?? `call_${tc.index}`,
              name: tc.function?.name ?? "",
              json: "",
              announced: false,
            };
            if (tc.id) acc.id = tc.id;
            if (tc.function?.name) acc.name = tc.function.name;
            if (tc.function?.arguments) acc.json += tc.function.arguments;
            toolAcc.set(tc.index, acc);
            if (!acc.announced && acc.name) {
              acc.announced = true;
              cb.onToolUse?.(acc.name);
            }
          }
        }
        if (choice.finish_reason) {
          // Map OpenAI finish_reason → the stop reason the agent loop checks.
          // The loop treats "tool_use" as "keep going"; everything else ends the turn.
          result.stopReason =
            choice.finish_reason === "tool_calls" ? "tool_use" : choice.finish_reason;
        }
      }
    }
    if (debugSink) void debugSink.end();

    for (const { id, name, json } of toolAcc.values()) {
      let input: unknown = {};
      try {
        input = json ? JSON.parse(json) : {};
      } catch {
        input = { _raw: json };
      }
      result.toolUses.push({ id, name, input });
    }
    // If we accumulated tool calls but the server sent no/odd finish_reason,
    // keep the loop going so they actually execute.
    if (result.toolUses.length && result.stopReason !== "tool_use") {
      result.stopReason = "tool_use";
    }
    return result;
  }

  // ---- Anthropic history → OpenAI messages --------------------------------

  private translateHistory(system: string, messages: ChatMessage[]): OAIMessage[] {
    const out: OAIMessage[] = [];
    if (system) out.push({ role: "system", content: system });
    for (const msg of messages) {
      if (typeof msg.content === "string") {
        out.push({ role: msg.role, content: msg.content });
        continue;
      }
      // Assistant turn: split into content + tool_calls.
      if (msg.role === "assistant") {
        const texts: string[] = [];
        const calls: NonNullable<OAIMessage["tool_calls"]> = [];
        for (const block of msg.content) {
          if (block.type === "text") texts.push(block.text);
          else if (block.type === "tool_use")
            calls.push({
              id: block.id,
              type: "function",
              function: { name: block.name, arguments: JSON.stringify(block.input ?? {}) },
            });
        }
        const entry: OAIMessage = { role: "assistant", content: texts.join("") || null };
        if (calls.length) entry.tool_calls = calls;
        out.push(entry);
        continue;
      }
      // User turn: may contain tool_result blocks and/or text.
      const toolResults: ContentBlock[] = [];
      const textParts: string[] = [];
      for (const block of msg.content) {
        if (block.type === "tool_result") toolResults.push(block);
        else if (block.type === "text") textParts.push(block.text);
      }
      for (const tr of toolResults) {
        out.push({ role: "tool", tool_call_id: tr.tool_use_id, content: tr.content });
      }
      if (textParts.length) out.push({ role: "user", content: textParts.join("\n") });
    }
    return out;
  }

  private translateTools(tools: ToolSpec[]): OAIFunctionSpec[] {
    return tools.map((t) => ({
      type: "function",
      function: {
        name: t.name,
        description: t.description,
        parameters: t.input_schema,
      },
    }));
  }
}

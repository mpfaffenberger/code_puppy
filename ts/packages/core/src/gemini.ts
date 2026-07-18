/**
 * Streaming client for Google's Gemini API (`generativelanguage.googleapis.com`
 * `:streamGenerateContent?alt=sse`), covering gemini / custom_gemini /
 * gemini_oauth. Uses the `x-goog-api-key` header (NOT Bearer, NOT ?key=).
 *
 * The agent loop keeps an Anthropic-shaped history; this client translates to
 * Gemini's `contents`/`parts` format and streams back normalized deltas.
 *
 * Key shape differences from OpenAI/Anthropic:
 *   - roles are `user`/`model` (not `assistant`)
 *   - tool calls are `functionCall` parts on a `model` message
 *   - tool results are `functionResponse` parts on a `user` message, and the
 *     response `name` MUST echo the originating functionCall's name
 *   - tool args arrive as complete `args` objects (merged across deltas)
 *   - `finishReason` is NOT authoritative for "tool calls present"; we infer
 *     from whether any functionCall part was emitted (matches the reference)
 *   - no `[DONE]` sentinel — the SSE stream just ends
 */

import type {
  ChatMessage,
  ContentBlock,
  ModelClient,
  StreamCallbacks,
  ToolSpec,
  TurnResult,
} from "./models";

// ---- Gemini wire shapes (the subset we read/write) -------------------------

interface GPart {
  text?: string;
  thought?: boolean;
  functionCall?: { name?: string; id?: string; args?: Record<string, unknown> };
  functionResponse?: { name: string; response: unknown };
  /** Replay marker on historical functionCall parts (Gemini 3 requirement). */
  thoughtSignature?: string;
}
interface GContent {
  role: "user" | "model";
  parts: GPart[];
}
interface GChunk {
  candidates?: {
    content?: { parts?: GPart[] };
    finishReason?: string;
  }[];
  usageMetadata?: {
    promptTokenCount?: number;
    candidatesTokenCount?: number;
  };
}

const BYPASS_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go";

export class GeminiClient implements ModelClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly model: string,
    private readonly type: string,
  ) {}

  private resolvedUrl(): string {
    // baseUrl already includes /v1beta (or is bare host for custom_gemini).
    const base = this.baseUrl.replace(/\/$/, "");
    const version = base.includes("/v1beta") || base.includes("/v1alpha") ? "" : "/v1beta";
    return `${base}${version}/models/${this.model}:streamGenerateContent?alt=sse`;
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
      contents: this.translateHistory(messages),
      generationConfig: { maxOutputTokens: maxTokens, temperature: 0 },
    };
    if (system) body.systemInstruction = { role: "user", parts: [{ text: system }] };
    if (tools.length) {
      // Strict proto-backed parser: ONLY name/description/parameters — an
      // extra field (e.g. a spread-in input_schema) is a 400 "Unknown name".
      body.tools = [
        {
          functionDeclarations: tools.map((t) => ({
            name: t.name,
            description: t.description,
            parameters: t.input_schema,
          })),
        },
      ];
      body.toolConfig = { functionCallingConfig: { mode: "AUTO" } };
    }

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        "x-goog-api-key": this.apiKey,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "");
      throw new Error(`gemini call failed: HTTP ${res.status} ${text.slice(0, 300)}`);
    }

    const result: TurnResult = {
      text: "",
      thinkingMs: 0,
      toolUses: [],
      stopReason: "stop",
      inputTokens: 0,
      outputTokens: 0,
    };
    // Per-call accumulation for streaming function-call args.
    let curName = "";
    let curId = "";
    let curArgs: Record<string, unknown> = {};
    let startedCall = false;

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
        if (!data || data === "[DONE]") continue;
        if (debugPath) {
          debugSink ??= Bun.file(debugPath).writer();
          debugSink.write(`${data}\n`);
        }
        let chunk: GChunk;
        try {
          chunk = JSON.parse(data);
        } catch {
          continue;
        }
        // Mid-stream provider errors arrive as {"error":{...}} after 200 OK.
        const errObj = (chunk as { error?: { message?: string } }).error;
        if (errObj) {
          throw new Error(
            `stream error: ${String(errObj.message ?? JSON.stringify(errObj)).slice(0, 300)}`,
          );
        }
        if (chunk.usageMetadata) {
          if (typeof chunk.usageMetadata.promptTokenCount === "number")
            result.inputTokens = chunk.usageMetadata.promptTokenCount;
          if (typeof chunk.usageMetadata.candidatesTokenCount === "number")
            result.outputTokens = chunk.usageMetadata.candidatesTokenCount;
        }
        const parts = chunk.candidates?.[0]?.content?.parts ?? [];
        for (const part of parts) {
          // Thinking delta (we don't surface it, but don't treat as text).
          if (part.thought) continue;
          if (typeof part.text === "string" && part.text.length > 0) {
            result.text += part.text;
            cb.onTextDelta?.(part.text);
          }
          if (part.functionCall) {
            const fc = part.functionCall;
            // A new call begins when name is present.
            if (fc.name) {
              if (startedCall) this.flushCall(result, curName, curId, curArgs);
              curName = fc.name;
              curId = fc.id ?? `call_${result.toolUses.length}`;
              curArgs = fc.args ?? {};
              startedCall = true;
              cb.onToolUse?.(curName);
            } else if (fc.args) {
              // Complete-args delta: merge.
              Object.assign(curArgs, fc.args);
            }
          }
        }
        const finish = chunk.candidates?.[0]?.finishReason;
        if (finish) {
          result.stopReason =
            finish === "STOP" ? "stop" : finish === "MAX_TOKENS" ? "max_tokens" : finish.toLowerCase();
        }
      }
    }
    if (debugSink) void debugSink.end();
    if (startedCall) this.flushCall(result, curName, curId, curArgs);
    // Tool calls present → keep the loop going (matches reference: infer from
    // parts, not finishReason).
    if (result.toolUses.length) result.stopReason = "tool_use";
    return result;
  }

  private flushCall(
    result: TurnResult,
    name: string,
    id: string,
    args: Record<string, unknown>,
  ): void {
    result.toolUses.push({ id, name, input: args });
  }

  // ---- Anthropic history → Gemini contents --------------------------------

  private translateHistory(messages: ChatMessage[]): GContent[] {
    // Gemini correlates functionResponse→functionCall BY NAME — build the
    // id→name map from the tool_use blocks before translating results.
    const nameById = new Map<string, string>();
    for (const msg of messages) {
      if (typeof msg.content === "string") continue;
      for (const block of msg.content) {
        if (block.type === "tool_use") nameById.set(block.id, block.name);
      }
    }
    const out: GContent[] = [];
    for (const msg of messages) {
      const role: "user" | "model" = msg.role === "assistant" ? "model" : "user";
      if (typeof msg.content === "string") {
        out.push({ role, parts: [{ text: msg.content }] });
        continue;
      }
      const parts: GPart[] = [];
      for (const block of msg.content) {
        const p = this.translateBlock(block, nameById);
        if (p) parts.push(p);
      }
      if (parts.length) out.push({ role, parts });
    }
    if (out.length === 0) out.push({ role: "user", parts: [{ text: "" }] });
    return out;
  }

  private translateBlock(block: ContentBlock, nameById: Map<string, string>): GPart | null {
    switch (block.type) {
      case "text":
        return { text: block.text };
      case "tool_use":
        return {
          functionCall: { name: block.name, args: (block.input ?? {}) as Record<string, unknown>, id: block.id },
          thoughtSignature: BYPASS_THOUGHT_SIGNATURE,
        };
      case "tool_result":
        // Gemini wants the response as an object; wrap raw strings.
        return {
          functionResponse: {
            name: nameById.get(block.tool_use_id) ?? "tool",
            response: { result: block.content },
          },
        };
      default:
        return null;
    }
  }
}

/**
 * Minimal streaming client for the Anthropic Messages API — including
 * Anthropic-compatible endpoints (register them as `custom_anthropic`;
 * e.g. z.ai's or minimax's `/anthropic` bases). The bare `minimax` type
 * routes to the OpenAI-protocol client instead.
 * Lenient parser: third-party endpoints omit fields; we only rely on the
 * event kinds the loop needs (text deltas, tool_use blocks, stop reason).
 *
 * Implements the provider-neutral `ModelClient` contract from ./models.ts;
 * the shared message/tool/result types live there.
 */

import type {
  ChatMessage,
  ContentBlock,
  ModelClient,
  StreamCallbacks,
  ToolSpec,
  TurnResult,
} from "./models";

export type { ChatMessage, ContentBlock, StreamCallbacks, ToolSpec, TurnResult };

export class AnthropicClient implements ModelClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly model: string,
  ) {}

  async stream(
    system: string,
    messages: ChatMessage[],
    tools: ToolSpec[],
    cb: StreamCallbacks = {},
    maxTokens = 8192,
  ): Promise<TurnResult> {
    const url = `${this.baseUrl.replace(/\/$/, "")}/v1/messages`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": this.apiKey,
        authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model: this.model,
        system,
        messages,
        tools: tools.length ? tools : undefined,
        max_tokens: maxTokens,
        stream: true,
      }),
    });
    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => "");
      throw new Error(`model call failed: HTTP ${res.status} ${body.slice(0, 300)}`);
    }

    const result: TurnResult = {
      text: "",
      thinkingMs: 0,
      toolUses: [],
      stopReason: "end_turn",
      inputTokens: 0,
      outputTokens: 0,
    };
    // Per-index accumulation of tool_use input JSON.
    const toolAcc = new Map<number, { id: string; name: string; json: string }>();
    let thinkingStart = 0;
    let thinkingLast = 0;

    let debugSink: import("bun").FileSink | null = null;
    const debugPath = process.env.MIST_DEBUG_STREAM;
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
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("");
        if (!data || data === "[DONE]") continue;
        // Raw-wire debug capture (the gpt-5.5 bug-hunt hook): every SSE data
        // payload, exactly as received, appended to MIST_DEBUG_STREAM.
        if (debugPath) {
          debugSink ??= Bun.file(debugPath).writer();
          debugSink.write(`${data}\n`);
        }
        let ev: Record<string, unknown>;
        try {
          ev = JSON.parse(data);
        } catch {
          continue;
        }
        const type = ev["type"];
        if (type === "content_block_start") {
          const idx = ev["index"] as number;
          const block = ev["content_block"] as Record<string, unknown> | undefined;
          if (block?.["type"] === "tool_use") {
            const name = String(block["name"] ?? "");
            toolAcc.set(idx, { id: String(block["id"] ?? `tu_${idx}`), name, json: "" });
            cb.onToolUse?.(name);
          }
        } else if (type === "content_block_delta") {
          {
            const delta0 = ev["delta"] as Record<string, unknown> | undefined;
            if (delta0?.["type"] === "thinking_delta") {
              if (thinkingStart === 0) thinkingStart = Date.now();
              thinkingLast = Date.now();
              result.thinkingChars = (result.thinkingChars ?? 0) + String(delta0["thinking"] ?? "").length;
            }
          }
          const idx = ev["index"] as number;
          const delta = ev["delta"] as Record<string, unknown> | undefined;
          if (delta?.["type"] === "text_delta") {
            const t = String(delta["text"] ?? "");
            result.text += t;
            cb.onTextDelta?.(t);
          } else if (delta?.["type"] === "input_json_delta") {
            const acc = toolAcc.get(idx);
            if (acc) acc.json += String(delta["partial_json"] ?? "");
          }
        } else if (type === "message_delta") {
          const d = ev["delta"] as Record<string, unknown> | undefined;
          if (d?.["stop_reason"]) result.stopReason = String(d["stop_reason"]);
          const usage = ev["usage"] as Record<string, unknown> | undefined;
          if (typeof usage?.["output_tokens"] === "number")
            result.outputTokens = usage["output_tokens"] as number;
        } else if (type === "message_start") {
          const msg = ev["message"] as Record<string, unknown> | undefined;
          const usage = msg?.["usage"] as Record<string, unknown> | undefined;
          if (typeof usage?.["input_tokens"] === "number")
            result.inputTokens = usage["input_tokens"] as number;
        } else if (type === "error") {
          const err = ev["error"] as Record<string, unknown> | undefined;
          throw new Error(`stream error: ${String(err?.["message"] ?? data).slice(0, 300)}`);
        }
      }
    }
    if (debugSink) void debugSink.end();
    if (thinkingStart) result.thinkingMs = Math.max(0, thinkingLast - thinkingStart);
    for (const { id, name, json } of toolAcc.values()) {
      let input: unknown = {};
      try {
        input = json ? JSON.parse(json) : {};
      } catch {
        input = { _raw: json };
      }
      result.toolUses.push({ id, name, input });
    }
    return result;
  }
}

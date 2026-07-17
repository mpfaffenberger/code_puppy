/**
 * The provider-neutral model-client surface.
 *
 * The agent loop keeps an Anthropic-shaped internal history as its single
 * source of truth (it's the richest common shape — text, tool_use, and
 * tool_result blocks). Each provider client implements `ModelClient.stream`
 * by translating that history into its own wire format and streaming back
 * normalized deltas.
 *
 * This mirrors Python's pydantic-ai split: one agent loop, many model
 * backends, each owning its own request/response mapping.
 */

// ---- Shared shapes (Anthropic-style, the internal source of truth) ---------

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: unknown }
  | {
      type: "tool_result";
      tool_use_id: string;
      content: string;
      is_error?: boolean;
    };

export interface ChatMessage {
  role: "user" | "assistant";
  content: string | ContentBlock[];
}

export interface StreamCallbacks {
  onTextDelta?: (text: string) => void;
  /** Fired the instant a tool call begins (before its arguments finish). */
  onToolUse?: (name: string) => void;
}

export interface TurnResult {
  text: string;
  thinkingMs: number;
  toolUses: { id: string; name: string; input: unknown }[];
  /** Provider-native stop reason; agent loop checks against "tool_use". */
  stopReason: string;
  inputTokens: number;
  outputTokens: number;
}

// ---- The contract every provider implements --------------------------------

export interface ModelClient {
  /**
   * Stream one model request. Resolves with the aggregated TurnResult once
   * the stream ends. Callbacks fire during streaming for live UI updates.
   */
  stream(
    system: string,
    messages: ChatMessage[],
    tools: ToolSpec[],
    cb: StreamCallbacks,
    maxTokens?: number,
  ): Promise<TurnResult>;
}

// ---- Factory: model_type → concrete client ---------------------------------

export interface ModelClientConfig {
  /** Resolved base URL (no trailing slash). */
  baseUrl: string;
  apiKey: string;
  model: string;
  /** Raw model_type from the registry (openai, anthropic, gemini, …). */
  type: string;
  /** Extra provider knobs if present on the ModelDef. */
  custom_endpoint?: { url: string; api_key?: string; timeout?: number };
  /** For round_robin: candidate model names + rotate_every. */
  models?: string[];
  rotate_every?: number;
}

/**
 * Resolve a model name to a ModelClient. Injected by the engine so the factory
 * can recurse for round-robin candidates without a circular import on config.
 */
export type ModelResolver = (modelName: string) => Promise<ModelClient>;

/**
 * Dispatch by `type`. The OpenAI-protocol family (openai, azure_openai,
 * custom_openai, cerebras, openrouter, synthetic, zai_*) all share one
 * chat-completions client. Anthropic-compatible endpoints share another.
 *
 * Pass `resolve` when the model tree may contain a `round_robin` node whose
 * candidates must be built recursively.
 */
export async function createModelClient(
  cfg: ModelClientConfig,
  resolve?: ModelResolver,
): Promise<ModelClient> {
  const t = cfg.type;

  if (t === "round_robin") {
    if (!resolve) throw new Error("round_robin requires a model resolver");
    const names = cfg.models ?? [];
    if (names.length === 0) {
      throw new Error(`round_robin model '${cfg.model}' has no candidates (models: [])`);
    }
    const { RoundRobinClient } = await import("./round_robin");
    const kids = await Promise.all(names.map((n) => resolve(n)));
    return new RoundRobinClient(kids, { rotateEvery: cfg.rotate_every ?? 1 });
  }

  // Anthropic-compatible: anthropic, custom_anthropic, claude_code, aws_bedrock.
  if (t === "anthropic" || t === "custom_anthropic" || t === "claude_code" || t === "aws_bedrock") {
    const { AnthropicClient } = await import("./anthropic");
    return new AnthropicClient(cfg.baseUrl, cfg.apiKey, cfg.model);
  }
  // OpenAI-compatible chat-completions family.
  if (
    t === "openai" ||
    t === "azure_openai" ||
    t === "azure_foundry_openai" ||
    t === "custom_openai" ||
    t === "cerebras" ||
    t === "openrouter" ||
    t === "synthetic" ||
    t === "zai_coding" ||
    t === "zai_api" ||
    t === "chatgpt_oauth" ||
    t === "copilot" ||
    t === "minimax"
  ) {
    const { OpenAIClient } = await import("./openai");
    return new OpenAIClient(cfg.baseUrl, cfg.apiKey, cfg.model, cfg.type);
  }
  // Gemini family — generateContent stream with Google function-calling schema.
  if (t === "gemini" || t === "custom_gemini" || t === "gemini_oauth") {
    const { GeminiClient } = await import("./gemini");
    return new GeminiClient(cfg.baseUrl, cfg.apiKey, cfg.model, cfg.type);
  }
  throw new Error(`unknown model type '${t}' for model '${cfg.model}'`);
}

/**
 * Build a ModelClientConfig from a registry ModelDef + env, the way the engine
 * does it. Exposed so resolve() can recurse for round-robin candidates.
 */
export function configFromDef(def: {
  name: string;
  type: string;
  custom_endpoint?: { url: string; api_key?: string; timeout?: number };
  models?: string[];
  rotate_every?: number;
}): ModelClientConfig {
  // Distributor types have no endpoint of their own — their candidates do.
  if (def.type === "round_robin") {
    return {
      baseUrl: "",
      apiKey: "",
      model: def.name,
      type: def.type,
      models: def.models,
      rotate_every: def.rotate_every,
    };
  }
  const key =
    def.custom_endpoint?.api_key ??
    process.env[envKeyForType(def.type)] ??
    process.env.ANTHROPIC_API_KEY ??
    "";
  const baseUrl = def.custom_endpoint?.url ?? defaultBaseForType(def.type);
  if (!baseUrl) {
    throw new Error(`model '${def.name}' (type '${def.type}') has no endpoint configured`);
  }
  // Fail fast with a config-shaped error when a PUBLIC endpoint has no key.
  // A custom_endpoint without api_key is allowed (local/keyless servers).
  if (!key && !def.custom_endpoint) {
    throw new Error(
      `model '${def.name}' (type '${def.type}') has no API key — set custom_endpoint.api_key or $${envKeyForType(def.type)}`,
    );
  }
  return {
    baseUrl,
    apiKey: key,
    model: def.name,
    type: def.type,
    custom_endpoint: def.custom_endpoint,
    models: def.models,
    rotate_every: def.rotate_every,
  };
}

/** Map a model_type to the env var holding its API key (Python's convention). */
export function envKeyForType(type: string): string {
  switch (type) {
    case "openai":
    case "azure_openai":
    case "azure_foundry_openai":
    case "custom_openai":
    case "chatgpt_oauth":
    case "copilot":
    case "synthetic":
      return "OPENAI_API_KEY";
    case "cerebras":
      return "CEREBRAS_API_KEY";
    case "openrouter":
      return "OPENROUTER_API_KEY";
    case "zai_coding":
    case "zai_api":
      return "ZAI_API_KEY";
    case "minimax":
      return "MINIMAX_API_KEY";
    case "gemini":
    case "custom_gemini":
    case "gemini_oauth":
      return "GEMINI_API_KEY";
    case "anthropic":
    case "custom_anthropic":
    case "claude_code":
    case "aws_bedrock":
    default:
      return "ANTHROPIC_API_KEY";
  }
}

/** Default base URL when no custom_endpoint is set (Python's per-type defaults). */
export function defaultBaseForType(type: string): string | undefined {
  switch (type) {
    case "anthropic":
    case "custom_anthropic":
    case "claude_code":
    case "aws_bedrock":
      return "https://api.anthropic.com";
    case "openai":
    case "azure_openai":
    case "azure_foundry_openai":
    case "chatgpt_oauth":
      return "https://api.openai.com/v1";
    case "copilot":
      return "https://api.githubcopilot.com";
    case "cerebras":
      return "https://api.cerebras.ai/v1";
    case "openrouter":
      return "https://openrouter.ai/api/v1";
    case "zai_coding":
    case "zai_api":
      return "https://api.z.ai/api/paas/v4";
    case "minimax":
      return "https://api.minimaxi.chat/v1";
    case "gemini":
    case "custom_gemini":
      return "https://generativelanguage.googleapis.com";
    default:
      return undefined; // custom_* / synthetic must supply a custom_endpoint
  }
}

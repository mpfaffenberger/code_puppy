# Pydantic AI v2 Migration Research Report (Phase 0.1)

**Prepared by:** web-retriever-16afc4
**Date:** 2026-08-15
**Baseline:** `pydantic-ai-slim==1.56.0` → **Latest release: `v2.31.0` (2026-08-14)**

**Version timeline (from GitHub releases + Upgrade Guide):**
- v2.0.0b1 (2026-05-20, forked from v1.100.0) … b7 (2026-06-10, forked from v1.107.0)
- **v2.0.0 stable: 2026-06-23**
- v1 line still maintained for security fixes (latest: v1.107.5, 2026-08-13)
- v2 line latest: **v2.31.0 (2026-08-14)**

**Primary sources:**
- Upgrade Guide (canonical breaking-change list): https://pydantic.dev/docs/ai/project/changelog/
- V1 → V2 Migration Map (name-for-name lookup): https://pydantic.dev/docs/ai/overview/migration/
- GitHub Releases: https://github.com/pydantic/pydantic-ai/releases

---

## A. Cancellation

**Verdict: v2 has a full first-party graceful-cancellation API (v2.26.0), and the "cancel actually closes the HTTP/SSE stream" guarantee is baked into the `StreamedResponse` contract. Several relevant fixes landed *after* 1.56.0 on both lines.**

### First-party cancellation API — introduced in v2.26.0 (PR #6497, #6498)

Source: https://github.com/pydantic/pydantic-ai/pull/6497 and v2.26.0 release notes; docs: https://pydantic.dev/docs/ai/core-concepts/agent/ ("Cancelling a Run").

Four first-party surfaces, all ending the run with `RunCancelled` (an ordinary catchable `AgentRunError`, **not** a `CancelledError`):

| Where you cancel from | API | Run ends with |
|---|---|---|
| Outside the run (stop button, another thread) | `CancellationToken` — `agent.run(prompt, cancellation_token=token)`; `token.cancel()` is idempotent, thread-safe; works on `run`, `run_sync`, `run_stream`, `run_stream_sync`, `run_stream_events`, `iter`; one token can govern several runs; only way to interrupt a blocked `run_sync()` | `RunCancelled` |
| Inside a tool / `event_stream_handler` / capability hook | `RunContext.cancel()` (returns normally; cancellation delivered at next `await`; tool return value discarded) | `RunCancelled` |
| Consuming `run_stream_events()` | `AgentRunEvents.cancel()` on the yielded handle (safe from another task) — handle promoted to public in v2.26.0 (#6498) | `RunCancelled` |
| Driving the graph via `agent.iter()` | `AgentRun.cancel()` | `RunCancelled` |
| Environment cancels you (`task.cancel()`, `asyncio.timeout()`, TaskGroup, Ctrl+C/shutdown) | nothing — `CancelledError` propagates **unchanged**, but now *carries the run state*: recover it with `RunCancelled.from_cancellation(exc)` | `CancelledError` |

`RunCancelled` carries the full `AgentRunResult` accessor surface: `all_messages()` / `new_messages()` (+ `_json` variants), `response`, `timestamp`, `usage`, `metadata`, `run_id`, `conversation_id` — a complete detached snapshot including partial streamed content and completed tool results. Interrupted history is resumable: pass it as `message_history` and pydantic-ai auto-repairs dangling tool calls with synthesized `ToolReturnPart`s ("Reusing interrupted history" in agent docs).

The interrupted `ModelResponse`/`ModelRequest` is recorded with a new `state='interrupted'` field (`ModelRequest.state` added in #5364, v2.0.0b1; also visible via `capture_run_messages()`).

Caveats documented: external cancellation always wins over first-party when they race (Python 3.11+); Python 3.10 has best-effort semantics (`from_cancellation()` traverses `__context__`, only on the first `await` of the cancelled task). Cancellation is terminal — hooks can observe/clean up but cannot recover the run.

### Does cancelling close the underlying HTTP/SSE stream? Yes — explicit contract

`pydantic_ai.models.StreamedResponse` (https://pydantic.dev/docs/ai/api/models/base/) now specifies:

- `async def cancel()` — "Cancel local stream consumption and request provider shutdown"; sets `cancelled=True` then delegates to `close_stream()`.
- `async def close_stream()` — **"Model classes must override this to close the local stream and, where the provider SDK exposes one, its transport."** Integrations that can't support local cancellation leave the default so `cancel()` fails clearly.
- `get_stream_cancel_errors()` — returns transport-error types expected when `cancel()` tears the stream down; default covers httpx-iterating SDKs (Anthropic, OpenAI, Groq, Mistral, Google GenAI, HuggingFace); gRPC/botocore models override.
- `cancelled: bool` and `state: ModelResponseState` attributes.
- `run_stream` responses also expose `await result.cancel()` directly (see "Message History After Cancellation" in agent docs).

Usage on cancelled streams is documented as partial/best-effort (final usage events may never arrive; some providers keep generating server-side) — do not use for cost-critical accounting.

### Fix timeline between 1.56.0 and v2.31.0 (from `releases?q=cancel`)

| Release | Fix | PR |
|---|---|---|
| v1.29.0 *(pre-baseline, FYI)* | Suppress broken resource errors if cancelling | #3675 |
| v1.42.0 *(pre-baseline)* | Cancel tool calls when `Agent.run`/`run_stream_events` coroutine is cancelled | #3961 |
| **v1.64.0** | Cancel sibling tasks on any exception in parallel tool execution | #4502 |
| **v1.92.0** | **"Clean up streaming responses on cancellation"** — the SSE/HTTP stream-teardown fix | #5313 |
| **v1.92.0** | **anyio cancel-scope fix:** "Fix attempted exit cancel scope in different task by running MCP session in a dedicated task" | #4514 |
| v2.1.0 | Prevent `cancel()` flipping complete state on finished stream | #5795 |
| v2.2.0 | Suppress `ClosedResourceError` when cancelling a graph run mid-send | #6149 |
| v2.22.0 | Fix Temporal workflow livelock when anyio scope cancellation hits an in-flight activity await | #6892 |
| **v2.26.0** | First-party cancellation (`CancellationToken`, `AgentRun.cancel()`, `RunContext.cancel()`, `RunCancelled`); `AgentRunEvents` handle with `cancel()` | #6497, #6498 |
| v2.28.0 | Test cancellation of concurrent `PeekableAsyncStream` pulls | #7023 |
| v2.29.0 | Fix concurrent provider stream shutdown | #7375 |

### anyio requirement (important)

v2's `pydantic_ai_slim/pyproject.toml` (main) pins **`anyio>=4.7.0`** with this comment: *"`anyio>=4.7.0` is required for cancellation delivery our streaming teardown relies on: on 4.6.0 and below, `test_streaming_handoff_survives_absorbed_cancellation` deadlocks (#6422)."* Ensure our lockfile has anyio ≥ 4.7.0 post-upgrade.

---

## B. History Management

**Verdict: `Agent(history_processors=...)` is removed in v2 (deprecated in v1.100.0) and replaced by the `ProcessHistory` capability (PR #5425). Semantics are otherwise the same — processors now *replace* the run's stored history, which is the sanctioned way to persist mutated history. The "must end with a ModelRequest" invariant still exists in v2.**

### ProcessHistory capability

Source: https://pydantic.dev/docs/ai/capabilities/process-history/ and https://pydantic.dev/docs/ai/core-concepts/message-history/#processing-message-history

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelMessage

def keep_recent(messages: list[ModelMessage]) -> list[ModelMessage]:
    return messages[-5:]

agent = Agent('openai:gpt-5.2', capabilities=[ProcessHistory(keep_recent)])
```

- Processor may be sync or async; may optionally take `RunContext` as first param (type hints resolved at runtime — annotations must be importable at runtime, else `UserError`).
- Multiple `ProcessHistory` capabilities apply in registration order.
- **`ProcessHistory` is documented as "a thin wrapper around the `before_model_request` lifecycle hook"** — hook that directly via `capabilities=[Hooks(before_model_request=fn)]` for richer control (full `RunContext` + `ModelRequestContext`, and the ability to short-circuit the model call with `SkipModelRequest(response)`).

### Persistence of mutated history — yes, public

Docs state explicitly: *"History processors **replace the message history in the state** with the processed messages, including the new user prompt part"* — i.e. `result.all_messages()` after the run reflects the processed history, so persisting mutated history between runs is first-class (copy first if you need the original). Caveats documented: preserve tool-call/return pairing; preserve `ToolAvailabilityDeltaPart`s for deferred tools; set `run_id=ctx.run_id` on inserted messages if they should appear in `new_messages()`.

### "Must end with ModelRequest" — still enforced in v2

Verified in source (`pydantic_ai/_agent_graph.py` on main, line ~1528):
`raise exceptions.UserError('Processed history must end with a `ModelRequest`.')`
(plus a new sibling: resuming a suspended turn requires history ending with a suspended `ModelResponse`, line ~1691). **Our existing "history must end with ModelRequest" handling must stay.**

### New context-management surface (all new since 1.56.0)

- **Provider-native compaction capabilities** (https://pydantic.dev/docs/ai/capabilities/compaction/): `OpenAICompaction` (OpenAI Responses API) and `AnthropicCompaction`, producing `CompactionPart` boundaries in history. (Note: the v1 `OpenAICompaction(instructions=...)` argument is removed in v2 per the migration map.) Anthropic also has `AnthropicModelSettings.anthropic_context_management` for server-side threshold-triggered compaction.
- **Pydantic AI Harness** (separate first-party package, https://pydantic.dev/docs/ai/harness/compaction/): ready-made model-agnostic strategies — sliding-window trimming, clearing old tool results, deduplicating repeated file reads, clamping oversized parts, LLM summarization, and a `TieredCompaction` orchestrator (recommended default) that escalates cheap→expensive.
- **Harness `StepPersistence`** capability for saving/resuming/forking whole agent-run state (replaces the removed `pydantic_graph.persistence`).
- v1.101.0 / v2.0.0b2+: pending message queue (`ctx.enqueue` / `agent_run.enqueue`) for injecting messages into run history mid-run.

---

## C. Anthropic Prompt Caching

**Verdict: fully supported, and mostly already available in our 1.56.0 baseline. `CachePoint`, `anthropic_cache_instructions`, `anthropic_cache_tool_definitions` (and `anthropic_cache_messages`) predate 1.56.0; TTL (`'5m'`/`'1h'`) support was added in v1.20.0 (#3450); *automatic* caching (`anthropic_cache`) was added in v1.83.0 (#4840) — after our baseline.**

Source: https://pydantic.dev/docs/ai/models/anthropic/#prompt-caching and https://pydantic.dev/docs/ai/api/models/anthropic/

### AnthropicModelSettings cache fields (v2.31.0)

All typed `bool | Literal['5m', '1h']` — `True` means TTL `'5m'`; pass `'1h'` for the extended TTL directly (no manual beta header needed; there is also `anthropic_betas: list[AnthropicBetaParam]` for arbitrary beta flags, merged with auto-added betas and `extra_headers['anthropic-beta']`):

- `anthropic_cache` — **automatic caching** (top-level `cache_control`; server moves the breakpoint forward each turn). Added v1.83.0 (#4840). On Bedrock/Vertex falls back to per-block caching on the last user message.
- `anthropic_cache_instructions` — cache_control on the last system prompt block.
- `anthropic_cache_tool_definitions` — cache_control on the last tool definition.
- `anthropic_cache_messages` — per-block cache_control on last message content block (for Anthropic-compatible gateways/proxies like OpenRouter/LiteLLM/MiniMax that don't support the top-level parameter). Mutually exclusive with `anthropic_cache`. (Per-block behavior fixed in v1.88.0, #5227.)

### CachePoint

`from pydantic_ai import CachePoint` — insert as a user-content part to cache everything before it:

```python
result = agent.run_sync([
    'Long context from documentation...',
    CachePoint(),   # cache everything up to this point
    'First question',
])
```

`CachePoint` also works on Bedrock (leading-CachePoint edge fixed in v2.28.0, #7071) and, since v1.107.0 / v2.0.0b7, on **OpenRouter** (#4604).

### Usage example (comprehensive strategy, from the docs)

```python
agent = Agent(
    'anthropic:claude-sonnet-4-6',
    instructions='Detailed instructions...',
    model_settings=AnthropicModelSettings(
        anthropic_cache=True,                   # server auto-caches last block
        anthropic_cache_instructions=True,      # cache system instructions (5m)
        anthropic_cache_tool_definitions='1h',  # cache tool defs with 1h TTL
    ),
)
```

### Extras worth knowing

- **4-cache-point limit auto-managed**: pydantic-ai trims excess explicit breakpoints (oldest first) so requests never error.
- **Smart instruction caching**: with `anthropic_cache_instructions`, static instructions are sorted before dynamic ones and the breakpoint is placed after the last *static* block (`ModelRequestParameters.instruction_parts` carries the static/dynamic metadata) — dynamic instructions don't bust the cache.
- Cache stats on `result.usage` (a **property** in v2): `cache_write_tokens`, `cache_read_tokens`, `cache_hit_ratio`.
- v2.26.0 added `Model.resolve_prompt_cache_retention(model_settings) -> timedelta | None` (#7254) — resolves effective retention from provider-specific settings (longest wins).
- Harness has a `WarnOnCacheBusts` capability (https://pydantic.dev/docs/ai/harness/warn-on-cache-busts/).

---

## D. Model ABC / StreamedResponse / ModelRequestParameters changes (1.56.0 → 2.31.0)

Source: https://pydantic.dev/docs/ai/api/models/base/ + Upgrade Guide. Impact on our three custom `Model` subclasses:

### Breaking / must-change

1. **`StreamedResponse.usage()` method → `usage` property** (PR #5546, v2.0.0b1; deprecation-warned on late v1). Custom subclasses that call or override `usage()` must change.
2. **`Model.profile` / `ModelProfile` is a `TypedDict(total=False)`**, not a dataclass (#5481). Attribute reads become `profile.get('field', default)`; `profile.update()`/`from_profile()` removed → `merge_profile()`; `isinstance(profile, XProfile)` raises `TypeError` at runtime. Resolution order: `DEFAULT_PROFILE` → `Provider.model_profile(model_name)` → user `profile=` (partial dict merged, or `Callable[[ModelProfile], ModelProfile]` for full replace). Resolved profiles now carry **cross-class fields** (v1 filtered them) — custom models reading foreign-profile keys may see new values.
3. **Model-name resolution**: bare prefix-less names (`Agent('gpt-5')`) raise `UserError` (#5464); `openai:` prefix now means the Responses API (#5469).
4. If you subclass and implement `request_stream`, note `run_context: RunContext[Any] | None = None` parameter and required `model_request_parameters` on `StreamedResponse` (both since v0.7.0 — already in 1.56.0 baseline, listed for completeness).

### New surface custom models should implement/know about

- **`AbstractModel`** base (shared identity for request-response and realtime models) with `model_id` (`'provider:model_name'`), `label`, `base_url`, `system`, and **`__aenter__`/`__aexit__`** (provider HTTP-client lifecycle).
- **`prepare_request(model_settings, model_request_parameters)`** — merges the model's own `settings` with per-request settings and applies `customize_request_parameters`; subclasses should call it at the start of `request`/`request_stream`.
- **`prepare_messages(messages, model_request_parameters=None)`** — framework-called message-prep normalizing cross-provider parts (native tool-search parts, non-leading system prompts, realtime `SpeechPart`s); normally not overridden.
- **`count_tokens(...) -> RequestUsage`** — used by `UsageLimits(count_tokens_before_request=True)`.
- **`compact_messages(...)`** — optional; provider-native compaction.
- **`cancel_suspended_response(response)`**, **`continuation_delay(response)`** — suspended/background-turn support (OpenAI background mode, Anthropic `pause_turn`).
- **`resolve_prompt_cache_retention(model_settings) -> timedelta | None`** (v2.26.0).
- **`supported_native_tools()` classmethod** (default empty — must declare); `supported_tool_deferral_modes` / `supported_tool_addition_modes` frozensets for hidden/deferred-tool rendering.
- `compaction_requires_encrypted_content` / `compaction_retains_standing_prompt` class flags.

### StreamedResponse — new members custom stream classes must handle

- `cancel()`, **`close_stream()` (override this or cancellation deliberately fails)**, `get_stream_cancel_errors()`, `cancelled`, `state: ModelResponseState` (`'complete'` default; `'interrupted'`, `'incomplete'` states exist), `provider_url`, `time_to_first_chunk(request_start)`.
- `FinalResultEvent` yielded alongside `PartStartEvent`/`PartDeltaEvent` (since v0.7.0, in baseline).

### ModelRequestParameters — significantly extended

New fields custom models receive (mostly consumable read-only): `declared_function_tools`, `declared_tool_defs`, `deferred_capability_ids`, `revealed_tool_names`, `tool_visibility` (+ `visibility_of(name)`), **`instruction_parts`** (static vs dynamic instruction metadata — what Anthropic/Bedrock use for cache-boundary placement), `thinking: ThinkingLevel | None` (unified thinking config resolved by `prepare_request`), and `with_default_output_mode(...)`.

### Misc renames hitting model code

- `Usage` → `RunUsage`; per-response usage is `RequestUsage`; `request_tokens`/`response_tokens` → `input_tokens`/`output_tokens` (#5476).
- `ModelResponse.vendor_details` → `provider_details`; `vendor_id`/`provider_request_id` → `provider_response_id`; `price()` → `cost()`.
- `pydantic_ai.models.cached_async_http_client` → **`create_async_http_client()`** (each call returns a new client; lifecycle managed by the Provider).
- `known_model_names()` — new public way to enumerate `KnownModelName` (v1.107.0).

---

## E. Tool-Call Interception (replacing our `_tool_manager.ToolManager` monkey-patch)

**Verdict: v2 gives us multiple public, layered APIs — the monkey-patch can be fully retired.** Also note: **the module we patch was renamed** — v2 has public `pydantic_ai.tool_manager` (no underscore; `ToolManager`, `ParallelExecutionMode` are documented API), so the v1 `pydantic_ai._tool_manager` patch would break on import anyway.

### 1. Lifecycle hooks via the `Hooks` capability (the headline v2 feature)

Source: https://pydantic.dev/docs/ai/core-concepts/hooks/ — `from pydantic_ai.capabilities import Hooks`.

Tool-relevant hook points (each with before/after/wrap/error variants, sync or async, decorator `@hooks.on.*` or constructor kwargs):

- **`before_tool_execute` / `after_tool_execute` / `tool_execute` (wrap) / `tool_execute_error`** — fire around function-tool execution; receive `call: ToolCallPart`, `tool_def: ToolDefinition`, `args: ValidatedToolArgs` (validated dict).
  - **Rewrite args**: return a modified `ValidatedToolArgs` from `before_tool_execute`.
  - **Block/short-circuit a call**: `raise SkipToolExecution(result)` from `before_tool_execute` or the wrap hook — the tool body never runs, `result` is returned to the model.
  - **Defer/require approval dynamically**: raise `ApprovalRequired` / `CallDeferred` from `before_tool_execute`.
  - **Fail/retry**: raise `ModelRetry` or `ToolFailed` from tool hooks.
- **`before_tool_validate` / `after_tool_validate` / `tool_validate` / `tool_validate_error`** — around JSON-args parsing; `raise SkipToolValidation(args)` to bypass validation.
- **Per-tool filtering**: `@hooks.on.before_tool_execute(tools=['send_email'])` — hook only fires for named tools.
- **Timeouts**: every hook takes `timeout=` (raises `HookTimeoutError`).
- **`prepare_tools` / `prepare_output_tools` hooks** (or the standalone `PrepareTools` capability, replacing `Agent(prepare_tools=...)`) — filter/modify `ToolDefinition`s per step; filtering also blocks execution.  v2 behavior change: a prepare callback returning `None` now raises `TypeError` (return `[]` for "no tools") — #5188/#5668, hard error since v2.0.0b4.
- Hook ordering is defined (before_* in capability order, after_* reverse, wrap_* nests as middleware) and hooks compose across capabilities.

### 2. Toolset wrappers (all public, all in v2; importable from `pydantic_ai`)

Source: https://pydantic.dev/docs/ai/tools-toolsets/toolsets/

- **`WrapperToolset`** — subclass and override `async def call_tool(self, name, tool_args, ctx, tool)`; call `super().call_tool(...)` for pre/post interception at the toolset level. Exported from top-level `pydantic_ai`.
- **`RenamedToolset`** / `toolset.renamed({new: old})` — **rename tools** (the docs explicitly note `PreparedToolset` cannot rename; use this).
- **`PrefixedToolset`** / `.prefixed('weather')` — prefix names to avoid collisions.
- **`FilteredToolset`** / `.filtered(lambda ctx, tool_def: ...)`.
- **`PreparedToolset`** / `.prepared(fn)` — per-step `ToolDefinition` rewriting (descriptions, schemas).
- **`ApprovalRequiredToolset`** / `.approval_required(fn)` — dynamic human-in-the-loop gating, integrating with `DeferredToolRequests`/`DeferredToolResults` (renamed from v1 `DeferredToolCalls`; `DeferredToolset` → `ExternalToolset`).
- `.with_metadata(...)` and the `SetToolMetadata` capability for tagging tool defs.

### 3. MCP-specific: `MCPToolset(process_tool_call=...)`

Source: https://pydantic.dev/docs/ai/mcp/client/#tool-call-customization

```python
from pydantic_ai.mcp import CallToolFunc, MCPToolset, ToolResult

async def process_tool_call(ctx: RunContext[int], call_tool: CallToolFunc,
                            name: str, tool_args: dict[str, Any]) -> ToolResult:
    return await call_tool(name, tool_args, {'deps': ctx.deps})

toolset = MCPToolset(..., process_tool_call=process_tool_call)
```

### 4. Deferred tools

`DeferredToolRequests` (calls + approvals) / `DeferredToolResults` (`requests.build_results(approve_all=True)` helper), `ExternalToolset`, `requires_approval=True` on tool registration, `ApprovalRequired`/`CallDeferred` exceptions, and the `HandleDeferredToolCalls` capability / `hooks.on.deferred_tool_calls` hook for resolving deferrals inline during a run.

### Migration recommendation

Map our monkey-patch behaviors onto: pre-call arg rewriting + blocking → `Hooks.before_tool_execute` (+ `SkipToolExecution`); global logging/timing → `WrapperToolset` or `wrap_tool_execute`; renames → `RenamedToolset`; per-step visibility → `PrepareTools` capability. If we truly still need `ToolManager`, it's now public API (`pydantic_ai.tool_manager.ToolManager`), but no patching should be necessary.

---

## F. Breaking-Changes Catalogue (v1.56.0 → v2)

Canonical sources: Upgrade Guide https://pydantic.dev/docs/ai/project/changelog/ (v2.0.0b1 entry) and Migration Map https://pydantic.dev/docs/ai/overview/migration/. Recommended path: upgrade to latest v1 (≥1.100.0, currently 1.107.5) → resolve every `PydanticAIDeprecationWarning` → then jump to v2. **V1-serialized message history (via `ModelMessagesTypeAdapter`) still deserializes in v2** (old `part_kind` wire values and field aliases retained).

### Not covered by deprecation warnings (review even on clean v1)

- **Generic defaults `None` → `object`**: unparameterized `Agent(...)` is now `Agent[object, str]`; update `Agent[None, ...]`, `RunContext[None]`, `Tool[None]` annotations (type-checking only). #5307
- **`pydantic_graph.persistence` and `pydantic_graph.mermaid` removed** (no pydantic_graph replacement; Harness `StepPersistence` for run-state save/resume; `Graph.render()` for diagrams). #5470
- **`ModelProfile` → TypedDict** (see section D). #5481

### Default-behavior changes (same API, different runtime)

- **Slimmer default extras**: bare `pip install pydantic-ai` now = `pydantic-ai-slim[openai,anthropic,google,cli,mcp,evals,web,retries,logfire]`. `bedrock`, `groq`, `mistral`, `cohere`, `xai`, `huggingface`, `temporal`, `ag-ui`, `ui`, `spec` no longer bundled — add explicitly. Removed outright: `outlines-*`, `vertexai` (now under `google`), `fastmcp` (shim removed), `a2a` (moved upstream to `fasta2a`). #5467
- **`end_strategy` default `'early'` → `'graceful'`**: function tools called alongside a successful output tool now *run*; tools execute in emission order; `sequential=True` is now a per-tool barrier (and applies to output tools via `ToolOutput(sequential=True)`); batch-serial is `agent.parallel_tool_call_execution_mode('sequential')`. Set `end_strategy='early'` to keep v1 behavior. #5339
- **Instrumentation defaults to version 5** with `gen_ai.aggregated_usage.*` on run spans (`use_aggregated_usage_attribute_names=True` default); version 1 + `event_mode=`/`logger_provider=` removed; versions 2–4 warn. #5523
- **`capture_run_messages()` now captures interrupted partials** (`state='interrupted'`; new `ModelRequest.state` field) — exact-count assertions on error paths may break. #5364
- **Output tool events**: dedicated `OutputToolCallEvent`/`OutputToolResultEvent` (no longer `FunctionTool*Event`); `BuiltinToolCallEvent`/`BuiltinToolResultEvent` **removed** (native tools surface only via `PartStartEvent`/`PartDeltaEvent`). #5332, #5476

### Silent flips announced by v1 warnings

- **`openai:` prefix → Responses API** (`OpenAIResponsesModel`); use `openai-chat:` for Chat Completions. #5334/#5469
- **`WebSearch`/`WebFetch` are native-only by default** (raise on unsupported models — restore fallbacks with `WebSearch(local='duckduckgo')`, `WebFetch(local=True)`); **`MCP(url=...)` runs the server locally by default** (`native=True` for v1 remote behavior). #5331/#5333

### Renames/removals (full table in migration map; highlights)

| v1 | v2 |
|---|---|
| `Agent(history_processors=...)` | `Agent(capabilities=[ProcessHistory(...)])` |
| `Agent(event_stream_handler=...)` | `Agent(capabilities=[ProcessEventStream(...)])` — **the `event_stream_handler=` argument on `run()`/`run_sync()`/`run_stream()`/`iter()` is unchanged** |
| `Agent(prepare_tools=...)` | `Agent(capabilities=[PrepareTools(...)])` |
| `Agent(builtin_tools=[...])` | `Agent(capabilities=[NativeTool(...)])`; `pydantic_ai.builtin_tools` → `pydantic_ai.native_tools`; `builtin=` → `native=`; `UrlContextTool` → `WebFetchTool` |
| `Agent(instrument=...)` | `Agent(capabilities=[Instrumentation(...)])` (property/`instrument_all()`/`InstrumentedModel` unchanged) |
| `Agent(mcp_servers=[...])` / `Agent.run_mcp_servers()` | `Agent(toolsets=[...])` / `async with agent:` |
| `MCPServerStdio`/`MCPServerSSE`/`MCPServerStreamableHTTP`/`MCPServerHTTP`, `FastMCPToolset` | **`pydantic_ai.mcp.MCPToolset`** (transport inferred;  defaults differ: `max_retries`, `read_timeout`, `init_timeout`, `elicitation_handler`); `load_mcp_servers` → `load_mcp_toolsets` |
| `OpenAIModel`/`OpenAIModelSettings` | `OpenAIChatModel`/`OpenAIChatModelSettings`; `system_prompt_role` moves into the profile |
| `GeminiModel`, `GoogleGLAProvider`/`GoogleVertexProvider`, prefixes `google-gla:`/`google-vertex:` | `GoogleModel`, `GoogleProvider`/`GoogleCloudProvider`, `google:`/`google-cloud:` |
| `grok:` / `GrokProvider` | `xai:` / `XaiProvider` + `XaiModel` |
| `Usage`, `request_tokens`, `response_tokens` | `RunUsage`, `input_tokens`, `output_tokens` |
| `UsageLimits(request_tokens_limit=, response_tokens_limit=)` | `UsageLimits(input_tokens_limit=, output_tokens_limit=)` — plus new `cost_limit` (Decimal USD), `tool_calls_limit`, `per_request_input_tokens_limit`, `count_tokens_before_request` |
| `result.usage()`, `result.timestamp()`, `stream.get()` | properties: `result.usage`, `result.timestamp`, `stream.response` (#5263) |
| `StreamedRunResult.stream` / `.stream_structured` / `.stream_responses()` / `.validate_structured_output` | `stream_output` / `stream_response` / `stream_response()` (singular; old `is_last` ≙ `response.state != 'incomplete'`) / `validate_response_output` |
| `async for e in agent.run_stream_events(...)` | `async with agent.run_stream_events(...) as events:` — **async context manager only** (#5440) |
| `DeferredToolCalls`(.tool_calls) / `DeferredToolset` | `DeferredToolRequests`(.calls) / `ExternalToolset` |
| `FunctionToolset.tool()` on context-free callable | `tool_plain()` — `tool()` now requires a `RunContext` first param (#5462) |
| `pydantic_ai.ext.aci`, Outlines model/provider | Removed (wrap with `Tool.from_schema`; no Outlines replacement) |
| `Agent.to_a2a()` | `fasta2a.pydantic_ai.agent_to_a2a` (`fasta2a[pydantic-ai]>=0.6.1`) |
| `Agent.to_ag_ui()`/`AGUIApp` | `pydantic_ai.ui.ag_ui.AGUIAdapter` |
| `cached_async_http_client` | `create_async_http_client()` |
| `from pydantic_graph.beta import GraphBuilder` | `from pydantic_graph import GraphBuilder` |

Pydantic Evals: keyword-only args, `Dataset(name=...)` required, `Evaluator.name` → `get_serialization_name()`, etc. (#5547–#5556).

### Minimum SDK / dependency versions (v2 main, `pydantic_ai_slim/pyproject.toml`)

- Python **>=3.10**; `pydantic>=2.12`; `httpx>=0.27`; **`anyio>=4.7.0`** (cancellation-critical, see A)
- **`openai>=2.45.0`** (+ `tiktoken>=0.12.0`)
- **`anthropic>=0.108.0`**
- `google-genai>=1.70.0`
- **MCP: `fastmcp-slim[client]>=3.3.0,<5`** — v2's MCP client is built on the FastMCP client (pulls the `mcp` SDK transitively; FastMCP 4 / MCP SDK v2 supported alongside FastMCP 3 as of **v2.29.0**, #6738). We no longer pin `mcp` directly.
- `groq>=0.25.0`, `mistralai>=2.4.2,!=2.4.6`, `boto3>=1.42.63`, `xai-sdk>=1.14.0`, `logfire[httpx]>=4.16.0`

---

## G. Misc

### `pydantic_ai.models.get_user_agent`

**Still exists in v2** (verified in `pydantic_ai_slim/pydantic_ai/models/__init__.py` on main):

```python
@cache
def get_user_agent() -> str:
    """Get the user agent string for the HTTP client."""
    return f'pydantic-ai/{__version__}'
```

It is importable but `@cache`-d and **not** in the documented API reference page; there is still **no public "set a custom User-Agent" API — our workaround must stay** if we override the UA on pydantic-ai-created clients. The *supported* route is to construct our own `httpx.AsyncClient(headers={'User-Agent': ...})` and pass it as `http_client=` to the provider (or use `create_async_http_client()` as a template — it sets `headers={'User-Agent': get_user_agent()}`). Note `cached_async_http_client` → `create_async_http_client()` rename if we touch that path.

### `RunContext` import location

`RunContext` is **still defined in the private module `pydantic_ai._run_context`** in v2 (verified on main), so our two `from pydantic_ai._run_context import RunContext` imports would technically keep working — but they're private and fragile. **Migrate both files to the public import**: `from pydantic_ai import RunContext` (re-exported top-level via `pydantic_ai.tools`). Also note the generic default change: `RunContext[None]` annotations should become `RunContext[object]` (or a real deps type) under v2's `object` default.

Bonus (relevant to our monkey-patch, section E): `pydantic_ai._tool_manager` was made **public as `pydantic_ai.tool_manager`** in v2 (its `ToolManager` and `ParallelExecutionMode` are cross-referenced in official API docs) — any import of the underscore path must be updated regardless of whether we keep patching (we shouldn't; see E).

---

## Migration-design implications (summary for the planning agent)

1. **Two-hop upgrade**: 1.56.0 → 1.107.5 (resolve all deprecation warnings) → 2.31.0. The Upgrade Guide explicitly blesses this path.
2. **Delete the ToolManager monkey-patch**; rebuild on `Hooks` (before/wrap `tool_execute`, `SkipToolExecution`) + `WrapperToolset`/`RenamedToolset`/`PrepareTools`.
3. **Custom Model subclasses**: `usage` property, TypedDict profiles, implement `close_stream()` (else our new cancellation UX silently degrades), adopt `prepare_request()`, audit `ModelRequestParameters` field usage.
4. **Cancellation**: replace any ad-hoc task-cancel plumbing with `CancellationToken` + `RunCancelled` (v2.26.0+); pin `anyio>=4.7.0`; keep `state='interrupted'` histories and resume them directly.
5. **History**: `history_processors=` → `ProcessHistory` capability; the end-with-`ModelRequest` invariant is unchanged; consider Harness `TieredCompaction` instead of bespoke summarization.
6. **Anthropic caching**: everything we need (`CachePoint`, `anthropic_cache_instructions/_tool_definitions`, `'1h'` TTLs) exists at our baseline; adopt `anthropic_cache=True` (v1.83.0+) for auto-caching during the v1 hop.
7. **Packaging**: audit extras after the slimmer-default change; MCP dependency becomes `fastmcp-slim`.

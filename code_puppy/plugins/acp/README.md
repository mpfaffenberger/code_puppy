# `acp` — Code Puppy as a native ACP agent

Run Code Puppy inside any ACP-capable editor's agent panel (e.g.
[Zed](https://github.com/zed-industries/zed))
by speaking the **Agent Client Protocol (ACP)** — the same JSON-RPC-over-stdio
protocol these editors use to host Gemini CLI and Claude Code.

This plugin is built on the **official [`agent-client-protocol`](https://pypi.org/project/agent-client-protocol/)
Python SDK** (`acp`). The SDK owns the wire — stdio binding, JSON-RPC framing,
typed Pydantic models, and the bidirectional connection — so this plugin is
pure *behaviour*: mapping ACP sessions to Code Puppy agents, translating
runtime events into `session/update`s, and routing Code Puppy's I/O + approval
edges to the client.

> **Status:** live over real stdio. Implemented: `initialize`, `session/new`,
> `session/load` (replays persisted history), `session/prompt`,
> `session/cancel` (also kills local shells), `session/list`, `session/close`,
> `session/fork` (duplicates history), `session/resume` (rehydrates across
restarts), `session/set_mode`, `session/set_config_option`. Assistant text +
> thinking stream as `agent_message_chunk` / `agent_thought_chunk`; tool calls
> stream as `tool_call` / `tool_call_update` (with `kind`, file `locations`,
> friendly titles, and inline diffs); slash commands are advertised via
> `available_commands_update` **and executed** when the client sends one. Prompt
> turns report token usage; **image** input is accepted. Client-injected MCP
> servers and multi-root `additionalDirectories` are honoured. Workspace file
> I/O and shell delegate to the client (capability-gated), and **permissions**
> for file writes and shell commands are surfaced in the client's own allow/deny
> dialog in non-yolo mode.
>
> Not implemented: `elicitation/*` (the SDK's connection API exposes no
> elicitation call in 0.10.1), `plan` updates (Code Puppy has no plan model),
> and the unstable `document/*` / `nes/*` / `providers/*` surface.

---

## How the client hosts an external agent

1. The client launches the agent as a **subprocess** and talks JSON-RPC 2.0 over the
   process's **stdin/stdout** (stderr is free for logging).
2. The agent advertises what it can do in an `initialize` handshake; the client
   advertises what *it* can do (read/write files, run terminals, permissions).
3. The client drives with `session/new` then `session/prompt`; the agent streams
   progress back with `session/update` notifications and can call *back into
   the client* for file I/O, terminals, and permission prompts.

This is a **bidirectional** JSON-RPC connection: both sides send requests.

### Registering us in a client

Registration is client-specific. Example — Zed's `settings.json`:

```jsonc
{
  "agent_servers": {
    "Code Puppy": { "command": "code-puppy", "args": ["--acp"], "env": {} }
  }
}
```

Then "Code Puppy" appears in the agent panel's "New Thread" menu.

---

## Why the official SDK

We adopted `agent-client-protocol` instead of hand-rolling JSON-RPC because it
gives us, maintained and spec-accurate:

* **Typed models** for the entire protocol (`InitializeResponse`,
  `SessionNotification`, all content/capability/tool-call types).
* **`acp.run_agent(agent)`** — binds stdio, frames ndjson JSON-RPC, parses
  params into models, dispatches to our `Agent`, and hands us a `Client`
  connection for talking back.
* **Update builders** (`update_agent_message_text`, `start_tool_call`, …).

Net effect: ~400 lines of hand-rolled transport/framing/capability code
deleted, correct-by-construction wire behaviour, and a PR that speaks the
project's own library. Our two small **core seams stay unchanged** — only the
plugin's protocol layer changed.

---

## Design decisions (locked in)

| Decision | Choice |
|----------|--------|
| **Protocol layer** | **Official `acp` SDK.** We implement its `Agent` interface; `acp.run_agent` owns stdio + framing. |
| **Who does I/O** | **Delegated to the client when the client supports it.** Workspace file reads/writes go through the client's `fs/read_text_file` / `fs/write_text_file` (edits land in the client's diff UI; reads see unsaved buffers), and shell commands run via the client's `terminal/*`. This rides two small, general **I/O-backend seams** in core (`code_puppy/tools/io_backends.py`): a sync `FileSystemBackend` and an async `CommandExecutor`, both `None` by default (local I/O) and installed by this plugin, capability-gated, after `initialize`. Internal writes (config, session state, agent metadata) deliberately stay local — only *workspace* edits reroute (via `common.write_project_file`). |
| **Permissions** | **the client is the authority (non-yolo).** Every approval — file writes and shell commands — is surfaced in the client's own allow/deny dialog via `session/request_permission`. No yolo forcing, no terminal prompts. |
| **Entry point** | A `--acp` CLI flag contributed via the `register_cli_args` hook; `handle_cli_args` boots the agent (on its own loop, in a thread) and short-circuits normal TUI startup. |
| **Core footprint** | Small, general, additive core seams — **no monkeypatching**: (1) a pluggable *approval backend* (`common.set_approval_backend`), (2) a *workspace write* wrapper (`common.write_project_file`) + backend-aware `_read_file`, and (3) `FileSystemBackend` / `CommandExecutor` registries (`tools/io_backends.py`). Each is useful to any non-terminal embedder, not ACP-specific. Everything else is this plugin + existing public hooks + the SDK. |

### Permissions in non-yolo mode (the important part)

Code Puppy has two approval edges. In a headless ACP server there is no TTY, so
the built-in stdin prompt would **fail closed** (auto-deny every file op — a
latent bug this integration also fixes). We route both edges to the client *without*
forcing yolo and *without* patching tool logic:

* **File operations** use the **approval-backend seam** in `tools.common`. Sync
  file tools run in Code Puppy's tool threadpool, so the backend
  (`permissions.py`) bridges to the ACP event loop with
  `run_coroutine_threadsafe` to ask the client via the SDK's `request_permission`,
  then blocks the worker thread for the answer. The loop is free to service the
  round-trip → no deadlock (guarded against being called on the loop itself).
* **Shell commands** use the async `run_shell_command` hook (it runs on the ACP
  loop and can `await` the client directly).

Both edges **fail closed** if the connection drops or the client errors.

---

## Module layout

Every file stays well under the 600-line cap and owns one concern.

| File | Responsibility |
|------|----------------|
| `register_callbacks.py` | Register the `--acp` flag; when present, redirect the console to stderr, run `acp.run_agent(CodePuppyAgent())` on its own loop in a thread, and return `{"handled": True}` so the TUI never starts. |
| `agent.py` | `CodePuppyAgent(acp.Agent)` — the SDK agent implementation: initialize, new/load/resume/fork/list/close session, prompt, cancel, set_session_mode/model, set_config_option, authenticate, plus `on_connect` (stashes the client handle + installs approvals). |
| `capabilities.py` | Declarative capability negotiation in SDK models: our `AgentCapabilities`, and parsing the client's `ClientCapabilities` into `(fs_read, fs_write, terminal)`. |
| `content.py` | Parse ACP prompt content blocks → text + multimodal attachments (`BinaryContent` / `ImageUrl`), honouring `embeddedContext` + `image`. |
| `session.py` | `ACPSession`: one ACP session ⇄ one `BaseAgent` + its `_message_history`. Runs each turn as a cancellable `asyncio.Task`; persists history after each turn; owns the final-result fallback. |
| `commands.py` | Execute client-typed `/slash` commands via `command_handler`, capturing MessageBus output and forwarding it (never touches stdin). |
| `persistence.py` | Pickle each session's history under `AUTOSAVE_DIR/acp` keyed by session id, plus an ACP metadata sidecar (`cwd` + `additionalDirectories` + title). Rehydrate on `load`/`resume`/`fork`; enumerate for `session/list` (`list_persisted`); tombstone on `session/close` (`delete`). |
| `replay.py` | On `load`/`resume`, stream the rehydrated history back to the client as ordered `session/update`s (user / agent text / thinking / past tool calls) so the client rebuilds the thread UI. |
| `mcp_config.py` | Translate client-injected ACP MCP server specs → pydantic-ai servers on the session agent. |
| `session_config.py` | Build the model list (surfaced as ACP *modes*) + safe config options; apply `set_mode` / `set_config_option`. |
| `bridge.py` | `EventBridge`: registers `stream_event` / `pre_tool_call` / `post_tool_call` hooks and translates them into SDK `session/update`s via `connection.session_update`. (Hooks, **not** MessageBus — see *Event source*.) |
| `permissions.py` | Wires Code Puppy's two approval edges to the client via the SDK's `request_permission`: the `tools.common` approval backend (files, cross-thread) and the `run_shell_command` hook (shell). Fails closed. |
| `io_delegation.py` | `DelegatedFileSystemBackend` (sync, cross-thread) + `DelegatedCommandExecutor` (async terminal lifecycle) that plug into the core I/O seams, capability-gated. |
| `state.py` | Process-wide run context: the SDK connection + its loop, the active session id, and the open-tool-call stack — so the permission/I/O seams (plain module functions) can reach the running connection and correlate events. |

```
Client ──stdin──▶ acp.run_agent ──▶ CodePuppyAgent.prompt ──▶ ACPSession ──▶ agent.run_with_mcp
                                                                 │
   stream_event / pre_tool_call / post_tool_call hooks fire ─────┘
      │
      ▼
  bridge ──▶ connection.session_update ──stdout──▶ the client
      ▲
      │ agent needs to read/write/run/ask
      └── permissions / io_delegation ──▶ connection.{request_permission,
              read_text_file, write_text_file, create_terminal, …} ──▶ the client
```

### Event source: hooks, not the MessageBus

Code Puppy's `MessageBus` is **single-consumer** and *buffers* until a renderer
attaches; agent text streams through pydantic-ai's `event_stream_handler`
(which fires the `stream_event` callback), not the bus. So the bridge taps the
**callback hooks** — the same seam the shipping `frontend_emitter` plugin uses:

| Hook | Fires with | ACP update |
|------|-----------|------------|
| `stream_event` (`part_delta`, `TextPartDelta`) | `event_data.delta.content_delta` | `agent_message_chunk` |
| `stream_event` (`part_delta`, `ThinkingPartDelta`) | `event_data.delta.content_delta` | `agent_thought_chunk` |
| `pre_tool_call` | `tool_name`, `tool_args` | `tool_call` (status `in_progress`) |
| `post_tool_call` | `tool_name`, `result` | `tool_call_update` (status `completed`/`failed`) |

Run context (active session id, whether text streamed, the open-tool-call
stack) lives in `state`, so `bridge`, `permissions`, and `io_delegation` share
one source of truth. `set_session_context(session_id)` is also set around each
run so streamed events carry the right session id.

### stdout is sacred

ACP speaks JSON-RPC on **stdout**, so nothing else may write there. At boot we
point the streaming console (`set_streaming_console`) and the root logger at
**stderr**; the interactive path that normally configures the console is
short-circuited in `--acp` mode.

### Streaming-off fallback

`use_streaming` is config-gated. When off, no `stream_event` deltas fire, so the
session sends the return value of `run_with_mcp` as a single final
`agent_message_chunk`. `state` tracks whether any text streamed so we never
double-send.

---

## ACP surface we implement

### Inbound (the client → us)

| Method | Behaviour |
|--------|-----------|
| `initialize` | Negotiate version + capabilities; install capability-gated I/O delegation. |
| `authenticate` / `logout` | No-op (auth is via Code Puppy's own model config/env). |
| `session/new` | Create an `ACPSession` (fresh `BaseAgent`) from `cwd` + `additionalDirectories`; attach client `mcpServers`; return models + config options; schedule `available_commands_update`. |
| `session/load` | Re-open a thread: **replay persisted history into the agent AND stream it back to the client** as `session/update`s so the client rebuilds the thread UI. |
| `session/resume` | Rehydrate + replay a session across a restart from persisted history. |
| `session/fork` | Branch a session: copy its history into a new id. Works on a live session **or** one persisted by a prior process (rehydrated from disk), so forking survives a restart. |
| `session/prompt` | Parse content blocks (text + image attachments) or execute a `/slash` command; run the agent as a cancellable task; stream updates; return stop reason **+ token usage**. |
| `session/cancel` | Cancel the in-flight run's task **and kill local shells** → `cancelled`. |
| `session/list` / `session/close` | List sessions (**live in-memory + persisted on disk**, deduped, so threads survive a restart and stay revivable) / drop a session (also deletes its persisted copy). |
| `session/set_mode` | Switch the active model, rebinding the session agent (history preserved). Code Puppy surfaces its model list as ACP *modes* (0.11 removed the separate models API). |
| `session/set_config_option` | Apply a safe config change (streaming toggle); never yolo. |
| `session/set_mode` | No-op (Code Puppy has one mode). |

Not implemented: `elicitation/*` (the SDK connection exposes no elicitation
call in 0.10.1), `plan` updates (no native plan model), and the unstable
`document/*` / `nes/*` / `providers/*` surface. The SDK router resolves any
unimplemented method to a clean "method not found", so we advertise honestly
and stub nothing.

### Outbound notifications (us → the client) — `session/update`

`agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update`,
`available_commands_update`. Tool calls carry human-friendly titles
("Edit foo.py", "Run: pytest"), a `kind`, file `locations`, and — on completion
— the unified diff as an inline `diff` content block so edits are visible in
the client's tool-call entry.

### Outbound requests (us → the client)

`session/request_permission` (approvals), and — when the client advertises the
capability — `fs/read_text_file`, `fs/write_text_file`, and the `terminal/*`
family (`create`, `wait_for_exit`, `output`, `kill`, `release`).

---

## Session & history model

- One ACP session id ⇄ one `ACPSession` ⇄ one `BaseAgent` instance.
- Multi-turn is native: `_message_history` persists across `session/prompt`
  calls within the same session.
- `cwd` from `session/new` anchors that session's tools.

---

## Interactive tools (`ask_user_question`)

Code Puppy's `ask_user_question` renders a terminal picker and reads stdin —
neither is available over ACP (stdin *is* the JSON-RPC pipe). The tool's own
`isatty()` guard already makes it fail closed there (no stdout corruption), but
the default "not an interactive terminal" error is a dead end.

So in ACP mode the `EventBridge` **blocks** `ask_user_question` at the
`pre_tool_call` seam (before any tool-call entry is opened) and returns guidance
steering the model to *ask the user directly in its normal text response* — which
the client renders as a regular assistant message the user can reply to. This is
the pragmatic stand-in until ACP ratifies structured **elicitation** (currently
only an [RFD](https://agentclientprotocol.com), not in stable v1 — no client,
including Zed, implements it yet). When elicitation lands and the SDK exposes a
connection method for it, this block becomes a real native picker.

---

## Testing

`tests/test_acp_plugin.py` drives `CodePuppyAgent` directly against a fake SDK
connection (no real stdio) and covers:

- capability negotiation + client-cap parsing,
- content-block flattening (incl. embedded resources),
- lifecycle: initialize / new_session / prompt (stream + fallback) / cancel /
  list / close / unknown-session error,
- tool-call `kind` / `locations` / pre↔post correlation,
- the core approval-backend seam (sync + async) + the shell hook,
- the **cross-thread approval bridge** (worker thread → ACP loop → the client → back),
- I/O delegation core seams + the client fs/terminal backends (capability-gated).

Real end-to-end: `code-puppy --acp` spawned as a subprocess answers
`initialize` + `session/new` with clean JSON-RPC on stdout. Manual: point a
real client at `code-puppy --acp` via `agent_servers`.

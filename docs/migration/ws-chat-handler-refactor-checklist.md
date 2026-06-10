# WS `chat_handler.py` modularization checklist

Base branch: `feature/puppy-desk-migration`  
Maestro owner: `maestro-687542`  
Primary bead chain: `code_puppy-40g` → `code_puppy-79a` → `code_puppy-8ql` → `code_puppy-e7v`

Goal: split `code_puppy/api/ws/chat_handler.py` into smaller modules **without any protocol, persistence, session, or streaming behavior regressions**.

Last reconciled against code: 2026-06-10

---

## Non-negotiable safety invariants

- [ ] WebSocket frame shapes stay identical for all existing message types.
- [ ] Frame ordering stays identical, especially around:
  - `thinking`
  - assistant `part_start` / `part_delta` / `part_end`
  - tool call/result events
  - `stream_end`
  - final `status=done`
- [ ] Session bootstrap semantics stay identical for both new and restored sessions.
- [ ] SQLite remains the source of truth for resumed sessions.
- [ ] `switch_session` behavior stays identical, including create-if-missing flow.
- [ ] `cancel` and disconnect behavior stays identical, including background-save behavior.
- [ ] Permission request/response flow stays identical.
- [ ] Working-directory banners + session row updates stay identical.
- [ ] Command execution behavior stays identical.
- [ ] Agent/model switch persistence stays identical.
- [ ] No shared mutable WS state leaks across sessions.
- [ ] No changes to `code_puppy/command_line/`.

---

## Current extracted modules already in place

These are already good extraction boundaries and should be preserved:

- [x] `code_puppy/api/ws/chat_context.py`
  - per-message / per-agent-run ContextVar setup & cleanup
- [x] `code_puppy/api/ws/chat_turn_state.py`
  - per-turn mutable streaming/tool state
- [x] `code_puppy/api/ws/chat_turn_runner.py`
  - concurrent `run_with_mcp` execution while receiving control messages
- [x] `code_puppy/api/ws/ws_turn_preparation.py`
  - working-directory prompt injection + attachment packaging
- [x] `code_puppy/api/ws/ws_stream_drain.py`
  - drain task lifecycle shell (subscribe/start/stop/cancel)
- [x] `code_puppy/api/ws/chat_event_adapter.py`
  - assistant text/thinking frame adaptation
- [x] `code_puppy/api/ws/chat_tool_lifecycle.py`
  - tool call/result reconciliation helpers
- [x] `code_puppy/api/ws/ws_post_run.py`
  - post-run cancelled/error/no-result resolution
- [x] `code_puppy/api/ws/ws_turn_finalization.py`
  - pre/post `stream_end` tool result emission + history snapshot logic
- [x] `code_puppy/api/ws/session_persistence.py`
  - session meta payloads + final persistence/broadcast orchestration

---

## What still lives inside `chat_handler.py`

`chat_handler.py` is still carrying too many responsibilities:

- [ ] WebSocket/session bootstrap
- [ ] resumed-session replay of persisted system banners
- [ ] non-message control routing (`switch_agent`, `switch_model`, `switch_session`, etc.)
- [ ] slash-command execution
- [ ] permission-response top-level handling
- [ ] per-message orchestration for `type=message`
- [ ] inline `drain_events_concurrent()` implementation
- [ ] pre-stream SQLite upsert + user-message write
- [ ] final send/persist/status wiring
- [ ] disconnect/final cleanup

That means the next safe split should be about **removing orchestration branches**, not changing lower-level behavior.

---

## Target file layout

### Keep as-is
- `chat_context.py`
- `chat_turn_state.py`
- `chat_turn_runner.py`
- `chat_event_adapter.py`
- `chat_tool_lifecycle.py`
- `ws_turn_preparation.py`
- `ws_stream_drain.py`
- `ws_post_run.py`
- `ws_turn_finalization.py`
- `session_persistence.py`
- `send_utils.py`
- `response_frames.py`
- `schemas.py`

### Add next
- [ ] `code_puppy/api/ws/ws_session_bootstrap.py`
- [ ] `code_puppy/api/ws/ws_control_messages.py`
- [ ] `code_puppy/api/ws/ws_command_handler.py`
- [ ] `code_puppy/api/ws/ws_stream_processor.py`
- [ ] `code_puppy/api/ws/ws_prestream_persistence.py`
- [ ] `code_puppy/api/ws/ws_message_orchestrator.py`
- [ ] `code_puppy/api/ws/ws_chat_runtime.py`

### End state for `chat_handler.py`
- [ ] endpoint registration only
- [ ] create runtime state
- [ ] call bootstrap helper
- [ ] receive loop delegates to control/message router
- [ ] final cleanup helper calls only

---

## File-by-file checklist

### 1) `code_puppy/api/ws/ws_chat_runtime.py` — create connection-scoped runtime state

Purpose: remove the long list of mutable local variables from `websocket_chat()`.

Create a runtime dataclass that holds only per-connection mutable state:

- [ ] `session_id`
- [ ] `ctx`
- [ ] `session_title`
- [ ] `session_working_directory`
- [ ] `session_pinned`
- [ ] `last_context_sent_directory`
- [ ] `existing_history`
- [ ] `agent`
- [ ] `agent_name`
- [ ] `model_name`
- [ ] `active_drain_task`
- [ ] `active_agent_task` (if still needed at outer level)
- [ ] `stop_draining`

Rules:
- [ ] instantiate inside `websocket_chat()` only
- [ ] no module-level mutable state
- [ ] use `field(default_factory=...)` for mutable fields like `asyncio.Event`
- [ ] keep it as a plain state bag, not a behavior-heavy class

Acceptance criteria:
- [ ] zero behavior change
- [ ] easier helper signatures because they take `runtime` instead of 8-12 loose arguments

---

### 2) `code_puppy/api/ws/ws_session_bootstrap.py` — extract connect / restore / init flow

Move the following logic out of `chat_handler.py`:

- [ ] validate incoming `session_id`
- [ ] generate timestamp-based session id when absent
- [ ] check SQLite for existing session
- [ ] create or load session via `session_manager`
- [ ] set `sender.session_id` and `sender.ctx`
- [ ] mark session active
- [ ] initialize process tracking
- [ ] set MessageBus session context
- [ ] derive initial `agent`, `agent_name`, `model_name`
- [ ] write initial config/directory system messages for brand-new sessions only
- [ ] send initial `ServerSystem(Connected!)`
- [ ] send session meta snapshot
- [ ] send `ServerSessionRestored` for resumed sessions
- [ ] replay persisted system rows (`init`, `config`, `directory`)

Recommended public helpers:
- [ ] `initialize_ws_session(...) -> WebSocketChatRuntime`
- [ ] `send_session_meta_snapshot(...)`
- [ ] `replay_restored_system_messages(...)`

Safety notes:
- [ ] preserve fallback behavior when `get_or_load_session()` returns `None`
- [ ] preserve SQLite-first semantics
- [ ] preserve warning-only behavior for bootstrap persistence failures

Suggested tests:
- [ ] new session bootstrap writes initial config row
- [ ] resumed session sends `session_restored`
- [ ] resumed session replays persisted system rows
- [ ] invalid `session_id` closes with policy violation behavior unchanged

---

### 3) `code_puppy/api/ws/ws_control_messages.py` — extract non-chat control routing

This file should handle all top-level message types except `type=message`.

Move branches for:
- [ ] `switch_agent`
- [ ] `switch_model`
- [ ] `switch_session`
- [ ] `set_working_directory`
- [ ] `update_session_meta`
- [ ] `get_config`
- [ ] `set_config`
- [ ] `cancel`
- [ ] `permission_response`

Recommended shape:
- [ ] one public dispatcher: `handle_control_message(...) -> bool`
- [ ] returns `True` when the message was handled and outer loop should continue
- [ ] returns `False` when caller should treat it as a chat message or unknown type

Internal helper split:
- [ ] `_handle_switch_agent(...)`
- [ ] `_handle_switch_model(...)`
- [ ] `_handle_switch_session(...)`
- [ ] `_handle_set_working_directory(...)`
- [ ] `_handle_update_session_meta(...)`
- [ ] `_handle_get_config(...)`
- [ ] `_handle_set_config(...)`
- [ ] `_handle_cancel(...)`
- [ ] `_handle_permission_response(...)`

Safety notes:
- [ ] preserve current send frames exactly
- [ ] preserve `cancel_active_streaming(...)` calls before session switch/cancel
- [ ] preserve create-if-missing semantics in `switch_session`
- [ ] preserve exact SQLite writes for directory changes and meta updates
- [ ] preserve `continue` behavior after handled control messages

Suggested tests:
- [ ] switch session existing target
- [ ] switch session create-new target
- [ ] set unchanged working directory returns `unchanged=True`
- [ ] invalid working directory returns failure payload
- [ ] update session meta does not zero counters in SQLite
- [ ] cancel cancels drain + in-flight task + sends cancelled status
- [ ] permission response routes request id unchanged

---

### 4) `code_puppy/api/ws/ws_command_handler.py` — isolate slash-command execution

Move the `type=command` branch into its own helper.

Move logic for:
- [ ] `/help` special rendering path
- [ ] generic `handle_command(command_str)` path
- [ ] `ServerCommandResult` success/error payload creation
- [ ] traceback logging on failure

Recommended public helper:
- [ ] `handle_command_message(...) -> bool`

Safety notes:
- [ ] do not change command backend
- [ ] do not modify `code_puppy/command_line/`
- [ ] preserve `/help` rich-to-plain rendering behavior

Suggested tests:
- [ ] `/help` returns rendered text
- [ ] normal command returns success payload
- [ ] exception returns `ServerCommandResult(success=False)`

---

### 5) `code_puppy/api/ws/ws_stream_processor.py` — extract `drain_events_concurrent()` internals

This is the largest remaining extraction still embedded inline.

Move from nested function into a module-level helper:
- [ ] event batching with `asyncio.wait_for(..., timeout=0.01)`
- [ ] `agent_invoked` forwarding
- [ ] `tool_call_start` forwarding
- [ ] `tool_call_complete` forwarding
- [ ] stream `part_start` routing
- [ ] stream `part_delta` routing
- [ ] stream `part_end` routing
- [ ] final queue drain collecting last text deltas
- [ ] websocket-close detection during sends
- [ ] batch/debug logging

Recommended public helper:
- [ ] `drain_stream_events(...)`

Recommended support dataclass if signatures become too wide:
- [ ] `StreamProcessorDeps` holding sender callbacks, logger, metadata, etc.

Safety notes:
- [ ] preserve exact event ordering
- [ ] preserve tool alias/group-id bookkeeping
- [ ] preserve final drain behavior after stop signal
- [ ] preserve current close-detection behavior from send exceptions

Suggested tests:
- [ ] part_start text/thinking adaptation still identical
- [ ] tool-call start/delta/end path still identical
- [ ] final drain still captures trailing deltas
- [ ] websocket-close error stops drain gracefully

---

### 6) `code_puppy/api/ws/ws_prestream_persistence.py` — isolate pre-stream SQLite writes

Move the pre-run persistence block out of `chat_handler.py`:

- [ ] session `upsert_session(...)`
- [ ] `ModelRequest(UserPromptPart(...))` construction
- [ ] `get_next_seq(...)`
- [ ] `insert_message(...)`
- [ ] attachment metadata JSON persistence
- [ ] warning-only failure handling

Recommended public helper:
- [ ] `persist_user_message_before_stream(...)`

Safety notes:
- [ ] preserve current `seq` behavior
- [ ] preserve warning-only semantics on failure
- [ ] preserve use of `original_user_message` not file-context-expanded content

Suggested tests:
- [ ] writes user message after existing system rows
- [ ] stores attachments JSON when provided
- [ ] pre-stream failure remains non-fatal

---

### 7) `code_puppy/api/ws/ws_message_orchestrator.py` — extract the `type=message` happy path

This module should own the high-level orchestration of a user chat turn.

Move orchestration for:
- [ ] setup of per-message context
- [ ] requested per-message model switch
- [ ] frontend `model_settings` application
- [ ] empty-message rejection
- [ ] user echo frame
- [ ] `WebSocketTurnState()` creation
- [ ] stream drain lifecycle start/stop
- [ ] send `status=thinking`
- [ ] working directory prompt context setup
- [ ] `prepare_turn_input(...)`
- [ ] `persist_user_message_before_stream(...)`
- [ ] `execute_turn_runner(...)`
- [ ] deferred switch/create-session handoff
- [ ] `resolve_post_run_resolution(...)`
- [ ] non-streaming assistant frame fallback
- [ ] B1 `stream_end` path
- [ ] `finalize_turn_history(...)`
- [ ] `persist_session_turn_and_broadcast(...)`
- [ ] final `status=done`
- [ ] error handling + `persist_error_payload(...)`
- [ ] final `cleanup_message_context(...)`

Recommended public helper:
- [ ] `handle_chat_message(...) -> dict | None`
  - returns deferred control message when one arrives during streaming
  - returns `None` otherwise

Safety notes:
- [ ] preserve exact post-run decision tree order
- [ ] preserve `stream_end` placement relative to tool results
- [ ] preserve history snapshot-before-await behavior
- [ ] preserve final `status=done` placement

Suggested tests:
- [ ] no-result, cancelled, exception, and success paths
- [ ] non-streaming fallback still emits start/delta/end triplet
- [ ] B1 streaming emits tool results before `stream_end`
- [ ] deferred `switch_session` during active run still background-saves and returns control

---

### 8) `code_puppy/api/ws/chat_handler.py` — reduce to thin endpoint wiring

After the extractions above, `chat_handler.py` should only:

- [ ] accept websocket
- [ ] construct `WebSocketSender`
- [ ] call session bootstrap helper
- [ ] loop on `receive_json()`
- [ ] route to `handle_command_message(...)`, `handle_control_message(...)`, and `handle_chat_message(...)`
- [ ] if chat helper returns deferred message, re-dispatch it
- [ ] handle top-level disconnect/runtime fallback
- [ ] call final cleanup helper(s)

Hard stop criteria before calling this “done”:
- [ ] no nested `drain_events_concurrent()` function remains
- [ ] no 150+ line control-message branch chain remains
- [ ] top-level loop is readable without scrolling through protocol details

Target outcome:
- [ ] `chat_handler.py` becomes endpoint composition/orchestration only
- [ ] most behavior-specific tests point at extracted modules, not the giant handler

---

## Recommended execution order

### Bead `code_puppy-40g` — planning + bootstrap/control split
- [ ] add `ws_chat_runtime.py`
- [ ] add `ws_session_bootstrap.py`
- [ ] add `ws_control_messages.py`
- [ ] trim corresponding branches from `chat_handler.py`

### Bead `code_puppy-79a` — stream/message execution split
- [ ] add `ws_stream_processor.py`
- [ ] add `ws_prestream_persistence.py`
- [ ] add `ws_message_orchestrator.py`
- [ ] trim `type=message` branch from `chat_handler.py`

### Bead `code_puppy-8ql` — regression coverage
- [ ] add focused tests for every new helper module
- [ ] keep existing WS tests green
- [ ] cover all four risk categories: happy-path / edge / boundary / negative

### Bead `code_puppy-e7v` — final docs/validation
- [ ] update this checklist with final landed module set
- [ ] capture residual risks
- [ ] record exact validation commands + outcomes

---

## Validation checklist

### Minimum automated validation
- [ ] `ruff check --fix code_puppy/api/ws`
- [ ] `ruff format code_puppy/api/ws docs/migration/ws-chat-handler-refactor-checklist.md`
- [ ] `pytest -q code_puppy/api/ws/tests`
- [ ] `pytest -q tests/test_messaging_bus.py`

### Coverage matrix requirement for this refactor

| Risk tag | Required coverage | Status |
|---|---|---|
| happy-path | normal new session + message + stream success | [ ] |
| edge | restored session replay + switch-session during stream | [ ] |
| boundary | unchanged CWD, empty message, unknown config key | [ ] |
| negative | invalid session id, command failure, send failure, cancel/disconnect | [ ] |

### Adversarial review prompts
- [ ] What bug would still pass if frame order changed around `stream_end`?
- [ ] What bug would still pass if resumed-session system banners stopped replaying?
- [ ] What bug would still pass if `switch_session` forgot to mark old session inactive?
- [ ] What bug would still pass if pre-stream SQLite insert wrote the wrong message content?
- [ ] What bug would still pass if a close/send exception did not stop the drain loop?

### Manual spot checks
- [ ] resume an existing WS session and confirm restored messages + system banners appear
- [ ] switch sessions without reconnecting
- [ ] interrupt a running command/tool
- [ ] set working directory twice and confirm second event is `unchanged=True`
- [ ] run at least one slash command and `/help`

---

## Definition of done

This refactor is only done when all of the following are true:

- [ ] `chat_handler.py` is mostly endpoint wiring, not business logic
- [ ] each extracted file has a single narrow responsibility
- [ ] existing frontend-visible behavior is unchanged
- [ ] focused tests cover the extracted helpers
- [ ] WS regression suite passes
- [ ] messaging regression suite passes
- [ ] residual risks are documented explicitly
- [ ] this checklist is updated to reflect the final landed state


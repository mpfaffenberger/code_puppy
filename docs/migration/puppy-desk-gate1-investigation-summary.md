# Puppy Desk Migration — Gate 1 Investigation Summary

Saved to avoid losing detailed context during summarization.

## User Requirements and Constraints

- Migrate divergent source branch `feature/puppy-desk` from `../../../../dev/puppy/code-puppy` into the current repo.
- Preserve features under `code_puppy/api/ws`, including:
  - WebSocket session handling
  - event streaming
  - tool args/results
  - streaming deltas
  - strict message ordering
  - permission handling
  - CWD setup
  - active agent/model handling
  - local config updates
  - async independent session management
  - multiple parallel sessions
- Do **not touch `main`**.
- Work from a new branch off `main` / migration branch, not directly on `main`.
- Keep legacy code until user explicitly approves cleanup.
- Duplicate current legacy into a `legacy/` namespace before behavioral changes.
- Use the same WS route only after full parity tests pass.
- No application code changes until explicit approval.
- Prioritize safety over speed.
- Plan for migration, GUGI testing, and cleanup.
- Modularize long files, especially very large WS handlers.

## Planning History

- Generated migration task plans:
  - `.maestro/tasks-20260601-093100-bzoj.json`, pack `zg6w`.
  - `.maestro/tasks-20260601-093500-giep.json`, pack `kzh5`.
- User approved Gate 1: read-only inventory/migration matrix.
- Attempted BD issue creation from the plan; tool reported success but created `0` BD issues.
- Current continuation plan generated as:
  - `.maestro/tasks-20260601-094423-9on6.json`, pack `vtyn`.

## Local Repo / Worktree Observations

- Working area root: `/Users/s0m0961/Documents/dev/personal/puppy/code_puppy.worktrees`.
- Candidate directories found:
  - `external-ws-replica-test/`
  - `h37o-input-notifier/`
  - `maestro-checkpoints-20260526/`
  - `puppy-desk-migration/`
- Important branches/statuses:
  - `/code_puppy.worktrees/external-ws-replica-test`
    - branch: `test/external-ws-migration-replica`
    - clean
    - no `code_puppy/api` directory
  - `/code_puppy.worktrees/puppy-desk-migration`
    - branch: `feature/puppy-desk-migration`
    - modified files:
      - `code_puppy/config.py`
      - `code_puppy/plugins/frontend_emitter/emitter.py`
      - `code_puppy/session_storage.py`
      - `code_puppy/tools/command_runner.py`
      - `pyproject.toml`
      - `uv.lock`
  - source repo `/Users/s0m0961/Documents/dev/puppy/code-puppy`
    - branch: `feature/puppy-desk`
    - modified files:
      - `code_puppy/model_utils.py`
      - `uv.lock`
    - untracked:
      - `scripts/run_ws_streaming_api_server.sh`

## Branch Diffs and Scope

- Source `feature/puppy-desk` vs `main` has 53 relevant changed/added files around:
  - `code_puppy/api/**`
  - `code_puppy/plugins/frontend_emitter/**`
  - `code_puppy/config.py`
  - `code_puppy/session_storage.py`
  - `code_puppy/tools/command_runner.py`
  - `pyproject.toml`
  - `uv.lock`
- Diff stat source vs main:
  - ~53 files changed
  - ~15.5k insertions
  - ~547 deletions
- Largest additions include:
  - `api/ws/chat_handler.py`
  - `api/db/queries.py`
  - `api/templates/chat.html`
  - API tests and WS tests
  - config/session storage/tool runner/frontend emitter changes
- `puppy-desk-migration` vs `main` appears to already contain a port of many API files.
- `external-ws-replica-test` appears useful for newer frontend emitter work but does not contain the API/WS stack.

## API / WS Stack Inventory

Source `feature/puppy-desk` includes full API/WS stack:

- `code_puppy/api/app.py`
- `code_puppy/api/db/`
- `code_puppy/api/permission_plugin.py`
- `code_puppy/api/permissions.py`
- routers
- `code_puppy/api/session_cache.py`
- `code_puppy/api/session_context.py`
- templates
- tests
- `code_puppy/api/websocket.py`
- `code_puppy/api/ws/` handlers, schemas, runtime, tests

`puppy-desk-migration` has a similar stack and extra tests:

- `test_config_router_schema.py`
- `test_session_model_compat.py`

`external-ws-replica-test` has no `code_puppy/api` directory but has newer frontend emitter files.

## Key Feature Search Findings

Searched for terms including:

- `assistant_message_delta`
- `ServerToolResult`
- `permission_response`
- `switch_session`
- `switch_model`
- `set_cwd`
- `working_directory`
- `b1_streaming_used`
- `stop_draining`
- `current_tool_group_id`

Findings:

- `schemas.py` defines protocol messages for:
  - `switch_model`
  - `switch_session`
  - `set_working_directory`
  - `permission_response`
  - `assistant_message_delta`
  - `tool_result`
- Tests assert `ServerToolResult(...)` includes `tool_group_id`.
- `background_save.py` handles `working_directory`.
- `session_runtime_manager.py` stores `working_directory`.

## Frontend Emitter Findings

Source `feature/puppy-desk` frontend emitter:

- Files:
  - `__init__.py`
  - `emitter.py`
  - `register_callbacks.py`
- No `session_context.py`.
- Supports:
  - session-scoped subscriptions
  - global legacy subscriptions
  - per-session recent event buffers
  - `emit_event(event_type, data, session_id=None)`
  - `subscribe(session_id=None)`
  - `unsubscribe(queue)`
  - `get_recent_events(session_id=None)`
  - `get_subscriber_count()`
  - `clear_recent_events()`
- Global subscribers receive all events.
- Session subscribers receive only matching session events.

`puppy-desk-migration` and `external-ws-replica-test` frontend emitter:

- Include `session_context.py`.
- External replica has a newer design with:
  - ContextVar fallback via `current_emitter_session_id`
  - explicit `session_id` kwarg precedence
  - wildcard and session-filtered subscribers
  - `_Subscriber` dataclass records
  - single recent events buffer
  - legacy `_subscribers` compatibility
  - double-delivery prevention.

Frontend callback module findings:

- Emits frontend events for:
  - pre-tool call
  - post-tool call
  - stream events
  - agent invocation
- Reads WebSocket context from permission plugin to attach session ID.
- Suppresses duplicate tool events during structured streaming.
- Sanitizes tool args and stream data.
- Serializes complex/Pydantic tool results.
- Preserves structured list/dict args when payload is small enough for frontend rendering.

## Key File Size / Hash Observations

Source `feature/puppy-desk`:

- `frontend_emitter/emitter.py`: ~6.2 KB
- `register_callbacks.py`: ~12.1 KB
- no `session_context.py`
- `api/ws/chat_handler.py`: ~238 KB
- `api/ws/schemas.py`: ~19.5 KB
- `api/session_context.py`: ~24.2 KB
- `api/db/queries.py`: ~40.8 KB

`puppy-desk-migration`:

- `frontend_emitter/emitter.py`: ~10 KB
- `register_callbacks.py`: ~14.9 KB
- `session_context.py`: ~2.1 KB
- `api/ws/chat_handler.py`: ~235.8 KB
- `api/ws/schemas.py`: same hash as source
- `api/session_context.py`: ~24.9 KB
- `api/db/queries.py`: same hash as source

`external-ws-replica-test`:

- emitter files similar to migration
- no API/WS files

## Source Git History Highlights

Recent source commits touched:

- daily backend logs
- DB empty-row guard
- `tool_group_id` consistency
- JSON serialization of tool results
- `RuntimeError` disconnect handling
- tracking `tool_group_id` outside drain scope
- pre-`stream_end` tool result extraction
- duck-typed tool return extraction
- emitter tool-event suppression scopes
- unified tool IDs / duplicate suppression
- schema migration of tool/terminal/permission messages
- schema migration of config/command/streaming messages
- advisory client validation
- protocol model Literal defaults
- `send_typed` helper migration

## Key Source File Summaries

### `code_puppy/api/websocket.py`

- Thin endpoint registrar delegating to `code_puppy.api.ws` handlers:
  - events
  - chat
  - terminal
  - health
  - sessions
- Re-exports attachment builder and connection manager for backward compatibility.

### `code_puppy/api/ws/schemas.py`

- Defines protocol version `1.0.0`.
- Defines typed Pydantic WebSocket protocol models.
- Client message types include:
  - `message`
  - `switch_agent`
  - `switch_model`
  - `switch_session`
  - `set_working_directory`
  - `update_session_meta`
  - `get_config`
  - `set_config`
  - `command`
  - `cancel`
  - `permission_response`
- Server message types include:
  - `system`
  - `session_restored`
  - `session_switched`
  - `working_directory_changed`
  - `session_meta_updated`
  - `config_value`
  - `command_result`
  - `status`
  - `user_message`
  - `assistant_message_start`
  - `assistant_message_delta`
  - `assistant_message_end`
  - `tool_call`
  - `tool_result`
  - `tool_return`
  - `agent_invoked`
  - `response`
  - `stream_end`
  - `error`
  - `permission_request`
  - `cancelled`

### `api/ws/runtime/session_runtime_manager.py`

- Async manager for per-session runtimes.
- Supports runtime creation, lookup, cancellation, removal, idle cleanup, and active task count.
- Designed for multiple hot sessions / multiplexed chat.

### `api/ws/runtime/session_runtime.py`

- Dataclass holding per-session runtime:
  - active task
  - cancel event
  - lock
  - created/last-used timestamps.

### `api/permissions.py`

- WebSocket permission request system.
- Maintains global `permission_futures`.
- `request_permission` sends typed permission request, waits up to 300s, honors YOLO mode, fails safe if no WS.
- `handle_permission_response` resolves pending futures.

### `api/permission_plugin.py`

- Uses task-scoped `ContextVar` for WS permission context.
- Has suppression flag for duplicate frontend emitter tool events.
- `pre_tool_call_permission` asks frontend for approval and blocks denied tools.
- Includes shell command permission handling.

### `api/ws/chat_handler.py`

Very large file, around 235–238 KB. Responsibilities include:

- Session provisioning/restoration via SQLite and `session_manager`.
- Initial config/CWD/system/session-restored messages.
- WS message handlers for:
  - switch agent
  - switch model
  - switch session
  - set working directory
  - update session metadata
  - get/set config
  - command
  - cancel
  - permission response
  - user message
- CWD persistence and unchanged-CWD messages.
- Agent streaming plus concurrent frontend emitter draining.
- Typed assistant/tool lifecycle messages:
  - `assistant_message_start`
  - `assistant_message_delta`
  - `assistant_message_end`
  - `tool_call`
  - `tool_result`
  - `stream_end`
- Tracking of active parts, collected text, pending tool calls, tool ID aliases, and tool group IDs.
- Handling deltas before starts by creating starts first.
- Accumulating tool call args deltas.
- Extracting full tool results before `stream_end`.
- Accepting permission responses and cancel while streaming.
- Supporting session switch/create while streaming through background save.

Specific inspected area around lines 2350–2530 showed:

- JSON parsing of tool args.
- `tool_group_id` generation if missing.
- Sending `ServerToolCall`.
- Storing pending tool-call metadata.
- Mapping raw tool call IDs to normalized IDs.
- Cleaning active parts.
- Handling WebSocket close during streaming.
- Final-draining queued stream events.
- Subscribing to frontend emitter by `session_id`.
- Starting concurrent drain task.

### `api/db/connection.py`

- SQLite connection singleton using `aiosqlite`.
- DB path from `PUPPY_DESK_DB`, otherwise `~/.puppy_desk/chat_messages.db`.
- Backend can create/migrate schema if frontend has not.
- Schema includes:
  - `sessions`
  - `messages`
  - `tool_calls`
  - `compaction_log`
- Tracks schema versions/migrations up to v4.
- Concurrency handled by `aiosqlite`, no threading lock.

### `api/db/queries.py`

- Large async query helper module for shared `chat_messages.db`.
- Session operations include:
  - `session_exists`
  - `get_session_row`
  - `get_session_metadata`
  - `upsert_session`
  - `update_session_stats`
  - `update_session_working_directory`
  - `update_session_meta_fields`
  - `soft_delete_session`
- Defines message sequencing/insertion helpers.
- Uses `aiosqlite` and commits/rollbacks around writes.

### `api/session_context.py`

- Multi-session isolation layer.
- Defines `SessionContext` with:
  - per-session agent
  - agent name
  - model name
  - working directory
  - title/pinned metadata
  - websocket reference
  - saved per-agent histories
  - compacted hashes
  - lazy async operation lock
- Defines validation for safe session IDs and known agent names.
- Defines `SessionManager` for:
  - create/get/destroy sessions
  - switch agents
  - preserve/restore history across agent switches
  - carry session model across agent reloads.

### `api/session_cache.py`

- LRU cache for deserialized session data.
- Uses async lock and thread pool for file-related work.
- Features:
  - max cached sessions
  - TTL expiry
  - file modification invalidation
  - pre-serialized JSON cache
  - stats for hits/misses/evictions/expirations.

## Current State / Important Notes

- No application code was modified during read-only Gate 1 investigation.
- This file itself is a documentation checkpoint requested by the user.
- Final migration matrix, options, risks, and recommendation still need to be completed.

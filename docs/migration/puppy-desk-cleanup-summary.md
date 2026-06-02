# Puppy Desk Migration — Cleanup Summary

## Current state

- Legacy puppy-desk migration behavior is considered working.
- Cleanup approval was given to remove temporary migration scaffolding.
- Active WebSocket route remains `/ws/chat`.

## Cleanup goals

- Remove `code_puppy/api/ws/legacy/` snapshot now that rollback-by-copy is no longer required.
- Reduce `chat_handler.py` size by extracting reusable protocol/error frame helpers.
- Preserve existing wire behavior with focused regression tests.

## This cleanup pass

- Deleted the temporary `code_puppy/api/ws/legacy/` reference snapshot.
- Extracted response/error frame helpers into `code_puppy/api/ws/response_frames.py`.
- Kept `/ws/chat` registration unchanged.
- Replaced Gate 2 snapshot assertions with post-cleanup route/namespace assertions.

## Follow-up modularization targets

Remaining large modules that should be split in later passes:

- `code_puppy/api/ws/chat_handler.py`
- `code_puppy/api/session_context.py`
- `code_puppy/api/db/queries.py`

Recommended next split inside `chat_handler.py`:

- drain/event lifecycle helpers
- session switch/create helpers
- persistence helpers
- typed send helpers

## Phase 2 checkpoint

- Extracted history wrapping/timestamp/token estimation helpers into `code_puppy/api/ws/history_utils.py`.
- Reduced inline persistence-preparation logic in `code_puppy/api/ws/chat_handler.py`.
- Added focused unit tests for history wrapping, timestamp extraction, attachment metadata backfill, and safe token estimation failure handling.

## Phase 3 checkpoint

### Extracted modules

- **`code_puppy/api/ws/send_utils.py`** (151 lines)
  - `WebSocketSender` class encapsulating `ws_closed`, `safe_send_json`,
    `persist_error_payload`, `send_typed`, `send_typed_tool_lifecycle`.
  - Replaces 4 nested closures (~90 lines) in `chat_handler.py`.
  - Independently testable without a live WebSocket or database.

- **`code_puppy/api/ws/session_persistence.py`** (143 lines)
  - `resolve_agent_model_meta(agent, ctx)` — or-chain fallback pattern.
  - `build_session_meta_payload(...)` — client `session_meta` frame.
  - `build_session_update_payload(...)` — broadcast payload for monitoring clients.
  - `persist_turn_to_sqlite(...)` — wraps DB write with try/except guard.

### chat_handler.py changes

- Removed inline closure definitions (safe_send_json, persist_error_payload,
  send_typed, send_typed_tool_lifecycle).
- Replaced with `WebSocketSender` construction and method aliases.
- Replaced inline agent/model meta resolution with `resolve_agent_model_meta()`.
- Replaced inline SQLite turn write with `persist_turn_to_sqlite()`.
- Replaced inline session_meta dict with `build_session_meta_payload()`.
- Replaced inline broadcast dict with `build_session_update_payload()`.
- Removed unused imports (`typing.Any`, `write_error_message_to_sqlite`,
  `write_turn_to_sqlite`, `ServerMessage`).
- `ws_closed` references replaced with `sender.ws_closed`.

### Size reduction

| File | Before | After |
|------|--------|-------|
| chat_handler.py | 3,687 lines / 220 KB | 3,586 lines / 215 KB |
| session_persistence.py | — | 143 lines |
| send_utils.py | — | 151 lines |

### Test coverage

- 22 new focused tests across `test_session_persistence.py` and `test_send_utils.py`.
- Import isolation tests confirm no eager loading of `chat_handler`.
- Full focused regression suite: 111 tests pass (0 failures).

### No wire protocol changes

- `/ws/chat` route unchanged.
- All session_meta, session_update, error persistence payloads match
  previous inline implementations exactly.
- No frontend emitter behavior changes.

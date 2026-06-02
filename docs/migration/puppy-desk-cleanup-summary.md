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

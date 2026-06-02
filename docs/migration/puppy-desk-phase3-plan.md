# Puppy Desk Migration — Phase 3 Cleanup Plan

## Objective

Continue reducing `code_puppy/api/ws/chat_handler.py` without changing the live
`/ws/chat` wire contract or the already-working puppy-desk migration behavior.
This phase should focus on extracting cohesive helper modules that are easier to
unit test and safer to evolve.

## Current baseline

- Active route remains `/ws/chat`
- Legacy snapshot under `code_puppy/api/ws/legacy/` has been removed
- `code_puppy/api/ws/__init__.py` uses lazy imports
- Response-frame helpers live in `code_puppy/api/ws/response_frames.py`
- History wrapping/timestamp/token helpers live in `code_puppy/api/ws/history_utils.py`
- `chat_handler.py` is still large and contains multiple embedded responsibilities

## Phase 3 scope

### Primary extraction seam

Extract session-save and client-broadcast preparation logic from
`chat_handler.py` into a focused helper module.

Candidate module:

- `code_puppy/api/ws/session_persistence.py`

Candidate responsibilities:

- build session meta payloads sent back to the client
- build session update payloads broadcast to session-monitoring clients
- normalize autosave timestamps/metadata fields
- centralize the SQLite turn-write call shape used by `/ws/chat`

### Secondary extraction seam

If the primary seam is clean and low risk, extract typed send/error helpers into
another focused helper module.

Candidate module:

- `code_puppy/api/ws/send_utils.py`

Candidate responsibilities:

- safe websocket JSON send wrapper
- structured error persistence wrapper
- typed message send adapters
- consistent closed-socket detection and logging

## Explicit non-goals for phase 3

- No protocol redesign
- No frontend emitter behavior changes
- No changes to active route names or namespace layout
- No migration of logic into `code_puppy/command_line/`
- No DB schema changes unless a separate approval is given

## Proposed execution order

1. Identify the exact persistence/broadcast block inside `chat_handler.py`
2. Extract pure payload-building helpers first
3. Add focused unit tests for payload assembly and fallback handling
4. Move the SQLite turn-write call wrapper if the interface remains stable
5. Re-run focused WS regression tests
6. If still low risk, extract send/error helpers in a follow-up patch set

## Validation strategy

### Automated

Minimum focused test set:

- `code_puppy/api/tests/test_streaming_protocol_transform.py`
- `code_puppy/api/tests/test_ws_history_utils.py`
- new tests for session meta/update payload building
- `code_puppy/api/tests/test_gate2_legacy_ws_namespace.py`

Add coverage for:

- session meta payload fields
- broadcast payload action selection (`created` vs `updated`)
- persistence fallback behavior when token estimation or DB writes fail
- no eager import regressions from new helper modules

### Manual / GUGI validation

After phase 3 code lands:

1. Start the backend in this repo
2. Connect the GUI/GUGI app to the migrated `/ws/chat` backend
3. Verify:
   - session creation
   - resumed session loading
   - streaming assistant output
   - tool lifecycle updates
   - session metadata updates in the UI
   - no regressions in frontend emitter behavior
4. Confirm session list updates still appear correctly after autosave

## Risks

### Low-risk

- extracting pure payload builders
- moving timestamp/metadata assembly helpers

### Medium-risk

- extracting send/error helpers that close over websocket state
- moving persistence wrappers that depend on runtime context

### Deferred/high-risk

- splitting `drain_events_concurrent`
- deeper session lifecycle/state machine changes
- DB query modularization in the same patch

## Done criteria for phase 3

- `chat_handler.py` shrinks further with no route/namespace changes
- extracted modules are independently importable and tested
- focused regression suite passes
- manual GUI/GUGI smoke test checklist is documented and run
- cleanup summary doc updated with a phase 3 checkpoint

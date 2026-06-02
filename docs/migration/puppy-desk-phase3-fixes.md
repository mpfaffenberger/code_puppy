# Phase 3 — Post-extraction fixes & next steps

> Generated 2026-06-02 after Phase 3 extraction + manual GUGI smoke test.

## Critical finding: tool calls not streaming

**Symptom:** User reported no tool calls visible in GUGI during manual test.
**Server logs confirmed:** `b1_streaming_used=False` on every agent run.

### Root cause: ContextVar bridge never wired

The frontend emitter's `emit_event()` relies on an implicit ContextVar
(`current_emitter_session_id`) to tag each event with the correct session.
The subscribe call in `chat_handler.py` uses session-filtered subscription:

```python
event_queue = subscribe(session_id=session_id)  # line ~2306
```

But `current_emitter_session_id` is **never set** anywhere in the codebase —
not in `chat_handler.py`, not on the original `feature/puppy-desk` branch.

Event routing works like this:
1. `register_callbacks.py::on_pre_tool_call()` calls `emit_event("tool_call_start", ...)`
   with **no explicit session_id**
2. `emit_event` resolves session_id via `current_emitter_session_id.get()` → `None`
3. Event is tagged `session_id=None`
4. Subscriber filtering: *"Events with session_id=None are NOT delivered
   to session-filtered subscribers"*
5. **Event is dropped** — never reaches `drain_events_concurrent`
6. `b1_streaming_used` stays `False`

**This is a pre-existing gap** — the original `feature/puppy-desk` branch also
never set the ContextVar. It was NOT caused by Phase 3 extraction.

### Fix (P0)

In `chat_handler.py`, before starting the agent run, set the ContextVar:

```python
from code_puppy.plugins.frontend_emitter.session_context import (
    current_emitter_session_id,
)

# Before agent.run_with_mcp / agent.run():
_emitter_token = current_emitter_session_id.set(session_id)

# In finally cleanup:
current_emitter_session_id.reset(_emitter_token)
```

Location: around line ~2340 (just before `run_with_mcp`) and in the
corresponding `finally` block around line ~2800.

---

## Bug 2: Stale session_id on WebSocketSender

### Problem

`WebSocketSender` is constructed at line 155 with the initial `session_id`
parameter from the URL query string. For new sessions, this is `None`.
At line 206, `session_id` gets reassigned to a generated value like
`WS_session_20260602_162504`, but the sender still holds the original `None`.

Evidence in server logs:
```
[WS:None] send_json failed for type=error ...
```

### Impact

- **Logging:** All send_utils log lines show `[WS:None]` — useless for debugging
- **Error persistence:** `persist_error_payload` checks
  `if not self._session_id: return` — silently skips DB writes for new sessions
- **No impact on sends themselves** — `safe_send_json` doesn't gate on session_id

### Fix (P1)

Option A — Add a `session_id` setter to `WebSocketSender` and call it after
session_id is generated/resolved:

```python
# In send_utils.py
@session_id.setter
def session_id(self, value: str) -> None:
    self._session_id = value

# In chat_handler.py after session_id is generated (line ~207):
sender._session_id = session_id  # or sender.session_id = session_id
```

Option B — Defer `WebSocketSender` construction until after session_id is
resolved (move from line 155 to ~line 210). This would require reworking the
early error sends that happen before session creation.

**Recommendation:** Option A — simpler, less risky.

---

## Bug 3: Session switch doesn't update sender.session_id

### Problem

Session switching at line ~577 reassigns `session_id = new_session_id` but
the sender's `_session_id` stays stale. Same stale-logging and
error-persistence issue as Bug 2, but specifically during session switches.

### Fix (P1)

Wherever `session_id` is reassigned during session switching, also update
the sender:

```python
session_id = new_session_id
sender._session_id = session_id  # sync sender
```

Locations to patch (grep `session_id =` inside switch_session blocks):
- Line ~577 (new session creation during switch)
- Line ~638 (existing session load during switch)

---

## Non-blocking issues found during investigation

### 4. `b1_streaming_used=False` fallback path (informational)

When B1 streaming doesn't fire, `chat_handler` falls through to the B2
path which reconstructs response frames from the completed agent result.
B2 does NOT stream tool calls — it only sends the final response text.

This means **the GUGI never sees tool lifecycle frames** when the ContextVar
bridge is missing. Fixing Bug 1 (ContextVar) resolves this entirely.

### 5. `app.py` plugin key access (already fixed)

`load_plugin_callbacks()` returns `{'builtin': [...], 'user': [...]}` but
`app.py` was accessing `result['external']` with bracket notation.
**Fixed:** commit `e8f6e56` — now uses `.get()` with defaults.

### 6. `ws_sessions` executor shutdown error (cosmetic)

```
ERROR code_puppy.api.app: Error shutting down ws_sessions executor:
    module 'code_puppy.api.routers.ws_sessions' has no attribute '_executor'
```

Non-blocking cosmetic error during server shutdown. Low priority.

---

## Execution plan

### Immediate (P0) — Fix tool call streaming

| Step | Action | Risk |
|------|--------|------|
| 1 | Wire `current_emitter_session_id` ContextVar in `chat_handler.py` | Low — additive, no existing behavior changed |
| 2 | Add `sender.session_id` setter to `WebSocketSender` | Low — internal property |
| 3 | Sync `sender._session_id` after session generation + switch | Low — logging/persistence only |
| 4 | Restart server, test with GUGI — verify tool_call frames appear | Validation |
| 5 | Run full test suite (111 tests) | Regression check |

### Follow-up (P1) — Tests for the fix

| Step | Action |
|------|--------|
| 6 | Add integration test: connect → send message → assert tool_call frames received |
| 7 | Add unit test: verify ContextVar is set before agent run and reset in finally |
| 8 | Add unit test: verify sender.session_id updates after session switch |

### Future phases — Further modularization

| Target | Lines | Extraction |
|--------|-------|------------|
| `drain_events_concurrent` + `drain_events_with_signal` | ~200 | → `event_drain.py` |
| Session switch/create handler | ~150 | → `session_switch.py` |
| Tool group ID resolution helpers | ~70 | → merge into `send_utils.py` or `tool_lifecycle.py` |
| `session_context.py` cleanup | ~400 | Split by concern |
| `db/queries.py` cleanup | ~260 | Split by table/domain |

### Phase 3 scorecard

| Item | Status |
|------|--------|
| `session_persistence.py` extracted | ✅ Done |
| `send_utils.py` extracted | ✅ Done |
| `chat_handler.py` uses new modules | ✅ Verified (traceback + unit tests) |
| Unit tests (22 new) | ✅ All pass |
| Full regression suite (111) | ✅ All pass |
| Wire protocol unchanged | ✅ Verified |
| ContextVar bridge for emitter | ❌ **Not wired — P0 fix needed** |
| Sender session_id sync | ❌ **Stale after generation — P1 fix needed** |
| GUGI tool call streaming | ❌ **Blocked by ContextVar bug** |

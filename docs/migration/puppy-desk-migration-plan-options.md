# Puppy Desk Migration — Gate 1 Matrix, Options, and Approval Gates

Status: **Gate 1 read-only planning + docs only**  
Base branch target: **main**  
Current working branch observed: `feature/puppy-desk-migration`  
Source branch/repo: `/Users/s0m0961/Documents/dev/puppy/code-puppy`, branch `feature/puppy-desk`  
Safety rule: **do not touch `main`; do not modify application code without explicit approval**

Related checkpoint: `docs/migration/puppy-desk-gate1-investigation-summary.md`

---

## 1. Migration Objective

Migrate the divergent `feature/puppy-desk` backend/API/WebSocket work into this repo while preserving all GUI-facing behavior needed by GUGI / Puppy Desk:

- Same final WS route, but only after parity tests pass.
- Legacy route/code preserved first in a `legacy/` namespace before behavior changes.
- No feature loss around streaming, tool calls, permissions, CWD, sessions, config, DB persistence, or multiple sessions.
- Long files must be modularized after parity is protected by tests.

---

## 2. High-Level Inventory Matrix

| Area | Source `feature/puppy-desk` | Current migration branch | Gap / Decision | Risk |
|---|---|---|---|---|
| API package | Full `code_puppy/api/**` stack added | Similar/full stack already present | Verify current branch contains all intended API files and no accidental omissions | Medium |
| WS route registrar | `api/websocket.py` delegates to `api.ws` handlers | Similar | Preserve legacy route until parity; same-route swap only after tests | High |
| WS schemas | Typed Pydantic protocol v1.0.0; source and migration same hash | Same hash | Treat as contract; freeze with schema tests | High |
| Huge chat handler | ~238 KB; central streaming/session/permission/CWD logic | ~230–236 KB; differs by small but important edits | Must first port/verify parity, then refactor behind tests | Very high |
| Runtime manager | Per-session async runtime manager | Same structure | Keep; validate parallel sessions and cancellation | High |
| Background save | Saves agent result/session metadata while switched away | Same file size/hash likely same | Validate session switch while streaming | High |
| DB connection/schema | SQLite `~/.puppy_desk/chat_messages.db`, schema/migrations to v4 | Same/similar | Need DB migration tests with temp `PUPPY_DESK_DB` | High |
| DB queries | Large async query helper; same hash in source/current | Same hash | Candidate to split after parity into session/message/tool modules | Medium |
| Session context | Source supports isolated agent/model/CWD/history | Current has compatibility helpers for missing `set_session_model` | Keep migration helper if needed; validate model switching | High |
| Permissions | WS permission futures + plugin context | Same/similar | Must validate approve/deny, timeout/fail-safe, YOLO | High |
| Frontend emitter | Source has session-scoped queues + per-session recent buffers | Current/external has newer ContextVar design | Choose final emitter design carefully; behavior must prevent cross-session leakage | High |
| Emitter callbacks | Source attaches session id via WS context and suppresses duplicate tool events | Current differs substantially | Need dedicated emitter parity tests | High |
| Config router | Source expects `CONFIG_SCHEMA` | Current has fallback if schema absent | Decide whether to preserve full schema or fallback; GUI likely benefits from full schema | Medium |
| Core config | Source contains larger `CONFIG_SCHEMA` and queue size default `10000`; current appears to remove schema and queue default returns `100` | Need explicit decision; queue size affects streaming reliability | High |
| Command runner | Source imports callback directly | Current has ImportError fallback | Keep fallback if current architecture requires; validate terminal streaming callbacks | Medium |
| Session storage | Same source/current | No action except integration validation | Low |
| Model utils | Source/current differ, source has uncommitted changes | Need inspect before migration; could affect active model handling | Medium |
| Dependencies | API requires FastAPI/aiosqlite/websockets/etc.; package files changed | `pyproject.toml` and `uv.lock` modified in current | Snyk required before testing if dependency changes are applied/retained | High |
| Tests | Source has API/WS tests; current adds config/model compatibility tests | Combine and strengthen | Must add GUGI/parity scenarios before same-route swap | High |

---

## 3. Source vs Current Migration Differences Requiring Decisions

### 3.1 `api/ws/chat_handler.py`

Observed diff current-vs-source is small but semantically important:

- Source appended a raw dict system message into agent in-memory history on CWD change.
- Current migration branch replaces that with a warning comment: do **not** append raw dicts because runtime expects typed `ModelMessage` objects and raw dict injection can corrupt later turns / `result=None` behavior.

Recommendation: **Keep the safer current behavior**, but verify the GUI still receives/persists directory banners through SQLite/system messages.

Required tests:

- Change CWD and verify WS `working_directory_changed` message.
- Verify directory system banner persists and reloads.
- Verify next agent turn after CWD change does not fail from corrupt history.

### 3.2 Frontend emitter design

Source design:

- Explicit `session_id` on `emit_event`.
- Global legacy subscribers receive all events.
- Session subscribers receive matching events only.
- Maintains global and per-session recent buffers.

Current/external design:

- Adds `ContextVar` fallback via `current_emitter_session_id`.
- Explicit kwarg takes precedence.
- Uses subscriber records to avoid double delivery.
- Single recent events buffer.

Recommendation: **Use the current/external ContextVar-capable design**, but add tests for source behavior:

- Explicit session id routing.
- ContextVar fallback routing.
- Explicit `session_id=None` opt-out if supported.
- Wildcard subscriber receives all events exactly once.
- Session subscriber does not receive unrelated/no-session events.
- No cross-session leakage with concurrent sessions.

Open question: Do we need per-session recent buffers for GUGI replay, or is one global recent buffer acceptable?

### 3.3 `config.py` and config schema

Observed current-vs-source differences include:

- Source appears to include a large `CONFIG_SCHEMA` used by `/api/config/schema`.
- Current `api/routers/config.py` has a fallback if `CONFIG_SCHEMA` is unavailable.
- Source has `frontend_emitter_queue_size` default around `10000` to support large responses.
- Current returns `100` if unset.

Recommendation: **Do not silently lose `CONFIG_SCHEMA` or queue capacity**. Either:

1. Restore/export full schema in modular form, or
2. Provide a new schema provider module consumed by router and GUI.

Queue size should be intentionally chosen; for streaming-heavy GUI, `100` may be too small and risks event drops.

### 3.4 `api/session_context.py`

Current migration branch adds helper functions:

- `_apply_session_model(agent, model_name)`
- `_reload_agent_if_supported(agent)`

These make model switching robust when legacy/migrated agents lack `set_session_model` or reload hooks.

Recommendation: **Keep compatibility helpers** unless deeper inspection proves all agents implement required methods.

Required tests:

- Switch model for code-puppy agent.
- Switch model for any older/simple agent lacking the method.
- Switch agent then model and verify session-local model is preserved.

### 3.5 `tools/command_runner.py`

Current migration branch adds fallback for missing `on_run_shell_command_output` callback import.

Recommendation: Keep if current branch compatibility requires it, but test terminal command streaming and callback registration.

---

## 4. Proposed Modular Architecture

The current `api/ws/chat_handler.py` is too large and risky to maintain. Refactor only **after parity tests protect behavior**.

Proposed module split:

```text
code_puppy/api/ws/
  chat_handler.py                 # thin route orchestration only
  chat/
    __init__.py
    context.py                    # per-connection/session state object
    lifecycle.py                  # connect/init/restore/cleanup
    dispatch.py                   # client message dispatch table
    session_ops.py                # switch/create/restore session
    agent_ops.py                  # switch agent/model
    cwd_ops.py                    # set working directory + persistence
    config_ops.py                 # get/set config WS handlers
    permission_ops.py             # permission response/cancel plumbing
    streaming.py                  # run agent and coordinate stream lifecycle
    drain.py                      # frontend emitter draining/event batching
    tool_lifecycle.py             # tool ids, args deltas, tool results/groups
    persistence.py                # save turn/session/tool/message data
    errors.py                     # typed error helpers
```

DB query split after tests:

```text
code_puppy/api/db/
  connection.py
  sessions.py
  messages.py
  tool_calls.py
  compaction.py
  queries.py                     # compatibility re-export layer temporarily
```

Config split option:

```text
code_puppy/config/
  schema.py                      # GUI schema metadata
  accessors.py                   # get/set helpers or wrappers
```

Migration rule: keep old import paths via compatibility wrappers until GUI and tests are stable.

---

## 5. Execution Options

### Option A — Big-bang copy, then fix

Copy source branch API/WS files wholesale over current repo, then resolve breakage.

Pros:

- Fastest initial copy.
- Lowest chance of missing a source file.

Cons:

- High regression risk.
- May overwrite already-needed frontend emitter fixes in this repo.
- Hard to isolate bugs.
- Does not respect modularity goal until later.

Recommendation: **Do not choose** except as emergency baseline branch.

### Option B — Current migration branch as base + targeted delta reconciliation

Treat `feature/puppy-desk-migration` as existing partial migration. Reconcile only source-vs-current gaps, preserve current repo emitter/frontend fixes, then test.

Pros:

- Most efficient because API stack already exists in current branch.
- Preserves already-made frontend emitter changes.
- Smaller deltas to review.
- Safer than big-bang.

Cons:

- Requires careful audit that current branch did not accidentally drop source behavior.
- Existing uncommitted app-code changes need review/ownership.
- Long `chat_handler.py` remains until post-parity refactor.

Recommendation: **Best default path**.

### Option C — Clean-room modular port from source into new branch off `main`

Start fresh from `main`, duplicate legacy into `legacy/`, port features module-by-module into modular architecture from the beginning.

Pros:

- Cleanest long-term architecture.
- Avoids carrying accidental partial migration decisions.
- Most aligned with modularity goal.

Cons:

- Slowest path.
- Higher risk of feature omissions during rewrite.
- GUGI validation delayed.

Recommendation: Use only if current migration branch is considered untrustworthy.

### Option D — Compatibility route side-by-side, then same-route swap

Add migrated API under a temporary side route/namespace, keep legacy route active, run parity tests against both, then switch same route after approval.

Pros:

- Safest runtime rollout.
- Easy rollback.
- Lets GUGI compare old/new behavior before final route swap.

Cons:

- More temporary routing/code complexity.
- Requires duplicated route plumbing.

Recommendation: Combine with **Option B** if route-level safety is important.

---

## 6. Recommended Path

Recommended execution path: **Option B + Option D safeguards**

1. Continue from `feature/puppy-desk-migration`, or create a fresh branch off `main` and replay the current migration branch cleanly.
2. Before touching behavior, duplicate legacy/current WS route implementation into `legacy/` namespace.
3. Preserve current frontend emitter improvements unless parity tests show behavior loss.
4. Reconcile source-vs-current differences explicitly:
   - Keep safer CWD history behavior.
   - Restore or modularize `CONFIG_SCHEMA` if GUI needs it.
   - Choose emitter recent-buffer policy.
   - Keep session model compatibility helpers.
   - Validate command runner callback fallback.
5. Add parity tests before same-route swap.
6. Run GUGI validation against temporary/new route.
7. Only after parity + GUGI pass, swap same route with approval.
8. Stabilize.
9. Refactor large files into modules under test coverage.
10. Cleanup legacy only after explicit user approval.

---

## 7. Approval Gates

### Gate 1 — Inventory and migration matrix

Status: **in progress / docs only**

Deliverables:

- Investigation checkpoint saved.
- Migration matrix/options saved.
- User confirms preferred path and goals.

Approval needed before Gate 2.

### Gate 2 — Branch hygiene and legacy duplication

No behavior changes except copying legacy/current route code into `legacy/` namespace.

Acceptance:

- Working branch confirmed not `main`.
- Legacy namespace created.
- Existing route behavior unchanged.
- Smoke tests pass.

### Gate 3 — Parity test harness

Acceptance:

- Tests cover all high-risk GUI protocol features:
  - connect/session restored
  - user message -> assistant start/delta/end/stream_end order
  - tool call args, result, `tool_group_id`
  - permission request/approve/deny/timeout
  - CWD set/unchanged/persistence
  - switch agent/model/session
  - config get/set/schema
  - terminal command result/streaming if route active
  - multiple sessions in parallel with no emitter leakage
  - cancel during streaming
  - switch session during streaming + background save
- Coverage matrix includes happy path, edge/boundary, negative/error, regression.

### Gate 4 — Targeted migration reconciliation

Acceptance:

- Source-vs-current gaps resolved with documented choices.
- No known source feature loss.
- Tests pass.
- Snyk scan completed if dependency files are changed.

### Gate 5 — GUGI validation on temporary/new route

Acceptance:

- GUGI can connect.
- Chat streams correctly.
- Tool panels show args/results.
- Permission UI works.
- Sessions list/load/switch correctly.
- CWD/model/agent/config UI flows work.
- Parallel sessions do not cross streams/events.

### Gate 6 — Same-route swap

Only after Gate 5 approval.

Acceptance:

- Same route uses migrated implementation.
- Legacy still retained for rollback.
- Full parity and GUGI smoke pass.

### Gate 7 — Modular cleanup

Only after migrated route is stable.

Acceptance:

- `chat_handler.py` split into modules.
- `db/queries.py` split or compatibility-layered.
- Import compatibility retained as needed.
- Tests remain green.

### Gate 8 — Legacy removal

Only after explicit user approval.

Acceptance:

- No GUGI dependency on legacy namespace.
- Rollback plan no longer needed or separately archived.
- Legacy code removed and docs updated.

---

## 8. Test Coverage Matrix Proposal

| ID | Requirement | Scenario | Risk Tag | Test Type | Status |
|---|---|---|---|---|---|
| T1 | WS connect/session restore | Existing session loads messages/meta | happy-path | automated WS | planned |
| T2 | Streaming order | start -> delta(s) -> end -> stream_end | regression | automated WS | planned |
| T3 | Delta before start robustness | handler emits synthetic start first | edge | automated unit/WS | planned |
| T4 | Tool call args | args deltas accumulate into full args | happy-path | automated WS | planned |
| T5 | Tool result | result emitted with `tool_group_id` | regression | automated WS | partially existing |
| T6 | Permission approve | tool proceeds after approval | happy-path | automated WS | planned |
| T7 | Permission deny | tool blocked and error/result surfaced safely | negative | automated WS | planned |
| T8 | Permission timeout/no WS | fail safe | negative | unit | planned |
| T9 | CWD set | path changes, persists, emits banner | happy-path | automated WS/DB | planned |
| T10 | CWD unchanged | unchanged flag, no duplicate corruption | edge | automated WS | planned |
| T11 | Switch model | session-local model changes and persists | happy-path | automated WS | planned |
| T12 | Agent without model setter | fallback does not crash | edge | unit | planned |
| T13 | Switch session during stream | old session saves in background | regression | automated WS | planned |
| T14 | Parallel sessions | no emitter leakage/crossed events | regression | automated concurrent WS | planned |
| T15 | Cancel stream | cancellation frame and cleanup | negative | automated WS | planned |
| T16 | Config schema | schema endpoint returns GUI-usable metadata | happy-path | API | planned/current extra test |
| T17 | Config missing schema fallback | endpoint still works | edge | API | current extra test |
| T18 | Terminal command | command result and output callback flow | happy-path | API/WS | planned |
| T19 | DB fresh init | empty DB creates schema v4 | happy-path | DB temp file | planned |
| T20 | DB migration/dedup | older schema upgrades safely | regression | DB temp file | planned |
| T21 | GUGI chat smoke | GUI sends prompt and renders stream | happy-path | manual/browser | planned |
| T22 | GUGI tools/permissions | GUI renders tool args/results + approval | high-risk manual | manual/browser | planned |

---

## 9. Open Questions for User

1. Should the existing `feature/puppy-desk-migration` branch be treated as the starting point, or should we create a brand-new clean branch off `main` and replay only approved changes?
2. Is a temporary side-by-side route acceptable for validation, or do you want legacy namespace only and then same-route swap?
3. For frontend emitter recent events, do you need per-session recent replay, or is global recent replay acceptable if session-filtered live delivery is correct?
4. Should `/api/config/schema` expose the full rich `CONFIG_SCHEMA` for GUGI, or is inferred fallback metadata enough?
5. What is the minimum GUGI validation flow you want before same-route swap?
6. Are the current uncommitted application-code changes on `feature/puppy-desk-migration` yours and intended to be preserved?

---

## 10. Proposed Immediate Next Step After Approval

If approved, proceed to **Gate 2**:

- Confirm/create safe migration branch off `main`.
- Snapshot current status.
- Duplicate legacy/current WS route implementation into `legacy/` namespace.
- Make no behavior switch yet.
- Add initial parity tests around existing behavior.


---

## 11. User Decisions Recorded — 2026-06-01

Confirmed by user:

1. **Use existing `feature/puppy-desk-migration` as the base.**
   - Do not restart from a fully clean branch unless a later blocker requires it.
   - Existing migration branch decisions and compatibility fixes are considered valuable.

2. **Temporary side-by-side route is acceptable.**
   - We may expose migrated/experimental WS/API behavior behind a temporary validation route while preserving legacy/current route behavior.
   - Same-route swap remains gated by parity + GUGI validation + explicit approval.

3. **Preserve uncommitted app-code changes on `feature/puppy-desk-migration`.**
   - Current modified files must not be overwritten casually:
     - `code_puppy/config.py`
     - `code_puppy/plugins/frontend_emitter/emitter.py`
     - `code_puppy/session_storage.py`
     - `code_puppy/tools/command_runner.py`
     - `pyproject.toml`
     - `uv.lock`
   - Before Gate 2 implementation, snapshot/diff these changes and treat them as intentional unless user says otherwise.

## 12. GUGI Recent-Event Replay Decision Detail

Open decision: whether GUGI needs **per-session recent-event replay** or whether a **global recent-event replay buffer** is acceptable when live delivery is correctly session-filtered.

### What “recent-event replay” means

The frontend emitter supports live event subscription, but it can also keep a small in-memory buffer of recent events. When GUGI reconnects, refreshes, or opens a panel late, it may ask for recent events to catch up on tool calls, stream chunks, permission events, or agent invocation events that occurred just before the subscriber attached.

Live routing and replay routing are separate concerns:

- **Live routing**: while connected, does session A only receive session A events?
- **Replay routing**: after reconnect/late subscribe, which older events are offered back to GUGI?

A system can have correct live routing but still leak or confuse replayed events if the recent buffer is global and the replay API does not filter carefully.

### Option R1 — Global recent buffer only

All events are stored in one recent-events list, each event includes optional `session_id`.

Expected behavior:

- Wildcard callers can inspect all recent events.
- GUGI/session-specific callers must filter by `session_id` before display.

Pros:

- Simpler implementation.
- Lower memory overhead.
- Easier backward compatibility with older `get_recent_events()` semantics.
- Matches the newer external emitter design observed in `external-ws-replica-test`.

Cons:

- Higher risk of accidental cross-session replay if any consumer forgets to filter.
- More frontend/API discipline required.
- A busy session can evict another session’s recent events from the shared buffer.
- Reconnecting to a quiet session after a busy parallel session may miss relevant older events.

Best if:

- GUGI mostly relies on DB/session state for reloads, not emitter replay.
- Recent events are only diagnostic or best-effort.
- Event volume is moderate.
- All replay call sites are strongly typed and tested for session filtering.

### Option R2 — Per-session recent buffers

Each session has its own recent-events list; optionally a global buffer is retained for legacy/wildcard subscribers.

Expected behavior:

- `get_recent_events(session_id="A")` returns only session A events.
- `get_recent_events()` returns legacy/global events or all events depending on compatibility policy.

Pros:

- Safer isolation by default.
- Prevents cross-session replay leakage even if frontend forgets to filter.
- Busy session B cannot evict session A’s recent events from A’s own buffer.
- Better for multi-tab/multi-session GUI behavior.
- Better fit for strict session isolation requirement.

Cons:

- More state to manage and clean up.
- Need buffer cleanup when sessions are destroyed/idle.
- Slightly more complex compatibility semantics.
- Must decide whether no-session/global events should be visible to session subscribers.

Best if:

- GUGI uses recent replay to reconstruct transient UI such as active tool calls or streaming panels.
- Multiple sessions can be active in parallel.
- Strict no-cross-session leakage is more important than simplicity.
- Reconnect/refresh behavior matters.

### Option R3 — Hybrid: global buffer plus per-session indexed replay

Maintain a global recent buffer for backward compatibility and diagnostics, but expose session-filtered replay APIs that are safe by default. Internally this can be implemented either as:

- a global list filtered by `session_id`, plus tests, or
- true per-session buffers plus a global legacy buffer.

Pros:

- Preserves backward compatibility.
- Allows safe GUGI code path: always request replay by session.
- Can start with global-filtered implementation and upgrade to true per-session if eviction becomes a problem.

Cons:

- More policy decisions to document.
- If implemented only as global-filtered, shared-buffer eviction risk remains.

Recommended default for migration:

**R3 with true per-session replay where practical.**

Reasoning:

- User explicitly requires async independent session management and multiple parallel sessions.
- GUI correctness depends on not crossing tool calls, deltas, permission prompts, or terminal output between sessions.
- The source branch already had per-session recent buffers, which is a useful safety feature.
- The newer current/external emitter adds ContextVar routing and double-delivery prevention, which is also valuable.
- Best final design is to combine both:
  - ContextVar-capable emission/routing from current/external work.
  - Per-session replay isolation from source behavior.
  - Legacy wildcard/global support retained for compatibility.

Suggested policy:

1. Live session subscribers receive only exact `session_id` matches.
2. Wildcard subscribers receive all events exactly once.
3. `get_recent_events(session_id="A")` returns only session A events.
4. `get_recent_events()` retains old behavior for legacy/debug consumers.
5. Explicit `session_id=None` events are global/broadcast for wildcard/debug only, not replayed to session-specific callers unless explicitly requested.
6. Session recent buffers are capped and cleaned up when sessions expire.

Required tests:

- Two sessions emit interleaved events; each session replay returns only its own events.
- Wildcard replay returns all expected events with no duplicates.
- Busy session B does not evict session A’s per-session recent events.
- ContextVar fallback attaches the correct session id.
- Explicit kwarg overrides ContextVar.
- Explicit `session_id=None` behavior is documented and tested.
- Reconnect/late subscribe during tool call does not show another session’s tool event.


---

## 13. User Clarification — GUGI State Replay Source

User clarified:

- Recent replay/state reconstruction is handled by **React GUI state** or by the **DB**.
- Both React GUI state and DB-backed state are already separated by `session_id`.

Updated implication:

- The frontend emitter recent-events buffer is **not** the primary source of truth for GUGI session reconstruction.
- Therefore, we do **not** need to over-optimize emitter replay as the authoritative reconnect/reload mechanism.
- However, live event routing remains critical: active stream/tool/permission events must never cross sessions.

Updated recommendation:

Use the current/external emitter direction as the base:

1. Keep **ContextVar-capable live routing**.
2. Keep explicit `session_id` routing and exact-match session subscribers.
3. Keep wildcard/global subscribers for legacy/debugging.
4. Treat emitter recent replay as **debug/best-effort compatibility**, not authoritative GUI state.
5. Ensure any replay API that GUGI might call can filter by `session_id`, even if internally stored in one global buffer.
6. Do not require true per-session recent buffers unless later GUGI testing shows replay eviction/leakage causes real UX issues.

Revised preference:

- **Global recent buffer is acceptable** if:
  - live delivery is strictly session-filtered,
  - replay consumers filter by `session_id`,
  - DB/React remain the source of truth for state reconstruction,
  - tests prove no live cross-session leakage.

Still required tests:

- Concurrent session live events do not cross.
- Wildcard subscribers receive all events exactly once.
- Session subscribers receive only matching session events.
- ContextVar fallback attaches correct session id.
- Explicit `session_id` overrides ContextVar.
- Replay filtering by `session_id` works if exposed/used.

Priority change:

- Per-session recent buffers move from **recommended default** to **optional enhancement**.
- Live session routing and DB/React session correctness are the hard requirements.


---

## 14. Gate 2 Implementation Shape — Proposed, Pending Explicit Approval

User has approved the strategy direction, but application-code changes should still be gated explicitly.

Confirmed base:

- Continue on `feature/puppy-desk-migration`.
- Preserve uncommitted app-code changes.
- Temporary side-by-side route is acceptable.
- Do not touch `main`.

### Current route shape observed

- `code_puppy/api/app.py` calls `setup_websocket(app)`.
- `code_puppy/api/websocket.py` calls:
  - `register_events_endpoint(app)`
  - `register_chat_endpoint(app)`
  - `register_terminal_endpoint(app)`
  - `register_health_endpoint(app)`
  - `register_sessions_endpoint(app)`
- `code_puppy/api/ws/chat_handler.py` defines `register_chat_endpoint(app)` and registers hardcoded route:
  - `@app.websocket("/ws/chat")`

### Gate 2 goal

Preserve current behavior before any migration/refactor work by duplicating the current route implementation into a legacy namespace, then prepare for side-by-side validation.

### Gate 2 code-change options

#### G2-A — Archive-only legacy namespace

Copy the current `code_puppy/api/ws` implementation into:

```text
code_puppy/api/ws/legacy/
```

Do not register the legacy copy yet.

Pros:

- Lowest behavioral risk.
- Existing `/ws/chat` route remains unchanged.
- Gives rollback/reference copy before edits.

Cons:

- Not enough by itself for side-by-side live validation.

#### G2-B — Parameterized route registration

Change endpoint registration functions to accept an optional path, defaulting to current paths:

```python
def register_chat_endpoint(app: FastAPI, path: str = "/ws/chat") -> None:
    @app.websocket(path)
    async def websocket_chat(...):
        ...
```

Then current behavior remains unchanged because default is still `/ws/chat`.

Later, a temporary route can register the same or modular implementation at e.g.:

```text
/ws/chat-migration
/ws/chat-next
/ws/chat-v2
```

Pros:

- Small, controlled change.
- Enables side-by-side validation without copying a 230KB handler again.
- Keeps same-route swap simple.

Cons:

- Touches the huge handler early.
- Must be covered by a smoke test verifying `/ws/chat` still registers.

#### G2-C — New route module wrapping copied implementation

Create a separate temporary route module that copies/wraps the current chat handler under a different path.

Pros:

- Avoids parameterizing current handler.
- Side-by-side route available immediately.

Cons:

- Duplicates very large code.
- Increases risk of divergence and merge pain.

### Recommended Gate 2 path

Recommended: **G2-A first, then G2-B only when we are ready to register side-by-side.**

Sequence:

1. Snapshot current uncommitted changes. ✅ done in docs
2. Copy current WS/API route implementation into `code_puppy/api/ws/legacy/` as a reference/rollback namespace.
3. Do not register legacy yet.
4. Add minimal smoke tests/import tests proving current `/ws/chat` registration still works.
5. Once tests are in place, parameterize `register_chat_endpoint(..., path="/ws/chat")` and register temporary route only when needed.

### Proposed temporary route name

Preferred temporary route:

```text
/ws/chat-migration
```

Alternatives:

```text
/ws/chat-next
/ws/chat-v2
```

Recommendation: `/ws/chat-migration` because it is explicit and unlikely to be confused with final versioning.

### Gate 2 acceptance checks

Before marking Gate 2 complete:

- `git branch --show-current` is not `main`.
- Existing uncommitted changes remain preserved.
- Legacy namespace exists as a copy/reference.
- `/ws/chat` behavior is unchanged.
- No same-route swap has occurred.
- Minimal import/route registration tests pass.
- No dependency/security scan required unless dependency files change beyond preserved existing state; if package files are touched, Snyk check is required before testing phase.


---

## 15. Gate 2 Execution Evidence — 2026-06-01

Gate 2 approved by user and executed on branch `feature/puppy-desk-migration`.

Application/test changes made:

- Created legacy WS snapshot namespace:
  - `code_puppy/api/ws/legacy/`
- Copied current WS implementation files into that namespace as a rollback/reference snapshot.
- Replaced `legacy/__init__.py` with a safe non-registering marker module.
- Added `code_puppy/api/ws/legacy/README.md` documenting that it is not registered and must not be cleaned up without approval.
- Added smoke tests:
  - `code_puppy/api/tests/test_gate2_legacy_ws_namespace.py`

Behavioral guarantees for Gate 2:

- Existing `/ws/chat` route remains registered from active `code_puppy.api.ws.chat_handler`.
- No temporary route is registered yet.
- No same-route swap occurred.
- Legacy snapshot is importable as a namespace marker only; importing `code_puppy.api.ws.legacy` does not register routes.
- Existing uncommitted app-code changes were preserved.

Targeted test evidence:

```text
uv run pytest code_puppy/api/tests/test_gate2_legacy_ws_namespace.py -q
2 passed in 19.57s
```

Security note:

- Gate 2 did not intentionally modify dependency files.
- `pyproject.toml` and `uv.lock` were already modified before Gate 2 and are preserved as user-approved existing changes.
- Snyk scan should still be run before broader test/security signoff if those dependency changes remain part of the migration deliverable.


### Gate 2 reviewer sign-off

Independent code review agent result: **APPROVE**

Reviewer findings summary:

- No `/ws/chat` behavior switch.
- No temporary route registered.
- Legacy package import is marker-only/non-registering.
- Existing uncommitted app-code changes remain preserved.
- Smoke tests are sufficient for Gate 2 scope.

Non-blocking caution recorded:

- The legacy snapshot is archive/reference quality, not yet a fully executable rollback route, because copied modules still contain absolute imports to active `code_puppy.api.ws.*` modules. This is acceptable for Gate 2 archive/non-registration, but must be addressed before using `legacy` as a live rollback route.


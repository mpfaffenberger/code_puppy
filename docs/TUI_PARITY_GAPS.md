# TUI Parity Gaps — findings from rebasing `feature/add-tui` onto `main`

**Context:** `feature/add-tui` was forked from `main` at `6df8f79e` (v0.0.567).
Since then, 110 commits landed on `main` (mostly backend fixes that "just
work" via the shared plugin/hook system — DRY paying off). This doc tracks
the **4 real parity gaps** found where a `main` feature doesn't work, or
works differently/worse, in the Textual TUI (`code_puppy/tui/`) vs classic.

A 5th gap (`/queue`) was found later during a per-plugin `register_screen`
audit and has since been **FIXED** — see Gap #5 below.

Status: **investigation done, fixes NOT YET STARTED** (except #5, done). Pick up here.

Fork point: `6df8f79e`. Rebase done cleanly onto `main` at `183298ac`
(0.0.605) — see git log for the merge commit `0dd54948`.

---

## Priority order (recommended)

1. **Turn-boundary hooks** (#4 below) — smallest fix, unblocks 2 existing plugins
2. **Sub-agent live panel** (#1 below) — biggest UX hole, users will notice immediately
3. ~~**Spinner catalogue wiring** (#3 below)~~ — **DONE** (both parts; see #3)
4. **Trust ceremony in `/plugins` TUI** (#2 below) — security-relevant, more UI work

---

## Gap #1: Sub-agent live status panel — invisible in TUI

**New in main (post-fork), plugin didn't exist before:** `code_puppy/plugins/subagent_panel/`
(confirmed via `git cat-file -e 6df8f79e:code_puppy/plugins/subagent_panel/register_callbacks.py` → not found)

### The problem
`subagent_panel/register_callbacks.py` renders live per-sub-agent rows by calling
`get_bottom_bar().set_panel_lines(lines)` (see `_push_panel()` in that file).
The bottom bar (`code_puppy/messaging/bottom_bar.py`) is a **classic-UI-only
construct** — it's only ever `.start()`'d via `code_puppy/messaging/run_ui.py`
(`bar.start()` at line 119), which is entered via `run_prompt_with_attachments(...,
use_run_ui=True)`.

The TUI **always** calls `run_prompt_with_attachments(..., use_run_ui=False)`
(see `code_puppy/tui/app.py` `_run_agent_turn`, ~line 1006-1010). So the bottom
bar never activates in the TUI, and `set_panel_lines()` calls go nowhere.

**Net effect:** fan out sub-agents in the TUI → **zero visibility** into their
live progress. No rows, no spin, no elapsed clock. The entire live-panel
feature is a no-op in the TUI.

The "frozen" completion record (printed via `RichConsoleRenderer._do_render`
when a `SubAgentResponseMessage` arrives) *might* still show up through the
TUI's capture bridge (`code_puppy/tui/capture.py`), since `subagent_panel`
monkeypatches `RichConsoleRenderer._do_render` at the **class** level, and the
capture bridge instantiates a private `RichConsoleRenderer` too. **Needs a
manual smoke test to confirm** — the monkeypatch in
`_install_render_wrapper()` calls `_handle_frozen(self._console, ...)`, which
in turn calls `console.print()` on whatever console `self` was constructed
with. If that's the capture bridge's `StringIO`-backed console, it might
actually render as scrollback text in the TUI (ugly but not silently lost).
The **live** panel (mid-run rows) is definitely 100% dead — that part
requires `bottom_bar.is_active()` to be true, and it's never even started.

### Where the code lives
- `code_puppy/plugins/subagent_panel/register_callbacks.py` — the whole plugin
- `code_puppy/plugins/subagent_panel/panel_render.py` — `_ordered_tree`, `_row_lines` (pure rendering helpers, reusable)
- `code_puppy/plugins/subagent_panel/state.py` — the live-tree state tracker (`state.snapshot()`, `state.mark_done()`, etc.)
- `code_puppy/messaging/bottom_bar.py::set_panel_lines` (line ~235) — what the plugin calls
- `code_puppy/tui/app.py` — `_run_agent_turn` (~line 985-1022), `handle_bus_message` (~line 660)

### Suggested approach
The TUI needs its **own** rendering of the live sub-agent tree, fed by the
same `state` module (or a `register_screen`/new-hook-driven equivalent) —
NOT by trying to activate the bottom bar (that would fight the Textual
screen the same way `/theme` and `/spinner`'s prompt_toolkit pickers do).

Options:
- **(a)** Add a new callback hook e.g. `subagent_panel_lines_changed` that
  the plugin fires instead of/in addition to `_push_panel()`, and have
  `tui/app.py` subscribe to render a small panel widget (mirrors how
  `bottom_bar.set_panel_lines` works, but Textual-native — a `Static` widget
  above the prompt, toggled visible while `state.has_active()`).
- **(b)** Have `_panel_lines()` / `_push_panel()` detect TUI mode (check
  `get_ui_mode()` or similar) and, when in TUI mode, push lines through the
  message bus as a structured message type instead of `bottom_bar`, which the
  TUI's `handle_bus_message` already knows how to route.
- Reuse `_ordered_tree()` / `_row_lines()` from `panel_render.py` either way —
  don't reimplement the tree-render logic (DRY).

### Also check
- `code_puppy/plugins/subagent_panel/register_callbacks.py` registers
  `stream_event`, `agent_run_end`, `agent_run_cancel`, `post_tool_call`. All
  of those callbacks presumably still fire fine in TUI mode (they're core
  hooks, not classic-only) — only the *rendering sink* (`bottom_bar`) is the
  gap. Confirm this assumption once fixing.

---

## Gap #2: Project-plugin trust ceremony — missing from TUI's `/plugins`

**New in main (post-fork):** commit `89bc4ad7` "feat: require explicit user
trust before loading project plugins (#527)". Added a whole trust-gate
system: `code_puppy/plugins/trust.py`, `code_puppy/plugins/trust_notice.py`,
`code_puppy/plugins/plugin_list/project_trust_flow.py`, plus rewrote
`plugins_menu.py` (classic prompt_toolkit) to add the ceremony.

### The problem
`code_puppy/plugins/plugin_list/plugins_tui.py` (`PluginsScreen`, the
Textual `ModalScreen` for `/plugins`) **predates** this trust system. It only
calls:
```python
from code_puppy.plugins import get_loaded_plugins
from code_puppy.plugins.config import get_disabled_plugins
```
— the old boolean enabled/disabled model. It never calls
`get_project_plugin_status()` (new API, used by classic's `plugins_menu.py`
`_refresh_data()`), so:
- Untrusted/changed/error-state **project plugins are completely invisible**
  in the TUI's `/plugins` list (classic shows them with a status label so
  `Enter` can open the trust ceremony).
- There's no ceremony UI at all in the TUI — no equivalent of classic's
  trust popup (`plugins_menu_layout.py`'s float + `TextArea` requiring the
  user to type `trust`).

**Security angle:** a user running the TUI has literally no way to see that
a project plugin exists-but-untrusted, let alone review/trust it. They'd
need to drop to classic mode to manage trust.

### Where the code lives (classic reference implementation)
- `code_puppy/plugins/plugin_list/plugins_menu.py` — `PluginsMenu` class,
  see `_refresh_data()` (loads `get_project_plugin_status()`),
  `_toggle_current()` (branches on `entry.status`), `_open_trust_modal()`,
  `_accept_trust()`
- `code_puppy/plugins/plugin_list/plugins_menu_render.py` — `render_trust_modal()`,
  the `_PROJECT_STATUS_LABELS`-style status text (also duplicated conceptually
  in `register_callbacks.py`'s `_PROJECT_STATUS_LABELS` for the `/plugins list` text output)
- `code_puppy/plugins/plugin_list/project_trust_flow.py` — the actual
  trust/activate logic (`activate_project_plugin()`, ceremony validation)
- `code_puppy/plugins/trust.py` — SHA-256 hashing, `~/.code_puppy/trusted_plugins.json`
- `code_puppy/plugins/__init__.py` — `get_project_plugin_status()`,
  `get_project_plugins_directory()` (the new APIs)

### Where the TUI needs work
- `code_puppy/plugins/plugin_list/plugins_tui.py` — `PluginsScreen`
  - `_load_rows()` needs to also pull `get_project_plugin_status()` entries
    (mirrors classic `_refresh_data()`'s project-tier merge logic — see lines
    ~155-165 in `plugins_menu.py`)
  - `_PluginRow` needs a `status` field beyond just `disabled: bool` (classic's
    `_PluginEntry.status` is the model: `"loaded"` | `"untrusted"` | `"changed"`
    | `"disabled"` | `"error"`)
  - `_toggle()` needs to branch: untrusted/changed → open a new trust modal
    (Textual `ModalScreen`, e.g. `TrustCeremonyScreen`) instead of just
    flipping the disabled flag; disabled/error (already trusted) → call
    `activate_project_plugin()` directly (no ceremony); normal plugins →
    existing `set_plugin_disabled()` path unchanged.
  - New: a Textual modal for the ceremony itself — needs to show the plugin's
    file list + require typing `trust` (mirror `render_trust_modal()`'s
    content, rendered natively instead of via `FormattedTextControl`).

### Suggested approach
Don't try to reuse the prompt_toolkit `Application`-based ceremony (same
"fights the Textual screen" problem as `/theme`/`/spinner`). Build a small
native `ModalScreen` (call it `TrustCeremonyScreen`) that:
1. Shows plugin name + file list (call `project_trust_flow`'s helpers for
   the file listing — check what's available, might need a small new export)
2. Has an `Input` requiring the literal string `trust` to confirm (mirrors
   classic's `_accept_trust`)
3. On confirm, calls the same `project_trust_flow.activate_project_plugin()`
   / trust-write logic classic uses (or whatever the trust.py-level function
   is — check `project_trust_flow.py` for the accept/hash-write path)
4. Dismisses back to `PluginsScreen`, which refreshes.

---

## Gap #3: Customizable spinners — TUI ignores your choice; `/spinner` picker breaks TUI  [FIXED]

> **Resolution (both parts done):**
> * **(b)** the TUI thinking-spinner now reads the active style live —
>   `tui/app.py::_tick_spinner`/`_render_spinner` call
>   `puppy_spinner.register_callbacks._current_frames_and_interval()` (the
>   deprecated shim `FRAMES` is only the `except` fallback). A custom
>   `/spinner` choice is reflected in the TUI.
> * **(a)** `/spinner` now opens a **real** native Textual live-preview modal
>   (`code_puppy/plugins/puppy_spinner/spinner_tui.py` — `SpinnerScreen` +
>   `open_spinner`), wired via `register_screen`. It animates each spinner at
>   its own speed, has the speed dial (-/+), `i` to init `spinners.json`, and
>   reads/writes the SAME catalogue / `set_active` data layer. It reuses the
>   classic picker's `_step_interval` speed-grid math (DRY). This replaces the
>   earlier text-redirect stopgap. Tests: `tests/plugins/test_puppy_spinner_tui.py`.
>
> The original investigation notes are kept below for context.

**New in main (post-fork):** `1c681a27` "feat(puppy_spinner): customizable
spinner styles via /spinner + spinners.json (#528)" and `ed75fffe` "fix
(puppy_spinner): quicker classic puppy + gap before status text (#529)".

### Two-part problem

**(a) `/spinner` (bare, no args) launches a prompt_toolkit fullscreen `Application`.**
See `code_puppy/plugins/puppy_spinner/picker.py` — `interactive_spinner_picker()`
uses `from prompt_toolkit import Application` directly, same class of bug the
TUI rebuild plan doc explicitly flagged for `/theme` ("fights the Textual
screen, corrupts it"). Unlike `/theme`, **nobody added a `register_screen`
guard/redirect for `/spinner`** — compare:
```python
# code_puppy/plugins/theme/register_callbacks.py (has the guard):
def _open_theme_in_tui(app) -> None:
    del app
    emit_info("In the TUI, themes live in the command palette...")
def _register_theme_screen():
    return [{"command": "theme", "open": _open_theme_in_tui}]
register_callback("register_screen", _register_theme_screen)
```
`code_puppy/plugins/puppy_spinner/register_callbacks.py` has **no**
`register_screen` registration at all. Running bare `/spinner` in the TUI
today will likely corrupt/crash the Textual screen (needs a repro to confirm
severity, but the theme precedent says it's bad).

**(b) The TUI's own thinking-spinner is hardcoded to the OLD static frame set
and never reads the user's chosen spinner.**
`code_puppy/tui/app.py`:
```python
def _tick_spinner(self) -> None:
    from code_puppy.messaging.spinner import FRAMES   # <-- static, old frames
    ...
def _render_spinner(self) -> None:
    from code_puppy.messaging.spinner import (
        FRAMES, THINKING_MESSAGE, get_context_info,
    )
```
`code_puppy/messaging/spinner/__init__.py` is explicitly a **DEPRECATED
compat shim** (its own docstring says so) — `FRAMES` there is a fixed
constant, unrelated to `code_puppy/plugins/puppy_spinner/spinners.py`'s
catalogue (`spinners.get_active_spinner()`, `spinners.BUILTIN_SPINNERS`,
user's `spinners.json` overrides). **The TUI's spinner never reflects a
custom `/spinner` choice, no matter what the user picks** (assuming (a) is
fixed so they even can pick one without crashing).

### Where the code lives
- `code_puppy/plugins/puppy_spinner/commands.py` — `handle_spinner()`, the `/spinner` command handler
- `code_puppy/plugins/puppy_spinner/picker.py` — the prompt_toolkit picker (`interactive_spinner_picker()`)
- `code_puppy/plugins/puppy_spinner/spinners.py` — the catalogue: `get_active_spinner()`, `get_catalogue()`, `set_active()`, `BUILTIN_SPINNERS`, `DEFAULT_SPINNER`
- `code_puppy/plugins/puppy_spinner/register_callbacks.py` — the classic bottom-bar ticker (`_current_frames_and_interval()` shows the RIGHT pattern to copy — reads `spinners.get_active_spinner()` live every tick)
- `code_puppy/tui/app.py` — `_start_spinner`, `_stop_spinner`, `_tick_spinner`, `_render_spinner` (~line 1569-1611)
- `code_puppy/messaging/spinner/__init__.py` — the deprecated shim `_tick_spinner`/`_render_spinner` currently import from (only use its `THINKING_MESSAGE`/`get_context_info`, drop `FRAMES`)

### Suggested approach
**(b) first (small, isolated, no UI risk):**
In `tui/app.py`, replace the `FRAMES` import with a live read of
`code_puppy.plugins.puppy_spinner.spinners.get_active_spinner()` each tick —
mirror exactly what `puppy_spinner/register_callbacks.py::_current_frames_and_interval()`
already does for classic mode (same catalogue, same interval logic, same
fallback-to-stock-puppy-on-broken-catalogue safety). Don't duplicate that
logic — consider extracting `_current_frames_and_interval()` into a shared
helper in `spinners.py` itself so both classic and TUI call the same
function (DRY).

**(a) second:**
Add a `register_screen` entry for `puppy_spinner`, same pattern as `theme`:
either (i) redirect to a message pointing at the (now TUI-aware) spinner via
`/spinner <name>` direct-set (which already works fine — it's just data
mutation, no UI), or (ii) build a native Textual picker (bigger lift, matches
theme's own aspiration noted in its comment about "themes live in the
command palette" — could genuinely just live behind Ctrl+P too, or get a
small `ModalScreen` with a live-preview `OptionList`, reusing `spinners.py`'s
catalogue). Given low usage, (i) — the redirect message — is probably the
pragmatic v1; a native picker is a nice-to-have follow-up.

---

## Gap #4: Missing turn-boundary hooks — regression for 2 pre-existing plugins

**Not a new main feature — a TUI regression.** Both `wiggum` and `herdr`
existed *before* the fork and rely on hooks the TUI never fires.

### The problem
Classic's `cli_runner.py` interactive loop fires three hooks at natural turn
boundaries that `code_puppy/tui/app.py`'s `_run_agent_turn` **never fires**:

| Hook | Classic call site | Signature |
|---|---|---|
| `user_prompt_submit` | fired inside `_runtime.py::run_with_mcp` (NOT cli_runner — fires automatically, TUI gets this one for free via `agent.run_with_mcp`) | `on_user_prompt_submit(prompt, group_id) -> List[str\|None]` |
| `interactive_turn_end` | `cli_runner.py` ~line 1172, in the continuation loop, after every prompt run (success or error) | `on_interactive_turn_end(agent, prompt, result, *, success, error) -> List[dict\|None]` |
| `interactive_turn_cancel` | `cli_runner.py`, multiple sites (~896, 1098, 1145, 1214, 1238) — on `KeyboardInterrupt` or `result is None` (cancellation) | `on_interactive_turn_cancel(prompt, *, reason) -> List[Any]` |

**Correction from earlier investigation:** `user_prompt_submit` is actually
fired inside `code_puppy/agents/_runtime.py::run_with_mcp` body (~line 504,
`submit_results = await on_user_prompt_submit(prompt, group_id)`), which BOTH
classic and TUI call into (`run_prompt_with_attachments` → `agent.run_with_mcp`).
**So `user_prompt_submit` probably already works fine in the TUI** — this
needs a quick re-verify, but it looks like only `interactive_turn_end` and
`interactive_turn_cancel` are the real gap (those are only called from
`cli_runner.py`'s classic-only interactive loop, never from `tui/app.py`).

Re-confirm before coding: grep `on_interactive_turn_end\(` and
`on_interactive_turn_cancel\(` call sites — as of this writing they only
appear in `code_puppy/cli_runner.py`, never in `code_puppy/tui/app.py`.

### What breaks without them
- **wiggum** (`code_puppy/plugins/wiggum/register_callbacks.py`):
  - `_on_interactive_turn_end` drives the entire `/goal` and `/wiggum` retry
    loop (judge running, remediation, continuation-prompt requests). **In
    the TUI, `/goal` and `/wiggum` loops silently never retry/judge/continue**
    — the turn just ends normally with no wiggum behavior at all.
  - `_on_interactive_turn_cancel` stops the goal/wiggum loop cleanly on
    Ctrl+C/Esc. Without it, cancelling a TUI turn mid-goal-loop leaves
    `wiggum/state.py`'s module-level state dangling (`state.is_active()`
    stays true), which could cause weird carry-over behavior into the next
    prompt in the same session.
- **herdr** (`code_puppy/plugins/herdr/register_callbacks.py` +
  `reporter.py`): registers `interactive_turn_end` / `interactive_turn_cancel`
  → both map to `_on_turn_end` → `reporter.on_turn_end()` → forces state to
  `IDLE`. Without these firing, herdr's idle-state tracking in the TUI relies
  *only* on `agent_run_end` reaching depth 0 (`on_run_end`, which DOES fire —
  it's a core `_runtime.py` hook, not cli_runner-only). So herdr is **partially
  degraded, not fully broken**, in the TUI: the depth-0 `agent_run_end` path
  covers the common case, but any plugin/flow that relies specifically on the
  turn boundary (vs. run boundary) semantics could see stale state. Lower
  severity than wiggum's gap.

### Where the code lives
- `code_puppy/cli_runner.py` — reference call sites (see table above; also
  see the whole `while True` continuation loop ~line 1155-1240 for exact
  sequencing: `on_interactive_turn_end` is called in a loop that supports
  continuation dicts with `{"prompt", "clear_context", "delay"}`)
- `code_puppy/tui/app.py` — `_run_agent_turn` (~line 985-1022) is where these
  need to be added; also `submit_prompt` (~line 891-908) is the TUI's
  equivalent of the classic REPL loop iteration
- `code_puppy/callbacks.py` — `on_interactive_turn_end` (~line 1128),
  `on_interactive_turn_cancel` (~line 1154) — the trigger functions to call

### Suggested approach
In `tui/app.py::_run_agent_turn`:
1. On `result is None` (cancelled) or in the `except Exception` path →
   call `await on_interactive_turn_cancel(task, reason=...)` (mirror
   classic's reason strings: `"cancellation"` for None-result, `"Ctrl+C"` for
   KeyboardInterrupt-equivalent — TUI's analogous cancel path is
   `action_cancel_turn`, which currently just cancels the Textual worker; may
   need to route the cancel notification through there instead of/in
   addition to `_run_agent_turn`'s own except block).
2. On successful completion → call `await on_interactive_turn_end(agent, task,
   result, success=True, error=None)` and **handle the continuation-request
   return value** (a dict with `prompt`/`clear_context`/`delay`) — this is
   the part that actually makes `/goal`/`/wiggum` work: if a plugin returns a
   continuation dict, the TUI needs to loop and re-run with the new prompt,
   same as classic's `while True` continuation loop. This is more than a
   one-line hook call — it's porting the continuation-loop *shape* into the
   Textual worker. Consider factoring classic's continuation loop out of
   `cli_runner.py` into a shared helper both UIs call, rather than
   duplicating the loop logic (DRY) — check if `run_prompt_with_attachments`
   is the right seam, or if a new shared `run_interactive_turn_with_continuations()`
   helper should wrap both the run + the turn-end/continuation dance.
3. On exception → same `on_interactive_turn_end(..., success=False, error=e)` path.

**Also verify:** does `action_cancel_turn` (Esc key) need its own
`on_interactive_turn_cancel` call, given it cancels the Textual worker
directly rather than going through `_run_agent_turn`'s own except block?
Check whether worker cancellation raises `CancelledError` inside
`_run_agent_turn` (it should, via `asyncio.CancelledError` propagating into
the `await run_prompt_with_attachments(...)` call) — if so, one try/except
in `_run_agent_turn` covers both Esc-cancel and any other cancellation path.

---

## Gap #5: `/queue` interactive menu — dead in the TUI  FIXED

**Found during a per-plugin `register_screen` audit** (not part of the original
4). `code_puppy/plugins/steer_queue/` ships `/queue`, an interactive manager
for the mid-run prompt queue (view / add / edit / delete).

### The problem
`queue_menu.py` builds the menu with `arrow_select_async` +
`PromptSession().prompt_async()`, and `open_queue_menu_blocking()` hops to a
worker thread to `asyncio.run()` it — a design that assumes
`suspended_run_ui` handed prompt_toolkit the raw terminal (the classic REPL /
mid-run drain both wrap command execution in it). **The Textual app has no
run-UI to suspend**, so running `/queue` in the TUI either no-ops, hangs the
worker thread until its 600s timeout, or fights the Textual screen — the exact
failure class the other five `register_screen` plugins were built to dodge.

`steer_queue` had **only** a `custom_command` hook — no `register_screen` —
so this was invisible in the TUI with no native fallback.

### The fix (done)
Added a native Textual `ModalScreen` mirroring the `prune` pattern:
- `code_puppy/plugins/steer_queue/queue_tui.py` — `QueueScreen` + `open_queue`.
  Single-select `OptionList` + live detail pane; `a` add / `e` edit /
  `d` delete / Esc close. Add/edit reuse the shared `tui/screens/form.py`
  `FormScreen` (textarea field) rather than a bespoke input modal (DRY).
- All mutations route through the **same** `PauseController` steer-queue
  (`peek_pending_steer_queued` / `request_steer(mode="queue")` /
  `replace_pending_steer_queued`), so the `(N pending)` status suffix updates
  live exactly as in classic.
- `register_callbacks.py` now registers the `register_screen` opener
  (`_register_queue_screen`).
- Tests: `tests/plugins/test_steer_queue_tui.py` (7 tests, green).

### Note for the next reader
The per-plugin audit that surfaced this confirmed that **every** interactive
picker plugin now has a real native Textual screen (`puppy_spinner`'s
text-redirect stopgap was replaced with a live-preview modal — see Gap #3).
Every other `custom_command` plugin is fire-and-forget (prints / toggles
config) and needs no screen.

---

## Things confirmed fine (no action needed)

- GLM/Claude-5/reasoning-effort model settings (`thinking_type`,
  `glm_reasoning_effort`, etc.) — TUI's `model_settings.py` imports
  `SETTING_DEFINITIONS` from the shared `command_line/model_settings_menu.py`
  and iterates generically. New settings appear automatically. 
- `/undo`, `/plan` — plain `register_command` handlers dispatched via
  `handle_command()`, identical in both UIs. 
- `register_screen`-based plugins (agent_skills, hook_manager, plugin_list's
  enable/disable list itself, prune, steer_queue's /queue, theme's redirect
  message) — all correctly wired for the TUI via the `register_screen` hook +
  `tui/menus.py::get_menu_opener`. 
- MCP agent-binding menu (`command_line/mcp_binding_menu.py`) — predates the
  fork (`d91c758e`, confirmed ancestor of `6df8f79e`), not a new feature; the
  TUI's `agent_picker.py` shows bound-server info read-only in the preview
  panel but has no `B` (bind) keybinding — **this might be worth a follow-up
  glance** but wasn't flagged as high-priority since it predates the fork and
  wasn't part of "main's new features."
- `dbos_durable_exec` SQLite migration race fix (`45b5e7a4`) — backend-only, no UI surface.
- quick_resume, statusline, context_indicator changes — backend/config-layer only.

---

## Testing notes for whoever picks this up

- Full TUI test suite: `uv run pytest -q tests/tui/` (250 tests passed as of
  the rebase commit `0dd54948`)
- `uv lock --check` confirms lockfile isn't stale after the rebase
- No merge conflicts occurred during the rebase (real overlap with main was
  only `pyproject.toml`/`uv.lock`, both trivial auto-merges)
- Branch: `feature/add-tui`, rebased onto `main` @ `183298ac` (0.0.605),
  pushed with `--force-with-lease` already — start fresh work from current
  HEAD, no rebase needed again for this session.

"""subagent_panel -- live per-sub-agent status rows on the bottom bar.

While running, the panel renders one aligned row per sub-agent on the
bottom bar's panel rows (above the status/context row, pinned outside
the scroll region):

     \U0001f916 INVOKE AGENT <name>  <model>  <spin> 00:19  calling read_file

On completion, a PERSISTENT frozen record is printed to the transcript that
mirrors the live look, with the status finalized green + check.

Install strategy (startup monkeypatches of seams with no hook + callbacks):
  1. Live panel -> rendered to PLAIN text lines and pushed to
     ``bottom_bar.set_panel_lines()`` on every state change (event-driven;
     no Rich Live, no dedicated animation thread — the spin frame advances
     whenever a stream event lands).
  2. RichConsoleRenderer._render_subagent_invocation -> CAPTURE exact metadata
     (name/model/session_id) + SUPPRESS the permanent banner.
  3. RichConsoleRenderer._do_render -> when a SubAgentResponseMessage arrives
     (core skips it), handle the frozen record. A NESTED child is marked done
     but KEPT in the live tree (shown 'completed') so it never vanishes
     mid-run; the whole subtree flushes to the transcript parent-first only
     when its ROOT finishes, then is removed from the live tree.
  4. subagent_invocation.emit_success -> suppress the redundant
     "<check> <name> completed successfully" line (it comes from the separate
     message_queue system, NOT the bus, so it must be dropped at its source).
  + stream_event callback feeds the live status (update-only).

Startup hard-disable with DISABLE_SUBAGENT_PANEL=1 or SUBAGENT_PANEL=0.
Runtime toggle with /set subagent_panel off|on.
"""

from __future__ import annotations

import os
import asyncio
import threading
import time
from contextvars import ContextVar

_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_falsey(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value.strip().lower() in _FALSEY


_DISABLED = _env_truthy("DISABLE_SUBAGENT_PANEL") or _env_falsey("SUBAGENT_PANEL")
_CONFIG_KEY = "subagent_panel"


def _config_value(name: str) -> str | None:
    try:
        from code_puppy.config import get_value

        value = get_value(name)
        return None if value is None else str(value).strip().lower()
    except Exception:
        return None


def _runtime_enabled() -> bool:
    if _DISABLED:
        return False
    if _config_value(f"disable_{_CONFIG_KEY}") in _TRUTHY:
        enabled = False
    elif _config_value(_CONFIG_KEY) in _FALSEY:
        enabled = False
    else:
        enabled = True
    if not enabled:
        try:
            state.clear()
        except Exception:
            pass
    return enabled


if not _DISABLED:
    from code_puppy.callbacks import register_callback

    from . import coalesce_patch, resume_repaint, state

# Async-safe parent-session pointer. The bus's _current_session_id is ONE
# global shared across every asyncio task, so two invoke_agent calls running
# concurrently clobber it (root B reads root A as its parent -> a bogus deep
# chain). A ContextVar is COPIED into each task at create_task time, so
# concurrent siblings each see their own correct parent. We mirror
# set_session_context into this var (see _install_parent_tracking) and read it
# in the emit hook.
_PARENT_SID: ContextVar = ContextVar("subagent_panel_parent_sid", default=None)


# ---------------------------------------------------------------------------
# Shared rendering helpers (moved to panel_render.py; re-exported here for
# backwards compatibility -- tests and out-of-tree code import these names
# from register_callbacks)
# ---------------------------------------------------------------------------
from .panel_render import (  # noqa: E402
    _model_short as _model_short,  # noqa: F401  (re-export)
    _model_variant as _model_variant,  # noqa: F401  (re-export)
    _model_version as _model_version,  # noqa: F401  (re-export)
    _ordered_tree,
    _row_lines,
)


def _resolve_model(agent_name, override):
    """Resolve the EFFECTIVE model for a sub-agent (override -> pinned ->
    global default), mirroring subagent_invocation's precedence. The invocation
    message only carries the override (usually None), so we ask the agent config
    directly. Returns the override (or None) on any failure."""
    try:
        from code_puppy.agents.agent_manager import load_agent

        cfg = load_agent(agent_name)
        if override:
            with cfg.temporary_model_name_override(override):
                return cfg.get_model_name()
        return cfg.get_model_name()
    except Exception:
        return override


# ---------------------------------------------------------------------------
# Live panel rendering (event-driven, pushed to the bottom bar)
# ---------------------------------------------------------------------------
#
# Compression scheme (bottom bar caps the panel at PANEL_MAX_ROWS=4 rows):
#   * The live format is already ONE aligned row per agent (badge/elbow +
#     name + model + spin/check + elapsed + status) — information-complete,
#     so no per-agent compression is needed.
#   * <= 4 agents: one row each.
#   * >  4 agents: first 3 rows (DFS order, parents first) + "(+N more)".
# Rows are rendered via the shared _row_lines() (same as the transcript)
# and pushed as rich.text.Text — the bottom bar paints styled Text rows in
# full color (SGRs regenerated from trusted Style objects; content still
# sanitized per-segment), so the live rows match the frozen record.

#: Max rows the bottom bar will display for us (mirrors PANEL_MAX_ROWS).
_PANEL_ROW_CAP = 4

#: Same-shape repaints (spin frame / elapsed churn) at most 10x/second.
_PUSH_MIN_INTERVAL = 0.1
# NOTE: deliberately unsynchronized. Multiple threads may race on these
# two scalar slots, but the worst outcome is one extra (or one skipped)
# throttled repaint — the next event self-heals. A lock here would buy
# nothing except contention on the hot stream-event path.
_push_state = {"t": 0.0, "count": -1}


def _panel_lines():
    """Render the live tree to styled Text rows for the bottom-bar panel."""
    if not _runtime_enabled():
        return []
    rows = state.snapshot()
    if not rows:
        return []
    frame = state.spinner_frame()
    ordered = _ordered_tree(rows)
    if len(ordered) <= _PANEL_ROW_CAP:
        shown = ordered
        extra = 0
    else:
        shown = ordered[: _PANEL_ROW_CAP - 1]
        extra = len(ordered) - len(shown)
    lines = list(_row_lines(shown, frame))
    if extra > 0:
        lines.append(f"  (+{extra} more)")
    return lines


# ---------------------------------------------------------------------------
# 4 Hz elapsed-clock ticker (asyncio task — zero new threads)
# ---------------------------------------------------------------------------
#
# The panel repaint is event-driven, so during a long SILENT model call
# no stream events arrive and the mm:ss column would freeze. The ticker
# repaints ~4x/second while any sub-agent is tracked — fast enough that
# the wall-clock-derived braille spin frame animates smoothly during
# silence, still comfortably above the 10fps same-shape throttle in
# _push_panel (0.25s > 0.1s), so a plain (non-force) push is sufficient.
# Flicker-safe: each repaint is ONE atomic bottom-bar write (CUP + EL +
# text per row) — the same machinery the puppy spinner drives at 20fps.

_TICK_INTERVAL_S = 0.25
_ticker_task: "asyncio.Task | None" = None
_ticker_lock = threading.Lock()


def _start_ticker() -> None:
    """Start the ticker task (idempotent; no-op without a running loop)."""
    global _ticker_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop (sync/odd context): stay event-driven only
    with _ticker_lock:
        if _ticker_task is not None and not _ticker_task.done():
            return
        _ticker_task = loop.create_task(_tick_loop())


def _stop_ticker() -> None:
    """Cancel the ticker task if it's running. Idempotent."""
    global _ticker_task
    with _ticker_lock:
        task = _ticker_task
        _ticker_task = None
    if task is not None and not task.done():
        task.cancel()


async def _tick_loop() -> None:
    """Repaint ~4x/second so clocks + spin frames advance during silence."""
    global _ticker_task
    try:
        while True:
            await asyncio.sleep(_TICK_INTERVAL_S)
            if not state.has_active():
                break  # belt-and-braces: never outlive the swarm
            _push_panel()
    except asyncio.CancelledError:
        pass
    finally:
        with _ticker_lock:
            if _ticker_task is asyncio.current_task():
                _ticker_task = None


def _push_panel(force: bool = False) -> None:
    """Push the rendered panel to the bottom bar (throttled).

    ``force=True`` bypasses the throttle — used for shape-changing events
    (register / done / clear) so grow/collapse is never delayed.
    """
    try:
        lines = _panel_lines()
        now = time.time()
        if (
            not force
            and len(lines) == _push_state["count"]
            and now - _push_state["t"] < _PUSH_MIN_INTERVAL
        ):
            return  # frame/elapsed churn — skip this repaint
        _push_state["t"] = now
        _push_state["count"] = len(lines)
        from code_puppy.messaging.bottom_bar import get_bottom_bar

        get_bottom_bar().set_panel_lines(lines)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Frozen (persistent) completion record
# ---------------------------------------------------------------------------
def _handle_frozen(console, session_id):
    """A sub-agent finished. Mark it done but KEEP it grouped in the live panel
    (rendered as 'completed'). The ENTIRE panel flushes to the transcript as one
    cohesive group ONLY once the whole swarm is idle (every tracked agent done).
    So a finished root never commits mid-swarm, and nothing -- steer lines or
    otherwise -- can ever be interleaved between the grouped agent rows.
    """
    if not session_id:
        return
    state.mark_done(session_id)
    _maybe_flush_group(console)
    _push_panel(force=True)


def _maybe_flush_group(console):
    """Flush the WHOLE live panel to scrollback as one group (parent-first DFS),
    then clear it -- but ONLY when no agent is still active. While any agent is
    running, completed agents stay grouped in the live panel (shown 'completed'),
    so the panel remains a single cohesive block pinned above the spinner.
    """
    rows = state.snapshot()
    if not rows:
        return
    if any(not e.get("done") for e in rows):
        return  # swarm still busy -- keep the panel grouped + live
    if console is None:
        return
    ordered = _ordered_tree(rows)
    console.print()  # breathing room between the transcript and the group
    for line in _row_lines(ordered, frame=None):
        console.print(line)
    state.clear()
    _stop_ticker()  # last agent flushed — nothing left to clock
    _push_panel(force=True)  # collapse the panel rows


# ---------------------------------------------------------------------------
# Monkeypatch installers
# ---------------------------------------------------------------------------
def _install_parent_tracking() -> None:
    """Mirror set_session_context() into an async-safe ContextVar.

    subagent_invocation.py calls set_session_context(child_sid) at :118 (in the
    INVITING agent's task) BEFORE create_task() spawns the child's run at :272.
    create_task copies the current context, so the child task inherits
    _PARENT_SID = its own sid; when the child later invokes a grandchild, the
    emit hook reads _PARENT_SID = the child sid = the true parent. Concurrent
    roots can't clobber each other because each task has its own copy (unlike
    the bus's single global _current_session_id).
    """
    import code_puppy.tools.subagent_invocation as sai

    original = sai.set_session_context
    if getattr(original, "_subagent_panel", False):
        return

    def _set(session_id):
        if _runtime_enabled():
            try:
                _PARENT_SID.set(session_id)
            except Exception:
                pass
        return original(session_id)

    _set._subagent_panel = True
    sai.set_session_context = _set


def _install_emit_hook() -> None:
    """Register sub-agents (with parent + model) at EMIT time.

    emit() at subagent_invocation.py:105 runs BEFORE set_session_context(child)
    at :118, so at emit time _PARENT_SID still holds the INVITING agent's sid
    (or None in the main agent's task -> a root). We read the async-safe
    ContextVar, NOT the bus's global _current_session_id, so parallel invokes
    don't cross-wire their parents.
    """
    from code_puppy.messaging.bus import MessageBus

    current = MessageBus.emit
    if getattr(current, "_subagent_panel", False):
        return

    def _emit(self, message):
        try:
            if (
                _runtime_enabled()
                and type(message).__name__ == "SubAgentInvocationMessage"
            ):
                parent = _PARENT_SID.get()
                model = _resolve_model(
                    message.agent_name, getattr(message, "model_name", None)
                )
                state.register(message.session_id, message.agent_name, model, parent)
                _push_panel(force=True)
                _start_ticker()  # keeps mm:ss advancing through silence
        except Exception:
            pass
        return current(self, message)

    _emit._subagent_panel = True
    MessageBus.emit = _emit


def _install_banner_capture() -> None:
    """Suppress the core permanent invocation banner. Registration now happens
    in the emit hook (where the parent is knowable), so this only suppresses."""
    from code_puppy.messaging.rich_renderer import RichConsoleRenderer

    current = RichConsoleRenderer._render_subagent_invocation
    if getattr(current, "_subagent_panel", False):
        return

    def _capture(self, msg):
        if not _runtime_enabled():
            return current(self, msg)
        return  # suppress the permanent banner -- live block owns it

    _capture._subagent_panel = True
    RichConsoleRenderer._render_subagent_invocation = _capture


def _install_render_wrapper() -> None:
    """Wrap _do_render to (a) print a frozen record when a sub-agent response
    arrives and (b) suppress the redundant completion text line."""
    from code_puppy.messaging.rich_renderer import RichConsoleRenderer

    current = RichConsoleRenderer._do_render
    if getattr(current, "_subagent_panel", False):
        return

    def _wrapped(self, message):
        try:
            if (
                _runtime_enabled()
                and type(message).__name__ == "SubAgentResponseMessage"
            ):
                _handle_frozen(self._console, getattr(message, "session_id", None))
                # Core skips SubAgentResponseMessage anyway -> fully handled.
                return
        except Exception:
            pass
        return current(self, message)

    _wrapped._subagent_panel = True
    RichConsoleRenderer._do_render = _wrapped


def _install_suppress_completion() -> None:
    """Suppress the redundant '<check> <name> completed successfully' line.

    That line is emitted by subagent_invocation via message_queue.emit_success
    (a DIFFERENT system than the bus that _do_render renders), so it must be
    suppressed at its source. We patch the name bound in subagent_invocation's
    namespace -- the only caller -- and pass everything else through.
    """
    import code_puppy.tools.subagent_invocation as sai

    current = getattr(sai, "emit_success", None)
    if current is None or getattr(current, "_subagent_panel", False):
        return

    def _filtered(content, *args, **kwargs):
        try:
            text = str(content).strip()
            if (
                _runtime_enabled()
                and text.endswith("completed successfully")
                and "\u2713" in text
            ):
                return  # the frozen record already says "completed"
        except Exception:
            pass
        return current(content, *args, **kwargs)

    _filtered._subagent_panel = True
    sai.emit_success = _filtered


# TODO(deferred): replace this pile of monkeypatches (MessageBus.emit,
# renderer seams, emit_success, set_session_context, coalesce wrapper)
# with real core hooks — e.g. subagent_registered / subagent_completed
# callbacks — so the plugin stops depending on private call signatures.
def _install() -> None:
    if _DISABLED:
        return
    for installer in (
        lambda: coalesce_patch.install(_runtime_enabled),
        _install_parent_tracking,
        _install_emit_hook,
        _install_banner_capture,
        _install_render_wrapper,
        _install_suppress_completion,
        lambda: resume_repaint.install(_runtime_enabled, state, _push_panel),
    ):
        try:
            installer()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Status callback
# ---------------------------------------------------------------------------
async def _on_stream_event(event_type, event_data, agent_session_id=None):
    if not _runtime_enabled():
        return
    try:
        state.record_event(agent_session_id, event_type, event_data)
    except Exception:
        pass
    # Event-driven animation: the spin frame + elapsed columns advance on
    # every repaint; _push_panel throttles same-shape churn to ~10fps.
    _push_panel()


async def _on_agent_run_end(
    agent_name=None,
    model_name=None,
    session_id=None,
    success=True,
    error=None,
    response_text=None,
    metadata=None,
):
    """When the TOP-LEVEL turn ends, wipe all tracked sub-agents so a root that
    errored or was cancelled (never flushed) can't leak its 'completed' children
    into the next prompt's live block. Only fires for the main agent -- sub-agent
    runs go through temp_agent.run(), not _runtime, and is_subagent() guards the
    rest.
    """
    if not _runtime_enabled():
        return
    try:
        from code_puppy.tools.subagent_context import is_subagent

        if is_subagent():
            return  # a sub-agent finishing -- leave the live tree intact
    except Exception:
        pass
    try:
        state.clear()
    except Exception:
        pass
    _stop_ticker()  # run over — never leave an orphan clock task
    _push_panel(force=True)


async def _on_agent_run_cancel(group_id=None):
    """Ctrl+C / cancel path: stop the ticker IMMEDIATELY and collapse.

    ``_tear_down_live_panels`` (core, sync signal handler) already wipes
    the bar's panel rows; without this hook the ticker's next 1s tick
    would repaint the stale rows right back until ``agent_run_end``
    fires. Clearing state here is idempotent with the run-end cleanup.
    """
    if not _runtime_enabled():
        return
    _stop_ticker()
    try:
        state.clear()
    except Exception:
        pass
    _push_panel(force=True)


async def _on_post_tool_call(tool_name, tool_args, result, duration_ms, context=None):
    """Authoritative completion **state** signal for sub-agent invocations.

    Background: the primary completion path is ``SubAgentResponseMessage`` ->
    ``_handle_frozen`` -> ``state.mark_done``. But ``_invoke_agent_impl`` in
    ``tools/subagent_invocation.py`` suppresses that emit in high-output mode
    when tokens have already streamed inline (to avoid double-rendering the
    response). Without a fallback the row would sit frozen on its last
    ``stream_event``-derived status forever -- a parent blocked awaiting
    children emits no further ``part_start`` events, so it stays on
    ``"thinking..."`` until the next top-level turn clears the panel.

    ``post_tool_call`` fires whenever the tool returns -- success OR failure,
    high mode OR not, response message emitted OR suppressed. It carries the
    ``AgentInvokeOutput`` (whose ``.session_id`` and ``.error`` are the durable
    truth). Idempotent with ``_handle_frozen``: ``mark_done`` / ``mark_failed``
    are set-then-keep on the entry, so the dual-fire path stays correct.

    Why we do NOT call ``_maybe_flush_group`` from here
    ---------------------------------------------------
    This callback runs from the pydantic-ai agent run loop -- OUTSIDE the
    renderer's coordination path. ``_handle_frozen`` can safely call flush
    because it lives inside ``_do_render``: the Rich Live region is paused /
    coordinated for that paint. Printing from an out-of-band task races the
    main agent's streaming tokens and produces character-level collisions in
    the terminal (visible as garbled, interleaved output).

    Mid-turn flush in high mode is therefore deferred to whichever
    render-serialized hook eventually fires next: ``_handle_frozen`` when a
    later sub-agent response IS emitted, or ``_on_agent_run_end`` /
    ``state.clear()`` at end of turn. The row at least now reads
    ``"completed"`` instead of lying about ``"thinking..."``; finding a
    render-serialized mid-turn flush trigger for high mode is a follow-up.
    """
    if not _runtime_enabled():
        return
    if tool_name not in ("invoke_agent", "invoke_agent_with_model"):
        return
    sid = getattr(result, "session_id", None)
    if not sid:
        return
    try:
        err = getattr(result, "error", None)
        if err:
            state.mark_failed(sid)
        else:
            state.mark_done(sid)
    except Exception:
        pass
    _push_panel(force=True)


if not _DISABLED:
    register_callback("startup", _install)
    register_callback("stream_event", _on_stream_event)
    register_callback("agent_run_end", _on_agent_run_end)
    register_callback("agent_run_cancel", _on_agent_run_cancel)
    register_callback("post_tool_call", _on_post_tool_call)

"""subagent_panel -- live two-line status per sub-agent in the puppy spinner.

While running (transient, in the puppy's Live region):

     INVOKE AGENT <name>  <model>
      <spin> 00:19  calling read_file

    <bouncing puppy>

On completion, a PERSISTENT frozen record is printed to the transcript that
mirrors the live look, with the status line finalized green + check:

     INVOKE AGENT <name>  <model>
      \u2713 00:45  completed

Install strategy (startup monkeypatches of seams with no hook + 1 callback):
  1. ConsoleSpinner._generate_spinner_panel  -> render the live block above the
     puppy (reuses the existing 20fps Live -- no second Live, no flicker).
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
import re
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
# Shared rendering helpers
# ---------------------------------------------------------------------------
def _banner_color():
    try:
        from code_puppy.config import get_banner_color

        return get_banner_color("invoke_agent")
    except Exception:
        return "blue"


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
# Hierarchy helpers (true parent -> child tree)
# ---------------------------------------------------------------------------
def _ordered_tree(rows):
    """Return [(entry, depth), ...] in DFS order. A row whose parent is not in
    the set (e.g. the main agent, or None) is a root (depth 0); descendants are
    indented one-liners. Cycle-safe; stable by start time."""
    by_id = {e["session_id"]: e for e in rows if e.get("session_id")}
    children = {}
    roots = []
    for e in rows:
        p = e.get("parent")
        if p and p in by_id:
            children.setdefault(p, []).append(e)
        else:
            roots.append(e)
    out = []
    seen = set()

    def walk(node, depth):
        sid = node.get("session_id")
        if sid in seen:
            return
        seen.add(sid)
        out.append((node, depth))
        for kid in sorted(children.get(sid, []), key=lambda c: c["start"]):
            walk(kid, depth + 1)

    for r in sorted(roots, key=lambda e: e["start"]):
        walk(r, 0)
    return out


# Tier/variant qualifiers that distinguish models sharing a version number
# (e.g. gpt-5.4 vs gpt-5.4-nano vs gpt-5.4-mini). Without these, three distinct
# models all collapse to "GPT 5.4" in the panel -- the exact confusion this maps
# away. key (lowercased token in the id) -> Display label.
_MODEL_VARIANTS = (
    ("nano", "Nano"),
    ("mini", "Mini"),
    ("micro", "Micro"),
    ("lite", "Lite"),
    ("turbo", "Turbo"),
    ("flash", "Flash"),
    ("instant", "Instant"),
    ("codex", "Codex"),
    ("thinking", "Thinking"),
    ("reasoning", "Reasoning"),
    ("preview", "Preview"),
    ("pro", "Pro"),
)


def _model_variant(m):
    """Extract a tier/variant qualifier (Nano, Mini, Flash, ...) from a lowercased
    model id. Matched ONLY as a hyphen/underscore/dot/space-delimited token, so
    'mini' inside 'gemini' (or 'pro' inside another word) can never false-fire.
    Returns '' when the id carries no recognised variant."""
    for key, label in _MODEL_VARIANTS:
        if re.search(rf"(?:^|[-_. ]){re.escape(key)}(?:$|[-_. ])", m):
            return label
    return ""


def _model_version(m):
    """Extract a 'major.minor' version from a lowercased model id, tolerating
    BOTH separators in the wild: a contiguous decimal ('gpt-5.4' -> '5.4') OR a
    dash-separated pair ('gpt-5-4', 'claude-4-8-opus' -> '5.4'/'4.8'). Only joins
    two integer groups when both are short (<=2 digits) so date/snapshot ids like
    'gpt-4-0125' don't get mangled into '4.0125'. Returns '' when no number."""
    dec = re.search(r"\d+\.\d+", m)
    if dec:
        return dec.group(0)
    nums = re.findall(r"\d+", m)
    if not nums:
        return ""
    if len(nums) >= 2 and len(nums[0]) <= 2 and len(nums[1]) <= 2:
        return f"{nums[0]}.{nums[1]}"
    return nums[0]


def _model_short(model):
    """Human-readable shorthand for a model id, for live readability.
    e.g. 'claude-4-8-opus' -> 'Opus 4.8', 'claude-sonnet-4-6' -> 'Sonnet 4.6',
    'gpt-5.5' -> 'GPT 5.5', 'gpt-5.4-nano' -> 'GPT 5.4-Nano'. The tier qualifier
    is preserved so same-version-different-tier models stay distinct. Falls back
    to the raw id if unrecognised."""
    if not model:
        return ""

    m = str(model).lower()
    variant = _model_variant(m)
    suffix = f"-{variant}" if variant else ""
    ver = _model_version(m)
    for key, label in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")):
        if key in m:
            return f"{label} {ver}{suffix}".strip()
    if "gpt" in m:
        return (f"GPT {ver}{suffix}" if ver else f"GPT{suffix}").strip()
    if "gemini" in m:
        return (f"Gemini {ver}{suffix}" if ver else f"Gemini{suffix}").strip()
    return str(model)


def _row_lines(ordered, frame):
    """Render a list of (entry, depth) as aligned single-line rows:
        <prefix><name>   <model>   <spin|check> <mm:ss>
    The model + indicator + time columns share a per-tree tab-stop computed
    from the widest (prefix+name) AND the widest model label, so longer model
    names (e.g. 'GPT 5.4-Nano') and deeper-indented names both push the whole
    right block over together -- columns stay aligned no matter what gets added.
    Alignment is done purely with U+0020 spaces (never literal tabs), and widths
    use Rich cell_len, so the layout renders identically on Windows and macOS.
    Root rows carry the INVOKE AGENT badge; nested rows carry the tree elbow.
    Used for BOTH the live block and the transcript.
    """
    from rich.cells import cell_len
    from rich.text import Text

    color = _banner_color()
    lefts = []
    models = []
    name_w = 0
    model_w = 0
    for e, depth in ordered:
        left = Text(no_wrap=True, overflow="ellipsis")
        if depth == 0:
            left.append(" \U0001f916 INVOKE AGENT ", style=f"bold white on {color}")
            left.append(" ")
            left.append(e["name"], style="bold cyan")
        else:
            left.append("  " + "   " * (depth - 1))
            left.append("\u2514\u2500 ", style="grey50")  # tree elbow
            left.append(e["name"], style="bold cyan")
        lefts.append(left)
        ms = _model_short(e.get("model"))
        models.append(ms)
        name_w = max(name_w, left.cell_len)
        model_w = max(model_w, cell_len(ms))

    lines = []
    for (e, depth), left, ms in zip(ordered, lefts, models):
        done = bool(e.get("done"))
        failed = bool(e.get("failed"))
        line = left.copy()
        # These rows are deliberately one-line status rows. If a long tool name
        # wraps (e.g. calling agent_run_shell_command on a narrow terminal), the
        # shared Rich Live grows at Ctrl+T and strands the previous frame into
        # scrollback. Crop visually; preserve full status in state.
        line.no_wrap = True
        line.overflow = "ellipsis"
        line.append(" " * (name_w - left.cell_len + 2))
        line.append(ms, style="magenta")
        line.append(" " * (model_w - cell_len(ms) + 2))
        if failed:
            line.append("\u2717 ", style="bold red")  # X mark
        elif done:
            line.append("\u2713 ", style="bold green")  # check
        else:
            line.append((frame or " ") + " ", style="bold cyan")
        line.append(state.fmt_elapsed_entry(e), style="dim")
        # Current action / status, color-coded (yellow=calling, magenta=thinking,
        # green=writing). Done rows show 'completed' green; failed rows 'failed' red.
        status = e.get("status", "starting")
        line.append("  ")
        if failed:
            line.append("failed", style="bold red")
        elif done:
            line.append("completed", style="green")
        else:
            line.append(status, style=state.status_style(status))
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Live panel rendering (called from the spinner repaint loop, ~20fps)
# ---------------------------------------------------------------------------
def _render_status_lines():
    if not _runtime_enabled():
        return None
    rows = state.snapshot()
    if not rows:
        return None

    from rich.text import Text

    frame = state.spinner_frame()
    ordered = _ordered_tree(rows)
    shown = ordered[: state.MAX_ROWS]
    lines = _row_lines(shown, frame)

    extra = len(ordered) - len(shown)
    if extra > 0:
        lines.append(Text(f"  (+{extra} more)", style="dim"))
    return lines


def _make_patched_panel(original_fn):
    from rich.console import Group
    from rich.text import Text

    def _patched(self):
        original = original_fn(self)
        if isinstance(original, Text) and str(original) == "":
            return original
        if not _runtime_enabled():
            return original

        try:
            block = _render_status_lines()
        except Exception:
            block = None
        if not block:
            return original
        return Group(*block, Text(""), original)

    _patched._subagent_panel = True
    return _patched


# ---------------------------------------------------------------------------
# Frozen (persistent) completion record
# ---------------------------------------------------------------------------
def _render_console():
    """The Rich console the puppy spinner's Live is attached to. Printing to it
    while the Live is active makes Rich relocate the panel BELOW the print, so
    the flushed group lands cleanly in scrollback above the live region."""
    try:
        from code_puppy.messaging.spinner import _active_spinners

        for sp in _active_spinners:
            con = getattr(sp, "console", None)
            if con is not None:
                return con
    except Exception:
        pass
    return None


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
    for line in _row_lines(ordered, frame=None):
        console.print(line)
    state.clear()


# ---------------------------------------------------------------------------
# Monkeypatch installers
# ---------------------------------------------------------------------------
def _install_spinner_patch() -> None:
    from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

    current = ConsoleSpinner._generate_spinner_panel
    if not getattr(current, "_subagent_panel", False):
        ConsoleSpinner._generate_spinner_panel = _make_patched_panel(current)


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


def _install() -> None:
    if _DISABLED:
        return
    for installer in (
        lambda: coalesce_patch.install(_runtime_enabled),
        _install_spinner_patch,
        _install_parent_tracking,
        _install_emit_hook,
        _install_banner_capture,
        _install_render_wrapper,
        _install_suppress_completion,
        lambda: resume_repaint.install(_runtime_enabled, state),
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


async def _on_post_tool_call(tool_name, tool_args, result, duration_ms, context=None):
    """Detect a FAILED sub-agent so it renders red 'failed' instead of a green
    'completed' checkmark.

    The invoke_agent tool returns an AgentInvokeOutput(session_id=..., error=...)
    and -- crucially -- does NOT raise on sub-agent failure (its own except block
    swallows the error and returns it on the output). So no SubAgentResponseMessage
    is emitted, the node is never marked done via the normal path, and the root
    flush would otherwise force it green. We read the returned .error here (the
    real failure signal, present only AFTER the retry plugin has exhausted all
    waves) and mark that exact session failed.
    """
    if not _runtime_enabled():
        return
    try:
        err = getattr(result, "error", None)
        sid = getattr(result, "session_id", None)
        if err and sid:
            state.mark_failed(sid)
            # A failed agent is 'done' too -- if it was the last one running,
            # flush the whole grouped panel now (failure path emits no
            # SubAgentResponseMessage, so _handle_frozen won't fire).
            _maybe_flush_group(_render_console())
    except Exception:
        pass


if not _DISABLED:
    register_callback("startup", _install)
    register_callback("stream_event", _on_stream_event)
    register_callback("agent_run_end", _on_agent_run_end)
    register_callback("post_tool_call", _on_post_tool_call)

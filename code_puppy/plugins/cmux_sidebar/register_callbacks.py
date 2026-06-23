"""cmux sidebar dashboard for Code Puppy.

A self-contained Code Puppy plugin that turns the cmux sidebar into a live
dashboard of agent activity:

* an **activity pill** with per-tool icons + colors (read / write / shell /
  search / delete / agent),
* a **context-window pill** (token usage %, color-coded),
* a **progress bar**,
* **detailed log entries** that show the actual file / command / pattern,
* a **run summary** on completion (duration, tool count, tokens, tok/s,
  context %) plus a desktop notification and a screen flash.

Self-contained on purpose: one module, no sibling imports, so it loads
identically as a builtin, user (~/.code_puppy/plugins/), or project plugin.
Enrichment data (run stats, context usage) is imported defensively -- if a
given Code Puppy build doesn't expose it, that piece is simply skipped.

No-ops cleanly when not running inside cmux.

Env toggles:
* ``CMUX_SIDEBAR_DISABLED=1`` -- turn the whole plugin off.
* ``CMUX_SIDEBAR_QUIET=1``    -- suppress per-tool log spam (keep pills +
  the end-of-run summary only).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from functools import lru_cache

from code_puppy.callbacks import register_callback

# --------------------------------------------------------------------------- #
# Sidebar identifiers
# --------------------------------------------------------------------------- #
KEY_ACTIVITY = "pup"
KEY_CONTEXT = "pup_ctx"
KEY_TASK = "pup_task"
KEY_SAY = "pup_say"
LOG_SOURCE = "code-puppy"

# Activity colors
COLOR_THINKING = "#7C4DFF"
COLOR_DONE = "#4CAF50"
COLOR_ERROR = "#EB5757"
COLOR_IDLE = "#9E9E9E"
COLOR_TASK = "#4F8EF7"
COLOR_SAY = "#00BFA5"

# How often (seconds) the live narration pill may update, to avoid spawning a
# cmux subprocess per streamed token.
_SAY_THROTTLE = 0.6

# Per-tool palette
COLOR_READ = "#2D9CDB"
COLOR_WRITE = "#F2994A"
COLOR_DELETE = "#EB5757"
COLOR_SHELL = "#9B51E0"
COLOR_SEARCH = "#56CCF2"
COLOR_AGENT = "#27AE60"
COLOR_TOOL = "#2D9CDB"

# Context %-buckets (match Code Puppy's own 30 / 65 indicator thresholds).
CTX_GREEN = "#4CAF50"
CTX_YELLOW = "#F2C94C"
CTX_RED = "#EB5757"

# tool_name -> (icon, color, (preferred arg keys...))
_TOOL_META: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "read_file": ("eye", COLOR_READ, ("file_path",)),
    "list_files": ("folder", COLOR_READ, ("directory", "path")),
    "grep": ("magnifyingglass", COLOR_SEARCH, ("search_string", "pattern")),
    "edit_file": ("pencil", COLOR_WRITE, ("file_path",)),
    "create_file": ("plus.square", COLOR_WRITE, ("file_path",)),
    "replace_in_file": ("pencil", COLOR_WRITE, ("file_path",)),
    "delete_snippet": ("scissors", COLOR_WRITE, ("file_path",)),
    "delete_file": ("trash", COLOR_DELETE, ("file_path",)),
    "agent_run_shell_command": ("terminal", COLOR_SHELL, ("command",)),
    "run_shell_command": ("terminal", COLOR_SHELL, ("command",)),
    "invoke_agent": ("person.2", COLOR_AGENT, ("agent_name",)),
    "list_agents": ("person.2", COLOR_AGENT, ()),
}
_DEFAULT_META = ("hammer", COLOR_TOOL, ("file_path", "command", "query", "name"))

# tool_name -> short category label (for the end-of-run breakdown).
_TOOL_CATEGORY: dict[str, str] = {
    "read_file": "read",
    "list_files": "read",
    "grep": "search",
    "edit_file": "edit",
    "create_file": "edit",
    "replace_in_file": "edit",
    "delete_snippet": "edit",
    "delete_file": "edit",
    "agent_run_shell_command": "shell",
    "run_shell_command": "shell",
    "invoke_agent": "agent",
    "list_agents": "agent",
}

# Progress heuristic (we can't know the total tool count up front).
_TOOL_STEP = 0.08
_TOOL_CAP = 0.9


# --------------------------------------------------------------------------- #
# cmux CLI wrapper (crash-proof, fire-and-forget)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def in_cmux() -> bool:
    """True only when inside cmux, the CLI is callable, and not disabled."""
    if os.environ.get("CMUX_SIDEBAR_DISABLED"):
        return False
    return bool(os.environ.get("CMUX_WORKSPACE_ID")) and shutil.which("cmux") is not None


def _quiet() -> bool:
    return bool(os.environ.get("CMUX_SIDEBAR_QUIET"))


def _run(args: list[str]) -> None:
    """Fire a cmux command and forget it. Never blocks, never raises."""
    if not in_cmux():
        return
    try:
        subprocess.Popen(
            ["cmux", *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        pass  # cosmetic feature: swallow everything


def _status(key: str, value: str, icon: str, color: str, priority: int = 0) -> None:
    _run(
        [
            "set-status", key, value,
            "--icon", icon, "--color", color, "--priority", str(priority),
        ]
    )


def _clear_status(key: str) -> None:
    _run(["clear-status", key])


def _log(message: str, level: str = "info") -> None:
    _run(["log", "--level", level, "--source", LOG_SOURCE, "--", message])


def _progress(value: float, label: str = "") -> None:
    value = max(0.0, min(1.0, value))
    args = ["set-progress", f"{value:.2f}"]
    if label:
        args += ["--label", label]
    _run(args)


def _clear_progress() -> None:
    _run(["clear-progress"])


def _notify(title: str, body: str, subtitle: str = "") -> None:
    args = ["notify", "--title", title, "--body", body]
    if subtitle:
        args += ["--subtitle", subtitle]
    _run(args)


def _flash() -> None:
    surface = os.environ.get("CMUX_SURFACE_ID")
    if surface:
        _run(["trigger-flash", "--surface", surface])


# --------------------------------------------------------------------------- #
# Optional enrichment (defensive imports -- skipped if build lacks them)
# --------------------------------------------------------------------------- #
def _context_pct() -> float | None:
    """Return context-window usage as a 0-100 percentage, or None."""
    try:
        from code_puppy.plugins.context_indicator.usage import get_current_usage

        usage = get_current_usage()
        if usage is None:
            return None
        return float(usage.percent)
    except Exception:
        return None


def _cycle_stats() -> dict:
    """Return last-cycle stats dict (model/gen_tps/output_tokens), or {}."""
    try:
        from code_puppy.agents.run_stats import AgentRunStats

        return AgentRunStats.get_last_cycle_stats() or {}
    except Exception:
        return {}


def _subagent() -> str | None:
    """Return the active sub-agent name if a tool is running inside one."""
    try:
        from code_puppy.tools.subagent_context import get_subagent_name, is_subagent

        if is_subagent():
            return get_subagent_name() or "subagent"
    except Exception:
        pass
    return None


def _stream_text(event_type: str, event_data) -> str:
    """Pull any text/thinking content out of a streaming event, defensively.

    Mirrors how Code Puppy's own run-stats reads stream events, but without
    importing pydantic-ai types -- we just duck-type ``.content`` /
    ``.content_delta``.
    """
    if not isinstance(event_data, dict):
        return ""
    try:
        if event_type == "part_start":
            part = event_data.get("part")
            return str(getattr(part, "content", "") or "")
        if event_type == "part_delta":
            delta = event_data.get("delta")
            return str(getattr(delta, "content_delta", "") or "")
    except Exception:
        pass
    return ""


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _ctx_color(pct: float) -> str:
    if pct < 30:
        return CTX_GREEN
    if pct < 65:
        return CTX_YELLOW
    return CTX_RED


def _update_context_pill() -> None:
    pct = _context_pct()
    if pct is None:
        return
    _status(
        KEY_CONTEXT, f"ctx {pct:.0f}%", "gauge", _ctx_color(pct), priority=60
    )


def _truncate(text: str, limit: int = 44) -> str:
    text = " ".join(str(text).split())  # collapse whitespace/newlines
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _arg_summary(tool_name: str, tool_args) -> str:
    """Pull the most meaningful argument (file / command / pattern) for display."""
    _, _, keys = _TOOL_META.get(tool_name, _DEFAULT_META)
    if not isinstance(tool_args, dict):
        return ""
    for k in keys:
        val = tool_args.get(k)
        if val:
            # For file paths, show just the basename to keep it tight.
            if k == "file_path":
                val = os.path.basename(str(val)) or str(val)
            return _truncate(val)
    return ""


def _human_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(int(n))


def _fmt_files(limit: int = 4) -> str:
    """Compact list of files touched this run, e.g. 'auth.py, main.py (+2 more)'."""
    if not _files:
        return ""
    shown = _files[:limit]
    extra = len(_files) - len(shown)
    text = ", ".join(shown)
    if extra > 0:
        text += f" (+{extra} more)"
    return text


def _fmt_breakdown() -> str:
    """Compact per-category tool breakdown, e.g. '2 read - 1 edit - 1 shell'."""
    if not _cats:
        return ""
    order = ["read", "search", "edit", "shell", "agent", "other"]
    parts = [f"{_cats[c]} {c}" for c in order if _cats.get(c)]
    return " \u00b7 ".join(parts)


def _fmt_summary(elapsed: float, tools: int) -> str:
    parts = [f"{elapsed:.1f}s", f"{tools} tool{'s' if tools != 1 else ''}"]
    stats = _cycle_stats()
    out = int(stats.get("output_tokens") or 0)
    tps = float(stats.get("gen_tps") or 0.0)
    if out:
        parts.append(f"{_human_tokens(out)} tok")
    if tps:
        parts.append(f"{tps:.0f} tok/s")
    pct = _context_pct()
    if pct is not None:
        parts.append(f"ctx {pct:.0f}%")
    return " \u00b7 ".join(parts)


# --------------------------------------------------------------------------- #
# Per-run state
# --------------------------------------------------------------------------- #
_state: dict[str, float] = {"tool_count": 0, "t0": 0.0}
_cats: dict[str, int] = {}
_files: list[str] = []
_say: dict[str, object] = {"buf": "", "last_push": 0.0, "last_text": ""}

# Tools whose file_path counts as a "touched" (mutated) file.
_WRITE_TOOLS = frozenset(
    {"edit_file", "create_file", "replace_in_file", "delete_file", "delete_snippet"}
)


# --------------------------------------------------------------------------- #
# Lifecycle -> sidebar mapping
# --------------------------------------------------------------------------- #
def _on_startup() -> None:
    if not in_cmux():
        return
    _status(KEY_ACTIVITY, "ready", "sparkle", COLOR_IDLE, priority=70)
    _update_context_pill()


def _on_user_prompt_submit(prompt: str, session_id=None):
    """Show a one-liner of the task the agent is about to work on.

    MUST return None so we never modify the user's prompt -- this hook can
    rewrite prompts, and we only want to *observe* it.
    """
    try:
        task = _truncate(prompt or "", 50)
        if task:
            _status(KEY_TASK, task, "list.bullet", COLOR_TASK, priority=90)
            if not _quiet():
                _log(f"Task: {task}", "info")
    except Exception:
        pass
    return None


def _on_agent_run_start(agent_name: str, model_name: str, session_id=None) -> None:
    _state["tool_count"] = 0
    _state["t0"] = time.monotonic()
    _cats.clear()
    _files.clear()
    _say["buf"] = ""
    _say["last_push"] = 0.0
    _say["last_text"] = ""
    _status(KEY_ACTIVITY, "thinking", "sparkle", COLOR_THINKING, priority=70)
    _progress(0.05, label=model_name or agent_name)
    _update_context_pill()
    if not _quiet():
        _log(f"Run started ({agent_name} / {model_name})", "info")


def _on_stream_event(event_type, event_data, agent_session_id=None) -> None:
    """Live one-liner of what the agent is currently saying/thinking."""
    if not in_cmux():
        return
    chunk = _stream_text(event_type, event_data)
    if not chunk:
        return
    buf = (str(_say.get("buf", "")) + chunk)[-400:]  # keep a rolling tail
    _say["buf"] = buf
    now = time.monotonic()
    if now - float(_say.get("last_push", 0.0)) < _SAY_THROTTLE:
        return
    # Show the most recent words (tail of the collapsed text).
    flat = " ".join(buf.split())
    if not flat:
        return
    tail = flat[-44:]
    if tail == _say.get("last_text"):
        return
    _say["last_push"] = now
    _say["last_text"] = tail
    _status(KEY_SAY, tail, "quote.bubble", COLOR_SAY, priority=80)


def _on_pre_tool_call(tool_name: str, tool_args, context=None) -> None:
    _state["tool_count"] += 1
    count = int(_state["tool_count"])
    _cats[_TOOL_CATEGORY.get(tool_name, "other")] = (
        _cats.get(_TOOL_CATEGORY.get(tool_name, "other"), 0) + 1
    )
    icon, color, _ = _TOOL_META.get(tool_name, _DEFAULT_META)
    summary = _arg_summary(tool_name, tool_args)
    sub = _subagent()
    prefix = f"[{sub}] " if sub else ""
    pill = f"{prefix}{tool_name}: {summary}" if summary else f"{prefix}{tool_name}"
    # Sub-agent activity gets the green agent color to stand out.
    pill_color = COLOR_AGENT if sub else color
    _status(KEY_ACTIVITY, _truncate(pill, 36), icon, pill_color, priority=70)
    _progress(min(0.05 + count * _TOOL_STEP, _TOOL_CAP), label=f"{tool_name} (#{count})")
    _update_context_pill()  # live context tracking per tool
    # Track touched (mutated) files for the end-of-run summary.
    if tool_name in _WRITE_TOOLS and isinstance(tool_args, dict):
        fp = tool_args.get("file_path")
        if fp:
            name = os.path.basename(str(fp)) or str(fp)
            if name not in _files:
                _files.append(name)
    if not _quiet():
        detail = f" {summary}" if summary else ""
        _log(f"-> {prefix}{tool_name}{detail}", "progress")


def _on_post_tool_call(
    tool_name: str, tool_args, result=None, duration_ms: float = 0.0, context=None
) -> None:
    if _quiet():
        return
    _log(f"   {tool_name} done in {duration_ms:.0f}ms", "info")


def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id=None,
    success: bool = True,
    error=None,
    response_text=None,
    metadata=None,
) -> None:
    elapsed = time.monotonic() - (_state.get("t0") or time.monotonic())
    tools = int(_state.get("tool_count", 0))
    summary = _fmt_summary(elapsed, tools)
    breakdown = _fmt_breakdown()
    _update_context_pill()
    if success:
        _progress(1.0, label="Complete")
        _status(KEY_ACTIVITY, "done", "checkmark", COLOR_DONE, priority=70)
        _log(f"Complete \u00b7 {summary}", "success")
        if breakdown:
            _log(f"Tools: {breakdown}", "info")
        files = _fmt_files()
        if files:
            _log(f"Files: {files}", "info")
        _notify("Code Puppy", summary, agent_name)
    else:
        _status(KEY_ACTIVITY, "error", "xmark", COLOR_ERROR, priority=70)
        _log(f"Failed: {error} \u00b7 {summary}", "error")
        _notify("Code Puppy", f"Run failed: {error}", agent_name)
    _flash()
    _clear_progress()
    _clear_status(KEY_SAY)


def _on_agent_run_cancel(group_id: str) -> None:
    elapsed = time.monotonic() - (_state.get("t0") or time.monotonic())
    tools = int(_state.get("tool_count", 0))
    _status(KEY_ACTIVITY, "cancelled", "xmark", COLOR_ERROR, priority=70)
    _log(f"Cancelled \u00b7 {elapsed:.1f}s \u00b7 {tools} tools", "warning")
    _clear_progress()
    _clear_status(KEY_SAY)


def _on_shutdown() -> None:
    _clear_progress()
    _clear_status(KEY_ACTIVITY)
    _clear_status(KEY_CONTEXT)
    _clear_status(KEY_TASK)
    _clear_status(KEY_SAY)


# --------------------------------------------------------------------------- #
# Registration (dedup-guarded so accidental double-loads can't double-fire)
# --------------------------------------------------------------------------- #
_REGISTERED = False


def register() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    # Each phase is registered independently: if a given Code Puppy build
    # doesn't support one (register_callback raises ValueError), we skip it
    # and keep the rest -- a missing narration pill must never disable the
    # whole dashboard.
    handlers = (
        ("startup", _on_startup),
        ("user_prompt_submit", _on_user_prompt_submit),
        ("agent_run_start", _on_agent_run_start),
        ("stream_event", _on_stream_event),
        ("pre_tool_call", _on_pre_tool_call),
        ("post_tool_call", _on_post_tool_call),
        ("agent_run_end", _on_agent_run_end),
        ("agent_run_cancel", _on_agent_run_cancel),
        ("shutdown", _on_shutdown),
    )
    for phase, fn in handlers:
        try:
            register_callback(phase, fn)
        except Exception:
            pass
    _REGISTERED = True


register()

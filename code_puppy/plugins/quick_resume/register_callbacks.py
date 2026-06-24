"""Quick-resume workspace observation hooks.

The autosave layer records a quick-resume pointer for cwd. This plugin teaches
Code Puppy about *child* workspaces touched through tools, so a later
``code-puppy -qr ./child`` (or ``/quick-resume ./child``) resolves the session
even when the process was launched from the parent directory the whole time.

Observation is a pure convenience: it only registers hashed pointer keys and
never blocks or alters tool output.
"""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback

# Map tool name -> ((arg_name, path_kind), ...) for tools whose args are plain
# local paths. path_kind tells the scope resolver whether the arg is a file
# (probe its parent) or a directory. Tools with non-string/nested path payloads
# (e.g. edit_file) are intentionally omitted.
_LOCAL_PATH_TOOL_ARGS: dict[str, tuple[tuple[str, str], ...]] = {
    "agent_run_shell_command": (("cwd", "directory"),),
    "create_file": (("file_path", "file"),),
    "delete_file": (("file_path", "file"),),
    "delete_snippet": (("file_path", "file"),),
    "grep": (("directory", "directory"),),
    "list_files": (("directory", "directory"),),
    "read_file": (("file_path", "file"),),
    "replace_in_file": (("file_path", "file"),),
}


def _result_failed(result: Any) -> bool:
    """Return True when a tool result clearly represents a failure.

    Handles both dict results and objects exposing ``error``/``success``.
    """
    if isinstance(result, dict):
        if result.get("error"):
            return True
        if result.get("success") is False:
            return True
    error = getattr(result, "error", None)
    if error:
        return True
    success = getattr(result, "success", None)
    return success is False


def _observe_tool_paths(
    tool_name: str,
    tool_args: dict[str, Any],
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    """Record local workspace paths from successful tool calls (best-effort)."""
    _ = duration_ms, context  # unused; kept for the post_tool_call signature
    if _result_failed(result):
        return

    path_specs = _LOCAL_PATH_TOOL_ARGS.get(tool_name)
    if not path_specs:
        return

    try:
        from code_puppy.config import observe_quick_resume_path

        for arg_name, path_kind in path_specs:
            raw_path = tool_args.get(arg_name)
            if isinstance(raw_path, str) and raw_path.strip():
                observe_quick_resume_path(raw_path, path_kind=path_kind)
    except Exception:
        # Observation is a convenience pointer, never worth breaking tool output.
        return


register_callback("post_tool_call", _observe_tool_paths)

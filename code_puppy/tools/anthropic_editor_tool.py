"""Canonical command dispatch for Anthropic's native text-editor tool.

Phase 3 of the Anthropic editor adapter plan
(``.context/plan/anthropic-editor-adapter.md``). Maps the fixed
``view``/``str_replace``/``create``/``insert`` command shape Claude was
trained on directly onto the same hardened engine the portable
``read_file``/``replace_in_file``/``create_file`` tools use --
``str_replace`` and ``create`` are thin dispatches into the exact-match-safe,
permission-checked, undo-tracked helpers in ``file_modifications.py`` (no
duplicated safety logic); ``view`` and ``insert`` are the two commands with
no existing generic-tool equivalent, implemented here.

Every branch fails loudly and specifically: unknown commands, missing
required fields, and out-of-range locations are all external-input parsing
errors, not silent no-ops.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic_ai import RunContext

from code_puppy.callbacks import on_edit_file, on_file_permission_async
from code_puppy.messaging import FileContentMessage, get_message_bus
from code_puppy.tools import fs_access
from code_puppy.tools.common import generate_group_id, resolve_path
from code_puppy.tools.file_modifications import (
    ContentPayload,
    Replacement,
    ReplacementsPayload,
    _create_rejection_response,
    _emit_diff_message,
    _log_error,
    _permission_denied,
    _write_to_file,
    replace_in_file_async,
    write_to_file_async,
)
from code_puppy.tools.line_endings import detect_dominant, split_lines, to_style

# Claude's older ``text_editor_20241022`` tool had an ``undo_edit`` command;
# the versions this façade targets (2025-04-29 / 2025-07-28) do not -- see
# ``model_capabilities.py``'s module docstring for the verification. Rejected
# by name, not silently ignored, in case a model trained on the older tool
# still emits it.
_UNSUPPORTED_COMMANDS = frozenset({"undo_edit"})
_SUPPORTED_COMMANDS = frozenset({"view", "str_replace", "create", "insert"})

# Reuse the same file-size guard the portable read_file tool applies, so
# `view` can't dump an unbounded file into context either.
_MAX_VIEW_TOKENS = 10_000

# Same intent for the directory-listing branch of `view`, which has no
# equivalent token-based guard of its own to piggyback on.
_MAX_VIEW_ENTRIES = 1_000


def _unsupported_command_error(command: str) -> Dict[str, Any]:
    if command in _UNSUPPORTED_COMMANDS:
        return {
            "error": "unsupported_command",
            "command": command,
            "message": (
                f"'{command}' is not supported by this tool version. There is "
                "no per-command undo stack; make a corrective str_replace or "
                "create call instead, or use the shell/undo tooling."
            ),
        }
    return {
        "error": "unknown_command",
        "command": command,
        "supported_commands": sorted(_SUPPORTED_COMMANDS),
        "message": f"Unknown command '{command}'. Supported: {sorted(_SUPPORTED_COMMANDS)}.",
    }


def _missing_field_error(command: str, field: str) -> Dict[str, Any]:
    return {
        "error": "missing_field",
        "command": command,
        "field": field,
        "message": f"command '{command}' requires '{field}'.",
    }


def _sanitize_surrogates(text: str) -> str:
    """Strip lone Unicode surrogates from file content read off disk.

    Same technique ``_replace_in_file``/``_finalize_read_output`` already
    apply (see ``file_modifications.py``/``file_operations.py``) -- a raw
    non-UTF-8 byte survives ``fs_access.read_text`` as a surrogate
    codepoint, which then raises an untyped ``UnicodeEncodeError`` deep
    inside the eventual write/JSON-serialization path instead of failing
    at this parsing boundary. Kept as its own tiny helper here (a third
    copy) rather than added to ``tools/common.py``/``file_modifications.py``,
    which the plan already flags as over the 600-line limit.
    """
    try:
        return text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        return "".join(
            ch if not (0xD800 <= ord(ch) <= 0xDFFF) else "\ufffd" for ch in text
        )


def _apply_edit_callback(
    context: RunContext, result: Dict[str, Any], payload: Any
) -> Dict[str, Any]:
    """Run the same ``on_edit_file`` enhancement hook the portable
    ``create_file``/``replace_in_file`` tools fire after a write, so a
    plugin listening for edit results (e.g. rejection-detail enrichment)
    sees native-editor writes too -- native and portable edits share the
    write engine but must not silently diverge in what fires afterward.
    """
    enhanced_results = on_edit_file(context, result, payload)
    if enhanced_results:
        for enhanced_result in enhanced_results:
            if enhanced_result is not None:
                return enhanced_result
    return result


async def dispatch_editor_command(
    context: RunContext,
    command: str,
    path: str,
    *,
    old_str: Optional[str] = None,
    new_str: Optional[str] = None,
    file_text: Optional[str] = None,
    insert_line: Optional[int] = None,
    view_range: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Route one native-editor command to the canonical engine."""
    if command == "view":
        return _view_file(path, view_range)

    if command == "str_replace":
        if old_str is None:
            return _missing_field_error(command, "old_str")
        if new_str is None:
            return _missing_field_error(command, "new_str")
        group_id = generate_group_id("str_replace_based_edit_tool", path)
        result = await replace_in_file_async(
            context,
            path,
            [{"old_str": old_str, "new_str": new_str}],
            message_group=group_id,
        )
        result.pop("diff", None)
        payload = ReplacementsPayload(
            file_path=path,
            replacements=[Replacement(old_str=old_str, new_str=new_str)],
        )
        return _apply_edit_callback(context, result, payload)

    if command == "create":
        if file_text is None:
            return _missing_field_error(command, "file_text")
        # Anthropic's documented `create` command always (over)writes the
        # full file at `path`, unlike the portable `create_file` tool (which
        # defaults to refusing an existing file) -- deliberate spec
        # conformance, not an oversight. The permission gate below still
        # applies, so an overwrite still requires approval.
        #
        # `overwrite` is derived from whether the file already exists
        # (rather than hardcoded True) purely so write_to_file_async's own
        # `"modify" if overwrite else "create"` diff-operation label comes
        # out correct -- a brand-new file must not be reported to the UI as
        # a "modify". Behavior is unchanged either way: `create` always
        # succeeds and always writes the full content, since `_write_to_file`
        # only refuses on `exists and not overwrite`, which never happens
        # here (the two always agree). The existence check has the same
        # narrow TOCTOU window as `_write_to_file`'s own equivalent check;
        # accepted for the same reason.
        already_existed = fs_access.exists(resolve_path(path))
        group_id = generate_group_id("str_replace_based_edit_tool", path)
        result = await write_to_file_async(
            context,
            path,
            file_text,
            overwrite=already_existed,
            message_group=group_id,
        )
        result.pop("diff", None)
        payload = ContentPayload(
            file_path=path, content=file_text, overwrite=already_existed
        )
        return _apply_edit_callback(context, result, payload)

    if command == "insert":
        if insert_line is None:
            return _missing_field_error(command, "insert_line")
        if new_str is None:
            return _missing_field_error(command, "new_str")
        return await _insert_into_file(context, path, insert_line, new_str)

    return _unsupported_command_error(command)


def _view_file(path: str, view_range: Optional[List[int]]) -> Dict[str, Any]:
    """Read-only view, no permission gate (matches the portable read_file tool)."""
    file_path = resolve_path(path)

    if not fs_access.exists(file_path):
        return {"error": "not_found", "path": file_path}

    if fs_access.is_dir(file_path):
        try:
            entries = fs_access.list_dir(file_path)
        except Exception as exc:
            # Broad on purpose: fs_access can be backed by a non-local
            # FileSystemBackend (e.g. an ACP host) that raises whatever its
            # transport raises, not just OSError -- matches the posture
            # _read_file already takes on its own backend-read path in
            # file_operations.py.
            return {"error": f"Failed to list directory '{file_path}': {exc}"}
        names = sorted((f"{e.name}/" if e.is_dir else e.name) for e in entries)
        # Same intent as _MAX_VIEW_TOKENS below: an unbounded directory
        # listing (e.g. node_modules, .git) would blow past the very
        # context budget the file-view branch already enforces.
        truncated = len(names) > _MAX_VIEW_ENTRIES
        result: Dict[str, Any] = {
            "path": file_path,
            "is_directory": True,
            "entries": names[:_MAX_VIEW_ENTRIES],
            "total_entries": len(names),
        }
        if truncated:
            result["truncated"] = True
        return result

    if not fs_access.is_file(file_path):
        return {"error": "not_a_regular_file", "path": file_path}

    try:
        content = fs_access.read_text(file_path)
    except Exception as exc:
        # Broad for the same reason as the directory-listing branch above.
        return {"error": f"Failed to read file '{file_path}': {exc}"}

    content = _sanitize_surrogates(content)
    lines = split_lines(content)
    total_lines = len(lines)
    start, end = 1, total_lines

    if view_range is not None:
        if len(view_range) != 2 or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in view_range
        ):
            return {
                "error": "invalid_view_range",
                "message": "view_range must be exactly [start_line, end_line], both integers.",
            }
        start, end = view_range
        if end == -1:
            end = total_lines
        if start < 1 or start > max(total_lines, 1) or end < start:
            return {
                "error": "invalid_view_range",
                "path": file_path,
                "total_lines": total_lines,
                "message": f"view_range {view_range} is out of bounds for a {total_lines}-line file.",
            }
        end = min(end, total_lines)

    if total_lines == 0:
        # Degenerate case: an empty file has no valid non-zero line range.
        # Normalize both the ranged and unranged paths to the same (0, 0)
        # shape instead of leaving `end` at the range-validation fallout of
        # 0 (view_range case) or `total_lines` (unranged case, also 0) --
        # either way `start` must not stay at its 1-based default when
        # there is nothing to number starting from line 1.
        start, end = 0, 0

    selected = lines[start - 1 : end] if total_lines else []
    numbered = "\n".join(
        f"{idx:6d}\t{line}" for idx, line in enumerate(selected, start=start)
    )

    if len(numbered) // 4 > _MAX_VIEW_TOKENS:
        return {
            "error": "content_too_large",
            "path": file_path,
            "message": (
                "The requested range is too large to view in one call; "
                "narrow view_range and retry."
            ),
        }

    # Matches read_file's UI contract: the raw (unnumbered) slice goes to
    # the message bus for display/telemetry; the line-numbered rendering
    # below is what actually goes back to the model. Without this, `view`
    # is invisible to the user/run_stats even though it is a real read.
    # Metadata is only meaningful for a real ranged, non-empty selection --
    # FileContentMessage requires num_lines >= 1, so an empty file (or the
    # unranged whole-file case, which read_file's own contract also reports
    # as start_line=None) must fall back to None rather than 0.
    raw_selected = "\n".join(selected)
    get_message_bus().emit(
        FileContentMessage(
            path=file_path,
            content=raw_selected,
            start_line=start if (view_range is not None and total_lines) else None,
            num_lines=(end - start + 1)
            if (view_range is not None and total_lines)
            else None,
            total_lines=total_lines,
            num_tokens=len(numbered) // 4,
        )
    )

    return {
        "path": file_path,
        "start_line": start,
        "end_line": end,
        "total_lines": total_lines,
        "content": numbered,
    }


async def _insert_into_file(
    context: RunContext, path: str, insert_line: int, new_str: str
) -> Dict[str, Any]:
    """Insert ``new_str`` after ``insert_line`` (0 = start of file).

    No generic-tool equivalent exists to delegate to, so this computes the
    resulting full-file content itself from a snapshot read at the top of
    this function. Unlike str_replace/create -- whose engine functions run
    permission check then read/validate/write as one call, so there is
    nothing to go stale -- insert's snapshot is taken *before* the
    permission prompt, and a human approval pause can be arbitrarily long.
    So after approval, and before writing, this re-reads the file and
    refuses to proceed if it no longer matches the snapshot the approved
    preview was built from, rather than silently splicing into content the
    approver never actually saw. (The permission audit label reads "write"
    rather than "insert" as a result; the operation data still carries the
    real inserted text.)
    """
    file_path = resolve_path(path)

    if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
        return {"error": "not_found", "path": file_path}

    try:
        original = fs_access.read_text(file_path)
    except Exception as exc:
        # Broad on purpose -- see the matching comment on _view_file's read.
        return {"error": f"Failed to read file '{file_path}': {exc}"}

    original = _sanitize_surrogates(original)
    lines = split_lines(original, keepends=True) if original else []
    line_count = len(lines)

    if not isinstance(insert_line, int) or isinstance(insert_line, bool):
        return {
            "error": "invalid_insert_line",
            "path": file_path,
            "message": f"insert_line must be an integer; got {insert_line!r}.",
        }

    if insert_line < 0 or insert_line > line_count:
        return {
            "error": "invalid_insert_line",
            "path": file_path,
            "line_count": line_count,
            "message": (
                f"insert_line must be between 0 and {line_count} "
                f"(the file's current line count); got {insert_line}."
            ),
        }

    style = detect_dominant(original) if original else "\n"
    inserted = to_style(new_str, style)

    if not inserted:
        # An empty new_str (after style conversion, which never turns a
        # non-empty string empty) is a genuine no-op. Return here, BEFORE
        # touching `lines`, so nothing below mutates the file's last line
        # just to attach a terminator to text we are not actually going to
        # insert -- that previously produced a false "changed: true" write
        # on any file whose last line lacked a trailing newline.
        return {
            "success": False,
            "path": file_path,
            "changed": False,
            "message": "No change: the inserted text was empty.",
        }

    if not inserted.endswith(style):
        inserted += style

    # If we're inserting after the current last line and that line is
    # missing its own terminator, add one so the insertion doesn't fuse onto
    # the previous line's text.
    if insert_line == line_count and lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] = lines[-1] + style

    new_content = "".join(lines[:insert_line] + [inserted] + lines[insert_line:])

    group_id = generate_group_id("str_replace_based_edit_tool", path)
    permission_results = await on_file_permission_async(
        context,
        file_path,
        "write",
        None,
        group_id,
        {"content": new_content, "overwrite": True},
    )
    if _permission_denied(permission_results):
        return _create_rejection_response(file_path)

    # Close the approval-wait race described in this function's docstring:
    # re-read now and compare byte-for-byte against the snapshot the
    # approved preview above was computed from. Any difference means the
    # file moved out from under us; fail closed rather than overwrite
    # content the approver never saw (the same "never silently guess"
    # philosophy the Phase 2 exact-match engine applies to ambiguous text
    # matches, applied here to a stale file snapshot instead).
    try:
        current = _sanitize_surrogates(fs_access.read_text(file_path))
    except Exception as exc:
        # Broad on purpose -- see the matching comment on _view_file's read.
        return {
            "error": f"Failed to read file '{file_path}': {exc}",
            "path": file_path,
        }
    if current != original:
        return {
            "error": "concurrent_modification",
            "path": file_path,
            "message": (
                "The file changed after permission was requested and "
                "before the insert was applied; view the file again and "
                "retry with an up-to-date insert_line."
            ),
        }

    result = _write_to_file(
        context, file_path, new_content, overwrite=True, message_group=group_id
    )
    diff = result.pop("diff", "")
    if diff:
        _emit_diff_message(file_path, "modify", diff, new_content=new_content)
    payload = ContentPayload(file_path=file_path, content=new_content, overwrite=True)
    return _apply_edit_callback(context, result, payload)


def register_str_replace_based_edit_tool(agent) -> None:
    """Register Anthropic's native text-editor tool on ``agent``.

    Declared here as an ordinary pydantic-ai function tool; the wire-level
    substitution that makes Anthropic treat it as the client-executed
    editor (instead of a generic JSON-schema tool) happens in
    ``AnthropicNativeEditorModel``, not here.
    """

    @agent.tool
    async def str_replace_based_edit_tool(
        context: RunContext,
        command: str,
        path: str,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        file_text: Optional[str] = None,
        insert_line: Optional[int] = None,
        view_range: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Anthropic's native client-executed text-editor tool.

        Commands: view (path, optional view_range=[start,end], -1=end of
        file), str_replace (path, old_str, new_str), create (path,
        file_text), insert (path, insert_line, new_str).
        """
        try:
            return await dispatch_editor_command(
                context,
                command,
                path,
                old_str=old_str,
                new_str=new_str,
                file_text=file_text,
                insert_line=insert_line,
                view_range=view_range,
            )
        except Exception as exc:
            # Last line of defense -- never let this tool crash the agent
            # run, matching the try/except every portable file-modification
            # tool wraps its own body in (see file_modifications.py).
            _log_error(
                "Unhandled exception in str_replace_based_edit_tool",
                exc,
                message_group=None,
            )
            return {
                "error": f"str_replace_based_edit_tool failed: {exc}",
                "command": command,
                "path": path,
            }

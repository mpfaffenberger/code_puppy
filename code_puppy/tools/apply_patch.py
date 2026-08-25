"""Codex/OpenCode-compatible multi-file patch application.

The public wire format intentionally follows the patch envelope used by Codex:

    *** Begin Patch
    *** Update File: path/to/file.py
    @@
     context
    -old
    +new
    *** Add File: new.py
    +content
    *** End Patch

All hunks are parsed and validated before any mutation is performed.  The
filesystem facade remains the single I/O boundary so configured editor/remote
backends continue to work.
"""

from __future__ import annotations

import os
import difflib
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.callbacks import on_apply_patch, on_edit_file
from code_puppy.tools import fs_access
from code_puppy.tools.common import generate_group_id, get_working_directory
from code_puppy.tools.file_modifications import _emit_diff_message


class ApplyPatchPayload(BaseModel):
    patch_text: str


@dataclass(frozen=True)
class _Chunk:
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]


@dataclass(frozen=True)
class PatchChange:
    path: str
    old_content: str
    new_content: str
    kind: str
    move_to: str | None = None


class PatchError(ValueError):
    """Raised when a patch is malformed, unsafe, or does not apply cleanly."""


def _safe_path(raw_path: str, base_dir: str) -> str:
    """Resolve a patch path while keeping it inside the active worktree."""
    path = raw_path.strip()
    if not path or os.path.isabs(path):
        raise PatchError(f"patch path must be a non-empty relative path: {raw_path!r}")

    base = os.path.abspath(base_dir)
    resolved = os.path.abspath(os.path.join(base, path))
    try:
        inside = os.path.commonpath((base, resolved)) == base
    except ValueError:
        inside = False
    if not inside:
        raise PatchError(f"patch path escapes the working directory: {raw_path!r}")
    return resolved


def _parse_chunks(lines: Sequence[str], path: str) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    old_lines: list[str] = []
    new_lines: list[str] = []
    saw_hunk = False

    def flush() -> None:
        nonlocal old_lines, new_lines
        if old_lines or new_lines:
            chunks.append(_Chunk(tuple(old_lines), tuple(new_lines)))
            old_lines, new_lines = [], []

    for line in lines:
        if line.startswith("@@"):
            flush()
            saw_hunk = True
            continue
        if line in (r"\ No newline at end of file", "*** End of File"):
            continue
        if not line:
            raise PatchError(f"invalid empty patch line in update for {path}")
        marker, content = line[0], line[1:]
        if marker == " ":
            old_lines.append(content)
            new_lines.append(content)
        elif marker == "-":
            old_lines.append(content)
        elif marker == "+":
            new_lines.append(content)
        else:
            raise PatchError(
                f"invalid patch line for {path}: expected ' ', '-', or '+', got {line!r}"
            )
    flush()
    if not saw_hunk:
        raise PatchError(f"update for {path} contains no @@ hunk")
    return chunks


def _split_patch(patch_text: str) -> list[tuple[str, str, list[str], str | None]]:
    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    raw_lines = normalized.split("\n")
    try:
        begin = next(i for i, line in enumerate(raw_lines) if line.strip() == "*** Begin Patch")
        end = next(
            i
            for i, line in enumerate(raw_lines)
            if i > begin and line.strip() == "*** End Patch"
        )
    except StopIteration as exc:
        raise PatchError("patch must begin with '*** Begin Patch' and end with '*** End Patch'")
    lines = raw_lines[begin : end + 1]

    def is_file_boundary(line: str) -> bool:
        return line.startswith(
            ("*** Add File: ", "*** Delete File: ", "*** Update File: ", "*** End Patch")
        )

    entries: list[tuple[str, str, list[str], str | None]] = []
    index = 1
    while index < len(lines) - 1:
        header = lines[index]
        if header.startswith("*** Add File: "):
            path = header.removeprefix("*** Add File: ")
            body: list[str] = []
            index += 1
            while index < len(lines) - 1 and not is_file_boundary(lines[index]):
                body.append(lines[index])
                index += 1
            entries.append(("add", path, body, None))
            continue
        elif header.startswith("*** Delete File: "):
            entries.append(("delete", header.removeprefix("*** Delete File: "), [], None))
        elif header.startswith("*** Update File: "):
            path = header.removeprefix("*** Update File: ")
            body: list[str] = []
            index += 1
            move_to: str | None = None
            if index < len(lines) - 1 and lines[index].startswith("*** Move to: "):
                move_to = lines[index].removeprefix("*** Move to: ")
                index += 1
            while index < len(lines) - 1 and not is_file_boundary(lines[index]):
                body.append(lines[index])
                index += 1
            entries.append(("update", path, body, move_to))
            continue
        else:
            raise PatchError(f"unexpected patch directive: {header!r}")
        index += 1

    if not entries:
        raise PatchError("patch contains no file changes")
    return entries


def _apply_chunks(path: str, old_content: str, chunks: Sequence[_Chunk]) -> str:
    had_final_newline = old_content.endswith("\n")
    source = old_content.splitlines()
    cursor = 0
    output: list[str] = []

    for chunk in chunks:
        expected = list(chunk.old_lines)
        # Codex hunks carry @@ locations, but the canonical patch format also
        # permits context-only matching. Search from the previous hunk.
        match_at = None
        for candidate in range(cursor, len(source) - len(expected) + 1):
            if source[candidate : candidate + len(expected)] == expected:
                match_at = candidate
                break
        if match_at is None:
            raise PatchError(f"patch hunk did not match {path}")
        output.extend(source[cursor:match_at])
        output.extend(chunk.new_lines)
        cursor = match_at + len(expected)

    output.extend(source[cursor:])
    new_content = "\n".join(output)
    if had_final_newline or new_content:
        new_content += "\n"
    return new_content


def parse_patch(patch_text: str, *, base_dir: str | None = None) -> list[PatchChange]:
    """Parse and fully validate a Codex/OpenCode patch without writing files."""
    base = base_dir or get_working_directory()
    changes: list[PatchChange] = []
    for kind, raw_path, body, raw_move_to in _split_patch(patch_text):
        path = _safe_path(raw_path, base)
        if kind == "add":
            if fs_access.exists(path):
                raise PatchError(f"cannot add existing file: {raw_path}")
            content_lines = []
            for line in body:
                if not line.startswith("+"):
                    raise PatchError(f"added file lines must start with '+': {line!r}")
                content_lines.append(line[1:])
            content = "\n".join(content_lines)
            if content_lines:
                content += "\n"
            changes.append(PatchChange(path, "", content, "add"))
        elif kind == "delete":
            if not fs_access.is_file(path):
                raise PatchError(f"cannot delete missing file: {raw_path}")
            changes.append(PatchChange(path, fs_access.read_text(path), "", "delete"))
        else:
            if not fs_access.is_file(path):
                raise PatchError(f"cannot update missing file: {raw_path}")
            old_content = fs_access.read_text(path)
            chunks = _parse_chunks(body, raw_path)
            new_content = _apply_chunks(path, old_content, chunks)
            move_to = _safe_path(raw_move_to, base) if raw_move_to else None
            if move_to and fs_access.exists(move_to):
                raise PatchError(f"cannot move over existing file: {raw_move_to}")
            changes.append(PatchChange(path, old_content, new_content, "move" if move_to else "update", move_to))
    return changes


def _apply_changes(changes: Sequence[PatchChange]) -> None:
    applied: list[tuple[str, str | None]] = []
    try:
        for change in changes:
            if change.kind == "delete":
                fs_access.delete_file(change.path)
                applied.append((change.path, change.old_content))
                continue
            target = change.move_to or change.path
            fs_access.make_dirs(os.path.dirname(target))
            fs_access.write_text(target, change.new_content)
            applied.append((target, None if change.move_to else change.old_content))
            if change.move_to:
                fs_access.delete_file(change.path)
                applied.append((change.path, change.old_content))
    except Exception:
        # Best-effort rollback protects the all-or-nothing validation contract
        # from leaving a partially applied patch when a backend write fails.
        for path, original in reversed(applied):
            try:
                if original is None:
                    if fs_access.exists(path):
                        fs_access.delete_file(path)
                else:
                    fs_access.write_text(path, original)
            except Exception:
                pass
        raise


def register_apply_patch(agent):
    """Register the Codex/OpenCode ``apply_patch`` tool."""

    @agent.tool
    async def apply_patch(
        context: RunContext,
        patchText: str,
    ) -> Dict[str, Any]:
        group_id = generate_group_id("apply_patch", "multi-file")
        try:
            patch_text = patchText
            changes = parse_patch(patch_text)
            for change in changes:
                from code_puppy.callbacks import on_file_permission_async

                permission = await on_file_permission_async(
                    context,
                    change.path,
                    "apply patch",
                    None,
                    group_id,
                    {
                        "patch_text": patch_text,
                        "path": change.path,
                        "operation": change.kind,
                    },
                )
                if any(result is False for result in permission if result is not None):
                    return {
                        "success": False,
                        "message": "USER REJECTED: The user explicitly rejected this patch.",
                        "changed": False,
                        "user_rejection": True,
                    }

            _apply_changes(changes)
            for change in changes:
                target = change.move_to or change.path
                diff = "".join(
                    difflib.unified_diff(
                        change.old_content.splitlines(keepends=True),
                        change.new_content.splitlines(keepends=True),
                        fromfile=f"a/{change.path}",
                        tofile=f"b/{target}",
                    )
                )
                if diff:
                    _emit_diff_message(target, change.kind, diff)
            result: Dict[str, Any] = {
                "success": True,
                "changed": True,
                "files": [change.move_to or change.path for change in changes],
                "message": f"Applied patch to {len(changes)} file(s).",
            }
            on_apply_patch(context, result, patch_text)
            on_edit_file(context, result, patch_text)
            return result
        except PatchError as exc:
            return {"success": False, "changed": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "changed": False, "error": f"apply_patch failed: {exc}"}

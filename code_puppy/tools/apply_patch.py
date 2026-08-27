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

import difflib
import os
from dataclasses import dataclass
from typing import Any, Dict, Sequence

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
    change_context: str | None
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]
    is_end_of_file: bool


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


def _unexpected_update_line(line: str) -> PatchError:
    return PatchError(
        f"Unexpected line found in update hunk: '{line}'. Every line should start "
        "with ' ' (context line), '+' (added line), or '-' (removed line)"
    )


def _parse_chunks(lines: Sequence[str], path: str) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    index = 0

    while index < len(lines):
        # Codex tolerates blank separators before a chunk.
        if lines[index].strip() == "":
            index += 1
            continue
        if lines[index].startswith("***"):
            break

        line = lines[index]
        if line == "@@":
            change_context = None
            index += 1
        elif line.startswith("@@ "):
            change_context = line[3:]
            index += 1
        elif not chunks:
            # Only the first chunk may start directly with diff lines.
            change_context = None
        else:
            raise PatchError(
                f"Expected update hunk to start with a @@ context marker, got: '{line}'"
            )

        if index >= len(lines):
            raise PatchError("Update hunk does not contain any lines")

        old_lines: list[str] = []
        new_lines: list[str] = []
        is_end_of_file = False
        parsed_lines = 0

        while index < len(lines):
            line = lines[index]
            if parsed_lines and line.strip() == "":
                next_nonblank = index
                while next_nonblank < len(lines) and lines[next_nonblank].strip() == "":
                    next_nonblank += 1
                if next_nonblank < len(lines) and lines[next_nonblank].startswith("@@"):
                    # Let the outer loop discard separators before the next chunk.
                    break
            if line == "*** End of File":
                if parsed_lines == 0:
                    raise PatchError("Update hunk does not contain any lines")
                is_end_of_file = True
                index += 1
                break

            if not line:
                old_lines.append("")
                new_lines.append("")
            elif line[0] == " ":
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line[0] == "+":
                new_lines.append(line[1:])
            elif line[0] == "-":
                old_lines.append(line[1:])
            elif parsed_lines == 0:
                raise _unexpected_update_line(line)
            else:
                # A context marker or other non-diff line begins the next chunk.
                break

            parsed_lines += 1
            index += 1

        chunks.append(
            _Chunk(
                change_context,
                tuple(old_lines),
                tuple(new_lines),
                is_end_of_file,
            )
        )

    if not chunks:
        raise PatchError(f"Update file hunk for path '{path}' is empty")
    return chunks


_UNICODE_PUNCTUATION = str.maketrans(
    {
        **{codepoint: "-" for codepoint in range(0x2010, 0x2016)},
        0x2212: "-",
        **{codepoint: "'" for codepoint in range(0x2018, 0x201C)},
        **{codepoint: '"' for codepoint in range(0x201C, 0x2020)},
        0x00A0: " ",
        **{codepoint: " " for codepoint in range(0x2002, 0x200B)},
        0x202F: " ",
        0x205F: " ",
        0x3000: " ",
    }
)


def _seek_sequence(
    lines: Sequence[str],
    pattern: Sequence[str],
    start: int,
    eof: bool = False,
) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    def normalized(line: str) -> str:
        return line.strip().translate(_UNICODE_PUNCTUATION)

    comparisons = (
        lambda line: line,
        lambda line: line.rstrip(),
        lambda line: line.strip(),
        normalized,
    )
    last_start = len(lines) - len(pattern)
    search_start = last_start if eof else start

    for transform in comparisons:
        transformed_pattern = [transform(line) for line in pattern]
        for candidate in range(search_start, last_start + 1):
            if [
                transform(line) for line in lines[candidate : candidate + len(pattern)]
            ] == transformed_pattern:
                return candidate
    return None


def _split_patch(patch_text: str) -> list[tuple[str, str, list[str], str | None]]:
    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    raw_lines = normalized.split("\n")
    try:
        begin = next(
            i for i, line in enumerate(raw_lines) if line.strip() == "*** Begin Patch"
        )
        end = next(
            i
            for i, line in enumerate(raw_lines)
            if i > begin and line.strip() == "*** End Patch"
        )
    except StopIteration:
        raise PatchError(
            "patch must begin with '*** Begin Patch' and end with '*** End Patch'"
        )
    lines = raw_lines[begin : end + 1]

    def is_file_boundary(line: str) -> bool:
        return line.startswith(
            (
                "*** Add File: ",
                "*** Delete File: ",
                "*** Update File: ",
                "*** End Patch",
            )
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
            entries.append(
                ("delete", header.removeprefix("*** Delete File: "), [], None)
            )
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
    source = old_content.split("\n")
    if source and source[-1] == "":
        source.pop()

    replacements: list[tuple[int, int, list[str]]] = []
    cursor = 0
    for chunk in chunks:
        if chunk.change_context is not None:
            context_at = _seek_sequence(
                source, [chunk.change_context], cursor, eof=False
            )
            if context_at is None:
                raise PatchError(
                    f"Failed to find context '{chunk.change_context}' in {path}"
                )
            cursor = context_at + 1

        if not chunk.old_lines:
            replacements.append((len(source), 0, list(chunk.new_lines)))
            continue

        expected = list(chunk.old_lines)
        new_lines = list(chunk.new_lines)
        match_at = _seek_sequence(source, expected, cursor, eof=chunk.is_end_of_file)
        if match_at is None and expected[-1] == "":
            expected.pop()
            if new_lines and new_lines[-1] == "":
                new_lines.pop()
            match_at = _seek_sequence(
                source, expected, cursor, eof=chunk.is_end_of_file
            )

        if match_at is None:
            raise PatchError(
                f"Failed to find expected lines in {path}:\n"
                + "\n".join(chunk.old_lines)
            )
        replacements.append((match_at, len(expected), new_lines))
        cursor = match_at + len(expected)

    replacements.sort(key=lambda replacement: replacement[0])
    for start, old_len, new_lines in reversed(replacements):
        source[start : start + old_len] = new_lines

    if not source or source[-1] != "":
        source.append("")
    return "\n".join(source)


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
            changes.append(
                PatchChange(
                    path,
                    old_content,
                    new_content,
                    "move" if move_to else "update",
                    move_to,
                )
            )
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
            return {
                "success": False,
                "changed": False,
                "error": f"apply_patch failed: {exc}",
            }

"""Filesystem access facade: one dispatch point for backend-or-local I/O.

Every filesystem *metadata*, *mutation*, and *traversal* operation the agent's
file tools perform goes through here. When a
:class:`~code_puppy.tools.io_backends.FileSystemBackend` is installed these
delegate to it; otherwise they run against the local disk exactly as before.

Centralizing the "backend or local?" decision keeps it in one place (instead of
scattering ``get_filesystem_backend()`` checks across every tool) and, crucially,
guarantees the agent sees a *single coherent filesystem*: with a backend
installed, ``list_files``, ``grep``, existence checks, deletes, and mkdir all
resolve against the same source as ``read_file`` / ``write_to_file``. Recursive
listing and content search are *composed* here from ``list_dir`` + text reads
(see :func:`walk`), so the backend contract stays small.

Content reads/writes for *workspace* files also honor the backend, but their
call sites already live in ``file_operations`` / ``common`` where local
encoding/atomic-write details matter; this module owns the metadata + traversal
surface and the backend-aware read used by :func:`walk`.

All paths passed in must be absolute (callers resolve via
``common.resolve_path``); the local branch here does not re-resolve.
"""

from __future__ import annotations

import os
from typing import Callable, Iterator, List, Optional, Tuple

from code_puppy.tools.io_backends import DirEntry, get_filesystem_backend


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
def exists(path: str) -> bool:
    backend = get_filesystem_backend()
    if backend is not None:
        return backend.exists(path)
    return os.path.exists(path)


def is_file(path: str) -> bool:
    backend = get_filesystem_backend()
    if backend is not None:
        return backend.is_file(path)
    return os.path.isfile(path)


def is_dir(path: str) -> bool:
    backend = get_filesystem_backend()
    if backend is not None:
        return backend.is_dir(path)
    return os.path.isdir(path)


def list_dir(path: str) -> List[DirEntry]:
    """List the immediate children of ``path`` (one level).

    Raises ``FileNotFoundError`` / ``NotADirectoryError`` consistently across
    backend and local paths.
    """
    backend = get_filesystem_backend()
    if backend is not None:
        return backend.list_dir(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if not os.path.isdir(path):
        raise NotADirectoryError(path)
    entries: List[DirEntry] = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if os.path.isdir(full):
                entries.append(DirEntry(name=name, is_dir=True, size=0))
            elif os.path.isfile(full):
                entries.append(DirEntry(name=name, is_dir=False, size=_safe_size(full)))
        except OSError:
            continue
    return entries


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Content (backend-aware read; used by traversal/grep and by callers that want
# to honor unsaved host buffers)
# ---------------------------------------------------------------------------
def read_text(
    path: str, line: Optional[int] = None, limit: Optional[int] = None
) -> str:
    """Read text of ``path`` through the backend, else local disk.

    ``line`` (1-based) + ``limit`` request a slice; both ``None`` = whole file.
    Local reads use ``surrogateescape`` so invalid-UTF-8 files never crash the
    tool (matching the existing tool behavior).
    """
    backend = get_filesystem_backend()
    if backend is not None:
        return backend.read_text_file(path, line=line, limit=limit)
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        if line is None or limit is None:
            return f.read()
        # 1-based line slice, mirroring the backend contract.
        out: List[str] = []
        for i, row in enumerate(f, start=1):
            if i < line:
                continue
            if i >= line + limit:
                break
            out.append(row)
        return "".join(out)


def write_text(path: str, content: str) -> None:
    """Write ``content`` (UTF-8 text) to ``path`` through the backend, else local.

    This is the low-level facade write used by machinery that must stay coherent
    with the active filesystem (e.g. undo). Tool-facing writes go through
    ``common.write_project_file`` for diffing/messaging, which itself honors the
    backend; this is the raw equivalent.
    """
    backend = get_filesystem_backend()
    if backend is not None:
        backend.write_text_file(path, content)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------
def delete_file(path: str) -> None:
    backend = get_filesystem_backend()
    if backend is not None:
        backend.delete_file(path)
        return
    os.remove(path)


def make_dirs(path: str) -> None:
    """Create ``path`` and parents (idempotent). No-op for the empty string."""
    if not path:
        return
    backend = get_filesystem_backend()
    if backend is not None:
        backend.make_dirs(path)
        return
    os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# Traversal (composed from list_dir; backend-agnostic)
# ---------------------------------------------------------------------------
# Depth backstop for hostile/buggy backends whose list_dir forms an infinite
# chain of *distinct* paths (so the visited-set can't catch it). Real source
# trees are nowhere near this deep; ripgrep (the local path) is likewise bounded.
MAX_WALK_DEPTH = 1000


def walk(
    root: str,
    *,
    skip_dir: Optional[Callable[[str], bool]] = None,
    skip_file: Optional[Callable[[str], bool]] = None,
) -> Iterator[Tuple[str, DirEntry]]:
    """Yield ``(full_path, DirEntry)`` under ``root`` (pre-order) via ``list_dir``.

    Directories are yielded before their contents. ``skip_dir(full_path)`` /
    ``skip_file(full_path)`` (when given) prune entries -- a pruned directory is
    not descended into. This is the single traversal used by both recursive
    ``list_files`` and ``grep`` when a backend is installed, so their view is
    identical to every other operation.

    Implemented **iteratively** with an explicit stack so a legitimately deep
    tree cannot overflow the interpreter stack. Cycles are broken two ways:
    a visited-set keyed on the resolved real path (catches symlink / same-path
    loops), plus a ``MAX_WALK_DEPTH`` backstop for a hostile backend that
    invents an unbounded chain of distinct paths. A ``list_dir`` that raises
    (missing/permission/not-a-dir) is skipped, never fatal.
    """
    visited: set[str] = set()
    # Stack of iterators-of-(full_path, entry); each level is one directory.
    stack: list[Iterator[Tuple[str, DirEntry]]] = [_walk_level(root, visited)]
    while stack:
        if len(stack) > MAX_WALK_DEPTH:
            stack.pop()  # too deep: stop descending this branch, keep going
            continue
        try:
            full, entry = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if entry.is_dir:
            if skip_dir is not None and skip_dir(full):
                continue
            yield full, entry
            stack.append(_walk_level(full, visited))
        else:
            if skip_file is not None and skip_file(full):
                continue
            yield full, entry


def _walk_level(directory: str, visited: set[str]) -> Iterator[Tuple[str, DirEntry]]:
    """Yield the immediate children of ``directory`` (sorted), skipping revisits.

    Records the directory's real path in ``visited`` and yields nothing if it
    was already seen -- the cycle guard shared across the whole walk.
    """
    try:
        key = os.path.realpath(directory)
    except OSError:
        key = directory
    if key in visited:
        return
    visited.add(key)
    try:
        entries = list_dir(directory)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return
    for entry in sorted(entries, key=lambda e: e.name):
        yield os.path.join(directory, entry.name), entry

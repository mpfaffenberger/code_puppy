"""Build a bounded, cacheable file index for the current working directory.

Used by the ``cwd_context`` plugin to inject a small directory snapshot into the
agent's dynamic system prompt so bare-filename references can be resolved
without a full directory scan on every turn.

Design constraints (keep these in mind when changing this file):

- **Prompt budget.** The output is appended to every turn's system prompt. Cap
  output at ~1500 tokens (~6000 chars) so we never blow the 12k ceiling. When
  the tree is larger, truncate and append a ``+N more`` hint.
- **Cache key.** ``(cwd, max_depth, budget_chars, _tree_signature)`` where
  ``_tree_signature`` is the max mtime across scanned entries. Cheap to
  compute, invalidates correctly on edits.
- **Skip noise.** The skip list mirrors what humans mentally filter — VCS,
  build outputs, virtualenvs, caches, lock files, generated media. Keep it
  in one place so we can audit the surface area.
- **No I/O surprises.** If anything raises (permission denied, vanished
  directory, ENOSPC), return ``None`` — the plugin will degrade to a cwd-only
  fragment rather than crash the agent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Basenames to skip at every depth. Matches what humans mentally filter.
SKIP_BASENAMES = frozenset(
    {
        # VCS
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        # Node / JS / TS
        "node_modules",
        ".next",
        ".nuxt",
        ".cache",
        ".parcel-cache",
        ".vite",
        "dist",
        "build",
        "out",
        "storybook-static",
        "coverage",
        ".nyc_output",
        # Python
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        ".venv-user",
        "site-packages",
        "htmlcov",
        ".tox",
        # Bundlers / package managers
        ".pnpm-store",
        ".yarn",
        ".npm",
        # OS / editor
        ".DS_Store",
        ".idea",
        ".vscode",
    }
)

# Files to skip regardless of location.
SKIP_FILENAMES = frozenset(
    {
        ".coverage",
        "coverage.json",
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "code_puppy.gif",
        "code_puppy.png",
        "mist_logo.png",
    }
)

# Extensions to always skip (media + archives).
SKIP_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".o",
    ".a",
    ".obj",
    ".gif",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pdf",
    ".wasm",
    ".map",
)


@dataclass(frozen=True)
class FileIndex:
    cwd: str
    lines: tuple[str, ...]
    truncated: bool
    total_entries: int

    def render(self) -> str:
        body = "\n".join(self.lines)
        if self.truncated:
            extra = self.total_entries - len(self.lines)
            if extra > 0:
                body += f"\n… +{extra} more entries (tree truncated)"
        return body


def _should_skip(name: str, is_dir: bool) -> bool:
    if name in SKIP_BASENAMES:
        return True
    if not is_dir and name in SKIP_FILENAMES:
        return True
    if not is_dir and name.endswith(SKIP_SUFFIXES):
        return True
    return False


def _walk(
    root: Path,
    max_depth: int,
    budget_chars: int,
    max_entries: int,
) -> tuple[list[str], int, bool]:
    """Walk ``root`` in deterministic order, returning ``(lines, total, truncated)``.

    Lines are formatted as ``"  " * depth + name`` so depth is visible.
    Directories end with ``/`` to disambiguate from files.
    """
    lines: list[str] = []
    total = 0
    chars = 0
    truncated = False

    # We do our own traversal instead of ``os.walk`` so we can keep tight
    # control over depth, ordering, and the skip list.
    def _recurse(directory: Path, depth: int) -> None:
        nonlocal total, chars, truncated
        if truncated or depth > max_depth:
            return
        try:
            entries = sorted(
                directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except (PermissionError, FileNotFoundError, OSError):
            return
        for entry in entries:
            if truncated:
                return
            is_dir = entry.is_dir(follow_symlinks=False)
            try:
                if _should_skip(entry.name, is_dir):
                    continue
            except OSError:
                continue
            total += 1
            label = entry.name + ("/" if is_dir else "")
            line = ("  " * depth) + label
            if chars + len(line) + 1 > budget_chars or len(lines) >= max_entries:
                truncated = True
                return
            lines.append(line)
            chars += len(line) + 1
            if is_dir:
                _recurse(entry, depth + 1)

    # Root itself isn't listed — the prompt already says the cwd.
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (PermissionError, FileNotFoundError, OSError):
        return ([], 0, False)

    for entry in entries:
        if truncated:
            break
        is_dir = entry.is_dir(follow_symlinks=False)
        try:
            if _should_skip(entry.name, is_dir):
                continue
        except OSError:
            continue
        total += 1
        label = entry.name + ("/" if is_dir else "")
        line = label
        if chars + len(line) + 1 > budget_chars or len(lines) >= max_entries:
            truncated = True
            break
        lines.append(line)
        chars += len(line) + 1
        if is_dir:
            _recurse(entry, 1)

    return (lines, total, truncated)


def _tree_signature(root: Path, max_depth: int) -> float:
    """Return a coarse mtime signature for the top layers of ``root``.

    Walking the whole tree to hash it would defeat the purpose. We sample
    files up to ``max_depth`` and take the max mtime — edits anywhere in that
    envelope invalidate the cache, which is good enough for "did the tree
    change since last turn" purposes.
    """
    max_mtime = 0.0

    def _scan(directory: Path, depth: int) -> None:
        nonlocal max_mtime
        if depth > max_depth:
            return
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    try:
                        if entry.name in SKIP_BASENAMES:
                            continue
                        st = entry.stat(follow_symlinks=False)
                    except (PermissionError, FileNotFoundError, OSError):
                        continue
                    if st.st_mtime > max_mtime:
                        max_mtime = st.st_mtime
                    if entry.is_dir(follow_symlinks=False):
                        _scan(Path(entry.path), depth + 1)
        except (PermissionError, FileNotFoundError, OSError):
            return

    try:
        st = root.stat()
        max_mtime = max(max_mtime, st.st_mtime)
    except OSError:
        pass
    _scan(root, 0)
    return max_mtime


def build_file_index(
    cwd: str,
    *,
    max_depth: int = 2,
    budget_chars: int = 4800,
    max_entries: int = 180,
) -> FileIndex | None:
    """Build a bounded file index for ``cwd``.

    Returns ``None`` if the cwd is unreadable or otherwise unusable.
    """
    root = Path(cwd)
    try:
        if not root.is_dir():
            return None
    except OSError:
        return None

    lines, total, truncated = _walk(root, max_depth, budget_chars, max_entries)
    return FileIndex(
        cwd=str(root),
        lines=tuple(lines),
        truncated=truncated,
        total_entries=total,
    )


def get_tree_signature(cwd: str, *, max_depth: int = 2) -> float:
    """Exposed so the plugin cache can use the same signature logic."""
    return _tree_signature(Path(cwd), max_depth)

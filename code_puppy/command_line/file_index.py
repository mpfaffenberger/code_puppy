"""In-memory recursive file index powered by ripgrep.

Used by ``FilePathCompleter`` to make fuzzy ``@`` completions span the whole
project, not just one directory. Built on demand, refreshed on ``/cd``.

Design notes
------------
* ``rg --files`` already respects ``.gitignore`` / ``.ignore`` and is wicked
  fast, so we lean on it instead of rolling our own ``os.walk``.
* Builds run on a background ``threading.Thread`` so the prompt never blocks.
* Reads are lock-free snapshots — completers grab the current ``Index``
  and iterate without coordinating with the builder.
* If ``rg`` isn't on PATH for some reason, we degrade to an empty index
  rather than crashing the prompt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import List, Optional

# Cap so we don't blow up RAM on absurdly huge repos. 200k paths is plenty
# for fuzzy ranking; anything beyond that is almost certainly noise.
MAX_INDEXED_PATHS = 200_000
INDEX_BUILD_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Index:
    """Immutable snapshot of an indexed directory tree."""

    root: str
    paths: tuple[str, ...] = field(default_factory=tuple)
    lowered: tuple[str, ...] = field(default_factory=tuple)
    basenames_lower: tuple[str, ...] = field(default_factory=tuple)


_EMPTY_INDEX = Index(root="")


class FileIndex:
    """Singleton-ish file index. Use module-level helpers below."""

    def __init__(self) -> None:
        self._current: Index = _EMPTY_INDEX
        self._lock = threading.Lock()
        self._build_thread: Optional[threading.Thread] = None
        self._test_mode: bool = False

    # ----------------------------------------------------------------- public

    @property
    def current(self) -> Index:
        return self._current

    def reindex(self, root: Optional[str] = None, *, blocking: bool = False) -> None:
        """Kick off a (re)build of the index.

        Args:
            root: Directory to index. Defaults to ``os.getcwd()``.
            blocking: When True, wait for the build to finish (used in tests).
        """
        # Skip reindexing in test mode unless explicitly blocking (tests
        # can still force a rebuild if needed).
        if self._test_mode and not blocking:
            return

        target_root = os.path.abspath(root or os.getcwd())

        # Don't pile up redundant rebuilds — if one's already in flight, let it
        # finish. The next /cd will trigger a fresh one anyway.
        with self._lock:
            if self._build_thread and self._build_thread.is_alive():
                if blocking:
                    thread_to_wait = self._build_thread
                else:
                    return
            else:
                thread_to_wait = None

        if thread_to_wait is not None:
            thread_to_wait.join()

        thread = threading.Thread(target=self._build, args=(target_root,), daemon=True)
        with self._lock:
            self._build_thread = thread
        thread.start()
        if blocking:
            thread.join()

    def set_for_testing(self, root: str, paths: List[str]) -> None:
        """Inject an index directly. Tests only — keeps subprocess out of unit tests.

        Also enables test mode which suppresses automatic reindexing for the rest
        of the test session until reset.
        """
        self._current = _make_index(os.path.abspath(root), paths)
        self._test_mode = True

    # ---------------------------------------------------------------- private

    def _build(self, root: str) -> None:
        paths = _run_ripgrep(root)
        if paths is None:
            # rg unavailable or errored — keep whatever we had so completion
            # still has *something* to chew on.
            return
        self._current = _make_index(root, paths)


def _run_ripgrep(root: str) -> Optional[List[str]]:
    rg = shutil.which("rg")
    if not rg:
        return None
    try:
        proc = subprocess.run(
            [rg, "--files", "--hidden", "--glob", "!.git"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=INDEX_BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    # rg exits 1 when there are no matches; that's fine, treat as empty.
    if proc.returncode not in (0, 1):
        return None
    lines = [ln for ln in proc.stdout.splitlines() if ln]
    if len(lines) > MAX_INDEXED_PATHS:
        lines = lines[:MAX_INDEXED_PATHS]
    return lines


def _make_index(root: str, paths: List[str]) -> Index:
    # Normalize once up front so every fuzzy lookup is a cheap tuple read.
    normalized = tuple(paths)
    lowered = tuple(p.lower() for p in normalized)
    basenames = tuple(os.path.basename(p).lower() for p in normalized)
    return Index(
        root=root,
        paths=normalized,
        lowered=lowered,
        basenames_lower=basenames,
    )


# --------------------------------------------------------------- module API

_INDEX = FileIndex()


def get_index() -> Index:
    """Return the current immutable index snapshot."""
    return _INDEX.current


def reindex(root: Optional[str] = None, *, blocking: bool = False) -> None:
    """Trigger an (async) reindex of ``root`` (defaults to cwd)."""
    _INDEX.reindex(root, blocking=blocking)


def set_index_for_testing(root: str, paths: List[str]) -> None:
    """Test helper — inject an index without invoking ripgrep."""
    _INDEX.set_for_testing(root, paths)

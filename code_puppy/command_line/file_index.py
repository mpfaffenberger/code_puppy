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
import threading
import time
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
        self._requested = ""
        self._attempted = ""
        self._finished = 0.0

    # ----------------------------------------------------------------- public

    @property
    def current(self) -> Index:
        return self._current

    def reindex(self, root: Optional[str] = None, *, blocking: bool = False) -> None:
        """Refresh at most every five seconds; failures use the same backoff.

        A single worker drains the latest requested root. Publishing and
        scheduling share a lock, so an older build cannot overwrite a new root.
        """
        if self._test_mode and not blocking:
            return
        target = os.path.abspath(root or os.getcwd())
        with self._lock:
            self._requested = target
            if self._build_thread is None:
                if (
                    not blocking
                    and target == self._attempted
                    and time.monotonic() - self._finished < 5.0
                ):
                    return
                self._build_thread = threading.Thread(target=self._work, daemon=True)
                self._build_thread.start()
            thread = self._build_thread
        if blocking:
            thread.join()

    def _work(self) -> None:
        while True:
            with self._lock:
                root = self._requested
            try:
                paths = _run_ripgrep(root)
                snapshot = _make_index(root, paths) if paths is not None else None
            except Exception:
                snapshot = None  # worker failures must not wedge future refreshes
            with self._lock:
                if root != self._requested:
                    continue
                if snapshot is not None:
                    self._current = snapshot
                elif self._current.root != root:
                    self._current = Index(root=root)
                self._attempted = root
                self._finished = time.monotonic()
                self._build_thread = None
                return

    def set_for_testing(self, root: str, paths: List[str]) -> None:
        """Inject an index directly. Tests only — keeps subprocess out of unit tests.

        Also enables test mode which suppresses automatic reindexing for the rest
        of the test session until reset.
        """
        self._current = _make_index(os.path.abspath(root), paths)
        self._test_mode = True


def _run_ripgrep(root: str) -> Optional[List[str]]:
    rg = shutil.which("rg")
    if not rg:
        return None
    from code_puppy.file_completion_io import read_paths

    return read_paths(rg, root, MAX_INDEXED_PATHS, INDEX_BUILD_TIMEOUT_SECONDS)


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

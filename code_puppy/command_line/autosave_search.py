"""Search/filter helpers for the ``/resume`` (autosave_load) session picker.

Lives separately from :mod:`code_puppy.command_line.autosave_menu` so that
file (already overweight at ~700+ lines) does not grow further. Everything
in here is pure / IO-tolerant so it is unit-testable without spinning up
a prompt_toolkit ``Application``.

The picker UX mirrors ``/set``: pressing ``/`` enters search mode, alphabet
chars append to a buffer, ``Enter`` commits the buffer, ``Esc`` cancels the
search. The novel bit is that this picker filters on *session content* --
the concatenated text of every message in each session -- rather than just
the timestamp/metadata visible in the left menu. Content is loaded lazily
and cached for the picker's lifetime so we do not re-unpickle session
files on every keystroke.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Iterator, Optional, Tuple

from code_puppy.session_storage import load_session

# Alphabet bound to the search buffer while ``in_search_mode`` is True.
# Lowercase ASCII letters (except ``e`` and ``q``), digits, underscore,
# hyphen, and space. ``e`` and ``q`` are deliberately excluded because
# autosave_menu.py already binds them to nav actions (browse-msgs and
# exit-browse respectively); those existing handlers are dual-mode --
# they append to the search buffer when ``in_search_mode`` is True and
# fire their nav action otherwise. Same trick set_menu uses for ``r``.
SEARCH_ALPHABET = "abcdfghijklmnoprstuvwxyz0123456789_- "


def iter_alphabet_bindings() -> Iterator[Tuple[str, str]]:
    """Yield ``(key_to_bind, char_to_append)`` pairs for the alphabet.

    For each lowercase character in :data:`SEARCH_ALPHABET` we yield both
    the lowercase and (when distinct) the uppercase form. Both forms
    append the *lowercase* character so the buffer stays case-folded --
    search match is already case-insensitive, and folding on input means
    the rendered ``Searching: '...'`` line is stable regardless of
    Shift/Caps Lock state.

    Yields lowercase before uppercase so prompt_toolkit's keybinding
    registration order is deterministic and easy to reason about.
    """
    for ch in SEARCH_ALPHABET:
        yield ch, ch
        upper = ch.upper()
        if upper != ch:
            yield upper, ch


def _session_text(history: list) -> str:
    """Concatenate the raw text content of every message part.

    Deliberately uses raw ``part.content`` (only when it is a non-empty
    ``str``) instead of going through
    :func:`code_puppy.command_line.autosave_menu._extract_message_content`.
    That helper decorates tool messages with ``"Tool Call: <name>"`` and
    ``"Tool Result: <name>"`` prefixes -- if we indexed the decorated
    form, typing ``tool call`` would match every session that ever
    called a tool. Noise, not signal.
    """
    chunks: list = []
    for msg in history:
        for part in getattr(msg, "parts", ()) or ():
            content = getattr(part, "content", None)
            if isinstance(content, str) and content:
                chunks.append(content)
    return "\n".join(chunks)


class SessionContentIndex:
    """Lazy, per-picker cache of ``{session_name -> lowercased text}``.

    Loading a session unpickles the whole file, so we only do it on
    demand and cache the result for the lifetime of one picker
    invocation. Errors are tolerated and cached as empty strings so we
    do not re-hit broken files on every keystroke.

    The ``loader`` injection point exists for testing -- production code
    always uses :func:`code_puppy.session_storage.load_session`.
    """

    def __init__(
        self,
        loader: Optional[Callable[[str, Path], list]] = None,
    ) -> None:
        self._loader = loader or load_session
        self._cache: Dict[str, str] = {}
        # The pre-warm task runs on an ``asyncio.to_thread`` worker while
        # the picker's render path reads cache state on the event loop;
        # the post-Enter filter (PR review accept #2) also runs on a
        # worker. CPython's GIL makes individual dict ops atomic, but
        # the ``check-then-load-then-store`` sequence in ``lookup`` is
        # not -- the lock keeps the invariant tidy and survives a future
        # free-threaded build where GIL atomicity disappears.
        self._lock = Lock()

    def lookup(self, session_name: str, base_dir: Path) -> str:
        with self._lock:
            cached = self._cache.get(session_name)
            if cached is not None or session_name in self._cache:
                # ``cached is not None`` short-circuits the common case;
                # the explicit ``in`` check picks up cached-empty-string
                # entries (failed loads) without re-running the loader.
                return cached or ""
        # Loader runs OUTSIDE the lock so a slow pickle read does not
        # block other threads from checking the cache for unrelated keys.
        try:
            history = self._loader(session_name, base_dir)
            text = _session_text(history).lower()
        except Exception:
            # Cache the failure so a broken pickle does not slow every keystroke.
            text = ""
        with self._lock:
            # Last-writer-wins. If a concurrent ``lookup`` for the same
            # key beat us here that is fine -- the value is identical.
            self._cache[session_name] = text
        return text

    def count(self) -> int:
        """Number of sessions cached so far (success or failure).

        The picker uses this to render an ``Indexing N/M…`` progress hint
        while the background pre-warm task is still running.
        """
        with self._lock:
            return len(self._cache)

    def __contains__(self, session_name: object) -> bool:
        """Membership check so callers don't have to peek at ``_cache``.

        Used by the picker's pre-warm loop to skip sessions that were
        already loaded on demand by an earlier ``lookup``.
        """
        with self._lock:
            return session_name in self._cache


def _formatted_timestamp(metadata: dict) -> str:
    """Mirror the ``YYYY-MM-DD HH:MM`` format the left menu shows.

    Search must hit what the user *sees*, so the formatting has to
    match :func:`autosave_menu._render_menu_panel`.
    """
    timestamp = metadata.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(timestamp)


def entry_matches(
    entry: Tuple[str, dict],
    needle: str,
    index: SessionContentIndex,
    base_dir: Path,
) -> bool:
    """Return True if ``needle`` is a substring of the session.

    Empty needle matches everything (the picker shows the full list).
    Cheap metadata checks (session name, formatted timestamp, message
    count) run first; the full session content is only loaded via
    ``index`` if the cheap checks miss. Typing ``2026-06`` therefore
    never triggers a single pickle read.
    """
    if not needle:
        return True
    needle_lower = needle.lower()
    session_name, metadata = entry

    if needle_lower in session_name.lower():
        return True
    if needle_lower in _formatted_timestamp(metadata).lower():
        return True
    if needle_lower in str(metadata.get("message_count", "")).lower():
        return True

    return needle_lower in index.lookup(session_name, base_dir)

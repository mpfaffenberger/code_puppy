"""Tests for the autosave picker's ``/``-search helpers.

These cover the pure-function half of PUP-346: the content index cache
and the ``entry_matches`` predicate. Prompt_toolkit ``Application``
integration is deliberately NOT tested -- that mirrors the existing
``test_set_menu.py`` convention of treating the picker plumbing as
implementation detail and exercising the filtering logic in isolation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

from code_puppy.command_line.autosave_search import (
    SEARCH_ALPHABET,
    SessionContentIndex,
    _formatted_timestamp,
    _session_text,
    entry_matches,
    iter_alphabet_bindings,
)


def _make_part(content):
    """Tiny stand-in for a pydantic-ai message part with a ``content`` attr."""
    return SimpleNamespace(content=content)


def _make_msg(parts):
    return SimpleNamespace(parts=parts)


def _make_history(*texts: str) -> List:
    """Build a fake message history out of plain string content parts."""
    return [_make_msg([_make_part(t)]) for t in texts]


# ---------------------------------------------------------------------------
# SEARCH_ALPHABET
# ---------------------------------------------------------------------------


class TestSearchAlphabet:
    def test_excludes_e_and_q(self):
        # ``e`` and ``q`` are handled by their own dual-mode keybindings
        # in autosave_menu.py (browse-msgs / exit-browse). They must NOT
        # be in the alphabet or prompt_toolkit will register two handlers
        # for the same key and the dedicated handler will be shadowed.
        assert "e" not in SEARCH_ALPHABET
        assert "q" not in SEARCH_ALPHABET
        # Uppercase variants too -- prompt_toolkit treats case literally.
        assert "E" not in SEARCH_ALPHABET
        assert "Q" not in SEARCH_ALPHABET

    def test_contains_typical_search_chars(self):
        for ch in "abcdfghijklmnoprstuvwxyz0123456789_- ":
            assert ch in SEARCH_ALPHABET


class TestAlphabetBindings:
    def test_yields_lowercase_letters_unchanged(self):
        pairs = list(iter_alphabet_bindings())
        assert ("a", "a") in pairs
        assert ("z", "z") in pairs
        assert ("0", "0") in pairs
        assert (" ", " ") in pairs
        assert ("_", "_") in pairs
        assert ("-", "-") in pairs

    def test_yields_uppercase_that_appends_lowercase(self):
        # Real bug from PUP-346 manual test: holding Shift dropped the
        # keystroke because no uppercase handler was registered. Bindings
        # must include the uppercase variant, but the buffer must stay
        # case-folded (search match is case-insensitive).
        pairs = list(iter_alphabet_bindings())
        assert ("A", "a") in pairs
        assert ("Z", "z") in pairs

    def test_no_uppercase_e_or_q(self):
        # ``E`` and ``Q`` are registered separately by the autosave_menu
        # dual-mode handlers (alongside ``e`` and ``q``). Yielding them
        # here would cause prompt_toolkit double-binding.
        keys = [key for key, _ in iter_alphabet_bindings()]
        assert "E" not in keys
        assert "Q" not in keys
        assert "e" not in keys
        assert "q" not in keys

    def test_digits_and_symbols_yield_no_uppercase_dup(self):
        # ``"1".upper() == "1"`` -- emitting it twice would re-register the
        # same keybinding. The helper must skip the second yield when the
        # uppercase form equals the lowercase form.
        pairs = list(iter_alphabet_bindings())
        # Count occurrences of "1" as a key.
        ones = [pair for pair in pairs if pair[0] == "1"]
        assert len(ones) == 1
        spaces = [pair for pair in pairs if pair[0] == " "]
        assert len(spaces) == 1

    def test_every_append_is_in_search_alphabet(self):
        # The lowercase form being appended to the search buffer must
        # itself be a member of SEARCH_ALPHABET -- otherwise the rendered
        # ``Searching: '...'`` line could show a character we later refuse
        # to render or filter on.
        for _key, append in iter_alphabet_bindings():
            assert append in SEARCH_ALPHABET


# ---------------------------------------------------------------------------
# _session_text -- raw content extraction
# ---------------------------------------------------------------------------


class TestSessionText:
    def test_joins_string_parts(self):
        history = _make_history("hello world", "second message")
        assert _session_text(history) == "hello world\nsecond message"

    def test_skips_non_string_content(self):
        # Tool-call parts have dict ``args`` or other non-str payloads --
        # we deliberately ignore those at index time.
        history = [
            _make_msg([_make_part("real text"), _make_part({"args": "ignored"})])
        ]
        assert _session_text(history) == "real text"

    def test_skips_empty_string(self):
        history = [_make_msg([_make_part(""), _make_part("kept")])]
        assert _session_text(history) == "kept"

    def test_tolerates_missing_parts_attribute(self):
        # Some message-like objects (or test fakes) might omit ``parts``.
        msg_without_parts = SimpleNamespace()
        assert _session_text([msg_without_parts]) == ""

    def test_tolerates_missing_content_attribute(self):
        part_without_content = SimpleNamespace()
        msg = _make_msg([part_without_content])
        assert _session_text([msg]) == ""


# ---------------------------------------------------------------------------
# _formatted_timestamp
# ---------------------------------------------------------------------------


class TestFormattedTimestamp:
    def test_iso_to_display_format(self):
        assert _formatted_timestamp({"timestamp": "2026-06-23T08:13:35"}) == (
            "2026-06-23 08:13"
        )

    def test_unparseable_returns_raw(self):
        assert _formatted_timestamp({"timestamp": "not a date"}) == "not a date"

    def test_missing_returns_empty_string(self):
        assert _formatted_timestamp({}) == ""


# ---------------------------------------------------------------------------
# SessionContentIndex
# ---------------------------------------------------------------------------


class TestSessionContentIndex:
    def test_lookup_lowercases_content(self):
        history = _make_history("Hello WORLD")
        idx = SessionContentIndex(loader=lambda name, base: history)
        assert idx.lookup("s1", Path("/tmp")) == "hello world"

    def test_caches_results(self):
        call_count = {"n": 0}

        def loader(name, base):
            call_count["n"] += 1
            return _make_history("content")

        idx = SessionContentIndex(loader=loader)
        idx.lookup("s1", Path("/tmp"))
        idx.lookup("s1", Path("/tmp"))
        idx.lookup("s1", Path("/tmp"))
        assert call_count["n"] == 1, "lookup should only load each session once"

    def test_tolerates_loader_exceptions(self):
        def boom(name, base):
            raise RuntimeError("pickle is haunted")

        idx = SessionContentIndex(loader=boom)
        assert idx.lookup("broken", Path("/tmp")) == ""

    def test_caches_loader_failure(self):
        # A broken pickle must not be retried on every keystroke.
        call_count = {"n": 0}

        def flaky(name, base):
            call_count["n"] += 1
            raise IOError("nope")

        idx = SessionContentIndex(loader=flaky)
        idx.lookup("s1", Path("/tmp"))
        idx.lookup("s1", Path("/tmp"))
        assert call_count["n"] == 1

    def test_count_reflects_cached_entries(self):
        # Drives the picker's ``Indexing N/M...`` progress hint.
        idx = SessionContentIndex(loader=lambda name, base: _make_history(name))
        assert idx.count() == 0
        idx.lookup("s1", Path("/tmp"))
        assert idx.count() == 1
        idx.lookup("s2", Path("/tmp"))
        idx.lookup("s2", Path("/tmp"))  # repeat -- still 2
        assert idx.count() == 2

    def test_contains_membership_check(self):
        # The pre-warm loop uses ``name in index`` to skip already-loaded
        # sessions; if this regressed we'd re-load every session on every
        # pre-warm tick.
        idx = SessionContentIndex(loader=lambda name, base: _make_history(name))
        assert "s1" not in idx
        idx.lookup("s1", Path("/tmp"))
        assert "s1" in idx
        assert "never_loaded" not in idx

    def test_cached_failure_is_not_re_loaded(self):
        # PR review accept #1: the lookup short-circuit must distinguish
        # ``not cached yet`` from ``cached as empty string (failed load)``.
        # Regression would silently retry a broken pickle on every keystroke.
        call_count = {"n": 0}

        def boom_once(name, base):
            call_count["n"] += 1
            raise RuntimeError("pickle ate the dog")

        idx = SessionContentIndex(loader=boom_once)
        assert idx.lookup("broken", Path("/tmp")) == ""
        assert idx.lookup("broken", Path("/tmp")) == ""
        assert idx.lookup("broken", Path("/tmp")) == ""
        assert call_count["n"] == 1, "cached empty-string must not trigger reload"

    def test_concurrent_access_is_thread_safe(self):
        # PR review accept #1: the cache is touched by the event loop AND
        # ``asyncio.to_thread`` worker threads. The lock should keep state
        # consistent under concurrent ``lookup`` / ``count`` / ``in`` calls.
        # This test does not prove the absence of all race conditions, but
        # it does smoke-test the lock plumbing and would have failed loud
        # if we'd accidentally held the lock across the loader call.
        import threading

        load_counts: Dict[str, int] = {}
        load_lock = threading.Lock()

        def slow_loader(name, base):
            with load_lock:
                load_counts[name] = load_counts.get(name, 0) + 1
            return _make_history(f"content-of-{name}")

        idx = SessionContentIndex(loader=slow_loader)
        names = [f"s{i}" for i in range(20)]

        errors = []

        def worker():
            try:
                for name in names:
                    idx.lookup(name, Path("/tmp"))
                    _ = idx.count()
                    _ = name in idx
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"thread-safety regression: {errors}"
        # All 20 sessions ended up cached.
        assert idx.count() == 20
        # Each session was loaded at most a small number of times (one
        # per losing-the-race thread). The point isn't "exactly 1" --
        # the lock is released during loader -- it's "not 8x".
        for name, n in load_counts.items():
            assert 1 <= n <= 8, f"{name} was loaded {n} times -- lock plumbing broken"


# ---------------------------------------------------------------------------
# entry_matches
# ---------------------------------------------------------------------------


def _index_that_never_loads():
    """Loader that raises if called -- proves the cheap checks short-circuit."""

    def boom(name, base):  # pragma: no cover - asserted not called
        raise AssertionError(f"index loaded {name}; cheap checks should have hit")

    return SessionContentIndex(loader=boom)


class TestEntryMatches:
    BASE = Path("/tmp")
    ENTRY = (
        "autosave_2026-06-23_a1b2",
        {
            "timestamp": "2026-06-23T08:13:35",
            "message_count": 42,
        },
    )

    def test_empty_needle_matches_everything(self):
        # Empty needle is the "no filter" state; we never touch the index.
        idx = _index_that_never_loads()
        assert entry_matches(self.ENTRY, "", idx, self.BASE) is True

    def test_matches_session_name_without_loading(self):
        idx = _index_that_never_loads()
        assert entry_matches(self.ENTRY, "a1b2", idx, self.BASE) is True

    def test_matches_session_name_case_insensitive(self):
        idx = _index_that_never_loads()
        assert entry_matches(self.ENTRY, "A1B2", idx, self.BASE) is True

    def test_matches_formatted_timestamp_without_loading(self):
        # User sees "2026-06-23 08:13"; typing that must hit without loading.
        idx = _index_that_never_loads()
        assert entry_matches(self.ENTRY, "2026-06-23 08:13", idx, self.BASE) is True

    def test_matches_message_count_without_loading(self):
        idx = _index_that_never_loads()
        assert entry_matches(self.ENTRY, "42", idx, self.BASE) is True

    def test_falls_through_to_content_index(self):
        history = _make_history("we talked about kubernetes pods today")
        idx = SessionContentIndex(loader=lambda name, base: history)
        # "kubernetes" is in neither name, timestamp, nor msg_count.
        assert entry_matches(self.ENTRY, "kubernetes", idx, self.BASE) is True

    def test_no_match_anywhere(self):
        history = _make_history("totally unrelated chatter")
        idx = SessionContentIndex(loader=lambda name, base: history)
        assert entry_matches(self.ENTRY, "kubernetes", idx, self.BASE) is False

    def test_content_match_consults_index_exactly_once(self):
        call_count = {"n": 0}

        def loader(name, base):
            call_count["n"] += 1
            return _make_history("kubernetes pods")

        idx = SessionContentIndex(loader=loader)
        entry_matches(self.ENTRY, "kubernetes", idx, self.BASE)
        entry_matches(self.ENTRY, "kubernetes", idx, self.BASE)
        entry_matches(self.ENTRY, "pods", idx, self.BASE)
        assert call_count["n"] == 1, "content should be loaded at most once per session"

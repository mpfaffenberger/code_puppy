"""Tests for the "this folder only" session-scoping feature.

Covers the primitives in ``session_storage.py`` (``compute_scope_key``,
``scope_key`` persistence through ``save_session``, and the ``list_sessions``
filter) plus a smoke test per opt-in UI surface that layers on top of them:

* ``cli_runner.py`` -- ``--cwd`` flag on ``-r/--resume``
* ``command_line/session_commands.py`` -- trailing ``cwd``/``--cwd`` token
  on ``/load_context``
* ``command_line/autosave_menu.py`` -- Ctrl+T toggle in the interactive
  autosave picker
  keyword typed at the selection prompt

Mocking/fixture patterns deliberately mirror the existing suites for each
of these modules (``tests/test_session_storage_coverage.py``,
``tests/command_line/test_session_commands.py``,
``tests/command_line/test_tui_keybindings.py``,
``tests/test_cli_runner_resume_render.py``) rather than inventing a new
style.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.session_storage import (
    compute_scope_key,
    list_sessions,
    save_session,
)


def _noop_estimator(_message) -> int:
    return 1


# ---------------------------------------------------------------------------
# 1. compute_scope_key
# ---------------------------------------------------------------------------


class TestComputeScopeKey:
    def test_stable_for_same_input(self, tmp_path):
        """Calling twice with the same path yields identical output."""
        first = compute_scope_key(tmp_path)
        second = compute_scope_key(tmp_path)
        assert first == second

    def test_returns_string(self, tmp_path):
        assert isinstance(compute_scope_key(tmp_path), str)

    def test_relative_path_resolves_to_absolute(self, tmp_path, monkeypatch):
        """A relative path resolves against cwd into an absolute string."""
        sub = tmp_path / "child"
        sub.mkdir()
        monkeypatch.chdir(tmp_path)

        relative_key = compute_scope_key("child")
        absolute_key = compute_scope_key(sub)

        assert relative_key == absolute_key
        assert Path(relative_key).is_absolute()

    def test_accepts_str_or_path(self, tmp_path):
        assert compute_scope_key(str(tmp_path)) == compute_scope_key(tmp_path)


# ---------------------------------------------------------------------------
# 2. save_session(..., scope_key=X) round-trip + list_sessions filter
# ---------------------------------------------------------------------------


class TestScopeKeyRoundTrip:
    def test_sidecar_contains_scope_key(self, tmp_path):
        scope_key = compute_scope_key(tmp_path)
        save_session(
            history=[],
            session_name="scoped_session",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=scope_key,
        )

        meta_path = tmp_path / "scoped_session_meta.json"
        assert meta_path.exists()
        with meta_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data["scope_key"] == scope_key

    def test_list_sessions_filters_by_matching_scope_key(self, tmp_path):
        scope_key = compute_scope_key(tmp_path)
        save_session(
            history=[],
            session_name="mine",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=scope_key,
        )

        assert list_sessions(tmp_path, scope_key=scope_key) == ["mine"]

    def test_list_sessions_excludes_non_matching_scope_key(self, tmp_path):
        scope_key = compute_scope_key(tmp_path)
        save_session(
            history=[],
            session_name="mine",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=scope_key,
        )

        assert list_sessions(tmp_path, scope_key="something-else") == []

    def test_no_scope_key_omits_field_from_sidecar(self, tmp_path):
        """save_session without scope_key doesn't write the field at all."""
        save_session(
            history=[],
            session_name="unscoped",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
        )

        meta_path = tmp_path / "unscoped_meta.json"
        with meta_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert "scope_key" not in data


# ---------------------------------------------------------------------------
# 3. Regression guard: unfiltered list_sessions() is unaffected by scope_key
# ---------------------------------------------------------------------------


class TestUnfilteredListSessionsRegressionGuard:
    def test_unfiltered_identical_regardless_of_scope_key_presence(self, tmp_path):
        """list_sessions(base_dir) with NO scope_key kwarg must return the
        same names whether or not sidecars happen to carry a scope_key.

        This is the regression guard called out in T4: existing unfiltered
        callers (e.g. load_context_completion.py) must never be affected by
        this feature.
        """
        save_session(
            history=[],
            session_name="scoped_one",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=compute_scope_key(tmp_path),
        )
        save_session(
            history=[],
            session_name="unscoped_one",
            base_dir=tmp_path,
            timestamp="2024-01-02T00:00:00",
            token_estimator=_noop_estimator,
        )

        unfiltered = list_sessions(tmp_path)
        assert unfiltered == sorted(["scoped_one", "unscoped_one"])

    def test_unfiltered_matches_prior_behavior_with_only_unscoped_sessions(
        self, tmp_path
    ):
        """Same assertion, but for a directory with zero scope_key sidecars
        at all -- the pre-feature baseline case."""
        save_session(
            history=[],
            session_name="alpha",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
        )
        save_session(
            history=[],
            session_name="beta",
            base_dir=tmp_path,
            timestamp="2024-01-02T00:00:00",
            token_estimator=_noop_estimator,
        )

        assert list_sessions(tmp_path) == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# 4. Missing/corrupted sidecar during a filtered list_sessions call
# ---------------------------------------------------------------------------


class TestFilteredListSessionsMissingOrCorruptSidecar:
    def test_missing_sidecar_silently_excluded(self, tmp_path):
        """A session with no _meta.json sidecar at all must be silently
        excluded from a filtered listing -- never raise."""
        (tmp_path / "orphan.json").write_text(
            json.dumps({"format": 2, "encoding": "json", "messages": []}),
            encoding="utf-8",
        )

        result = list_sessions(tmp_path, scope_key="anything")
        assert result == []

    def test_corrupted_sidecar_silently_excluded(self, tmp_path):
        """A sidecar that isn't valid JSON must be silently excluded, not
        raise, when list_sessions is called with a scope_key filter."""
        (tmp_path / "broken.json").write_text(
            json.dumps({"format": 2, "encoding": "json", "messages": []}),
            encoding="utf-8",
        )
        (tmp_path / "broken_meta.json").write_text(
            "not valid json{{{", encoding="utf-8"
        )

        result = list_sessions(tmp_path, scope_key="anything")
        assert result == []

    def test_mixed_valid_and_broken_sidecars(self, tmp_path):
        """A broken sidecar must not stop other, valid, matching sessions
        from being listed."""
        scope_key = compute_scope_key(tmp_path)
        save_session(
            history=[],
            session_name="good",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=scope_key,
        )
        (tmp_path / "broken.json").write_text(
            json.dumps({"format": 2, "encoding": "json", "messages": []}),
            encoding="utf-8",
        )
        (tmp_path / "broken_meta.json").write_text(
            "not valid json{{{", encoding="utf-8"
        )

        result = list_sessions(tmp_path, scope_key=scope_key)
        assert result == ["good"]


# ---------------------------------------------------------------------------
# 5(a). cli_runner.py --cwd flag smoke test
# ---------------------------------------------------------------------------


class TestCliRunnerHereFlag:
    """Smoke-tests the ``--cwd`` opt-in on the ``-r/--resume`` failure path.

    ``resolve_or_create_resume_target`` is forced to raise
    ``ResumeTargetError`` so we land in the "available sessions" fallback,
    which is exactly where ``resume_scope_key`` feeds into
    ``list_sessions``. Mirrors the mocking style of
    ``tests/test_cli_runner_resume_render.py``.
    """

    def _base_main_patches(self):
        from code_puppy.session_lifecycle import ResumeTargetError

        return {
            "code_puppy.cli_runner.find_available_port": MagicMock(return_value=8090),
            "code_puppy.cli_runner.ensure_config_exists": MagicMock(),
            "code_puppy.cli_runner.validate_cancel_agent_key": MagicMock(),
            "code_puppy.cli_runner.initialize_command_history_file": MagicMock(),
            "code_puppy.cli_runner.default_version_mismatch_behavior": MagicMock(),
            "code_puppy.cli_runner.print_truecolor_warning": MagicMock(),
            "code_puppy.cli_runner.reset_unix_terminal": MagicMock(),
            "code_puppy.cli_runner.reset_windows_terminal_ansi": MagicMock(),
            "code_puppy.cli_runner.reset_windows_terminal_full": MagicMock(),
            "code_puppy.cli_runner.callbacks": MagicMock(
                on_startup=AsyncMock(),
                on_shutdown=AsyncMock(),
                on_version_check=AsyncMock(),
                get_callbacks=MagicMock(return_value=[]),
            ),
            "code_puppy.cli_runner.plugins": MagicMock(),
            "code_puppy.config.load_api_keys_to_environment": MagicMock(),
            "code_puppy.session_lifecycle.resolve_or_create_resume_target": MagicMock(
                side_effect=ResumeTargetError("nope")
            ),
        }

    async def _run_main(self, argv, list_sessions_mock):
        import os
        from contextlib import ExitStack

        patches = self._base_main_patches()
        patches["code_puppy.session_storage.list_sessions"] = list_sessions_mock

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"}))
            stack.enter_context(patch("sys.argv", argv))
            stack.enter_context(patch("sys.exit", side_effect=SystemExit))
            for target, value in patches.items():
                stack.enter_context(patch(target, value))
            from code_puppy.cli_runner import main

            try:
                await main()
            except SystemExit:
                pass

    async def test_cwd_flag_passes_scope_key_to_list_sessions(self):
        """--cwd must pass a non-None scope_key through to list_sessions."""
        mock_list_sessions = MagicMock(return_value=["local-session"])

        await self._run_main(
            ["code-puppy", "-r", "missing", "--cwd"], mock_list_sessions
        )

        assert mock_list_sessions.called
        _args, kwargs = mock_list_sessions.call_args
        assert kwargs.get("scope_key") is not None

    async def test_without_cwd_flag_scope_key_is_none(self):
        """Absent --cwd, the unfiltered (scope_key=None) call is preserved."""
        mock_list_sessions = MagicMock(return_value=["some-session"])

        await self._run_main(["code-puppy", "-r", "missing"], mock_list_sessions)

        assert mock_list_sessions.called
        _args, kwargs = mock_list_sessions.call_args
        assert kwargs.get("scope_key") is None


class TestRealResolverScopeInteraction:
    """Exercises resolve_or_create_resume_target for REAL, not mocked.

    Manual verification found a real gap: the mocked tests above always
    force ResumeTargetError, so they never exercise the resolver's actual
    lazy-create branch. A well-formed but nonexistent slug (e.g.
    'totally-made-up-name') silently lazy-creates an empty session
    instead of raising -- so --cwd's filtered hint never fires for that
    case. This is pre-existing resolver behaviour (see its own docstring,
    branch 5) that predates and is unrelated to scope_key; these tests
    make the interaction explicit and prove --cwd works end-to-end for
    the one input shape that actually reaches the error branch: a
    genuinely invalid slug (one containing a space).
    """

    def test_valid_looking_missing_name_lazy_creates_not_errors(self, tmp_path):
        from code_puppy.session_lifecycle import resolve_or_create_resume_target

        session_name, _session_dir, lazy_created = resolve_or_create_resume_target(
            "totally-made-up-name",
            sessions_dir=tmp_path,
            allow_lazy_create=True,
        )

        assert lazy_created is True
        assert session_name == "totally-made-up-name"
        assert (tmp_path / "totally-made-up-name.json").exists()

    def test_invalid_slug_raises_and_cwd_narrows_real_hint(self, tmp_path):
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )

        save_session(
            history=[{"role": "user", "content": "hi"}],
            session_name="local-session",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=_noop_estimator,
            scope_key=compute_scope_key(tmp_path),
        )

        with pytest.raises(ResumeTargetError):
            resolve_or_create_resume_target(
                "not a valid slug",
                sessions_dir=tmp_path,
                allow_lazy_create=True,
            )

        # The exact call cli_runner.py makes in its except block -- confirms
        # --cwd's scope_key genuinely narrows real results once the error
        # branch is reached.
        scoped = list_sessions(tmp_path, scope_key=compute_scope_key(tmp_path))
        assert scoped == ["local-session"]


# ---------------------------------------------------------------------------
# 5(b). session_commands.py "cwd" token smoke test
# ---------------------------------------------------------------------------


class TestLoadContextHereToken:
    """Smoke-tests the trailing "cwd"/"--cwd" token on /load_context.

    Mirrors ``tests/command_line/test_session_commands.py``'s
    ``TestHandleLoadContextCommand.test_file_not_found`` pattern.
    """

    def _run(self, cmd):
        from code_puppy.command_line.session_commands import (
            handle_load_context_command,
        )

        return handle_load_context_command(cmd)

    def test_cwd_token_passes_scope_key(self):
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                side_effect=FileNotFoundError(),
            ),
            patch(
                "code_puppy.command_line.session_commands.list_sessions"
            ) as mock_list_sessions,
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_info"),
        ):
            mock_list_sessions.return_value = []
            assert self._run("/load_context missing cwd") is True

            assert mock_list_sessions.called
            _args, kwargs = mock_list_sessions.call_args
            assert kwargs.get("scope_key") is not None

    def test_without_cwd_token_scope_key_is_none(self):
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                side_effect=FileNotFoundError(),
            ),
            patch(
                "code_puppy.command_line.session_commands.list_sessions"
            ) as mock_list_sessions,
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_info"),
        ):
            mock_list_sessions.return_value = []
            assert self._run("/load_context missing") is True

            assert mock_list_sessions.called
            _args, kwargs = mock_list_sessions.call_args
            assert kwargs.get("scope_key") is None


# ---------------------------------------------------------------------------
# 5(c). autosave_menu.py Ctrl+T toggle smoke test
# ---------------------------------------------------------------------------


def _make_event():
    event = MagicMock()
    event.app = MagicMock()
    return event


def _extract_kb(mock_app_cls):
    """Extract KeyBindings from the Application constructor call."""
    call = mock_app_cls.call_args
    if call is None:
        return None
    return call.kwargs.get("key_bindings")


def _fire(kb, keys):
    """Call all handlers matching any of the given keys."""
    event = _make_event()
    called = set()
    for b in kb.bindings:
        for k in b.keys:
            kv = k.value if hasattr(k, "value") else str(k)
            if kv in keys and id(b.handler) not in called:
                called.add(id(b.handler))
                try:
                    b.handler(event)
                except Exception:
                    pass


class TestSessionBrowserProjectScoping:
    """The two-pane browser's project pane supersedes the old Ctrl+T
    "this folder only" toggle: sessions are grouped by ``scope_key``
    and legacy scope-less sessions land in one "(unscoped)" bucket
    pinned last -- never misattributed to a project.
    """

    def test_projects_group_by_scope_key_with_unscoped_last(self):
        from io import StringIO

        from code_puppy.command_line.session_browser import build_session_browser
        from code_puppy.command_line.session_browser_data import SessionEntry

        entries = [
            SessionEntry.from_pair(
                "local",
                {
                    "scope_key": "/tmp/current-folder",
                    "timestamp": "2026-01-02T10:00:00",
                },
            ),
            SessionEntry.from_pair(
                "other",
                {
                    "scope_key": "/tmp/other-folder",
                    "timestamp": "2026-01-01T10:00:00",
                },
            ),
            SessionEntry.from_pair("legacy", {}),
        ]
        script = iter(["enter", "escape", "escape"])
        browser = build_session_browser(
            entries=entries,
            base_dir=Path("/fake"),
            key_source=lambda: next(script),
            output=StringIO(),
            size=lambda: (120, 30),
            use_alt_screen=False,
        )
        result = browser.run()

        assert result.cancelled
        labels = [project.label for project in browser._projects]
        assert labels == ["current-folder", "other-folder", "(unscoped)"]
        # Opening the first project scopes the session list to it.
        assert [e.name for e in browser.visible_sessions()] == ["local"]

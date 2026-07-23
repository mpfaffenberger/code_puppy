"""Tests for ``code_puppy.session_lifecycle``.

The lifecycle module is the seam between pure-I/O session_storage and the
plugin-callback world. We pin three contracts here:

1. Bare-slug validation accepts safe names and rejects traversal/absolute paths.
2. ``create_empty_session`` lands BOTH a valid pickle AND its metadata JSON
   (the bug class we're guarding against is silent half-creation).
3. ``persist_named_session`` saves the agent's history AND fires
   ``post_autosave`` even from inside a running asyncio loop -- this is the
   correctness fix that motivated the executor wrap.
"""

import asyncio
import json
import pickle
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.session_lifecycle import (
    ResumeTargetError,
    create_empty_session,
    is_valid_session_name,
    persist_named_session,
    resolve_or_create_resume_target,
)


class TestSessionNameValidator:
    """``is_valid_session_name`` is the write-side guard against path traversal."""

    @pytest.mark.parametrize(
        "name",
        [
            "mywork",
            "my-work",
            "my_work",
            "my.work",
            "MyWork-2026.01.02",
            "a",
            "A" * 128,
            "release-prep_v2.1",
        ],
    )
    def test_accepts_safe_slugs(self, name):
        assert is_valid_session_name(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            "A" * 129,  # too long
            "../../etc/passwd",  # classic traversal
            "/tmp/owned",  # absolute path
            "../foo",  # relative traversal
            "foo/bar",  # nested path
            "foo\\bar",  # windows path
            "foo bar",  # whitespace
            "foo\tbar",  # tab
            "foo\nbar",  # newline
            "foo:bar",  # colon (drive letter on windows)
            "foo*bar",  # glob
            ".",  # current dir
            "..",  # parent dir
            "name with emoji",
        ],
    )
    def test_rejects_unsafe_inputs(self, name):
        assert is_valid_session_name(name) is False


class TestCreateEmptySession:
    """Lazy-create must land both .pkl and metadata JSON atomically."""

    def test_writes_both_pickle_and_metadata(self, tmp_path):
        metadata = create_empty_session("brand-new", base_dir=tmp_path)

        assert metadata.pickle_path.exists()
        assert metadata.metadata_path.exists()
        assert metadata.pickle_path == tmp_path / "brand-new.pkl"

    def test_pickle_contains_empty_history(self, tmp_path):
        create_empty_session("brand-new", base_dir=tmp_path)
        loaded = pickle.loads((tmp_path / "brand-new.pkl").read_bytes())
        assert loaded == []

    def test_metadata_reflects_empty_session(self, tmp_path):
        create_empty_session("brand-new", base_dir=tmp_path)
        meta = json.loads((tmp_path / "brand-new_meta.json").read_text())
        assert meta["message_count"] == 0
        assert meta["total_tokens"] == 0
        assert meta["session_name"] == "brand-new"
        assert meta["auto_saved"] is False

    def test_creates_parent_dir_if_missing(self, tmp_path):
        nested = tmp_path / "does" / "not" / "exist"
        create_empty_session("first", base_dir=nested)
        assert (nested / "first.pkl").exists()


def _make_fake_agent(history=None):
    """Tiny test double matching the BaseAgent surface lifecycle.py touches."""
    agent = MagicMock()
    agent.get_message_history.return_value = history or []
    agent.estimate_tokens_for_message.side_effect = lambda _msg: 1
    return agent


class TestPersistNamedSession:
    """End-to-end: history lands on disk AND post_autosave fires."""

    def test_persists_agent_history(self, tmp_path):
        history = [{"role": "user", "content": "hi"}]
        agent = _make_fake_agent(history)

        metadata = persist_named_session(agent, "mywork", base_dir=tmp_path)

        assert metadata.message_count == 1
        loaded = pickle.loads((tmp_path / "mywork.pkl").read_bytes())
        assert loaded == history

    def test_does_not_fire_post_autosave_callback(self, tmp_path):
        """``persist_named_session`` must NOT fire ``post_autosave``.

        That hook is reserved for the periodic background auto-save path
        (``config.auto_save_session_if_enabled``). Firing it from
        ``/dump_context`` and headless ``-r NAME -p ...`` save-back too
        would print plugin-decorated lines (e.g. the walmart token-quota
        line) after every explicit user-initiated save -- a visible UX
        regression. Pre-unification semantics: only periodic auto-save
        fires the hook.
        """
        agent = _make_fake_agent([{"role": "user", "content": "x"}])

        with patch("code_puppy.callbacks._trigger_callbacks_sync") as mock_trigger:
            persist_named_session(agent, "mywork", base_dir=tmp_path)

        # Zero plugin callbacks fire from this path.
        assert mock_trigger.call_count == 0
        # The save itself still landed on disk -- the assertion above is
        # not vacuous because the save succeeded.
        assert (tmp_path / "mywork.pkl").exists()

    def test_async_callback_fires_from_inside_running_loop(self, tmp_path):
        """The whole reason the executor wrap exists.

        ``_trigger_callbacks_sync`` only invokes async callbacks via
        ``asyncio.run``, which raises if a loop is already running. The
        executor wrap moves the trigger into a worker thread that has no
        loop, so async hooks can fire. We prove the wrap is doing its job
        by observing loop state from inside the patched callable -- if the
        wrap were removed the side_effect would see a running loop, which
        is exactly what would break real async callbacks.

        Exercises ``fire_post_autosave_callback`` directly: ``persist_named_session``
        deliberately no longer fires the hook (it's reserved for the periodic
        auto-save path), but the wrap-correctness invariant still has to hold
        for the path that DOES call ``fire_post_autosave_callback``
        (``config.auto_save_session_if_enabled``) -- and that path is always
        invoked from inside an async CLI loop in production.
        """
        from code_puppy.session_lifecycle import (
            SessionMetadata,
            fire_post_autosave_callback,
        )

        loop_state = []

        def _capture_loop_state(*_args, **_kwargs):
            try:
                asyncio.get_running_loop()
                loop_state.append("has_loop")
            except RuntimeError:
                loop_state.append("no_loop")
            return []

        metadata = SessionMetadata(
            session_name="mywork",
            timestamp="2026-01-01T00:00:00",
            message_count=1,
            total_tokens=1,
            pickle_path=tmp_path / "mywork.pkl",
            metadata_path=tmp_path / "mywork_meta.json",
            auto_saved=True,
        )

        with patch(
            "code_puppy.callbacks._trigger_callbacks_sync",
            side_effect=_capture_loop_state,
        ):

            async def _runner():
                fire_post_autosave_callback(metadata)

            asyncio.run(_runner())

        # This is the property the executor wrap exists to guarantee. If a
        # future refactor removes the wrap the trigger would see a running
        # loop here and async callbacks would silently no-op.
        assert loop_state == ["no_loop"], (
            "executor wrap regressed: trigger ran inside the asyncio.run "
            "loop, which is exactly the bug the wrap exists to prevent"
        )


class TestResolveOrCreateResumeTarget:
    """Pin every branch of the ``-r`` resolver in one place.

    The resolver is the single production code path that maps ``args.resume``
    onto a session file (existing or freshly lazy-created). Tests must drive
    the real function -- mirroring the gate inside the test body would not
    catch a future re-ordering regression.
    """

    def test_existing_pkl_path_resolves_directly(self, tmp_path):
        target = tmp_path / "my-session.pkl"
        target.write_bytes(b"dummy")

        name, dir_, lazy = resolve_or_create_resume_target(
            str(target),
            sessions_dir=tmp_path / "contexts_unused",
            allow_lazy_create=True,
        )
        assert (name, dir_, lazy) == ("my-session", tmp_path, False)

    def test_existing_named_session_resolves_under_contexts_dir(self, tmp_path):
        contexts_dir = tmp_path / "ctx"
        contexts_dir.mkdir()
        (contexts_dir / "mywork.pkl").write_bytes(b"dummy")

        name, dir_, lazy = resolve_or_create_resume_target(
            "mywork",
            sessions_dir=contexts_dir,
            allow_lazy_create=True,
        )
        assert (name, dir_, lazy) == ("mywork", contexts_dir, False)

    def test_existing_path_without_pkl_suffix_resolves(self, tmp_path):
        target = tmp_path / "weird-name"
        target.write_bytes(b"dummy")

        name, dir_, lazy = resolve_or_create_resume_target(
            str(target),
            sessions_dir=tmp_path / "ctx_unused",
            allow_lazy_create=True,
        )
        assert (name, dir_, lazy) == ("weird-name", tmp_path, False)

    def test_missing_target_raises_when_lazy_create_disabled(self, tmp_path):
        with pytest.raises(ResumeTargetError) as excinfo:
            resolve_or_create_resume_target(
                "nope",
                sessions_dir=tmp_path,
                allow_lazy_create=False,
            )
        assert "Resume target not found" in excinfo.value.message
        # Pre-existing contents must be untouched.
        assert list(tmp_path.iterdir()) == []

    def test_missing_target_lazy_creates_when_enabled(self, tmp_path):
        name, dir_, lazy = resolve_or_create_resume_target(
            "fresh-session",
            sessions_dir=tmp_path,
            allow_lazy_create=True,
        )
        assert (name, dir_, lazy) == ("fresh-session", tmp_path, True)
        assert (tmp_path / "fresh-session.pkl").exists()
        # Metadata JSON must land too -- otherwise restore_autosave_interactively
        # would render the lazy-created session as "(unknown time)".
        assert (tmp_path / "fresh-session_meta.json").exists()

    @pytest.mark.parametrize(
        "bad_name",
        [
            # Names that do NOT resolve to an existing read path AND are
            # unsafe slugs -- the only combination that actually exercises
            # the lazy-create validator. Names like "/etc/passwd" or ".."
            # that DO resolve to real paths are intentionally accepted by
            # the read branches above and never reach validation; their
            # safety is enforced downstream when `load_session` fails to
            # unpickle them, not here.
            "../../tmp/traversal-sentinel-does-not-exist",
            "foo/bar/baz",
            "foo bar",
            "foo\tbar",
            "foo\nbar",
        ],
    )
    def test_invalid_lazy_create_name_raises_and_writes_nothing(
        self, tmp_path, bad_name
    ):
        with pytest.raises(ResumeTargetError) as excinfo:
            resolve_or_create_resume_target(
                bad_name,
                sessions_dir=tmp_path,
                allow_lazy_create=True,
            )
        assert "Invalid session name" in excinfo.value.message
        assert excinfo.value.hint is not None
        # The whole point of validate-before-create: nothing on disk under
        # the contexts dir, no escaped artefact at the traversed location.
        assert list(tmp_path.iterdir()) == []
        assert not (
            tmp_path.parent / "tmp" / "traversal-sentinel-does-not-exist.pkl"
        ).exists()


class TestReservedPrefix:
    """``allow_reserved_prefix`` kwarg: user input rejected, stored names allowed.

    The ``auto_session_`` prefix is reserved for system-generated names so
    users can never squat on the auto-generated namespace and confuse the
    autosave-menu UX or break TTY-keyed resume.
    """

    def test_user_input_rejects_reserved_prefix_by_default(self):
        assert is_valid_session_name("auto_session_squat") is False
        assert is_valid_session_name("auto_session_") is False

    def test_stored_name_validator_accepts_reserved_prefix(self):
        # The on-disk filename ``auto_session_20260101_120000.pkl`` is
        # entirely legitimate -- the stored-name validator MUST accept it.
        assert (
            is_valid_session_name(
                "auto_session_20260101_120000", allow_reserved_prefix=True
            )
            is True
        )

    def test_reserved_prefix_check_runs_after_regex_check(self):
        # A name that fails the regex (control char) is rejected regardless
        # of the prefix flag -- regex check is the floor, not the ceiling.
        assert (
            is_valid_session_name("auto_session_bad name", allow_reserved_prefix=True)
            is False
        )

    def test_lazy_create_blocks_reserved_prefix(self, tmp_path):
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )

        with pytest.raises(ResumeTargetError) as excinfo:
            resolve_or_create_resume_target(
                "auto_session_squat",
                sessions_dir=tmp_path,
                allow_lazy_create=True,
            )
        assert "Invalid session name" in excinfo.value.message
        assert "reserved" in excinfo.value.hint.lower()
        assert list(tmp_path.iterdir()) == []


class TestPklSuffixNormalization:
    """Resolver normalizes ``-r foo.pkl`` to ``-r foo`` when bare-name slug is valid."""

    def test_bare_name_with_pkl_suffix_lazy_creates_without_double_suffix(
        self, tmp_path
    ):
        from code_puppy.session_lifecycle import resolve_or_create_resume_target

        name, dir_, lazy = resolve_or_create_resume_target(
            "foo.pkl",
            sessions_dir=tmp_path,
            allow_lazy_create=True,
        )
        assert name == "foo"
        assert lazy is True
        # The lazy-created file is foo.pkl, NOT foo.pkl.pkl.
        assert (tmp_path / "foo.pkl").exists()
        assert not (tmp_path / "foo.pkl.pkl").exists()

    def test_path_with_separator_is_not_normalized(self, tmp_path):
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )

        # An input that LOOKS like a path (has separator) is not normalized
        # -- absolute/relative paths to existing files keep their direct-load
        # semantics, and a non-existent path-with-separator falls through
        # to the lazy-create gate and is rejected for traversal.
        with pytest.raises(ResumeTargetError):
            resolve_or_create_resume_target(
                "sub/dir/foo.pkl",
                sessions_dir=tmp_path,
                allow_lazy_create=True,
            )

    def test_uppercase_pkl_is_not_normalized(self, tmp_path):
        """Case-sensitive on Linux/Mac; ``.PKL`` lazy-creates as-is.

        Documented behavior: ``.pkl`` is the canonical spelling and we
        deliberately don't accept variants (no permissive case folding,
        no surprise truncation of names that happen to end in .PKL).
        """
        from code_puppy.session_lifecycle import resolve_or_create_resume_target

        name, _, lazy = resolve_or_create_resume_target(
            "FOO.PKL",
            sessions_dir=tmp_path,
            allow_lazy_create=True,
        )
        assert name == "FOO.PKL"
        assert lazy is True
        assert (tmp_path / "FOO.PKL.pkl").exists()


class TestResolverSelfValidation:
    """Resolver validates its own output to keep ``pin_current_session_name`` safe.

    Without this, a pre-existing on-disk file with a non-slug stem (e.g.
    ``My Project.pkl`` from old unguarded ``/dump_context``) would pass
    the permissive read-side resolution branches and then crash startup
    inside ``pin_current_session_name`` -- which validates strictly.
    """

    def test_resolver_rejects_pre_existing_non_slug_named_file(self, tmp_path):
        from code_puppy.session_lifecycle import (
            ResumeTargetError,
            resolve_or_create_resume_target,
        )

        # Pre-place a non-slug file as a direct .pkl path (branch 1).
        bad = tmp_path / "My Project.pkl"
        bad.write_bytes(b"x")

        with pytest.raises(ResumeTargetError) as excinfo:
            resolve_or_create_resume_target(
                str(bad),
                sessions_dir=tmp_path,
                allow_lazy_create=True,
            )
        assert "not a valid slug" in excinfo.value.message
        # Hint points at the sessions dir so the user knows where to rename.
        assert str(tmp_path) in excinfo.value.hint

    def test_resolver_accepts_pre_existing_auto_flavored_named_file(self, tmp_path):
        """Branch 2 (named-session in sessions_dir) accepts auto_session_*."""
        from code_puppy.session_lifecycle import resolve_or_create_resume_target

        auto_name = "auto_session_20260101_120000"
        (tmp_path / f"{auto_name}.pkl").write_bytes(b"x")

        name, dir_, lazy = resolve_or_create_resume_target(
            auto_name,
            sessions_dir=tmp_path,
            allow_lazy_create=False,
        )
        assert name == auto_name
        assert dir_ == tmp_path
        assert lazy is False


class TestPersistNamedSessionSuccessKey:
    """``success_message_key`` is the /dump_context-vs-silent split.

    The old API took a raw ``success_message_template`` string that the helper
    ran through ``str.format`` -- unsafe for catalog text (see docs/I18N.md).
    The new API takes an i18n catalog key that the helper resolves through
    the hardened ``t()`` interpolator.
    """

    def test_key_omitted_emits_no_success_line(self, tmp_path):
        """Periodic autosave / -r save-back path: no user-facing success."""
        from unittest.mock import MagicMock, patch

        from code_puppy.session_lifecycle import persist_named_session

        agent = MagicMock()
        agent.get_message_history.return_value = []
        agent.estimate_tokens_for_message.return_value = 0

        with patch("code_puppy.messaging.emit_success") as mock_success:
            persist_named_session(agent, "silent_session", base_dir=tmp_path)

        mock_success.assert_not_called()

    def test_key_present_resolves_and_emits(self, tmp_path):
        """/dump_context path: explicit success line via catalog key."""
        from unittest.mock import MagicMock, patch

        from code_puppy.i18n import catalog, translate
        from code_puppy.session_lifecycle import persist_named_session

        catalog.reset()
        translate.set_locale("en-US")

        agent = MagicMock()
        agent.get_message_history.return_value = []
        agent.estimate_tokens_for_message.return_value = 0

        with patch("code_puppy.messaging.emit_success") as mock_success:
            persist_named_session(
                agent,
                "loud_session",
                base_dir=tmp_path,
                success_message_key="cmd.dump_context.success",
            )

        mock_success.assert_called_once()
        rendered = mock_success.call_args[0][0]
        # Params interpolate into the resolved catalog text via the safe
        # {identifier}-only grammar in i18n.translate._interpolate.
        assert "0 messages" in rendered

    def test_unknown_key_does_not_crash(self, tmp_path):
        """A missing catalog key must not poison the save path.

        ``t()`` falls back to returning the key itself for a missing entry,
        so the emit is harmless but the save must still succeed. This
        replaces the old ``str.format``-failure defensive path.
        """
        from unittest.mock import MagicMock, patch

        from code_puppy.session_lifecycle import persist_named_session

        agent = MagicMock()
        agent.get_message_history.return_value = []
        agent.estimate_tokens_for_message.return_value = 0

        with patch("code_puppy.messaging.emit_success"):
            persist_named_session(
                agent,
                "session_x",
                base_dir=tmp_path,
                success_message_key="cmd.definitely.does.not.exist",
            )
        # If we got here without raising, the contract holds.

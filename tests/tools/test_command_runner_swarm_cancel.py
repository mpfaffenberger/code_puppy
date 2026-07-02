"""Tests for the Ctrl+C -> stop-the-whole-swarm behavior.

A single Ctrl+C during a sub-agent swarm must kill the shells AND request a
cancel of every sub-agent task + the main agent, instead of only killing the
current batch of shells (which forced the user to mash Ctrl+C once per
still-running sub-agent).
"""

from unittest.mock import patch

import code_puppy.tools.command_runner as command_runner
from code_puppy.tools.command_runner import (
    _shell_sigint_handler,
    _tear_down_live_panels,
    clear_agent_cancel,
    register_agent_cancel,
)


class TestSwarmCancelOnSigint:
    def teardown_method(self):
        # Never let a registered callback leak into another test.
        clear_agent_cancel()

    def test_headless_only_kills_shells(self):
        """No active run registered -> behave like the old shells-only handler."""
        clear_agent_cancel()
        with (
            patch.object(
                command_runner, "kill_all_running_shell_processes"
            ) as mock_kill,
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)
        mock_kill.assert_called_once()

    def test_sigint_kills_shells_then_cancels_with_force(self):
        """With a run registered: kill shells AND call cancel cb with force=True."""
        calls = []

        def fake_cancel(force=False):
            calls.append(force)

        register_agent_cancel(fake_cancel)
        with (
            patch.object(
                command_runner, "kill_all_running_shell_processes"
            ) as mock_kill,
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)

        mock_kill.assert_called_once()
        assert calls == [True], "cancel cb must be invoked exactly once with force=True"

    def test_banner_and_cancel_are_deduped(self):
        """Mashing Ctrl+C during teardown must not re-fire the cancel sweep."""
        calls = []

        register_agent_cancel(lambda force=False: calls.append(force))
        with (
            patch.object(command_runner, "kill_all_running_shell_processes"),
            patch.object(command_runner, "emit_warning") as mock_warn,
        ):
            _shell_sigint_handler(None, None)
            _shell_sigint_handler(None, None)
            _shell_sigint_handler(None, None)

        assert calls == [True], "cancel sweep must fire only once per run"
        # Only the first press emits the stop banner.
        assert mock_warn.call_count == 1

    def test_register_resets_dedupe_flag(self):
        """A fresh run (re-register) re-arms the one-shot dedupe flag."""
        calls = []
        register_agent_cancel(lambda force=False: calls.append(force))
        with (
            patch.object(command_runner, "kill_all_running_shell_processes"),
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)
            # New run starts -> should be cancellable again.
            register_agent_cancel(lambda force=False: calls.append(force))
            _shell_sigint_handler(None, None)

        assert calls == [True, True]

    def test_clear_drops_callback(self):
        """clear_agent_cancel() makes the handler fall back to shells-only."""
        calls = []
        register_agent_cancel(lambda force=False: calls.append(force))
        clear_agent_cancel()
        with (
            patch.object(
                command_runner, "kill_all_running_shell_processes"
            ) as mock_kill,
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)
        mock_kill.assert_called_once()
        assert calls == [], "callback was cleared; it must not fire"

    def test_cancel_cb_exception_does_not_crash_handler(self):
        """A failing cancel cb must never blow up the signal handler."""

        def boom(force=False):
            raise RuntimeError("nope")

        register_agent_cancel(boom)
        with (
            patch.object(
                command_runner, "kill_all_running_shell_processes"
            ) as mock_kill,
            patch.object(command_runner, "emit_warning"),
        ):
            # Must not raise.
            _shell_sigint_handler(None, None)
        mock_kill.assert_called_once()


class TestTearDownLivePanels:
    """Phase 3: the Rich Live spinner is gone, so teardown is a compat
    no-op — but the SIGINT handler's ordering contract (banner BEFORE the
    slow shell kill, cancel last) must survive.
    """

    def teardown_method(self):
        clear_agent_cancel()

    def test_teardown_is_a_safe_noop(self):
        # Must not raise and must not touch anything.
        _tear_down_live_panels()

    def test_banner_fires_before_the_slow_kill(self):
        """REGRESSION: the user must get instant feedback on Ctrl+C.

        ``kill_all_running_shell_processes`` blocks for ~2s *per* nested
        shell. The banner MUST precede the kill so the UI responds
        instantly; the cancel sweep runs last.
        """
        order = []
        register_agent_cancel(lambda force=False: order.append("cancel"))
        with (
            patch.object(
                command_runner,
                "kill_all_running_shell_processes",
                side_effect=lambda: order.append("kill"),
            ),
            patch.object(
                command_runner,
                "emit_warning",
                side_effect=lambda *_a, **_k: order.append("banner"),
            ),
        ):
            _shell_sigint_handler(None, None)

        assert order == ["banner", "kill", "cancel"], (
            "banner must precede the blocking shell kill so the UI responds "
            f"instantly; got {order}"
        )

    def test_headless_path_also_banners_before_kill(self):
        """Even with no agent run, banner before the slow kill."""
        order = []
        clear_agent_cancel()
        with (
            patch.object(
                command_runner,
                "kill_all_running_shell_processes",
                side_effect=lambda: order.append("kill"),
            ),
            patch.object(
                command_runner,
                "emit_warning",
                side_effect=lambda *_a, **_k: order.append("banner"),
            ),
        ):
            _shell_sigint_handler(None, None)

        assert order == ["banner", "kill"], (
            f"headless path must announce before killing; got {order}"
        )

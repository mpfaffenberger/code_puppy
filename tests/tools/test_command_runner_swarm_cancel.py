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


class FakeSpinner:
    """Minimal stand-in for ConsoleSpinner that records pause() calls."""

    def __init__(self, *, explode: bool = False):
        self.paused = 0
        self._explode = explode

    def pause(self):
        if self._explode:
            raise RuntimeError("spinner teardown failed")
        self.paused += 1


class TestTearDownLivePanels:
    """The cancel path must hide the spinner Live (and the sub-agent panel it
    hosts) the same way steer does, so the cancel banner isn't repainted over.
    """

    def teardown_method(self):
        clear_agent_cancel()

    def test_pauses_every_active_spinner(self):
        import code_puppy.messaging.spinner as spinner_mod

        spinners = [FakeSpinner(), FakeSpinner()]
        with patch.object(spinner_mod, "_active_spinners", spinners):
            _tear_down_live_panels()
        assert [s.paused for s in spinners] == [1, 1]

    def test_one_spinner_blowing_up_does_not_stop_the_rest(self):
        import code_puppy.messaging.spinner as spinner_mod

        good_a, boom, good_b = FakeSpinner(), FakeSpinner(explode=True), FakeSpinner()
        with patch.object(spinner_mod, "_active_spinners", [good_a, boom, good_b]):
            # Must not raise even though the middle spinner explodes.
            _tear_down_live_panels()
        assert good_a.paused == 1 and good_b.paused == 1

    def test_sigint_hides_panel_before_emitting_banner(self):
        """On the first Ctrl+C the panel is torn down so the banner shows."""
        import code_puppy.messaging.spinner as spinner_mod

        spinner = FakeSpinner()
        register_agent_cancel(lambda force=False: None)
        with (
            patch.object(spinner_mod, "_active_spinners", [spinner]),
            patch.object(command_runner, "kill_all_running_shell_processes"),
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)
        assert spinner.paused == 1, "panel must be hidden on cancel"

    def test_extra_presses_keep_panel_hidden(self):
        """Deduped extra presses still re-hide the panel in case a frame raced."""
        import code_puppy.messaging.spinner as spinner_mod

        spinner = FakeSpinner()
        register_agent_cancel(lambda force=False: None)
        with (
            patch.object(spinner_mod, "_active_spinners", [spinner]),
            patch.object(command_runner, "kill_all_running_shell_processes"),
            patch.object(command_runner, "emit_warning"),
        ):
            _shell_sigint_handler(None, None)  # first: hide + banner
            _shell_sigint_handler(None, None)  # deduped: still hides
        assert spinner.paused == 2

    def test_teardown_and_banner_fire_before_the_slow_kill(self):
        """REGRESSION: the deep-swarm 'panel stays up until shells die' bug.

        ``kill_all_running_shell_processes`` blocks for ~2s *per* nested shell
        (SIGTERM->SIGINT->SIGKILL escalation). If the panel teardown / banner
        run AFTER it (the old order), the spinner Live keeps repainting the
        sub-agent panel for that whole window and the user sees nothing happen.
        The teardown + banner MUST precede the kill so the UI responds instantly.
        """
        import code_puppy.messaging.spinner as spinner_mod

        order = []
        spinner = FakeSpinner()
        # Record relative ordering of the three observable side effects.
        spinner.pause = lambda: order.append("teardown")  # type: ignore[assignment]

        register_agent_cancel(lambda force=False: order.append("cancel"))
        with (
            patch.object(spinner_mod, "_active_spinners", [spinner]),
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

        assert order == ["teardown", "banner", "kill", "cancel"], (
            "panel teardown and banner must precede the blocking shell kill so "
            f"the UI responds instantly; got {order}"
        )

    def test_headless_path_also_hides_panel_before_kill(self):
        """Even with no agent run, hide the panel + banner before the slow kill."""
        import code_puppy.messaging.spinner as spinner_mod

        order = []
        spinner = FakeSpinner()
        spinner.pause = lambda: order.append("teardown")  # type: ignore[assignment]
        clear_agent_cancel()
        with (
            patch.object(spinner_mod, "_active_spinners", [spinner]),
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

        assert order == ["teardown", "banner", "kill"], (
            f"headless path must hide + announce before killing; got {order}"
        )

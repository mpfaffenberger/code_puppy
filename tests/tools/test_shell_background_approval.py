"""Regression tests: a background shell command must still be approved.

Background: the ``background=True`` branch of ``run_shell_command`` returned
*before* the interactive approval gate, so the model could run any command
without the user's permission just by passing ``background=True``. A user
running with yolo mode off expects every shell command to be approved.
"""

from unittest.mock import MagicMock

from code_puppy.i18n import t
from code_puppy.tools import command_runner


async def _no_callbacks(*args, **kwargs):
    return []


def _arm_approval(monkeypatch, confirmed=True, feedback=None):
    """Arm the interactive approval gate and report how it was called."""
    calls = []

    async def _approval(*args, **kwargs):
        calls.append(kwargs)
        return confirmed, feedback

    monkeypatch.setattr(command_runner, "get_user_approval_async", _approval)
    monkeypatch.setattr("code_puppy.callbacks.on_run_shell_command", _no_callbacks)
    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: False)
    monkeypatch.setattr(command_runner, "is_subagent", lambda: False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    return calls


def _fake_popen(monkeypatch):
    """Replace Popen so no real process is spawned."""
    spawned = []

    class _Proc:
        pid = 4242

    def _popen(*args, **kwargs):
        spawned.append(args)
        return _Proc()

    monkeypatch.setattr(command_runner.subprocess, "Popen", _popen)
    return spawned


class TestBackgroundNeedsApproval:
    async def test_background_command_is_approved_before_it_starts(self, monkeypatch):
        """The approval prompt must run for a background command too."""
        calls = _arm_approval(monkeypatch)
        spawned = _fake_popen(monkeypatch)

        result = await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, True
        )

        assert len(calls) == 1
        assert result.background is True
        assert result.success is True
        assert len(spawned) == 1

    async def test_rejected_background_command_never_starts(self, monkeypatch):
        """A rejected background command must not spawn anything."""
        calls = _arm_approval(monkeypatch, confirmed=False)
        spawned = _fake_popen(monkeypatch)

        result = await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, True
        )

        assert len(calls) == 1
        assert not spawned
        assert result.success is False
        assert result.background is False
        assert "rejected" in (result.error or "").lower()

    async def test_foreground_command_still_approved(self, monkeypatch):
        """The foreground path keeps behaving exactly as before."""
        calls = _arm_approval(monkeypatch)
        executed = {}

        async def _execute(*args, **kwargs):
            executed["called"] = True
            return command_runner.ShellCommandOutput(
                success=True,
                command="echo hello",
                stdout=None,
                stderr=None,
                exit_code=None,
            )

        monkeypatch.setattr(command_runner, "_execute_shell_command", _execute)

        result = await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, False
        )

        assert len(calls) == 1
        assert executed.get("called")
        assert result.success is True


class TestBackgroundApprovalPanel:
    async def test_panel_tells_the_user_it_runs_in_the_background(self, monkeypatch):
        """A detached process outlives the turn -- say so before approving."""
        calls = _arm_approval(monkeypatch)
        _fake_popen(monkeypatch)

        await command_runner.run_shell_command(MagicMock(), "echo hello", None, 5, True)

        panel = calls[0]["content"]
        # Compare against the catalog entry itself: the notice is localized,
        # and the suite may run with any locale active.
        assert t("tools.command_runner.background_notice") in panel.plain

    async def test_foreground_panel_has_no_background_notice(self, monkeypatch):
        calls = _arm_approval(monkeypatch)

        async def _execute(*args, **kwargs):
            return command_runner.ShellCommandOutput(
                success=True,
                command="echo hello",
                stdout=None,
                stderr=None,
                exit_code=None,
            )

        monkeypatch.setattr(command_runner, "_execute_shell_command", _execute)

        await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, False
        )

        panel = calls[0]["content"]
        assert t("tools.command_runner.background_notice") not in panel.plain


class TestUnchangedPaths:
    async def test_yolo_mode_skips_the_prompt(self, monkeypatch):
        """yolo mode is the explicit 'do not ask me' switch."""
        calls = _arm_approval(monkeypatch)
        monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: True)
        spawned = _fake_popen(monkeypatch)

        result = await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, True
        )

        assert not calls
        assert result.background is True
        assert len(spawned) == 1

    async def test_subagent_skips_the_prompt(self, monkeypatch):
        """Sub-agents run without user interaction -- unchanged."""
        calls = _arm_approval(monkeypatch)
        monkeypatch.setattr(command_runner, "is_subagent", lambda: True)
        spawned = _fake_popen(monkeypatch)

        result = await command_runner.run_shell_command(
            MagicMock(), "echo hello", None, 5, True
        )

        assert not calls
        assert result.background is True
        assert len(spawned) == 1

    async def test_empty_command_is_rejected_before_spawning(self, monkeypatch):
        """An empty command must not spawn a shell, in either mode."""
        _arm_approval(monkeypatch)
        spawned = _fake_popen(monkeypatch)

        result = await command_runner.run_shell_command(
            MagicMock(), "   ", None, 5, True
        )

        assert not spawned
        assert result.success is False
        assert "empty" in (result.error or "").lower()

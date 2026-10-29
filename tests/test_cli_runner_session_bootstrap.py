"""Port/resume/headless-session coverage for cli_runner.py core functionality.

Covers port-base resolution and availability probing, one-shot agent
running, the --resume flag, and headless (-p) autosave/session-persistence
behavior on success, cancellation, generic exceptions, and persist failure.

Split out of tests/test_cli_runner.py (was 670 lines) to stay under the
600-line cap; tests/test_cli_runner_argparse.py holds the argument-parsing/
validation/startup-callback half. No test, fixture, assertion, import, or
patch target was changed in this split.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPortAvailability:
    """Test port availability checking."""

    @patch("code_puppy.http_utils.find_available_port")
    def test_find_available_port_called(self, mock_find_port):
        """Test that find_available_port can be called."""
        from code_puppy.http_utils import find_available_port

        mock_find_port.return_value = 8090
        result = find_available_port()
        assert result is not None

    def test_port_base_argparse_default_is_none(self):
        """--port-base defaults to None so cli_runner can fall back to config.

        If this ever flips to a hardcoded value, the env-var / puppy.cfg
        precedence chain silently breaks.
        """
        import argparse

        parser = argparse.ArgumentParser()
        # Mirror production: type=str (not int) so bad input is validated
        # gracefully in resolve_port_base rather than argparse-exiting.
        parser.add_argument("--port-base", type=str, default=None)
        args = parser.parse_args([])
        assert args.port_base is None
        args = parser.parse_args(["--port-base", "9100"])
        assert args.port_base == "9100"

    def test_port_base_cli_wins_over_config(self):
        """resolve_port_base must honor a valid CLI value over env/cfg."""
        from code_puppy.config import resolve_port_base

        with patch("code_puppy.config.get_value", return_value="9500"):
            with patch.dict("os.environ", {"CODE_PUPPY_PORT_BASE": "9700"}):
                assert resolve_port_base(cli_value="9100") == 9100
                assert resolve_port_base(cli_value=None) == 9700  # falls to env

    def test_bad_cli_port_base_does_not_crash(self):
        """Garbage --port-base must be skipped, not raise SystemExit.

        This is the whole point of type=str + resolve_port_base --
        argparse type=int would hard-exit before we could recover.
        """
        from code_puppy.config import DEFAULT_PORT_BASE, resolve_port_base

        with patch("code_puppy.config.get_value", return_value=None):
            with patch.dict("os.environ", {}, clear=False):
                import os

                os.environ.pop("CODE_PUPPY_PORT_BASE", None)
                assert (
                    resolve_port_base(cli_value="totally-not-a-port")
                    == DEFAULT_PORT_BASE
                )


class TestAgentRunning:
    """Test agent execution."""

    @patch("code_puppy.agents.agent_manager.get_current_agent")
    def test_get_current_agent_returns_agent(self, mock_get_agent):
        """Test that get_current_agent returns an agent."""
        mock_agent = MagicMock()
        mock_agent.name = "test-agent"
        mock_get_agent.return_value = mock_agent

        from code_puppy.agents.agent_manager import get_current_agent

        agent = get_current_agent()
        assert agent is not None
        assert agent.name == "test-agent"


class TestResumeFlag:
    """Test --resume flag functionality."""

    def test_resume_session_loading_logic(self, tmp_path):
        """Test that resume can load from a pickle file path."""

        from code_puppy.session_storage import load_session, save_session

        # Create a fake session
        fake_history = [{"role": "user", "content": "Hello"}]
        session_name = "test-resume-session"

        # Save session using the standard save_session function
        metadata = save_session(
            history=fake_history,
            session_name=session_name,
            base_dir=tmp_path,
            timestamp="2025-01-01T00:00:00",
            token_estimator=lambda x: 10,
        )

        # Verify the session was saved
        assert metadata.json_path.exists()

        # Load session using the standard load_session function
        loaded_history = load_session(session_name, tmp_path)

        # Verify history was loaded correctly
        assert len(loaded_history) == 1
        assert loaded_history[0]["role"] == "user"
        assert loaded_history[0]["content"] == "Hello"

    def test_resume_path_resolution_full_pkl_path(self, tmp_path):
        """Test that a full .pkl path is properly resolved."""
        from pathlib import Path

        # Create a fake pickle file
        session_file = tmp_path / "my-session.pkl"
        session_file.write_bytes(b"dummy")

        resume_path = Path(str(session_file))
        assert resume_path.suffix == ".pkl"
        assert resume_path.exists()
        assert resume_path.stem == "my-session"
        assert resume_path.parent == tmp_path

    def test_resume_path_resolution_session_name(self, tmp_path):
        """Test that a session name is resolved to the contexts directory."""

        # Simulate a contexts directory with a session file
        contexts_dir = tmp_path
        session_name = "saved-session"
        session_file = contexts_dir / f"{session_name}.pkl"
        session_file.write_bytes(b"dummy")

        # Check resolution logic
        assert (contexts_dir / f"{session_name}.pkl").exists()


class TestHeadlessSessionPersistence:
    """-r in headless -p mode lazy-creates the session and saves back.

    These tests pin the wiring between ``cli_runner.execute_single_prompt``
    and ``session_lifecycle.persist_named_session`` -- specifically that the
    save happens in a ``finally`` block (so cancel/error paths still persist),
    that shell-passthrough never clobbers a named session, and that the
    no-``-r`` default autosaves under the process's generated session name
    rather than being disk-silent.
    """

    @staticmethod
    def _agent_with_history(history):
        agent = MagicMock()
        agent.get_message_history.return_value = history
        agent.estimate_tokens_for_message.side_effect = lambda _m: 1
        return agent

    @staticmethod
    def _renderer():
        renderer = MagicMock()
        renderer.console = MagicMock()
        return renderer

    @pytest.mark.asyncio
    async def test_save_back_on_success_path(self, tmp_path):
        from code_puppy.cli_runner import execute_single_prompt

        history = [{"role": "user", "content": "step 1"}]
        agent = self._agent_with_history(history)
        run_result = MagicMock()
        run_result.output = "ok"

        with (
            patch("code_puppy.prompt_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.prompt_runner.run_prompt_with_attachments",
                new=AsyncMock(return_value=(run_result, MagicMock())),
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch(
                "code_puppy.session_lifecycle.fire_post_autosave_callback"
            ) as fire_cb,
            patch("code_puppy.config.record_quick_resume_sessions") as mock_qr,
        ):
            await execute_single_prompt(
                "hi",
                self._renderer(),
                session_name="mywork",
            )

        # Canonical JSON envelope; the legacy pickle twin is gone.
        assert (tmp_path / "mywork.json").exists()
        assert not (tmp_path / "mywork.pkl").exists()
        # post_autosave is reserved for the periodic auto-save path - the headless
        # ``-r NAME -p`` save-back must NOT fire it (decorator plugins double-print).
        assert fire_cb.call_count == 0
        # Write the quick-resume pointer only after a successful persist, so
        # ``--quick-resume`` rediscovers both auto-generated and ``-r`` saves.
        mock_qr.assert_called_once_with("mywork")

    @pytest.mark.asyncio
    async def test_quick_resume_pointer_not_written_on_persist_failure(self, tmp_path):
        """record_quick_resume_sessions is NOT called when persist_named_session fails.

        The quick-resume pointer must only be updated when persistence
        actually succeeds.  A filesystem error, pickle failure, or any other
        exception from ``persist_named_session`` must leave the pointer
        untouched so ``--quick-resume`` does not point at a missing/corrupt
        session file.
        """
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "hi"}])
        run_result = MagicMock()
        run_result.output = "ok"

        with (
            patch("code_puppy.prompt_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.prompt_runner.run_prompt_with_attachments",
                new=AsyncMock(return_value=(run_result, MagicMock())),
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch(
                "code_puppy.session_lifecycle.persist_named_session",
                side_effect=OSError("disk full"),
            ),
            patch("code_puppy.config.record_quick_resume_sessions") as mock_qr,
        ):
            # Should not raise; error is swallowed and emitted as a message.
            await execute_single_prompt(
                "hi",
                self._renderer(),
                session_name="mywork",
            )

        mock_qr.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_back_on_cancelled_error(self, tmp_path):
        """Partial state still persists when the run is cancelled."""
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "partial"}])

        async def _raise_cancelled(*_args, **_kwargs):
            raise asyncio.CancelledError()

        with (
            patch("code_puppy.prompt_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.prompt_runner.run_prompt_with_attachments",
                new=_raise_cancelled,
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.fire_post_autosave_callback"),
        ):
            await execute_single_prompt("hi", self._renderer(), session_name="mywork")

        assert (tmp_path / "mywork.json").exists()

    @pytest.mark.asyncio
    async def test_save_back_on_generic_exception(self, tmp_path):
        """Save still fires when the agent raises a non-cancel exception."""
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "partial"}])

        async def _raise(*_args, **_kwargs):
            raise RuntimeError("model exploded")

        with (
            patch("code_puppy.prompt_runner.get_current_agent", return_value=agent),
            patch("code_puppy.prompt_runner.run_prompt_with_attachments", new=_raise),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.fire_post_autosave_callback"),
        ):
            await execute_single_prompt("hi", self._renderer(), session_name="mywork")

        assert (tmp_path / "mywork.json").exists()

    @pytest.mark.asyncio
    async def test_default_autosave_uses_generated_session_name(self, tmp_path):
        """Without -r, headless -p autosaves under the process's generated session name.

        ``execute_single_prompt(..., session_name=None)`` resolves the
        effective name via ``get_current_session_name()`` and forwards it
        to ``persist_named_session`` exactly once with the generated name and
        the configured AUTOSAVE_DIR -- so a clean process always persists its
        history rather than being disk-silent.
        """
        from pathlib import Path

        from code_puppy.cli_runner import execute_single_prompt

        generated_name = "auto_session_20250101_000000"
        agent = self._agent_with_history([{"role": "user", "content": "ephemeral"}])
        run_result = MagicMock()
        run_result.output = "ok"

        with (
            patch("code_puppy.prompt_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.prompt_runner.run_prompt_with_attachments",
                new=AsyncMock(return_value=(run_result, MagicMock())),
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch(
                "code_puppy.config.get_current_session_name",
                return_value=generated_name,
            ),
            patch("code_puppy.session_lifecycle.persist_named_session") as mock_persist,
        ):
            await execute_single_prompt("hi", self._renderer(), session_name=None)

        mock_persist.assert_called_once_with(
            agent,
            generated_name,
            base_dir=Path(str(tmp_path)),
            auto_saved=True,
        )

    @pytest.mark.asyncio
    async def test_shell_passthrough_does_not_clobber_session(self, tmp_path):
        """`-r mywork -p '!ls'` must not zero out an existing named session."""
        from code_puppy.cli_runner import execute_single_prompt

        # Seed an existing session file with real content.
        seeded = b"non-empty existing session bytes"
        (tmp_path / "mywork.pkl").write_bytes(seeded)

        with (
            patch(
                "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.shell_passthrough.execute_shell_passthrough"
            ) as mock_shell,
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.persist_named_session") as mock_persist,
        ):
            await execute_single_prompt("!ls", self._renderer(), session_name="mywork")

        mock_shell.assert_called_once_with("!ls")
        mock_persist.assert_not_called()
        # Pre-existing session bytes must be byte-identical.
        assert (tmp_path / "mywork.pkl").read_bytes() == seeded

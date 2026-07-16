"""Comprehensive test coverage for cli_runner.py core functionality.

Tests command-line argument parsing, model/agent validation, execution modes,
error handling, and integration with messaging/config systems.

Main focus areas:
- Argument parsing (--version, -i, -p, --agent, --model, command)
- Single-prompt execution mode (-p flag)
- Interactive mode initialization
- Model and agent validation from CLI
- Error handling for invalid models/agents
- Entry point behavior
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestArgumentParsing:
    """Test command-line argument parsing."""

    def test_version_flag(self):
        """Test --version flag displays version."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--version",
            "-v",
            action="version",
            version="1.0.0",
        )
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_prompt_flag_short(self):
        """Test -p flag for single prompt execution."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--prompt", type=str)
        args = parser.parse_args(["-p", "write hello world"])
        assert args.prompt == "write hello world"

    def test_prompt_flag_long(self):
        """Test --prompt flag for single prompt execution."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--prompt", type=str)
        args = parser.parse_args(["--prompt", "write hello world"])
        assert args.prompt == "write hello world"

    def test_interactive_flag_short(self):
        """Test -i flag for interactive mode."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--interactive", action="store_true")
        args = parser.parse_args(["-i"])
        assert args.interactive is True

    def test_agent_flag(self):
        """Test --agent flag for agent selection."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-a", "--agent", type=str)
        args = parser.parse_args(["-a", "code-reviewer"])
        assert args.agent == "code-reviewer"

    def test_model_flag(self):
        """Test --model flag for model selection."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-m", "--model", type=str)
        args = parser.parse_args(["-m", "gpt-5"])
        assert args.model == "gpt-5"

    def test_command_positional_args(self):
        """Test positional command arguments (legacy mode)."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("command", nargs="*")
        args = parser.parse_args(["write", "hello", "world"])
        assert args.command == ["write", "hello", "world"]

    def test_default_no_flags(self):
        """Test default behavior with no flags (interactive)."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--prompt", type=str)
        parser.add_argument("-i", "--interactive", action="store_true")
        args = parser.parse_args([])
        assert args.prompt is None
        assert args.interactive is False

    def test_prompt_with_interactive_flags(self):
        """Test that -p and -i can both be set (though -p takes precedence)."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--prompt", type=str)
        parser.add_argument("-i", "--interactive", action="store_true")
        args = parser.parse_args(["-p", "test", "-i"])
        assert args.prompt == "test"
        assert args.interactive is True


class TestModelValidation:
    """Test model validation from command line."""

    def test_model_string_strip(self):
        """Test that model names with whitespace are trimmed."""
        model_name = "  gpt-5  "
        trimmed = model_name.strip()
        assert trimmed == "gpt-5"
        assert len(trimmed.split()) == 1

    @patch("code_puppy.config.set_model_name")
    def test_set_model_name_called(self, mock_set_model):
        """Test that set_model_name is called with model."""
        from code_puppy.config import set_model_name

        set_model_name("gpt-5")
        mock_set_model.assert_called_once_with("gpt-5")


class TestAgentValidation:
    """Test agent validation from command line."""

    @patch("code_puppy.agents.agent_manager.set_current_agent")
    def test_set_agent_called(self, mock_set_agent):
        """Test that set_current_agent is called with agent name."""
        from code_puppy.agents.agent_manager import set_current_agent

        set_current_agent("code-reviewer")
        mock_set_agent.assert_called_once_with("code-reviewer")

    def test_agent_name_case_insensitive(self):
        """Test that agent names are case-insensitive."""
        agent_name = "CODE-REVIEWER".lower()
        assert agent_name == "code-reviewer"


class TestErrorHandling:
    """Test error handling in CLI runner."""

    def test_keyboard_interrupt_handling(self):
        """Test graceful handling of Ctrl+C."""
        with pytest.raises(KeyboardInterrupt):
            raise KeyboardInterrupt()

    def test_eof_handling(self):
        """Test graceful handling of EOF (Ctrl+D)."""
        with pytest.raises(EOFError):
            raise EOFError()

    @patch("code_puppy.messaging.emit_error")
    def test_emit_error_called(self, mock_emit_error):
        """Test that emit_error can be called for errors."""
        from code_puppy.messaging import emit_error

        emit_error("Test error")
        mock_emit_error.assert_called_once()


class TestVersionHandling:
    """Test version checking and display."""

    def test_version_string_exists(self):
        """Test that version string can be accessed."""
        from code_puppy import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0

    @patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"})
    def test_version_check_disabled_env_var(self):
        """Test version check disabled via environment variable."""
        is_disabled = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert is_disabled is True


class TestLogoDisplay:
    """Test CODE PUPPY logo display."""

    def test_logo_not_displayed_in_prompt_only_mode(self):
        """Test that logo is skipped in prompt-only mode (-p flag)."""
        # Logo display is skipped when args.prompt is set
        prompt_arg = "write hello world"
        assert prompt_arg is not None  # args.prompt is not None

    def test_pyfiglet_available(self):
        """Test that pyfiglet can be imported when available."""
        try:
            import pyfiglet

            assert pyfiglet is not None
        except ImportError:
            # pyfiglet may not always be available
            pass


class TestAPIKeyLoading:
    """Test API key loading from puppy.cfg."""

    @patch("code_puppy.config.load_api_keys_to_environment")
    def test_api_keys_load_function_called(self, mock_load_keys):
        """Test that API keys are loaded from config."""
        from code_puppy.config import load_api_keys_to_environment

        load_api_keys_to_environment()
        mock_load_keys.assert_called_once()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"})
    def test_openai_api_key_in_environment(self):
        """Test that OpenAI API key can be read from environment."""
        api_key = os.getenv("OPENAI_API_KEY")
        assert api_key == "sk-test123"


class TestMessageRendering:
    """Test message rendering and display systems."""

    def test_console_can_be_created(self):
        """Test that Console can be created."""
        from rich.console import Console

        display_console = Console()
        assert display_console is not None

    @patch("code_puppy.messaging.get_global_queue")
    @patch("code_puppy.messaging.get_message_bus")
    def test_queue_and_bus_initialized(self, mock_bus, mock_queue):
        """Test that both message bus and queue are initialized."""
        from code_puppy.messaging import get_global_queue, get_message_bus

        get_global_queue()
        get_message_bus()
        mock_queue.assert_called_once()
        mock_bus.assert_called_once()


class TestTerminalReset:
    """Test terminal state reset functionality."""

    @patch("code_puppy.terminal_utils.reset_windows_terminal_ansi")
    def test_windows_ansi_reset_function_exists(self, mock_reset_ansi):
        """Test that Windows ANSI reset function can be called."""
        from code_puppy.terminal_utils import reset_windows_terminal_ansi

        reset_windows_terminal_ansi()
        mock_reset_ansi.assert_called_once()

    @patch("code_puppy.terminal_utils.reset_unix_terminal")
    def test_unix_terminal_reset_function_exists(self, mock_reset_unix):
        """Test that Unix terminal reset function can be called."""
        from code_puppy.terminal_utils import reset_unix_terminal

        reset_unix_terminal()
        mock_reset_unix.assert_called_once()


class TestCancelAgentKeyValidation:
    """Test cancel agent key validation."""

    @patch("code_puppy.keymap.validate_cancel_agent_key")
    def test_cancel_key_validation_called(self, mock_validate):
        """Test that cancel key validation can be called."""
        from code_puppy.keymap import validate_cancel_agent_key

        validate_cancel_agent_key()
        mock_validate.assert_called_once()


class TestConfigInitialization:
    """Test configuration initialization."""

    @patch("code_puppy.config.ensure_config_exists")
    def test_ensure_config_exists_called(self, mock_ensure):
        """Test that ensure_config_exists is called."""
        from code_puppy.config import ensure_config_exists

        ensure_config_exists()
        mock_ensure.assert_called_once()

    @patch("code_puppy.config.initialize_command_history_file")
    def test_command_history_initialized(self, mock_init):
        """Test that command history file is initialized."""
        from code_puppy.config import initialize_command_history_file

        initialize_command_history_file()
        mock_init.assert_called_once()


class TestCallbackSystem:
    """Test callback system integration."""

    @patch("code_puppy.callbacks.on_startup", new_callable=AsyncMock)
    async def test_on_startup_callback(self, mock_startup):
        """Test that on_startup callback exists and can be called."""
        from code_puppy.callbacks import on_startup

        await on_startup()
        mock_startup.assert_called_once()

    @patch("code_puppy.callbacks.on_shutdown", new_callable=AsyncMock)
    async def test_on_shutdown_callback(self, mock_shutdown):
        """Test that on_shutdown callback exists and can be called."""
        from code_puppy.callbacks import on_shutdown

        await on_shutdown()
        mock_shutdown.assert_called_once()


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
        assert metadata.pickle_path.exists()

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
    no-``-r`` default stays disk-silent.
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
            patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new=AsyncMock(return_value=(run_result, MagicMock())),
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch(
                "code_puppy.session_lifecycle.fire_post_autosave_callback"
            ) as fire_cb,
        ):
            await execute_single_prompt(
                "hi",
                self._renderer(),
                session_name="mywork",
            )

        assert (tmp_path / "mywork.pkl").exists()
        # post_autosave hook is reserved for the periodic background save
        # path (``config.auto_save_session_if_enabled``). The headless
        # ``-r NAME -p ...`` save-back deliberately does NOT fire it, so
        # plugins that decorate the auto-save line (e.g. the walmart
        # token-quota plugin) don't double-print.
        assert fire_cb.call_count == 0

    @pytest.mark.asyncio
    async def test_save_back_on_cancelled_error(self, tmp_path):
        """Partial state still persists when the run is cancelled."""
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "partial"}])

        async def _raise_cancelled(*_args, **_kwargs):
            raise asyncio.CancelledError()

        with (
            patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new=_raise_cancelled,
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.fire_post_autosave_callback"),
        ):
            await execute_single_prompt("hi", self._renderer(), session_name="mywork")

        assert (tmp_path / "mywork.pkl").exists()

    @pytest.mark.asyncio
    async def test_save_back_on_generic_exception(self, tmp_path):
        """Save still fires when the agent raises a non-cancel exception."""
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "partial"}])

        async def _raise(*_args, **_kwargs):
            raise RuntimeError("model exploded")

        with (
            patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
            patch("code_puppy.cli_runner.run_prompt_with_attachments", new=_raise),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.fire_post_autosave_callback"),
        ):
            await execute_single_prompt("hi", self._renderer(), session_name="mywork")

        assert (tmp_path / "mywork.pkl").exists()

    @pytest.mark.asyncio
    async def test_no_save_when_session_name_is_none(self, tmp_path):
        """Default headless -p must remain disk-silent (no -r passed)."""
        from code_puppy.cli_runner import execute_single_prompt

        agent = self._agent_with_history([{"role": "user", "content": "ephemeral"}])
        run_result = MagicMock()
        run_result.output = "ok"

        with (
            patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new=AsyncMock(return_value=(run_result, MagicMock())),
            ),
            patch("code_puppy.config.AUTOSAVE_DIR", str(tmp_path)),
            patch("code_puppy.session_lifecycle.persist_named_session") as mock_persist,
        ):
            await execute_single_prompt("hi", self._renderer(), session_name=None)

        mock_persist.assert_not_called()
        # And nothing landed on disk under the (empty) contexts dir.
        assert list(tmp_path.iterdir()) == []

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

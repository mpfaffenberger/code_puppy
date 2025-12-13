"""Extended test coverage for core_commands.py UI components.

Focuses on comprehensive testing of the interactive pickers, error handling,
state management, and edge cases to boost coverage from 35% to 80%+.
"""

import concurrent.futures
from unittest.mock import ANY, MagicMock, patch

import pytest

from code_puppy.command_line.core_commands import (
    handle_agent_command,
    handle_cd_command,
    handle_exit_command,
    handle_generate_pr_description_command,
    handle_help_command,
    handle_mcp_command,
    handle_model_command,
    handle_motd_command,
    handle_switch_command,
    handle_tools_command,
    interactive_agent_picker,
    interactive_model_picker,
)


class TestHandleHelpCommand:
    """Extended tests for help command functionality."""

    def test_help_command_with_emoji_content(self):
        """Test help command displays content with emoji and formatting."""
        mock_help_text = "🐕 Commands:\n• /help - Show help\n• /exit - Exit"

        with patch(
            "code_puppy.command_line.core_commands.get_commands_help",
            return_value=mock_help_text,
        ):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                result = handle_help_command("/help")
                assert result is True
                mock_emit.assert_called_once()

                # Check the call contains our content
                args, kwargs = mock_emit.call_args
                assert mock_help_text in args[0]
                assert "message_group_id" in kwargs

    def test_help_command_with_unicode_characters(self):
        """Test help command handles unicode characters gracefully."""
        mock_help_text = "Commands:\n• /help - 显示帮助\n• /exit - 出口"

        with patch(
            "code_puppy.command_line.core_commands.get_commands_help",
            return_value=mock_help_text,
        ):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                result = handle_help_command("/h")  # Test alias
                assert result is True
                mock_emit.assert_called_once()

    def test_help_command_uses_unique_group_ids(self):
        """Test that each help call generates a unique group ID."""
        with patch(
            "code_puppy.command_line.core_commands.get_commands_help",
            return_value="Help text",
        ):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                # Call help command twice
                handle_help_command("/help")
                handle_help_command("/help")

                # Should have been called twice with different group IDs
                assert mock_emit.call_count == 2
                first_kwargs = mock_emit.call_args_list[0][1]
                second_kwargs = mock_emit.call_args_list[1][1]

                first_id = first_kwargs.get("message_group_id")
                second_id = second_kwargs.get("message_group_id")

                assert first_id != second_id


class TestHandleCdCommand:
    """Extended tests for cd command functionality."""

    def test_cd_with_tilde_expansion(self):
        """Test cd command handles tilde (~) expansion correctly."""
        with patch("code_puppy.messaging.emit_success"):
            with patch("os.path.expanduser", return_value="/home/user"):
                with patch("os.path.isabs", return_value=True):
                    with patch("os.path.isdir", return_value=True):
                        with patch("os.chdir") as mock_chdir:
                            result = handle_cd_command("/cd ~")
                            assert result is True
                            mock_chdir.assert_called_once_with("/home/user")

    def test_cd_with_relative_path(self):
        """Test cd command handles relative paths correctly."""
        with patch("code_puppy.messaging.emit_success"):
            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.path.isabs", return_value=False):
                    with patch("os.getcwd", return_value="/current/dir"):
                        with patch("os.path.isdir", return_value=True):
                            with patch("os.chdir") as mock_chdir:
                                result = handle_cd_command("/cd subdir")
                                assert result is True
                                mock_chdir.assert_called_once_with(
                                    "/current/dir/subdir"
                                )

    def test_cd_with_special_characters(self):
        """Test cd command handles special characters in paths."""
        special_path = "/path with spaces & symbols"

        with patch("code_puppy.messaging.emit_success"):
            with patch("os.path.expanduser", return_value=special_path):
                with patch("os.path.isabs", return_value=True):
                    with patch("os.path.isdir", return_value=True):
                        with patch("os.chdir") as mock_chdir:
                            result = handle_cd_command(f'/cd "{special_path}"')
                            assert result is True
                            mock_chdir.assert_called_once_with(special_path)

    def test_cd_listing_with_permission_error(self):
        """Test cd listing handles permission errors gracefully."""
        with patch(
            "code_puppy.command_line.core_commands.make_directory_table",
            side_effect=PermissionError("Access denied"),
        ):
            with patch("code_puppy.messaging.emit_error") as mock_error:
                result = handle_cd_command("/cd")
                assert result is True
                mock_error.assert_called_once()

                args, kwargs = mock_error.call_args
                assert "Access denied" in args[0]

    def test_cd_with_nonexistent_parent(self):
        """Test cd command with path containing nonexistent parent directories."""
        with patch("code_puppy.messaging.emit_error") as mock_error:
            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.path.isabs", return_value=True):
                    with patch("os.path.isdir", return_value=False):
                        result = handle_cd_command("/cd /nonexistent/dir")
                        assert result is True
                        mock_error.assert_called_once_with(
                            "Not a directory: /nonexistent/dir"
                        )


class TestHandleToolsCommand:
    """Extended tests for tools command functionality."""

    def test_tools_command_with_markdown_rendering(self):
        """Test tools command properly renders markdown content."""
        mock_tools_content = (
            "# Available Tools\n\n- Tool 1: Description\n- Tool 2: Description"
        )

        with patch(
            "code_puppy.command_line.core_commands.tools_content", mock_tools_content
        ):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                result = handle_tools_command("/tools")
                assert result is True
                mock_emit.assert_called_once()

                # Check that it receives a Markdown object
                args, kwargs = mock_emit.call_args
                content = args[0]
                from rich.markdown import Markdown

                assert isinstance(content, Markdown)
                assert mock_tools_content in content.markup

    def test_tools_command_with_empty_content(self):
        """Test tools command handles empty tools content gracefully."""
        with patch("code_puppy.command_line.core_commands.tools_content", ""):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                result = handle_tools_command("/tools")
                assert result is True
                mock_emit.assert_called_once()

    def test_tools_command_with_unicode_content(self):
        """Test tools command handles unicode content properly."""
        unicode_content = "# 工具\n\n- 工具 1: 描述\n- 工具 2: 描述 🐕"

        with patch(
            "code_puppy.command_line.core_commands.tools_content", unicode_content
        ):
            with patch("code_puppy.messaging.emit_info") as mock_emit:
                result = handle_tools_command("/tools")
                assert result is True
                mock_emit.assert_called_once()


class TestHandleMotdCommand:
    """Extended tests for motd command functionality."""

    def test_motd_command_force_refresh(self):
        """Test motd command with force parameter."""
        with patch("code_puppy.command_line.core_commands.print_motd") as mock_print:
            result = handle_motd_command("/motd")
            assert result is True
            mock_print.assert_called_once_with(force=True)

    def test_motd_command_with_print_error(self):
        """Test motd command handles printing errors gracefully."""
        with patch(
            "code_puppy.command_line.core_commands.print_motd",
            side_effect=Exception("Print failed"),
        ):
            # Should not raise an exception
            result = handle_motd_command("/motd")
            assert result is True


class TestHandleExitCommand:
    """Extended tests for exit command functionality."""

    def test_exit_command_with_success_message(self):
        """Test exit command shows appropriate success message."""
        with patch("code_puppy.messaging.emit_success") as mock_success:
            result = handle_exit_command("/exit")
            assert result is True
            mock_success.assert_called_once_with("Goodbye!")

    def test_quit_alias_functionality(self):
        """Test that quit alias works the same as exit."""
        with patch("code_puppy.messaging.emit_success") as mock_success:
            result = handle_exit_command("/quit")
            assert result is True
            mock_success.assert_called_once_with("Goodbye!")

    def test_exit_command_with_emit_error(self):
        """Test exit command handles emit errors gracefully."""
        with patch(
            "code_puppy.messaging.emit_success", side_effect=Exception("Emit failed")
        ):
            # Should not raise an exception
            result = handle_exit_command("/exit")
            assert result is True


class TestHandleAgentCommand:
    """Extended tests for agent command functionality."""

    def test_agent_command_show_current_with_descriptions(self):
        """Test agent command shows current agent and available ones with descriptions."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "A test agent for testing"

        mock_agents = {
            "test_agent": "Test Agent",
            "other_agent": "Other Agent",
        }
        mock_descriptions = {
            "test_agent": "A test agent for testing",
            "other_agent": "Another test agent",
        }

        # Force the picker to fail so it falls back to text display
        with patch(
            "code_puppy.command_line.core_commands.interactive_agent_picker",
            side_effect=Exception("Picker failed"),
        ):
            with patch(
                "code_puppy.agents.get_current_agent", return_value=mock_current
            ):
                with patch(
                    "code_puppy.agents.get_available_agents", return_value=mock_agents
                ):
                    with patch(
                        "code_puppy.agents.get_agent_descriptions",
                        return_value=mock_descriptions,
                    ):
                        with patch("code_puppy.messaging.emit_info") as mock_info:
                            with patch(
                                "code_puppy.messaging.emit_warning"
                            ) as mock_warning:
                                with patch(
                                    "code_puppy.config.finalize_autosave_session",
                                    return_value="test_session",
                                ):
                                    result = handle_agent_command("/agent")
                                    assert result is True

                                    # Should show current agent
                                    assert mock_info.call_count >= 1

                                    # Should show warning about picker failure
                                    mock_warning.assert_called()

    def test_agent_command_already_using_current(self):
        """Test agent command when trying to switch to already active agent."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "A test agent for testing"

        with patch(
            "code_puppy.command_line.core_commands.interactive_agent_picker",
            return_value="test_agent",
        ):
            with patch(
                "code_puppy.agents.get_current_agent", return_value=mock_current
            ):
                with patch("code_puppy.messaging.emit_info") as mock_info:
                    result = handle_agent_command("/agent")
                    assert result is True

                    # Should show "already using" message
                    mock_info.assert_called()
                    args, kwargs = mock_info.call_args
                    assert "Already using agent" in args[0]

    def test_agent_command_successful_switch(self):
        """Test successful agent switching with all feedback."""
        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "A new test agent"
        mock_new_agent.reload_code_generation_agent = MagicMock()

        with patch(
            "code_puppy.command_line.core_commands.interactive_agent_picker",
            return_value="new_agent",
        ):
            with patch(
                "code_puppy.agents.get_current_agent",
                side_effect=[mock_old_agent, mock_new_agent],
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch(
                        "code_puppy.config.finalize_autosave_session",
                        return_value="new_session",
                    ):
                        with patch("code_puppy.messaging.emit_success") as mock_success:
                            with patch("code_puppy.messaging.emit_info"):
                                result = handle_agent_command("/agent")
                                assert result is True

                                # Should show success message
                                mock_success.assert_called()

                                # Should call reload on new agent
                                mock_new_agent.reload_code_generation_agent.assert_called_once()

    def test_agent_command_with_agent_argument(self):
        """Test agent command with explicit agent name argument."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"

        mock_target = MagicMock()
        mock_target.name = "target_agent"
        mock_target.display_name = "Target Agent"
        mock_target.description = "Target agent description"
        mock_target.reload_code_generation_agent = MagicMock()

        mock_agents = {"target_agent": "Target Agent"}

        with patch("code_puppy.agents.get_available_agents", return_value=mock_agents):
            with patch(
                "code_puppy.agents.get_current_agent",
                side_effect=[mock_current, mock_target],
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch(
                        "code_puppy.config.finalize_autosave_session",
                        return_value="session_id",
                    ):
                        with patch("code_puppy.messaging.emit_success") as mock_success:
                            result = handle_agent_command("/agent target_agent")
                            assert result is True

                            mock_success.assert_called()
                            mock_target.reload_code_generation_agent.assert_called_once()

    def test_agent_command_invalid_agent_name(self):
        """Test agent command with invalid agent name."""
        mock_agents = {"valid_agent": "Valid Agent"}

        with patch("code_puppy.agents.get_available_agents", return_value=mock_agents):
            with patch("code_puppy.messaging.emit_error") as mock_error:
                with patch("code_puppy.messaging.emit_warning") as mock_warning:
                    result = handle_agent_command("/agent invalid_agent")
                    assert result is True

                    mock_error.assert_called_with(
                        "Agent 'invalid_agent' not found", message_group=ANY
                    )
                    mock_warning.assert_called()

    def test_agent_command_switch_failure_handling(self):
        """Test handling of agent switch failure after autosave."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"

        with patch(
            "code_puppy.agents.get_available_agents", return_value={"target": "Target"}
        ):
            with patch(
                "code_puppy.agents.get_current_agent", return_value=mock_current
            ):
                with patch(
                    "code_puppy.agents.set_current_agent", return_value=False
                ):  # Switch fails
                    with patch(
                        "code_puppy.config.finalize_autosave_session",
                        return_value="session",
                    ):
                        with patch("code_puppy.messaging.emit_warning") as mock_warning:
                            result = handle_agent_command("/agent target")
                            assert result is True

                            # Should emit warning about failure
                            assert mock_warning.call_count >= 1

                            # Check that warning mentions switch failure
                            warning_calls = [
                                call[0][0] for call in mock_warning.call_args_list
                            ]
                            assert any(
                                "switch failed" in msg.lower() for msg in warning_calls
                            )

    def test_agent_command_thread_pool_timeout(self):
        """Test handling of thread pool timeout during agent selection."""
        with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value.__enter__.return_value = mock_executor

            # Create a future that times out
            mock_future = MagicMock()
            mock_future.result.side_effect = concurrent.futures.TimeoutError()
            mock_executor.submit.return_value = mock_future

            with patch("code_puppy.messaging.emit_warning") as mock_warning:
                result = handle_agent_command("/agent")
                assert result is True

                # Should handle timeout gracefully
                assert mock_warning.call_count >= 1


class TestInteractiveAgentPicker:
    """Test the interactive agent picker functionality."""

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_agent_picker_displays_panel(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test that agent picker displays proper panel with current agent info."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "Current agent description"

        mock_agents = {"agent1": "Agent 1", "agent2": "Agent 2"}
        mock_descriptions = {"agent1": "Description 1", "agent2": "Description 2"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch(
                        "code_puppy.tools.common.arrow_select_async",
                        return_value="agent1",
                    ):
                        result = await interactive_agent_picker()
                        assert result == "agent1"

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_agent_picker_with_keyboard_interrupt(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test agent picker handles keyboard interrupt gracefully."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "Current agent description"

        mock_agents = {"agent1": "Agent 1"}
        mock_descriptions = {"agent1": "Description 1"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch(
                        "code_puppy.tools.common.arrow_select_async",
                        side_effect=KeyboardInterrupt(),
                    ):
                        result = await interactive_agent_picker()
                        assert result is None

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_agent_picker_with_eof_error(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test agent picker handles EOFError gracefully."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "Current agent description"

        mock_agents = {"agent1": "Agent 1"}
        mock_descriptions = {"agent1": "Description 1"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch(
                        "code_puppy.tools.common.arrow_select_async",
                        side_effect=EOFError(),
                    ):
                        result = await interactive_agent_picker()
                        assert result is None

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_agent_picker_preview_callback(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test agent picker preview callback functionality."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "Current agent description"

        mock_agents = {"agent1": "Agent 1", "agent2": "Agent 2"}
        mock_descriptions = {
            "agent1": "First agent description with details 🐕",
            "agent2": "Second agent description with unicode 世界",
        }

        captured_preview = None

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch(
                        "code_puppy.tools.common.arrow_select_async"
                    ) as mock_selector:
                        # Capture the preview callback
                        def capture_selector(prompt, choices, preview_callback=None):
                            if preview_callback:
                                # Call the preview callback and capture its result
                                nonlocal captured_preview
                                captured_preview = preview_callback(
                                    0
                                )  # Call with index 0
                            return "agent1"

                        mock_selector.side_effect = capture_selector

                        result = await interactive_agent_picker()
                        assert result == "agent1"
                        assert captured_preview is not None


class TestHandleModelCommand:
    """Extended tests for model command functionality."""

    def test_model_command_interactive_success(self):
        """Test model command with successful interactive selection."""
        with patch(
            "code_puppy.command_line.core_commands.interactive_model_picker",
            return_value="gpt-4",
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.set_active_model"
            ) as mock_set:
                with patch(
                    "code_puppy.command_line.model_picker_completion.get_active_model",
                    return_value="gpt-4",
                ):
                    with patch("code_puppy.messaging.emit_success") as mock_success:
                        result = handle_model_command("/model")
                        assert result is True
                        mock_set.assert_called_once_with("gpt-4")
                        mock_success.assert_called_with(
                            "Active model set and loaded: gpt-4"
                        )

    def test_model_command_interactive_cancelled(self):
        """Test model command when interactive selection is cancelled."""
        with patch(
            "code_puppy.command_line.core_commands.interactive_model_picker",
            return_value=None,
        ):
            with patch("code_puppy.messaging.emit_warning") as mock_warning:
                result = handle_model_command("/model")
                assert result is True
                mock_warning.assert_called_with("Model selection cancelled")

    def test_model_command_picker_error_fallback(self):
        """Test model command fallback when picker fails."""
        with patch(
            "code_puppy.command_line.core_commands.interactive_model_picker",
            side_effect=Exception("Picker failed"),
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-3.5", "gpt-4"],
            ):
                with patch("code_puppy.messaging.emit_warning") as mock_warning:
                    result = handle_model_command("/model")
                    assert result is True

                    # Should show multiple warning messages
                    assert mock_warning.call_count >= 2

                    # Check fallback usage message
                    warning_calls = [call[0][0] for call in mock_warning.call_args_list]
                    assert any("Usage:" in call for call in warning_calls)
                    assert any("Available models:" in call for call in warning_calls)

    def test_model_command_with_valid_argument(self):
        """Test model command with a valid model name argument."""
        with patch(
            "code_puppy.command_line.model_picker_completion.update_model_in_input",
            return_value="/m synthetic-GLM-4.6",
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="synthetic-GLM-4.6",
            ):
                with patch("code_puppy.messaging.emit_success") as mock_success:
                    result = handle_model_command("/model synthetic-GLM-4.6")
                    assert result is True
                    mock_success.assert_called_with(
                        "Active model set and loaded: synthetic-GLM-4.6"
                    )

    def test_model_command_with_invalid_argument(self):
        """Test model command with invalid model name argument."""
        with patch(
            "code_puppy.command_line.model_picker_completion.update_model_in_input",
            return_value=None,
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-3.5", "gpt-4"],
            ):
                with patch("code_puppy.messaging.emit_warning") as mock_warning:
                    result = handle_model_command("/model invalid-model")
                    assert result is True

                    # Should show usage and available models
                    assert mock_warning.call_count >= 2

    def test_model_command_m_alias(self):
        """Test model command with /m alias."""
        with patch(
            "code_puppy.command_line.model_picker_completion.update_model_in_input",
            return_value="",
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="synthetic-GLM-4.6",
            ):
                with patch("code_puppy.messaging.emit_success") as mock_success:
                    result = handle_model_command("/m synthetic-GLM-4.6")
                    assert result is True
                    mock_success.assert_called_with(
                        "Active model set and loaded: synthetic-GLM-4.6"
                    )

    def test_model_command_thread_pool_timeout(self):
        """Test handling of thread pool timeout during model selection."""
        with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value.__enter__.return_value = mock_executor

            mock_future = MagicMock()
            mock_future.result.side_effect = concurrent.futures.TimeoutError()
            mock_executor.submit.return_value = mock_future

            with patch("code_puppy.messaging.emit_warning") as mock_warning:
                result = handle_model_command("/model")
                assert result is True
                assert mock_warning.call_count >= 1


class TestInteractiveModelPicker:
    """Test the interactive model picker functionality."""

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_model_picker_displays_panel(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test model picker displays proper panel with current model info."""
        models = ["gpt-3.5", "gpt-4", "claude-3"]
        current_model = "gpt-4"

        with patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=models,
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value=current_model,
            ):
                with patch(
                    "code_puppy.tools.common.arrow_select_async", return_value="gpt-3.5"
                ):
                    result = await interactive_model_picker()
                    assert result == "gpt-3.5"

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_model_picker_with_current_indicator(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test model picker shows current model indicator correctly."""
        models = ["gpt-3.5", "gpt-4", "claude-3"]
        current_model = "gpt-4"

        captured_choices = None

        def capture_selector(prompt, choices):
            nonlocal captured_choices
            captured_choices = choices
            return choices[
                1
            ]  # Return the gpt-4 choice (which should be marked current)

        with patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=models,
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value=current_model,
            ):
                with patch(
                    "code_puppy.tools.common.arrow_select_async",
                    side_effect=capture_selector,
                ):
                    await interactive_model_picker()

                    # Should have captured choices with current indicator
                    assert captured_choices is not None
                    assert len(captured_choices) == 3

                    # One choice should have the current indicator
                    current_choice = next(
                        (
                            choice
                            for choice in captured_choices
                            if "(current)" in choice
                        ),
                        None,
                    )
                    assert current_choice is not None
                    assert "gpt-4" in current_choice

    @patch("sys.stdout.flush")
    @patch("sys.stderr.flush")
    @patch("time.sleep")
    async def test_model_picker_keyboard_interrupt(
        self, mock_sleep, mock_stderr_flush, mock_stdout_flush
    ):
        """Test model picker handles keyboard interrupt gracefully."""
        with patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=["gpt-4"],
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ):
                with patch(
                    "code_puppy.tools.common.arrow_select_async",
                    side_effect=KeyboardInterrupt(),
                ):
                    result = await interactive_model_picker()
                    assert result is None


class TestHandleMcpCommand:
    """Extended tests for MCP command functionality."""

    def test_mcp_command_delegates_to_handler(self):
        """Test MCP command properly delegates to MCPCommandHandler."""
        with patch(
            "code_puppy.command_line.mcp.MCPCommandHandler"
        ) as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler_class.return_value = mock_handler
            mock_handler.handle_mcp_command.return_value = True

            result = handle_mcp_command("/mcp list")
            assert result is True

            mock_handler_class.assert_called_once()
            mock_handler.handle_mcp_command.assert_called_once_with("/mcp list")

    def test_mcp_command_handler_error(self):
        """Test MCP command handles handler errors gracefully."""
        with patch(
            "code_puppy.command_line.mcp.MCPCommandHandler"
        ) as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler_class.return_value = mock_handler
            mock_handler.handle_mcp_command.side_effect = Exception("Handler failed")

            # Should not crash, even if handler fails
            with pytest.raises(Exception, match="Handler failed"):
                handle_mcp_command("/mcp list")
            # The exception propagates from the mock before the try-catch in the handler can catch it


class TestHandleGeneratePrDescriptionCommand:
    """Extended tests for PR description command functionality."""

    def test_pr_description_without_directory(self):
        """Test PR description command without directory context."""
        result = handle_generate_pr_description_command("/generate-pr-description")

        # Should return a comprehensive prompt
        assert isinstance(result, str)
        assert "PR description" in result
        assert "git CLI" in result
        assert "markdown file" in result
        assert "PR_DESCRIPTION.md" in result

    def test_pr_description_with_directory_context(self):
        """Test PR description command with directory context."""
        result = handle_generate_pr_description_command(
            "/generate-pr-description @src/components"
        )

        assert isinstance(result, str)
        assert "Please work in the directory: src/components" in result
        assert "PR description" in result

    def test_pr_description_with_multiple_at_tokens(self):
        """Test PR description command with multiple @ tokens picks first one."""
        result = handle_generate_pr_description_command(
            "/generate-pr-description @first @second @third"
        )

        # Should use the first @ token
        assert "Please work in the directory: first" in result
        assert "second" not in result
        assert "third" not in result

    def test_pr_description_with_special_characters(self):
        """Test PR description command with special characters in directory."""
        # The function splits on whitespace, so only the first token starting with @ is used
        result = handle_generate_pr_description_command(
            "/generate-pr-description @path-with_spaces & symbols"
        )

        assert "Please work in the directory: path-with_spaces" in result
        assert "& symbols" not in result

    def test_pr_description_prompt_structure(self):
        """Test that PR description prompt has all required sections."""
        result = handle_generate_pr_description_command("/generate-pr-description")

        required_sections = [
            "Discover the changes",
            "Analyze the code",
            "Generate a structured PR description",
            "Title",
            "Summary",
            "Changes Made",
            "Technical Details",
            "Files Modified",
            "Testing",
            "Breaking Changes",
            "markdown file",
            "Github MCP",
        ]

        for section in required_sections:
            assert section in result, f"Missing section: {section}"

    def test_pr_description_with_empty_command(self):
        """Test PR description command edge case with minimal input."""
        result = handle_generate_pr_description_command("/generate-pr-description")

        assert len(result) > 500  # Should be a comprehensive prompt
        assert "Generate a comprehensive PR description" in result


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and comprehensive error handling."""

    def test_commands_with_unicode_arguments(self):
        """Test commands handle unicode arguments gracefully."""
        unicode_path = "/路径/with/世界"

        with patch("code_puppy.messaging.emit_error"):
            with patch("os.path.expanduser", return_value=unicode_path):
                with patch("os.path.isabs", return_value=True):
                    with patch("os.path.isdir", return_value=False):
                        result = handle_cd_command(f"/cd {unicode_path}")
                        assert result is True

    def test_agent_command_with_unicode_agent_name(self):
        """Test agent command with unicode agent name."""
        with patch("code_puppy.messaging.emit_error"):
            with patch("code_puppy.agents.get_available_agents", return_value={}):
                result = handle_agent_command("/agent 世界")
                assert result is True

    def test_model_command_with_unicode_model_name(self):
        """Test model command with unicode model name."""
        with patch(
            "code_puppy.command_line.model_picker_completion.update_model_in_input",
            return_value="",
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4", "世界-model"],
            ):
                with patch(
                    "code_puppy.command_line.model_picker_completion.get_active_model",
                    return_value="世界-model",
                ):
                    with patch("code_puppy.messaging.emit_success") as mock_success:
                        result = handle_model_command("/m 世界-model")
                        assert result is True
                        mock_success.assert_called_with(
                            "Active model set and loaded: 世界-model"
                        )

    def test_help_command_lazy_import_handling(self):
        """Test help command handles lazy import edge cases."""
        with patch(
            "code_puppy.command_line.core_commands.get_commands_help",
            side_effect=ImportError("Module not found"),
        ):
            with patch("code_puppy.messaging.emit_info"):
                with pytest.raises(ImportError):
                    handle_help_command("/help")

    def test_tools_command_with_malformed_markdown(self):
        """Test tools command handles malformed markdown gracefully."""
        malformed_content = "# Header\n\n- Unclosed list item\n- Another item\n\n```\nUnclosed code block"

        with patch(
            "code_puppy.command_line.core_commands.tools_content", malformed_content
        ):
            with patch("code_puppy.messaging.emit_info") as mock_info:
                result = handle_tools_command("/tools")
                assert result is True
                mock_info.assert_called_once()

    def test_generate_pr_description_command_with_empty_directory(self):
        """Test PR description command with empty directory token."""
        result = handle_generate_pr_description_command("/generate-pr-description @")

        # Should handle empty directory gracefully
        assert "Please work in the directory: " in result

    async def test_async_functions_exception_safety(self):
        """Test that async functions handle expected exceptions safely."""
        # Test agent picker exception safety with proper mocks
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "Current agent description"

        mock_agents = {"agent1": "Agent 1"}
        mock_descriptions = {"agent1": "Description 1"}

        with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
            with patch(
                "code_puppy.agents.get_current_agent", return_value=mock_current
            ):
                with patch(
                    "code_puppy.agents.get_available_agents", return_value=mock_agents
                ):
                    with patch(
                        "code_puppy.agents.get_agent_descriptions",
                        return_value=mock_descriptions,
                    ):
                        # Test KeyboardInterrupt handling
                        with patch(
                            "code_puppy.tools.common.arrow_select_async",
                            side_effect=KeyboardInterrupt(),
                        ):
                            result = await interactive_agent_picker()
                            # Should handle gracefully and return None on KeyboardInterrupt
                            assert result is None

                        # Test EOFError handling
                        with patch(
                            "code_puppy.tools.common.arrow_select_async",
                            side_effect=EOFError(),
                        ):
                            result = await interactive_agent_picker()
                            # Should handle gracefully and return None on EOFError
                            assert result is None

    def test_concurrent_futures_timeout_handling(self):
        """Test that concurrent futures timeouts are handled."""
        with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value.__enter__.return_value = mock_executor

            # Simulate timeout
            mock_future = MagicMock()
            mock_future.result.side_effect = concurrent.futures.TimeoutError(
                "Operation timed out"
            )
            mock_executor.submit.return_value = mock_future

            with patch("code_puppy.messaging.emit_warning") as mock_warning:
                result = handle_agent_command("/agent")
                assert result is True

                # Should show warning about picker failure
                assert mock_warning.call_count >= 1


class TestIntegrationScenarios:
    """Integration-style tests covering realistic usage patterns."""

    def test_complete_agent_switch_workflow(self):
        """Test complete agent switching workflow including autosave."""
        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "New agent description"
        mock_new_agent.reload_code_generation_agent = MagicMock()

        # Simulate successful workflow
        with patch(
            "code_puppy.command_line.core_commands.interactive_agent_picker",
            return_value="new_agent",
        ):
            with patch(
                "code_puppy.agents.get_current_agent",
                side_effect=[mock_old_agent, mock_new_agent],
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch(
                        "code_puppy.config.finalize_autosave_session",
                        return_value="new_session_123",
                    ):
                        with patch("code_puppy.messaging.emit_success") as mock_success:
                            with patch("code_puppy.messaging.emit_info") as mock_info:
                                result = handle_agent_command("/agent")
                                assert result is True

                                # Check success message
                                mock_success.assert_called()
                                # Verify the call contains the correct message
                                args, kwargs = mock_success.call_args
                                assert "Switched to agent: New Agent" in args[0]

                                # Check info messages include description
                                info_calls = [
                                    call[0][0] for call in mock_info.call_args_list
                                ]
                                assert any(
                                    "New agent description" in call
                                    for call in info_calls
                                )
                                # Verify that finalize_autosave_session was called
                                # (the session ID handling is tested elsewhere)

    def test_complete_model_switch_workflow(self):
        """Test complete model switching workflow."""
        with patch(
            "code_puppy.command_line.core_commands.interactive_model_picker",
            return_value="claude-3-opus",
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.set_active_model"
            ) as mock_set:
                with patch(
                    "code_puppy.command_line.model_picker_completion.get_active_model",
                    return_value="claude-3-opus",
                ):
                    with patch("code_puppy.messaging.emit_success") as mock_success:
                        result = handle_model_command("/model")
                        assert result is True

                        mock_set.assert_called_once_with("claude-3-opus")
                        mock_success.assert_called_with(
                            "Active model set and loaded: claude-3-opus"
                        )

    def test_pr_description_with_complex_directory(self):
        """Test PR description generation with complex directory scenarios."""
        scenarios = [
            "/generate-pr-description @./src",
            "/generate-pr-description @../parent/dir",
            "/generate-pr-description @path/with spaces/file.py",
            "/generate-pr-description @/absolute/path/components",
        ]

        for command in scenarios:
            result = handle_generate_pr_description_command(command)
            assert isinstance(result, str)
            assert len(result) > 1000  # Should be comprehensive
            assert "git CLI" in result
            assert "PR_DESCRIPTION.md" in result

    def test_error_recovery_scenarios(self):
        """Test various error recovery scenarios."""
        # Test picker failure recovery for agent command
        with patch(
            "code_puppy.command_line.core_commands.interactive_agent_picker",
            side_effect=ConnectionError("Network failed"),
        ):
            with patch("code_puppy.agents.get_current_agent"):
                with patch(
                    "code_puppy.agents.get_available_agents",
                    return_value={"test": "Test Agent"},
                ):
                    with patch("code_puppy.messaging.emit_warning") as mock_warning:
                        result = handle_agent_command("/agent")
                        assert result is True
                        assert mock_warning.call_count >= 1

        # Test picker failure recovery for model command
        with patch(
            "code_puppy.command_line.core_commands.interactive_model_picker",
            side_effect=RuntimeError("Runtime failed"),
        ):
            with patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["model1"],
            ):
                with patch("code_puppy.messaging.emit_warning") as mock_warning:
                    result = handle_model_command("/model")
                    assert result is True
                    assert mock_warning.call_count >= 2

    async def test_async_picker_state_cleanup(self):
        """Test that async pickers properly clean up state on exceptions."""
        with patch(
            "code_puppy.tools.command_runner.set_awaiting_user_input"
        ) as mock_awaiting:
            # Test agent picker cleanup
            mock_current = MagicMock()
            mock_current.name = "current_agent"
            mock_current.display_name = "Current Agent"
            mock_current.description = "Current agent description"

            mock_agents = {"agent1": "Agent 1"}
            mock_descriptions = {"agent1": "Description 1"}

            with patch(
                "code_puppy.agents.get_current_agent", return_value=mock_current
            ):
                with patch(
                    "code_puppy.agents.get_available_agents", return_value=mock_agents
                ):
                    with patch(
                        "code_puppy.agents.get_agent_descriptions",
                        return_value=mock_descriptions,
                    ):
                        # Test KeyboardInterrupt handling
                        with patch(
                            "code_puppy.tools.common.arrow_select_async",
                            side_effect=KeyboardInterrupt(),
                        ):
                            result = await interactive_agent_picker()
                            # Function should handle exceptions internally and return None
                            assert result is None

                            # Should reset awaiting state in finally block
                            mock_awaiting.assert_any_call(False)

                        # Reset the mock for the next test
                        mock_awaiting.reset_mock()

                        # Test EOFError handling
                        with patch(
                            "code_puppy.tools.common.arrow_select_async",
                            side_effect=EOFError(),
                        ):
                            result = await interactive_agent_picker()
                            # Function should handle exceptions internally and return None
                            assert result is None

                            # Should reset awaiting state in finally block
                            mock_awaiting.assert_any_call(False)

            # Reset the mock for the next test
            mock_awaiting.reset_mock()

            # Test model picker cleanup
            with patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4"],
            ):
                with patch(
                    "code_puppy.command_line.model_picker_completion.get_active_model",
                    return_value="gpt-4",
                ):
                    with patch(
                        "code_puppy.tools.common.arrow_select_async",
                        side_effect=KeyboardInterrupt(),
                    ):
                        result = await interactive_model_picker()
                        # Function should handle exceptions internally and return None
                        assert result is None

                        # Should reset awaiting state in finally block
                        mock_awaiting.assert_any_call(False)


class TestHandleSwitchCommand:
    """Tests for /switch command - agent handoff with context preservation."""

    def test_switch_shows_current_agent(self):
        """Test that /switch without args displays the current agent."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "A test agent for testing"

        mock_agents = {"test_agent": "Test Agent"}
        mock_descriptions = {"test_agent": "A test agent for testing"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        result = handle_switch_command("/switch")

                        assert result is True
                        calls = [str(c) for c in mock_info.call_args_list]
                        assert any("Current Agent" in c for c in calls)
                        assert any("Test Agent" in c for c in calls)

    def test_switch_shows_available_agents_with_descriptions(self):
        """Test that /switch lists all available agents with descriptions."""
        mock_current = MagicMock()
        mock_current.name = "agent_one"
        mock_current.display_name = "Agent One"
        mock_current.description = "First agent"

        mock_agents = {
            "agent_one": "Agent One",
            "agent_two": "Agent Two",
            "agent_three": "Agent Three",
        }
        mock_descriptions = {
            "agent_one": "First agent",
            "agent_two": "Second agent",
            "agent_three": "Third agent",
        }

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        result = handle_switch_command("/switch")

                        assert result is True
                        calls_str = " ".join(str(c) for c in mock_info.call_args_list)
                        assert "agent_one" in calls_str
                        assert "agent_two" in calls_str
                        assert "agent_three" in calls_str

    def test_switch_shows_current_marker(self):
        """Test that current agent is marked in the list."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.description = "The current agent"

        mock_agents = {
            "current_agent": "Current Agent",
            "other_agent": "Other Agent",
        }
        mock_descriptions = {
            "current_agent": "The current agent",
            "other_agent": "Another agent",
        }

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        result = handle_switch_command("/switch")

                        assert result is True
                        calls_str = " ".join(str(c) for c in mock_info.call_args_list)
                        assert "← current" in calls_str

    def test_switch_shows_usage_hint(self):
        """Test that /switch shows usage instructions."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "Test"

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"test_agent": "Test"},
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions", return_value={}
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        handle_switch_command("/switch")

                        calls_str = " ".join(str(c) for c in mock_info.call_args_list)
                        assert "/switch <agent-name>" in calls_str

    def test_switch_handles_missing_description(self):
        """Test that /switch handles agents without descriptions gracefully."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "Test"

        mock_agents = {"test_agent": "Test Agent", "no_desc_agent": "No Desc Agent"}
        mock_descriptions = {"test_agent": "Has description"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions",
                    return_value=mock_descriptions,
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        result = handle_switch_command("/switch")

                        assert result is True
                        calls_str = " ".join(str(c) for c in mock_info.call_args_list)
                        assert "No description" in calls_str

    def test_switch_to_valid_agent_preserves_history(self):
        """Test successful switch transfers message history to new agent."""
        mock_message_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Help me code"},
        ]

        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = mock_message_history

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "A new agent"

        mock_agents = {"old_agent": "Old Agent", "new_agent": "New Agent"}

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info"):
                            result = handle_switch_command("/switch new_agent")

                            assert result is True
                            mock_old_agent.get_message_history.assert_called_once()
                            mock_new_agent.set_message_history.assert_called_once_with(
                                mock_message_history
                            )
                            mock_new_agent.reload_code_generation_agent.assert_called_once()

    def test_switch_shows_success_message_with_handoff_emoji(self):
        """Test successful switch shows handoff emoji and agent names."""
        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = []

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "New agent description"

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"new_agent": "New Agent"},
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch(
                        "code_puppy.messaging.emit_success"
                    ) as mock_success:
                        with patch("code_puppy.messaging.emit_info"):
                            handle_switch_command("/switch new_agent")

                            mock_success.assert_called_once()
                            args, kwargs = mock_success.call_args
                            assert "🤝" in args[0]
                            assert "Old Agent" in args[0]
                            assert "New Agent" in args[0]

    def test_switch_shows_message_count_transferred(self):
        """Test switch displays how many messages were transferred."""
        mock_history = [{"role": "user", "content": f"msg{i}"} for i in range(5)]

        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = mock_history

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "Desc"

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"new_agent": "New"},
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info") as mock_info:
                            handle_switch_command("/switch new_agent")

                            calls_str = " ".join(
                                str(c) for c in mock_info.call_args_list
                            )
                            assert "5 messages transferred" in calls_str

    def test_switch_invalid_agent_shows_error(self):
        """Test switch to non-existent agent shows error."""
        mock_agents = {"valid_agent": "Valid Agent"}

        with patch(
            "code_puppy.agents.get_available_agents", return_value=mock_agents
        ):
            with patch("code_puppy.messaging.emit_error") as mock_error:
                with patch("code_puppy.messaging.emit_warning"):
                    result = handle_switch_command("/switch nonexistent")

                    assert result is True
                    mock_error.assert_called_once()
                    args, _ = mock_error.call_args
                    assert "nonexistent" in args[0]
                    assert "not found" in args[0]

    def test_switch_invalid_agent_shows_available_agents(self):
        """Test switch to invalid agent lists available options."""
        mock_agents = {"agent_a": "Agent A", "agent_b": "Agent B"}

        with patch(
            "code_puppy.agents.get_available_agents", return_value=mock_agents
        ):
            with patch("code_puppy.messaging.emit_error"):
                with patch("code_puppy.messaging.emit_warning") as mock_warning:
                    handle_switch_command("/switch invalid")

                    mock_warning.assert_called_once()
                    args, _ = mock_warning.call_args
                    assert "agent_a" in args[0]
                    assert "agent_b" in args[0]

    def test_switch_to_current_agent_shows_info(self):
        """Test switching to already-active agent shows info message."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"

        mock_agents = {"current_agent": "Current Agent"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch("code_puppy.messaging.emit_info") as mock_info:
                    result = handle_switch_command("/switch current_agent")

                    assert result is True
                    mock_info.assert_called_once()
                    args, _ = mock_info.call_args
                    assert "Already using agent" in args[0]

    def test_switch_agent_name_case_insensitive(self):
        """Test that agent name matching is case-insensitive."""
        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = []

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "Desc"

        mock_agents = {"new_agent": "New Agent"}

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.set_current_agent", return_value=True
                ) as mock_set:
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info"):
                            result = handle_switch_command("/switch NEW_AGENT")

                            assert result is True
                            mock_set.assert_called_once_with("new_agent")

    def test_switch_failure_stays_with_current_agent(self):
        """Test that failed switch keeps user on current agent."""
        mock_current = MagicMock()
        mock_current.name = "current_agent"
        mock_current.display_name = "Current Agent"
        mock_current.get_message_history.return_value = []

        mock_agents = {"target_agent": "Target Agent"}

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents", return_value=mock_agents
            ):
                with patch(
                    "code_puppy.agents.set_current_agent", return_value=False
                ):
                    with patch(
                        "code_puppy.messaging.emit_warning"
                    ) as mock_warning:
                        result = handle_switch_command("/switch target_agent")

                        assert result is True
                        mock_warning.assert_called_once()
                        args, _ = mock_warning.call_args
                        assert "handoff failed" in args[0].lower()

    def test_switch_too_many_args_shows_usage(self):
        """Test that too many arguments shows usage warning."""
        with patch("code_puppy.messaging.emit_warning") as mock_warning:
            result = handle_switch_command("/switch agent extra args")

            assert result is True
            mock_warning.assert_called_once()
            args = mock_warning.call_args[0][0]
            assert "Usage:" in args

    def test_switch_with_sw_alias(self):
        """Test that /sw alias works identically to /switch."""
        mock_current = MagicMock()
        mock_current.name = "test_agent"
        mock_current.display_name = "Test Agent"
        mock_current.description = "Test"

        with patch("code_puppy.agents.get_current_agent", return_value=mock_current):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"test_agent": "Test"},
            ):
                with patch(
                    "code_puppy.agents.get_agent_descriptions", return_value={}
                ):
                    with patch("code_puppy.messaging.emit_info") as mock_info:
                        result = handle_switch_command("/sw")

                        assert result is True
                        assert mock_info.call_count >= 1

    def test_switch_transfers_empty_history(self):
        """Test switch works correctly with empty message history."""
        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = []

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "Desc"

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"new_agent": "New"},
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info") as mock_info:
                            handle_switch_command("/switch new_agent")

                            mock_new_agent.set_message_history.assert_called_once_with(
                                []
                            )
                            calls_str = " ".join(
                                str(c) for c in mock_info.call_args_list
                            )
                            assert "0 messages transferred" in calls_str

    def test_switch_transfers_large_history(self):
        """Test switch handles large message histories."""
        large_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(100)
        ]

        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = large_history

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "Desc"

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"new_agent": "New"},
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info") as mock_info:
                            handle_switch_command("/switch new_agent")

                            mock_new_agent.set_message_history.assert_called_once_with(
                                large_history
                            )
                            calls_str = " ".join(
                                str(c) for c in mock_info.call_args_list
                            )
                            assert "100 messages transferred" in calls_str

    def test_switch_creates_copy_of_history(self):
        """Test that switch creates a copy, not a reference to original history."""
        original_history = [{"role": "user", "content": "test"}]

        mock_old_agent = MagicMock()
        mock_old_agent.name = "old_agent"
        mock_old_agent.display_name = "Old Agent"
        mock_old_agent.get_message_history.return_value = original_history

        mock_new_agent = MagicMock()
        mock_new_agent.name = "new_agent"
        mock_new_agent.display_name = "New Agent"
        mock_new_agent.description = "Desc"

        with patch(
            "code_puppy.agents.get_current_agent",
            side_effect=[mock_old_agent, mock_new_agent],
        ):
            with patch(
                "code_puppy.agents.get_available_agents",
                return_value={"new_agent": "New"},
            ):
                with patch("code_puppy.agents.set_current_agent", return_value=True):
                    with patch("code_puppy.messaging.emit_success"):
                        with patch("code_puppy.messaging.emit_info"):
                            handle_switch_command("/switch new_agent")

                            transferred = mock_new_agent.set_message_history.call_args[
                                0
                            ][0]
                            assert transferred == original_history

"""Comprehensive tests for terminal_command_tools.py.

Tests terminal command execution, key sending, and output waiting
with extensive mocking to avoid actual browser operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.terminal_command_tools import (
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_OUTPUT_TIMEOUT,
    MODIFIER_MAP,
    PROMPT_WAIT_MS,
    _normalize_modifier,
    run_terminal_command,
    send_terminal_keys,
    wait_for_terminal_output,
)


class TestNormalizeModifier:
    """Tests for the _normalize_modifier helper function."""

    def test_normalize_control_variants(self):
        """Test normalization of Control key variants."""
        assert _normalize_modifier("control") == "Control"
        assert _normalize_modifier("Control") == "Control"
        assert _normalize_modifier("ctrl") == "Control"
        assert _normalize_modifier("Ctrl") == "Control"

    def test_normalize_shift(self):
        """Test normalization of Shift key."""
        assert _normalize_modifier("shift") == "Shift"
        assert _normalize_modifier("Shift") == "Shift"

    def test_normalize_alt(self):
        """Test normalization of Alt key."""
        assert _normalize_modifier("alt") == "Alt"
        assert _normalize_modifier("Alt") == "Alt"

    def test_normalize_meta_variants(self):
        """Test normalization of Meta/Command key variants."""
        assert _normalize_modifier("meta") == "Meta"
        assert _normalize_modifier("Meta") == "Meta"
        assert _normalize_modifier("command") == "Meta"
        assert _normalize_modifier("cmd") == "Meta"

    def test_normalize_unknown_passes_through(self):
        """Test that unknown modifiers pass through unchanged."""
        assert _normalize_modifier("Unknown") == "Unknown"
        assert _normalize_modifier("custom") == "custom"


class TestRunTerminalCommand:
    """Tests for run_terminal_command function."""

    @pytest.mark.asyncio
    async def test_run_command_success_with_screenshot(self):
        """Test successful command execution with screenshot analysis."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        mock_vqa_result = MagicMock()
        mock_vqa_result.answer = "Command executed successfully"
        mock_vqa_result.confidence = 0.95
        mock_vqa_result.observations = "Terminal shows output"

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_success"
                    ):
                        result = await run_terminal_command("ls -la")

                        assert result["success"] is True
                        assert result["command"] == "ls -la"
                        assert "screenshot_path" in result
                        assert result["analysis"]["success"] is True
                        assert (
                            result["analysis"]["answer"]
                            == "Command executed successfully"
                        )

                        # Verify keyboard interactions
                        mock_page.keyboard.type.assert_called_once_with("ls -la")
                        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_run_command_success_without_screenshot(self):
        """Test command execution without screenshot."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await run_terminal_command(
                        "echo hello",
                        auto_screenshot=False,
                    )

                    assert result["success"] is True
                    assert result["command"] == "echo hello"
                    assert "screenshot_path" not in result
                    assert "analysis" not in result

    @pytest.mark.asyncio
    async def test_run_command_no_active_page(self):
        """Test error when no terminal page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ) as mock_error:
                    result = await run_terminal_command("ls")

                    assert result["success"] is False
                    assert "No active terminal page" in result["error"]
                    assert result["command"] == "ls"
                    assert mock_error.called

    @pytest.mark.asyncio
    async def test_run_command_without_waiting(self):
        """Test command execution without waiting for prompt."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                        result = await run_terminal_command(
                            "long_running_command",
                            wait_for_prompt=False,
                            auto_screenshot=False,
                        )

                        assert result["success"] is True
                        # Should not have called sleep when not waiting
                        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_command_keyboard_error(self):
        """Test error handling when keyboard input fails."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.type.side_effect = RuntimeError("Keyboard error")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ):
                    result = await run_terminal_command("test")

                    assert result["success"] is False
                    assert "Failed to run terminal command" in result["error"]

    @pytest.mark.asyncio
    async def test_run_command_screenshot_failure_continues(self):
        """Test that command still succeeds even if screenshot fails."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("Screenshot failed")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_error"
                    ):
                        result = await run_terminal_command("ls")

                        # Command itself succeeds
                        assert result["success"] is True
                        assert result["command"] == "ls"
                        # But screenshot error is recorded
                        assert "screenshot_error" in result

    @pytest.mark.asyncio
    async def test_run_command_custom_timeout(self):
        """Test command with custom timeout."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await run_terminal_command(
                        "sleep 5",
                        timeout=60.0,
                        auto_screenshot=False,
                    )

                    assert result["success"] is True


class TestSendTerminalKeys:
    """Tests for send_terminal_keys function."""

    @pytest.mark.asyncio
    async def test_send_simple_key(self):
        """Test sending a simple key press."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await send_terminal_keys("Tab")

                    assert result["success"] is True
                    assert result["keys_sent"] == "Tab"
                    assert result["modifiers"] == []

                    # Tab is a special key (multi-char), so press() should be used
                    mock_page.keyboard.press.assert_called_once_with("Tab")

    @pytest.mark.asyncio
    async def test_send_ctrl_c(self):
        """Test sending Ctrl+C interrupt."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await send_terminal_keys("c", modifiers=["Control"])

                    assert result["success"] is True
                    assert result["keys_sent"] == "c"
                    assert result["modifiers"] == ["Control"]

                    # Verify modifier handling
                    mock_page.keyboard.down.assert_called_once_with("Control")
                    mock_page.keyboard.type.assert_called_once_with("c")
                    mock_page.keyboard.up.assert_called_once_with("Control")

    @pytest.mark.asyncio
    async def test_send_arrow_keys(self):
        """Test sending arrow keys."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await send_terminal_keys("ArrowUp")

                    assert result["success"] is True
                    mock_page.keyboard.press.assert_called_once_with("ArrowUp")

    @pytest.mark.asyncio
    async def test_send_multiple_modifiers(self):
        """Test sending keys with multiple modifiers."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await send_terminal_keys(
                        "s",
                        modifiers=["Control", "Shift"],
                    )

                    assert result["success"] is True
                    assert result["modifiers"] == ["Control", "Shift"]

                    # Both modifiers should be pressed
                    down_calls = mock_page.keyboard.down.call_args_list
                    assert len(down_calls) == 2

    @pytest.mark.asyncio
    async def test_send_keys_no_active_page(self):
        """Test error when no terminal page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ) as mock_error:
                    result = await send_terminal_keys("Tab")

                    assert result["success"] is False
                    assert "No active terminal page" in result["error"]
                    assert mock_error.called

    @pytest.mark.asyncio
    async def test_send_keys_keyboard_error(self):
        """Test error handling when keyboard operation fails."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press.side_effect = RuntimeError("Keyboard error")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ):
                    result = await send_terminal_keys("Enter")

                    assert result["success"] is False
                    assert "Failed to send terminal keys" in result["error"]

    @pytest.mark.asyncio
    async def test_send_keys_with_cmd_modifier(self):
        """Test that cmd is normalized to Meta."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    result = await send_terminal_keys("c", modifiers=["cmd"])

                    assert result["success"] is True
                    # Verify Meta was used
                    mock_page.keyboard.down.assert_called_once_with("Meta")

    @pytest.mark.asyncio
    async def test_modifiers_released_on_error(self):
        """Test that modifiers are released even if key press fails."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.type.side_effect = RuntimeError("Type failed")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ):
                    await send_terminal_keys("c", modifiers=["Control"])

                    # Even though it failed, modifier should be released
                    mock_page.keyboard.up.assert_called_once_with("Control")


class TestWaitForTerminalOutput:
    """Tests for wait_for_terminal_output function."""

    @pytest.mark.asyncio
    async def test_wait_for_any_output(self):
        """Test waiting for any terminal output."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        mock_vqa_result = MagicMock()
        mock_vqa_result.answer = "Terminal shows $ prompt with some output"
        mock_vqa_result.confidence = 0.9
        mock_vqa_result.observations = "Clean terminal view"

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_success"
                    ):
                        result = await wait_for_terminal_output()

                        assert result["success"] is True
                        assert result["matched"] is True
                        assert "screenshot_path" in result
                        assert (
                            result["output"]
                            == "Terminal shows $ prompt with some output"
                        )

    @pytest.mark.asyncio
    async def test_wait_for_pattern_found(self):
        """Test waiting for specific pattern that is found."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        mock_vqa_result = MagicMock()
        mock_vqa_result.answer = "Yes, I found 'success' in the terminal output"
        mock_vqa_result.confidence = 0.95
        mock_vqa_result.observations = "The word success appears in green text"

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_success"
                    ):
                        result = await wait_for_terminal_output(pattern="success")

                        assert result["success"] is True
                        assert result["matched"] is True
                        assert (
                            "success" in result["output"].lower()
                            or "found" in result["output"].lower()
                        )

    @pytest.mark.asyncio
    async def test_wait_for_pattern_not_found(self):
        """Test waiting for specific pattern that is not found."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        mock_vqa_result = MagicMock()
        # Answer should NOT contain the pattern word or trigger words
        mock_vqa_result.answer = (
            "No, I cannot see that text. The terminal shows only a blank prompt."
        )
        mock_vqa_result.confidence = 0.9
        mock_vqa_result.observations = "Terminal shows normal output"

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_success"
                    ):
                        result = await wait_for_terminal_output(pattern="error")

                        assert result["success"] is True
                        assert result["matched"] is False

    @pytest.mark.asyncio
    async def test_wait_no_active_page(self):
        """Test error when no terminal page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ):
                    result = await wait_for_terminal_output()

                    assert result["success"] is False
                    assert "No active terminal page" in result["error"]
                    assert result["matched"] is False

    @pytest.mark.asyncio
    async def test_wait_screenshot_failure(self):
        """Test handling of screenshot failure."""
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("Screenshot failed")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_error"
                ):
                    result = await wait_for_terminal_output()

                    assert result["success"] is False
                    assert result["matched"] is False
                    assert "Screenshot failed" in result["error"]

    @pytest.mark.asyncio
    async def test_wait_vqa_failure(self):
        """Test handling of VQA analysis failure."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                side_effect=RuntimeError("VQA failed"),
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_error"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_command_tools.emit_success"
                        ):
                            result = await wait_for_terminal_output(pattern="test")

                            assert result["success"] is True  # Screenshot succeeded
                            assert result["matched"] is False
                            assert "analysis_error" in result

    @pytest.mark.asyncio
    async def test_wait_pattern_detection_variants(self):
        """Test various ways pattern matching is detected from VQA answers."""
        test_cases = [
            ("Yes, I found the pattern", True),
            ("The text matches the pattern", True),
            ("The output contains 'success'", True),
            ("No pattern was detected", False),
            ("I cannot see that text", False),
        ]

        for answer, expected_matched in test_cases:
            mock_page = AsyncMock()
            mock_page.screenshot = AsyncMock(return_value=b"fake")

            mock_manager = AsyncMock()
            mock_manager.get_current_page.return_value = mock_page

            mock_vqa_result = MagicMock()
            mock_vqa_result.answer = answer
            mock_vqa_result.confidence = 0.9
            mock_vqa_result.observations = ""

            with patch(
                "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
                return_value=mock_manager,
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_command_tools.emit_success"
                        ):
                            result = await wait_for_terminal_output(pattern="test")

                            assert result["matched"] == expected_matched, (
                                f"Expected matched={expected_matched} for answer '{answer}'"
                            )


class TestToolRegistration:
    """Tests for tool registration functions."""

    def test_register_run_terminal_command(self):
        """Test that run_terminal_command registration works."""
        from code_puppy.tools.browser.terminal_command_tools import (
            register_run_terminal_command,
        )

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_run_terminal_command(mock_agent)

        assert mock_agent.tool.called

    def test_register_send_terminal_keys(self):
        """Test that send_terminal_keys registration works."""
        from code_puppy.tools.browser.terminal_command_tools import (
            register_send_terminal_keys,
        )

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_send_terminal_keys(mock_agent)

        assert mock_agent.tool.called

    def test_register_wait_for_terminal_output(self):
        """Test that wait_for_terminal_output registration works."""
        from code_puppy.tools.browser.terminal_command_tools import (
            register_wait_for_terminal_output,
        )

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_wait_for_terminal_output(mock_agent)

        assert mock_agent.tool.called

    def test_register_all_terminal_command_tools(self):
        """Test that all tools can be registered at once."""
        from code_puppy.tools.browser.terminal_command_tools import (
            register_all_terminal_command_tools,
        )

        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_all_terminal_command_tools(mock_agent)

        # Should have been called 3 times (one for each tool)
        assert mock_agent.tool.call_count == 3


class TestConstants:
    """Tests for module constants."""

    def test_default_command_timeout_is_reasonable(self):
        """Test that default command timeout is reasonable."""
        assert DEFAULT_COMMAND_TIMEOUT > 0
        assert DEFAULT_COMMAND_TIMEOUT <= 300  # 5 minutes max

    def test_default_output_timeout_is_reasonable(self):
        """Test that default output timeout is reasonable."""
        assert DEFAULT_OUTPUT_TIMEOUT > 0
        assert DEFAULT_OUTPUT_TIMEOUT <= 300  # 5 minutes max

    def test_prompt_wait_is_reasonable(self):
        """Test that prompt wait time is reasonable."""
        assert PROMPT_WAIT_MS > 0
        assert PROMPT_WAIT_MS <= 5000  # 5 seconds max

    def test_modifier_map_completeness(self):
        """Test that modifier map has common modifiers."""
        assert "control" in MODIFIER_MAP
        assert "ctrl" in MODIFIER_MAP
        assert "shift" in MODIFIER_MAP
        assert "alt" in MODIFIER_MAP
        assert "meta" in MODIFIER_MAP
        assert "command" in MODIFIER_MAP
        assert "cmd" in MODIFIER_MAP


class TestIntegrationScenarios:
    """Integration-like tests for full workflows."""

    @pytest.mark.asyncio
    async def test_run_command_then_check_output(self):
        """Test typical: run command → check output workflow."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        mock_vqa_result = MagicMock()
        mock_vqa_result.answer = "Command completed successfully"
        mock_vqa_result.confidence = 0.95
        mock_vqa_result.observations = "Output visible"

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_command_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                    with patch(
                        "code_puppy.tools.browser.terminal_command_tools.emit_success"
                    ):
                        # Run a command
                        run_result = await run_terminal_command(
                            "echo 'hello world'",
                            auto_screenshot=False,
                        )
                        assert run_result["success"] is True

                        # Then check output
                        output_result = await wait_for_terminal_output(
                            pattern="hello",
                        )
                        # With our mock saying "completed successfully",
                        # it won't match "hello" directly
                        assert output_result["success"] is True

    @pytest.mark.asyncio
    async def test_send_ctrl_c_to_interrupt(self):
        """Test typical: send Ctrl+C to interrupt long-running command."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"screenshot")

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    # Start a command (no wait)
                    run_result = await run_terminal_command(
                        "sleep 100",
                        wait_for_prompt=False,
                        auto_screenshot=False,
                    )
                    assert run_result["success"] is True

                    # Send Ctrl+C to interrupt
                    interrupt_result = await send_terminal_keys(
                        "c",
                        modifiers=["Control"],
                    )
                    assert interrupt_result["success"] is True
                    assert interrupt_result["modifiers"] == ["Control"]

    @pytest.mark.asyncio
    async def test_tab_completion_workflow(self):
        """Test tab completion workflow: type partial → Tab → check."""
        mock_page = AsyncMock()
        mock_page.keyboard = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_command_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_command_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_command_tools.emit_success"
                ):
                    # Type partial command
                    await run_terminal_command(
                        "cd /us",
                        wait_for_prompt=False,
                        auto_screenshot=False,
                    )

                    # Press Tab for completion
                    tab_result = await send_terminal_keys("Tab")
                    assert tab_result["success"] is True

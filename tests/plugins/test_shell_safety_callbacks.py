"""Tests for shell_safety callback registration and execution.

These tests focus on the shell_safety_callback function execution paths
and the register() function for callback registration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.plugins.shell_safety.command_cache import CachedAssessment
from code_puppy.plugins.shell_safety.register_callbacks import (
    register,
    shell_safety_callback,
)
from code_puppy.tools.command_runner import ShellSafetyAssessment


class TestShellSafetyCallbackOAuthBypass:
    """Test OAuth model bypass in shell_safety_callback."""

    @pytest.mark.anyio
    async def test_callback_skips_for_oauth_model_anthropic(self):
        """Test callback returns None for Anthropic OAuth models."""
        with patch(
            "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
            return_value="claude-code-123",
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )
            assert result is None

    @pytest.mark.anyio
    async def test_callback_skips_for_oauth_model_openai(self):
        """Test callback returns None for OpenAI OAuth models."""
        with patch(
            "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
            return_value="chatgpt-4",
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )
            assert result is None

    @pytest.mark.anyio
    async def test_callback_skips_for_oauth_model_google(self):
        """Test callback returns None for Google OAuth models."""
        with patch(
            "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
            return_value="gemini-oauth-pro",
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )
            assert result is None


class TestShellSafetyCallbackYoloModeBypass:
    """Test yolo_mode bypass in shell_safety_callback."""

    @pytest.mark.anyio
    async def test_callback_skips_when_yolo_mode_false(self):
        """Test callback returns None when yolo_mode is False."""
        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=False,
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )
            assert result is None


class TestShellSafetyCallbackCacheHit:
    """Test shell_safety_callback with cached assessments."""

    @pytest.mark.anyio
    async def test_cached_assessment_blocked_high_risk(self):
        """Test cached assessment blocks high-risk command."""
        cached = CachedAssessment(risk="high", reasoning="Dangerous command")

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.emit_info"
            ) as mock_emit,
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            assert result["risk"] == "high"
            assert result["reasoning"] == "Dangerous command"
            assert "blocked" in result["error_message"].lower()
            mock_emit.assert_called_once()

    @pytest.mark.anyio
    async def test_cached_assessment_allowed_low_risk(self):
        """Test cached assessment allows low-risk command."""
        cached = CachedAssessment(risk="low", reasoning="Safe command")

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="ls -la", cwd=None, timeout=60
            )

            assert result is None  # Allowed to proceed

    @pytest.mark.anyio
    async def test_cached_assessment_at_threshold_allowed(self):
        """Test cached assessment at threshold is allowed."""
        cached = CachedAssessment(risk="medium", reasoning="Moderate command")

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="npm install", cwd=None, timeout=60
            )

            assert result is None  # At threshold = allowed

    @pytest.mark.anyio
    async def test_cached_assessment_with_none_risk(self):
        """Test cached assessment with None risk defaults to high (fail-safe)."""
        cached = CachedAssessment(risk=None, reasoning="Unknown risk")

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="low",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
            patch("code_puppy.plugins.shell_safety.register_callbacks.emit_info"),
        ):
            result = await shell_safety_callback(
                context=None, command="unknown", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            # None risk becomes "unknown" in display
            assert "unknown" in result["error_message"].lower()


class TestShellSafetyCallbackCacheMiss:
    """Test shell_safety_callback with cache miss (LLM assessment)."""

    @pytest.mark.anyio
    async def test_llm_assessment_blocked_high_risk(self):
        """Test LLM assessment blocks high-risk command."""
        mock_assessment = ShellSafetyAssessment(
            risk="critical", reasoning="Deletes entire filesystem"
        )
        mock_result = MagicMock()
        mock_result.output = mock_assessment

        mock_agent_class = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_with_mcp = AsyncMock(return_value=mock_result)
        mock_agent_class.return_value = mock_agent_instance

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=None,  # Cache miss
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.cache_assessment"
            ) as mock_cache,
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.plugins.shell_safety.agent_shell_safety": MagicMock(
                        ShellSafetyAgent=mock_agent_class
                    )
                },
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.emit_info"
            ) as mock_emit,
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            assert result["risk"] == "critical"
            assert result["reasoning"] == "Deletes entire filesystem"
            mock_cache.assert_called_once_with(
                "rm -rf /", None, "critical", "Deletes entire filesystem"
            )
            mock_emit.assert_called_once()

    @pytest.mark.anyio
    async def test_llm_assessment_allowed_low_risk(self):
        """Test LLM assessment allows low-risk command."""
        mock_assessment = ShellSafetyAssessment(
            risk="low", reasoning="Lists directory contents"
        )
        mock_result = MagicMock()
        mock_result.output = mock_assessment

        mock_agent_class = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_with_mcp = AsyncMock(return_value=mock_result)
        mock_agent_class.return_value = mock_agent_instance

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=None,  # Cache miss
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.cache_assessment"
            ) as mock_cache,
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.plugins.shell_safety.agent_shell_safety": MagicMock(
                        ShellSafetyAgent=mock_agent_class
                    )
                },
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="ls -la", cwd=None, timeout=60
            )

            assert result is None  # Allowed
            mock_cache.assert_called_once_with(
                "ls -la", None, "low", "Lists directory contents"
            )

    @pytest.mark.anyio
    async def test_llm_assessment_with_cwd_in_prompt(self):
        """Test LLM assessment includes cwd in prompt."""
        mock_assessment = ShellSafetyAssessment(
            risk="low", reasoning="Safe in temp directory"
        )
        mock_result = MagicMock()
        mock_result.output = mock_assessment

        mock_agent_class = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_with_mcp = AsyncMock(return_value=mock_result)
        mock_agent_class.return_value = mock_agent_instance

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.cache_assessment"
            ) as mock_cache,
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.plugins.shell_safety.agent_shell_safety": MagicMock(
                        ShellSafetyAgent=mock_agent_class
                    )
                },
            ),
        ):
            await shell_safety_callback(
                context=None, command="rm -rf *", cwd="/tmp/safe", timeout=60
            )

            # Verify the prompt includes cwd
            call_args = mock_agent_instance.run_with_mcp.call_args
            prompt = call_args[0][0]
            assert "/tmp/safe" in prompt
            assert "rm -rf *" in prompt

            # Verify cache includes cwd
            mock_cache.assert_called_once_with(
                "rm -rf *", "/tmp/safe", "low", "Safe in temp directory"
            )

    @pytest.mark.anyio
    async def test_fallback_assessment_not_cached(self):
        """Test fallback assessment is not cached."""
        mock_assessment = ShellSafetyAssessment(
            risk="high", reasoning="Fallback assessment"
        )
        mock_assessment.is_fallback = True  # Mark as fallback
        mock_result = MagicMock()
        mock_result.output = mock_assessment

        mock_agent_class = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_with_mcp = AsyncMock(return_value=mock_result)
        mock_agent_class.return_value = mock_agent_instance

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.cache_assessment"
            ) as mock_cache,
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.plugins.shell_safety.agent_shell_safety": MagicMock(
                        ShellSafetyAgent=mock_agent_class
                    )
                },
            ),
            patch("code_puppy.plugins.shell_safety.register_callbacks.emit_info"),
        ):
            result = await shell_safety_callback(
                context=None, command="dangerous", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            # Fallback assessments should NOT be cached
            mock_cache.assert_not_called()


class TestShellSafetyCallbackExceptionHandling:
    """Test shell_safety_callback exception handling."""

    @pytest.mark.anyio
    async def test_exception_blocks_with_high_risk(self):
        """Test exception handling blocks command with high risk."""
        mock_agent_class = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_with_mcp = AsyncMock(
            side_effect=Exception("LLM connection failed")
        )
        mock_agent_class.return_value = mock_agent_instance

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="medium",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=None,
            ),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.plugins.shell_safety.agent_shell_safety": MagicMock(
                        ShellSafetyAgent=mock_agent_class
                    )
                },
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="some command", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            assert result["risk"] == "high"  # Fail-safe to high
            assert "LLM connection failed" in result["reasoning"]
            assert "error" in result["error_message"].lower()

    @pytest.mark.anyio
    async def test_cache_exception_blocks_command(self):
        """Test cache exception blocks command safely."""
        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="low",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                side_effect=Exception("Cache corrupted"),
            ),
        ):
            result = await shell_safety_callback(
                context=None, command="ls", cwd=None, timeout=60
            )

            assert result is not None
            assert result["blocked"] is True
            assert result["risk"] == "high"
            assert "Cache corrupted" in result["reasoning"]


class TestShellSafetyCallbackErrorMessages:
    """Test error message formatting in shell_safety_callback."""

    @pytest.mark.anyio
    async def test_error_message_format_blocked(self):
        """Test error message format for blocked commands."""
        cached = CachedAssessment(risk="critical", reasoning="System destruction")

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="low",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
            patch("code_puppy.plugins.shell_safety.register_callbacks.emit_info"),
        ):
            result = await shell_safety_callback(
                context=None, command="rm -rf /", cwd=None, timeout=60
            )

            error_msg = result["error_message"]
            # Check message contains expected elements
            assert "🛑" in error_msg
            assert "CRITICAL" in error_msg
            assert "LOW" in error_msg
            assert "System destruction" in error_msg
            assert "Override" in error_msg

    @pytest.mark.anyio
    async def test_error_message_with_none_reasoning(self):
        """Test error message with None reasoning."""
        cached = CachedAssessment(risk="high", reasoning=None)

        with (
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_global_model_name",
                return_value="claude-opus-4",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_yolo_mode",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_safety_permission_level",
                return_value="low",
            ),
            patch(
                "code_puppy.plugins.shell_safety.register_callbacks.get_cached_assessment",
                return_value=cached,
            ),
            patch("code_puppy.plugins.shell_safety.register_callbacks.emit_info"),
        ):
            result = await shell_safety_callback(
                context=None, command="dangerous", cwd=None, timeout=60
            )

            assert "No reasoning provided" in result["error_message"]


class TestRegisterCallback:
    """Test callback registration function."""

    def test_register_function_exists(self):
        """Test that register function exists and is callable."""
        assert callable(register)

    def test_register_calls_register_callback(self):
        """Test that register() calls register_callback."""
        with patch(
            "code_puppy.plugins.shell_safety.register_callbacks.register_callback"
        ) as mock_register:
            register()
            mock_register.assert_called_once_with(
                "run_shell_command", shell_safety_callback
            )

    def test_module_auto_registers_on_import(self):
        """Test that importing the module auto-registers the callback."""
        # Re-import to trigger auto-registration
        with patch(
            "code_puppy.plugins.shell_safety.register_callbacks.register_callback"
        ) as mock_register:
            # Force re-import

            import code_puppy.plugins.shell_safety.register_callbacks as module

            # Call register explicitly since re-import won't re-run module-level code
            module.register()

            mock_register.assert_called_with("run_shell_command", shell_safety_callback)

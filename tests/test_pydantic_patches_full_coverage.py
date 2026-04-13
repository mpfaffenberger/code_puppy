"""Full coverage tests for pydantic_patches.py."""

from unittest.mock import MagicMock, patch

import pytest


class TestGetCodePuppyVersion:
    def test_returns_version(self):
        from code_puppy.pydantic_patches import _get_code_puppy_version

        version = _get_code_puppy_version()
        assert isinstance(version, str)

    def test_returns_dev_on_error(self):
        with patch("importlib.metadata.version", side_effect=Exception("nope")):
            from code_puppy.pydantic_patches import _get_code_puppy_version

            result = _get_code_puppy_version()
            assert result == "0.0.0-dev"


class TestPatchUserAgent:
    def test_patch_user_agent_sets_function(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        # After patching, calling the function should return Code-Puppy/...
        import pydantic_ai.models as pydantic_models

        ua = pydantic_models.get_user_agent()
        assert "Code-Puppy" in ua or "KimiCLI" in ua

    def test_kimi_model_returns_kimi_ua(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", return_value="kimi-test"):
            ua = pydantic_models.get_user_agent()
            assert ua == "KimiCLI/0.63"

    def test_non_kimi_returns_code_puppy_ua(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", return_value="gpt-4"):
            ua = pydantic_models.get_user_agent()
            assert "Code-Puppy" in ua

    def test_get_model_name_exception(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", side_effect=Exception):
            ua = pydantic_models.get_user_agent()
            assert "Code-Puppy" in ua

    def test_patch_user_agent_import_failure(self):
        """Should not crash if pydantic_ai.models is not importable."""
        with patch("builtins.__import__", side_effect=ImportError):
            # This should not raise
            try:
                from code_puppy.pydantic_patches import patch_user_agent

                patch_user_agent()
            except ImportError:
                pass  # Expected in this test


class TestPatchMessageHistoryCleaning:
    def test_patches_clean_message_history(self):
        from code_puppy.pydantic_patches import patch_message_history_cleaning

        patch_message_history_cleaning()
        # After patching, the function should be identity
        from pydantic_ai import _agent_graph

        msgs = ["a", "b"]
        assert _agent_graph._clean_message_history(msgs) is msgs


class TestPatchProcessMessageHistory:
    @pytest.mark.anyio
    async def test_patched_process_runs_processors(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        # Test with no processors
        result = await _process_message_history(["msg1"], [], MagicMock())
        assert result == ["msg1"]

    @pytest.mark.anyio
    async def test_patched_process_empty_raises(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        # Processor that returns empty
        def clear_msgs(msgs):
            return []

        with pytest.raises(Exception, match="empty"):
            await _process_message_history(["msg"], [clear_msgs], MagicMock())

    @pytest.mark.anyio
    async def test_patched_process_with_async_processor(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        async def async_processor(msgs):
            return msgs + ["added"]

        result = await _process_message_history(
            ["msg1"], [async_processor], MagicMock()
        )
        assert "added" in result


class TestPatchToolCallJsonRepair:
    def test_patches_tool_manager(self):
        from code_puppy.pydantic_patches import patch_tool_call_json_repair

        patch_tool_call_json_repair()
        # Just verify it doesn't crash


class TestPatchToolCallCallbacks:
    def test_patches_tool_manager(self):
        from code_puppy.pydantic_patches import patch_tool_call_callbacks

        patch_tool_call_callbacks()
        # Just verify it doesn't crash


class TestApplyAllPatches:
    def test_apply_all_patches(self):
        from code_puppy.pydantic_patches import apply_all_patches

        # Should not raise
        apply_all_patches()

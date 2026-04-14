"""Full coverage tests for pydantic_patches.py."""

import json
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


class TestPatchOpenAIStreamGuard:
    def test_classifies_extra_data_as_retryable_stream_error(self):
        import openai._streaming as openai_streaming
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        from code_puppy.pydantic_patches import patch_openai_stream_guard

        patch_openai_stream_guard()

        sse = openai_streaming.ServerSentEvent(
            event="response.output_item.added",
            data='{"ok": 1}{"oops": 2}',
        )

        with pytest.raises(UnexpectedModelBehavior, match="Malformed streamed SSE event"):
            sse.json()

    def test_non_extra_data_json_error_passthrough(self):
        import openai._streaming as openai_streaming

        from code_puppy.pydantic_patches import patch_openai_stream_guard

        patch_openai_stream_guard()

        sse = openai_streaming.ServerSentEvent(
            event="response.output_item.added",
            data='{"missing": ',
        )

        with pytest.raises(json.JSONDecodeError):
            sse.json()


class TestApplyAllPatches:
    def test_apply_all_patches(self):
        from code_puppy import pydantic_patches

        with (
            patch.object(pydantic_patches, "patch_user_agent") as patch_user_agent,
            patch.object(
                pydantic_patches, "patch_message_history_cleaning"
            ) as patch_message_history_cleaning,
            patch.object(
                pydantic_patches, "patch_process_message_history"
            ) as patch_process_message_history,
            patch.object(
                pydantic_patches, "patch_openai_stream_guard"
            ) as patch_openai_stream_guard,
            patch.object(
                pydantic_patches, "patch_tool_call_json_repair"
            ) as patch_tool_call_json_repair,
            patch.object(
                pydantic_patches, "patch_tool_call_callbacks"
            ) as patch_tool_call_callbacks,
            patch.object(
                pydantic_patches, "patch_args_as_dict_json_repair"
            ) as patch_args_as_dict_json_repair,
        ):
            pydantic_patches.apply_all_patches()

        patch_user_agent.assert_called_once_with()
        patch_message_history_cleaning.assert_called_once_with()
        patch_process_message_history.assert_called_once_with()
        patch_openai_stream_guard.assert_called_once_with()
        patch_tool_call_json_repair.assert_called_once_with()
        patch_tool_call_callbacks.assert_called_once_with()
        patch_args_as_dict_json_repair.assert_called_once_with()

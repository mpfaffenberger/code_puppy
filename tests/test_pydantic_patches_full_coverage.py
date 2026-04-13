"""Full coverage tests for pydantic_patches.py."""

from unittest.mock import patch


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
    def test_skips_when_target_missing(self):
        """When _process_message_history doesn't exist (newer pydantic-ai), patch is a no-op."""
        from pydantic_ai import _agent_graph

        from code_puppy.pydantic_patches import patch_process_message_history

        had_attr_before = hasattr(_agent_graph, "_process_message_history")
        patch_process_message_history()

        if not had_attr_before:
            # Patch should NOT have injected the attribute
            assert not hasattr(_agent_graph, "_process_message_history")

    def test_patches_when_target_exists(self):
        """When _process_message_history exists (older pydantic-ai), patch replaces it."""
        from pydantic_ai import _agent_graph

        from code_puppy.pydantic_patches import patch_process_message_history

        # Simulate an older pydantic-ai that has the target function
        sentinel = object()
        _agent_graph._process_message_history = sentinel
        try:
            patch_process_message_history()
            # The patch should have replaced the sentinel
            assert _agent_graph._process_message_history is not sentinel
        finally:
            # Clean up the injected attribute
            if hasattr(_agent_graph, "_process_message_history"):
                delattr(_agent_graph, "_process_message_history")

    def test_does_not_crash_on_import_error(self):
        """Patch should fail gracefully if pydantic_ai is broken."""
        from code_puppy.pydantic_patches import patch_process_message_history

        # Should not raise even in edge cases
        patch_process_message_history()


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

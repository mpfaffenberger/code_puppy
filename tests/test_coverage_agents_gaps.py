"""Coverage tests for agents & small gaps (code_puppy-ont).

Targeted tests to reach 100% on specific missed lines.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Agent instantiation tests (get_available_tools + get_system_prompt)
# =============================================================================


_REVIEWER_AGENTS = [
    ("code_puppy.agents.agent_qa_kitten", "QualityAssuranceKittenAgent"),
]


@pytest.mark.parametrize("module_path,class_name", _REVIEWER_AGENTS)
def test_reviewer_agent_tools_and_prompt(module_path, class_name):
    """Exercise get_available_tools() and get_system_prompt() for each surviving agent."""
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    agent = cls()

    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0

    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100


class TestPlanningAgent:
    def test_tools_and_prompt(self):
        from code_puppy.agents.agent_planning import PlanningAgent

        agent = PlanningAgent()
        tools = agent.get_available_tools()
        assert "list_files" in tools
        assert "invoke_agent" in tools

        prompt = agent.get_system_prompt()
        assert "Planning Mode" in prompt
        assert "EXECUTION PLAN" in prompt


class TestCodePuppyAgentTools:
    def test_get_available_tools(self):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        agent = CodePuppyAgent()
        tools = agent.get_available_tools()
        assert "create_file" in tools
        assert "replace_in_file" in tools
        assert "delete_snippet" in tools
        assert "invoke_agent" in tools

    def test_default_code_puppy_does_not_get_model_override_tools(self):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        agent = CodePuppyAgent()
        tools = agent.get_available_tools()
        prompt = agent.get_system_prompt()

        assert "invoke_agent" in tools
        assert "invoke_agent_with_model" not in tools
        assert "list_available_models" not in tools
        assert "model_name" not in prompt
        assert "invoke_agent_with_model" not in prompt


# =============================================================================
# display.py line 39 – subagent early return
# =============================================================================


class TestDisplaySubagentSkip:
    def test_skips_when_subagent_not_verbose(self):
        """Early return for subagent without verbose: nothing renders."""
        from code_puppy.tools.display import display_non_streamed_result

        with (
            patch("code_puppy.tools.display.is_subagent", return_value=True),
            patch("code_puppy.tools.display.get_subagent_verbose", return_value=False),
            patch("code_puppy.tools.display.Console") as mock_console_cls,
        ):
            display_non_streamed_result("hello")
            mock_console_cls.assert_not_called()  # Should have returned early


# =============================================================================
# __init__.py lines 8-10 – exception fallback
# =============================================================================


class TestInitVersionFallback:
    def test_version_fallback_on_exception(self):
        """The Code Puppy version keeps its development fallback on lookup errors."""
        with patch(
            "importlib.metadata.version", side_effect=Exception("nope")
        ) as mock_version:
            # Re-exec the module code
            import importlib

            import code_puppy

            importlib.reload(code_puppy)
            assert code_puppy.__version__ == "0.0.0-dev"
            mock_version.assert_called_once_with("code-puppy")

    def test_version_fallback_on_empty(self):
        """The Code Puppy version keeps its development fallback when empty."""
        with patch("importlib.metadata.version", return_value="") as mock_version:
            import importlib

            import code_puppy

            importlib.reload(code_puppy)
            assert code_puppy.__version__ == "0.0.0-dev"
            mock_version.assert_called_once_with("code-puppy")

    @pytest.mark.parametrize("metadata_version", ["0.0.2", "  1.2.3rc1+build.5  "])
    def test_core_plugins_version_uses_installed_distribution_metadata(
        self, metadata_version
    ):
        import code_puppy

        with patch(
            "importlib.metadata.version", return_value=metadata_version
        ) as mock_version:
            assert code_puppy.get_core_plugins_version() == metadata_version.strip()

        mock_version.assert_called_once_with("code-puppy-core-plugins")

    @pytest.mark.parametrize(
        "metadata_version",
        [
            "",
            "   ",
            None,
            object(),
            "not-a-version",
            "1.2.3\nInjected second line",
            "\x1b[2J",
        ],
    )
    def test_core_plugins_version_rejects_empty_or_malformed_metadata(
        self, metadata_version
    ):
        import code_puppy

        with patch("importlib.metadata.version", return_value=metadata_version):
            assert code_puppy.get_core_plugins_version() is None

    def test_core_plugins_version_handles_normalization_failure(self):
        import code_puppy

        class BrokenVersion(str):
            def strip(self):
                raise RuntimeError("broken metadata")

        with patch("importlib.metadata.version", return_value=BrokenVersion("1.2.3")):
            assert code_puppy.get_core_plugins_version() is None

    def test_core_plugins_version_handles_missing_distribution(self):
        import code_puppy

        with patch(
            "importlib.metadata.version",
            side_effect=PackageNotFoundError("code-puppy-core-plugins"),
        ):
            assert code_puppy.get_core_plugins_version() is None

    @pytest.mark.parametrize("metadata_version", [" 1.2.3 ", object()])
    def test_code_puppy_version_preserves_truthy_metadata(self, metadata_version):
        import importlib

        import code_puppy

        try:
            with patch("importlib.metadata.version", return_value=metadata_version):
                importlib.reload(code_puppy)
                assert code_puppy.__version__ is metadata_version
        finally:
            importlib.reload(code_puppy)


# =============================================================================
# __main__.py lines 7-10
# =============================================================================


class TestMainModule:
    def test_main_module_importable(self):
        """Cover the import of __main__ (lines 7-10 minus __name__ guard)."""
        import code_puppy.__main__  # noqa: F401
        # The if __name__ == '__main__' guard won't fire, but the import covers lines 7-8


# =============================================================================
# messaging.spinner compat shim gaps
# =============================================================================


class TestSpinnerShimGaps:
    def test_format_context_info_zero_capacity(self):
        """capacity <= 0 returns empty."""
        from code_puppy.messaging.spinner import format_context_info

        assert format_context_info(100, 0, 0.0) == ""
        assert format_context_info(100, -1, 0.0) == ""

    def test_format_context_info_normal(self):
        from code_puppy.messaging.spinner import format_context_info

        result = format_context_info(5000, 10000, 0.5)
        assert "5k" in result
        assert "50%" in result


# =============================================================================
# ask_user_question/models.py lines 57-59 – timeout_response
# =============================================================================


class TestAskUserQuestionModelsGaps:
    def test_timeout_response(self):
        """Cover lines 57-59: timeout_response classmethod."""
        from code_puppy.tools.ask_user_question.models import AskUserQuestionOutput

        resp = AskUserQuestionOutput.timeout_response(30)
        assert resp.timed_out is True
        assert resp.cancelled is False
        assert "30 seconds" in resp.error
        assert not resp.success


# =============================================================================
# ask_user_question/registration.py line 87
# =============================================================================


class TestAskUserRegistrationGap:
    def test_handler_called(self):
        """Cover line 87: the actual handler invocation."""
        from code_puppy.tools.ask_user_question.models import AskUserQuestionOutput

        mock_output = AskUserQuestionOutput(cancelled=True)

        with patch(
            "code_puppy.tools.ask_user_question.registration._ask_user_question_impl",
            return_value=mock_output,
        ) as mock_impl:
            # We need to register the tool on a real agent, or just call the inner function
            # Simplest: import and call the impl wrapper directly
            from code_puppy.tools.ask_user_question.registration import (
                register_ask_user_question,
            )

            mock_agent = MagicMock()
            # Capture the decorated function
            registered_fn = None

            def capture_tool(fn):
                nonlocal registered_fn
                registered_fn = fn
                return fn

            mock_agent.tool = capture_tool
            register_ask_user_question(mock_agent)

            assert registered_fn is not None
            # Call it with a mock context
            result = registered_fn(
                MagicMock(),
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ],
            )
            mock_impl.assert_called_once()
            assert result is mock_output


# =============================================================================
# mcp_/async_lifecycle.py lines 99-103 – timeout branch
# =============================================================================


class TestAsyncLifecycleGaps:
    @pytest.mark.asyncio
    async def test_start_server_timeout(self):
        """Cover lines 99-103: timeout waiting for server to start."""
        from code_puppy.mcp_.async_lifecycle import AsyncServerLifecycleManager

        manager = AsyncServerLifecycleManager()
        mock_server = MagicMock()
        mock_server.is_running = False

        # Make the lifecycle task never set the ready_event by patching create_task
        import asyncio

        async def fake_lifecycle(server_id, server, ready_event):
            # Never set ready_event, just sleep forever
            await asyncio.sleep(100)

        with patch.object(
            manager, "_server_lifecycle_task", side_effect=fake_lifecycle
        ):
            result = await asyncio.wait_for(
                manager.start_server("test-server", mock_server),
                timeout=15.0,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_start_server_task_fails_during_startup(self):
        """Cover the task.done() + exception path after timeout."""
        from code_puppy.mcp_.async_lifecycle import AsyncServerLifecycleManager

        manager = AsyncServerLifecycleManager()
        mock_server = MagicMock()
        mock_server.is_running = False

        import asyncio

        async def failing_lifecycle(server_id, server, ready_event):
            raise RuntimeError("startup failed")

        with patch.object(
            manager, "_server_lifecycle_task", side_effect=failing_lifecycle
        ):
            result = await asyncio.wait_for(
                manager.start_server("test-server", mock_server),
                timeout=15.0,
            )
            assert result is False

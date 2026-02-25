"""Coverage tests for agents & small gaps (code_puppy-ont).

Targeted tests to reach 100% on specific missed lines.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Agent instantiation tests (get_available_tools + get_system_prompt)
# =============================================================================


_REVIEWER_AGENTS = [
    ("code_puppy.agents.agent_c_reviewer", "CReviewerAgent"),
    ("code_puppy.agents.agent_code_reviewer", "CodeQualityReviewerAgent"),
    ("code_puppy.agents.agent_cpp_reviewer", "CppReviewerAgent"),
    ("code_puppy.agents.agent_golang_reviewer", "GolangReviewerAgent"),
    ("code_puppy.agents.agent_javascript_reviewer", "JavaScriptReviewerAgent"),
    ("code_puppy.agents.agent_python_reviewer", "PythonReviewerAgent"),
    ("code_puppy.agents.agent_python_programmer", "PythonProgrammerAgent"),
    ("code_puppy.agents.agent_qa_expert", "QAExpertAgent"),
    ("code_puppy.agents.agent_qa_kitten", "QualityAssuranceKittenAgent"),
    ("code_puppy.agents.agent_security_auditor", "SecurityAuditorAgent"),
    ("code_puppy.agents.agent_typescript_reviewer", "TypeScriptReviewerAgent"),
]


@pytest.mark.parametrize("module_path,class_name", _REVIEWER_AGENTS)
def test_reviewer_agent_tools_and_prompt(module_path, class_name):
    """Exercise get_available_tools() and get_system_prompt() for each reviewer agent."""
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


class TestPromptReviewerAgent:
    def test_tools_and_prompt(self):
        from code_puppy.agents.prompt_reviewer import PromptReviewerAgent

        agent = PromptReviewerAgent()
        tools = agent.get_available_tools()
        assert "read_file" in tools

        prompt = agent.get_system_prompt()
        assert "Prompt Review Mode" in prompt
        assert "Quality Dimensions" in prompt


class TestSchedulerAgent:
    def test_tools_and_prompt(self):
        from code_puppy.agents.agent_scheduler import SchedulerAgent

        agent = SchedulerAgent()
        tools = agent.get_available_tools()
        assert "scheduler_list_tasks" in tools

        prompt = agent.get_system_prompt()
        assert "Scheduler Agent" in prompt


class TestCodePuppyAgentTools:
    def test_get_available_tools(self):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        agent = CodePuppyAgent()
        tools = agent.get_available_tools()
        assert "edit_file" in tools
        assert "invoke_agent" in tools


# =============================================================================
# summarization_agent.py gaps
# =============================================================================


class TestSummarizationGaps:
    def test_ensure_thread_pool_recreates_after_shutdown(self):
        """Cover lines 38-40: pool._shutdown check."""
        import code_puppy.summarization_agent as mod

        pool = ThreadPoolExecutor(max_workers=1)
        pool.shutdown(wait=False)
        mod._thread_pool = pool

        new_pool = mod._ensure_thread_pool()
        assert new_pool is not pool
        assert not new_pool._shutdown

    def test_summarization_error_with_original(self):
        """Cover lines 66-67: SummarizationError.__init__."""
        from code_puppy.summarization_agent import SummarizationError

        orig = ValueError("boom")
        err = SummarizationError("wrapper", original_error=orig)
        assert err.original_error is orig
        assert "wrapper" in str(err)

    def test_run_summarization_sync_agent_init_failure(self):
        """Cover the except branch when get_summarization_agent raises."""
        from code_puppy.summarization_agent import (
            SummarizationError,
            run_summarization_sync,
        )

        with patch(
            "code_puppy.summarization_agent.get_summarization_agent",
            side_effect=RuntimeError("no model"),
        ):
            with pytest.raises(SummarizationError, match="Failed to initialize"):
                run_summarization_sync("prompt", [])

    def test_run_summarization_sync_llm_failure(self):
        """Cover lines 88-105: the _run_in_thread path and LLM error wrapping."""
        from code_puppy.summarization_agent import (
            SummarizationError,
            run_summarization_sync,
        )

        mock_agent = MagicMock()
        mock_agent.run = MagicMock(side_effect=RuntimeError("LLM down"))

        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.summarization_agent.get_global_model_name",
                return_value="test",
            ),
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
        ):
            mock_prep.return_value = MagicMock(user_prompt="p", instructions="i")
            with pytest.raises(SummarizationError, match="LLM call failed"):
                run_summarization_sync("summarize", [])


# =============================================================================
# display.py line 39 – subagent early return
# =============================================================================


class TestDisplaySubagentSkip:
    def test_skips_when_subagent_not_verbose(self):
        """Cover line 39: early return for subagent without verbose."""
        from code_puppy.tools.display import display_non_streamed_result

        with (
            patch("code_puppy.tools.display.is_subagent", return_value=True),
            patch("code_puppy.tools.display.get_subagent_verbose", return_value=False),
            patch("code_puppy.messaging.spinner.pause_all_spinners") as mock_pause,
        ):
            display_non_streamed_result("hello")
            mock_pause.assert_not_called()  # Should have returned early


# =============================================================================
# __init__.py lines 8-10 – exception fallback
# =============================================================================


class TestInitVersionFallback:
    def test_version_fallback_on_exception(self):
        """Cover lines 8-10: exception branch."""
        with patch("importlib.metadata.version", side_effect=Exception("nope")):
            # Re-exec the module code
            import importlib

            import code_puppy

            importlib.reload(code_puppy)
            assert code_puppy.__version__ == "0.0.0-dev"

    def test_version_fallback_on_empty(self):
        """Cover the empty-string branch."""
        with patch("importlib.metadata.version", return_value=""):
            import importlib

            import code_puppy

            importlib.reload(code_puppy)
            assert code_puppy.__version__ == "0.0.0-dev"


# =============================================================================
# __main__.py lines 7-10
# =============================================================================


class TestMainModule:
    def test_main_module_importable(self):
        """Cover the import of __main__ (lines 7-10 minus __name__ guard)."""
        import code_puppy.__main__  # noqa: F401
        # The if __name__ == '__main__' guard won't fire, but the import covers lines 7-8


# =============================================================================
# spinner_base.py gaps
# =============================================================================


class TestSpinnerBaseGaps:
    def _make_spinner(self):
        """Create a concrete spinner subclass for testing."""
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        class DummySpinner(SpinnerBase):
            def start(self):
                super().start()

            def stop(self):
                super().stop()

            def update_frame(self):
                super().update_frame()

        return DummySpinner()

    def test_update_frame_when_not_spinning(self):
        """Cover line 54: update_frame does nothing when not spinning."""
        s = self._make_spinner()
        assert not s.is_spinning
        s.update_frame()
        assert s._frame_index == 0  # unchanged

    def test_update_frame_when_spinning(self):
        s = self._make_spinner()
        s.start()
        s.update_frame()
        assert s._frame_index == 1

    def test_clear_context_info(self):
        """Cover line 70: clear_context_info."""
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        SpinnerBase.set_context_info("something")
        assert SpinnerBase.get_context_info() == "something"
        SpinnerBase.clear_context_info()
        assert SpinnerBase.get_context_info() == ""

    def test_format_context_info_zero_capacity(self):
        """Cover line 93: capacity <= 0 returns empty."""
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        assert SpinnerBase.format_context_info(100, 0, 0.0) == ""
        assert SpinnerBase.format_context_info(100, -1, 0.0) == ""

    def test_format_context_info_normal(self):
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        result = SpinnerBase.format_context_info(5000, 10000, 0.5)
        assert "5,000" in result
        assert "50.0%" in result


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

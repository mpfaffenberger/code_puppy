"""Tests for per-run usage/latency reporting in subagent_invocation.

These cover the additive token-usage and ``duration_ms`` fields added to
``AgentInvokeOutput``:

- success path populates all five fields
- a failing ``result.usage()`` leaves token fields None but still times the run
- the deprecated ``request_tokens``/``response_tokens`` field names still map
- an error path (the sub-agent run raises) leaves all five fields None

The suite is intentionally isolated from ``test_agent_tools_coverage.py`` so the
new behaviour stays focused and readable.
"""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.subagent_invocation import (
    _extract_usage_metrics,
    register_invoke_agent_with_model,
)


def _passthrough_retry(*_args, **_kwargs):
    """Replacement for make_streaming_retry: run the coroutine once, no retries."""

    def _decorator(func):
        return func

    return _decorator


def _capture_invoke_with_model():
    """Capture the registered invoke_agent_with_model callable."""
    mock_agent = MagicMock()
    captured = {}

    def capture_tool(func):
        captured["func"] = func
        return func

    mock_agent.tool = capture_tool
    register_invoke_agent_with_model(mock_agent)
    return captured["func"]


def _build_agent_config():
    config = MagicMock()

    @contextmanager
    def temporary_override(_model_name):
        yield

    config.temporary_model_name_override.side_effect = temporary_override
    config.get_model_name.return_value = "override-model"
    config.get_full_system_prompt.return_value = "Test instructions"
    config.get_available_tools.return_value = ["list_files"]
    config.get_message_history.return_value = []
    return config


async def _run_invoke(*, usage=None, usage_raises=False, run_raises=False, perf=None):
    """Drive _invoke_agent_impl with a mocked temp agent and return the output."""
    invoke = _capture_invoke_with_model()
    mock_context = MagicMock()
    agent_config = _build_agent_config()

    mock_temp_agent = MagicMock()
    if run_raises:
        mock_temp_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        result = MagicMock()
        result.output = "subagent response"
        result.all_messages.return_value = ["updated-history"]
        if usage_raises:
            result.usage = MagicMock(side_effect=RuntimeError("no usage"))
        else:
            result.usage = MagicMock(return_value=usage)
        mock_temp_agent.run = AsyncMock(return_value=result)

    with ExitStack() as stack:
        p = stack.enter_context
        p(patch(
            "code_puppy.tools.subagent_invocation.generate_group_id",
            return_value="test-group",
        ))
        p(patch("code_puppy.tools.subagent_invocation.get_message_bus"))
        p(patch(
            "code_puppy.tools.subagent_invocation.get_session_context",
            return_value="parent",
        ))
        p(patch("code_puppy.tools.subagent_invocation.set_session_context"))
        p(patch("code_puppy.tools.subagent_invocation.emit_info"))
        p(patch("code_puppy.tools.subagent_invocation.emit_error"))
        p(patch("code_puppy.tools.subagent_invocation.emit_success"))
        p(patch("code_puppy.tools.subagent_invocation._save_session_history"))
        p(patch(
            "code_puppy.tools.subagent_invocation._load_session_history",
            return_value=[],
        ))
        p(patch(
            "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
            return_value="abc123",
        ))
        p(patch(
            "code_puppy.agents.agent_manager.load_agent",
            return_value=agent_config,
        ))
        p(patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"default-model": {}, "override-model": {}},
        ))
        p(patch("code_puppy.model_factory.ModelFactory.get_model"))
        p(patch("code_puppy.model_factory.make_model_settings"))
        p(patch("code_puppy.agents._builder.load_puppy_rules", return_value=None))
        p(patch("code_puppy.callbacks.on_load_prompt", return_value=[]))
        mock_prepare = p(patch("code_puppy.model_utils.prepare_prompt_for_model"))
        mock_prepare.return_value = MagicMock(
            instructions="prepared instructions", user_prompt="prepared prompt"
        )
        p(patch(
            "code_puppy.agents._builder.autostart_bound_servers_async",
            new=AsyncMock(),
        ))
        # Disable MCP so no manager/servers are touched.
        p(patch("code_puppy.config.get_value", return_value="true"))
        p(patch("code_puppy.config.get_output_level", return_value="medium"))
        p(patch(
            "code_puppy.agents._compaction.make_history_processor",
            return_value=lambda messages: messages,
        ))
        p(patch(
            "code_puppy.tools.subagent_invocation.Agent",
            return_value=mock_temp_agent,
        ))
        p(patch("code_puppy.tools.register_tools_for_agent"))
        p(patch(
            "code_puppy.tools.subagent_invocation.on_wrap_pydantic_agent",
            side_effect=lambda _cfg, agent, **_kwargs: agent,
        ))
        p(patch(
            "code_puppy.tools.subagent_invocation.on_agent_run_context",
            return_value=[],
        ))
        # Pass-through retry: run once, no backoff, so failures propagate fast.
        p(patch(
            "code_puppy.agents.retry_profiles.make_streaming_retry",
            new=_passthrough_retry,
        ))
        if perf is not None:
            p(patch(
                "code_puppy.tools.subagent_invocation.time.perf_counter",
                side_effect=perf,
            ))

        return await invoke(
            mock_context,
            agent_name="test-agent",
            prompt="Hello",
            model_name="override-model",
        )


class TestExtractUsageMetrics:
    """Unit tests for the defensive usage-mapping helper."""

    def test_none_usage_yields_all_none(self):
        assert _extract_usage_metrics(None) == {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "num_requests": None,
        }

    def test_modern_fields(self):
        usage = SimpleNamespace(
            input_tokens=10, output_tokens=5, total_tokens=15, requests=2
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "num_requests": 2,
        }

    def test_deprecated_fields_and_computed_total(self):
        usage = SimpleNamespace(request_tokens=7, response_tokens=3, requests=1)
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
            "num_requests": 1,
        }

    def test_zero_is_valid_not_missing(self):
        usage = SimpleNamespace(
            input_tokens=0, output_tokens=0, total_tokens=0, requests=0
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "num_requests": 0,
        }

    def test_bool_and_non_finite_are_rejected(self):
        usage = SimpleNamespace(
            input_tokens=True, output_tokens=float("nan"), requests=float("inf")
        )
        metrics = _extract_usage_metrics(usage)
        assert metrics["input_tokens"] is None
        assert metrics["output_tokens"] is None
        assert metrics["num_requests"] is None


class TestInvokeReportsUsageAndLatency:
    """Integration-ish tests through the registered tool."""

    @pytest.mark.asyncio
    async def test_success_populates_all_fields(self):
        usage = SimpleNamespace(
            input_tokens=12, output_tokens=8, total_tokens=20, requests=3
        )
        out = await _run_invoke(usage=usage)

        assert out.response == "subagent response"
        assert out.error is None
        assert out.input_tokens == 12
        assert out.output_tokens == 8
        assert out.total_tokens == 20
        assert out.num_requests == 3
        assert isinstance(out.duration_ms, float)
        assert out.duration_ms >= 0.0

    @pytest.mark.asyncio
    async def test_success_duration_is_measured(self):
        usage = SimpleNamespace(
            input_tokens=1, output_tokens=1, total_tokens=2, requests=1
        )
        # perf_counter: start=1000.0, stop=1000.5 -> 500.0 ms; extra calls stay
        # at the stop value so nothing raises if the clock is touched again.
        out = await _run_invoke(usage=usage, perf=[1000.0, 1000.5, 1000.5, 1000.5])

        assert out.duration_ms == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_success_when_usage_call_raises(self):
        out = await _run_invoke(usage_raises=True)

        assert out.response == "subagent response"
        assert out.error is None
        assert out.input_tokens is None
        assert out.output_tokens is None
        assert out.total_tokens is None
        assert out.num_requests is None
        # Latency is still measured even when usage extraction fails.
        assert isinstance(out.duration_ms, float)
        assert out.duration_ms >= 0.0

    @pytest.mark.asyncio
    async def test_success_with_deprecated_usage_fields(self):
        usage = SimpleNamespace(request_tokens=7, response_tokens=3, requests=1)
        out = await _run_invoke(usage=usage)

        assert out.input_tokens == 7
        assert out.output_tokens == 3
        assert out.total_tokens == 10
        assert out.num_requests == 1

    @pytest.mark.asyncio
    async def test_error_path_leaves_all_metrics_none(self):
        out = await _run_invoke(run_raises=True)

        assert out.response is None
        assert out.error is not None
        assert out.input_tokens is None
        assert out.output_tokens is None
        assert out.total_tokens is None
        assert out.num_requests is None
        assert out.duration_ms is None

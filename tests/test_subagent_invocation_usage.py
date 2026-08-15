"""Tests for per-run usage/latency reporting in subagent_invocation.

These cover the additive token-usage and timing fields on
``AgentInvokeWithModelOutput`` -- scoped EXCLUSIVELY to
``invoke_agent_with_model``. ``invoke_agent`` keeps returning the original,
unmodified ``AgentInvokeOutput`` with no usage/timing fields at all; that
contract is locked in by ``TestInvokeAgentUnaffected`` below.

- success path populates every new field (non-cached input_tokens, cache read /
  creation buckets, output_tokens, total_tokens, num_requests, start_time,
  end_time, duration_ms) with ``start_time <= end_time``
- token buckets are normalized per provider so cached tokens are not
  double-counted (Anthropic / OpenAI / Gemini shapes)
- a failing ``result.usage()`` leaves token fields None but still times the run
- an error path (the sub-agent run raises) leaves all new fields None
- ``invoke_agent`` (no model override) never sees any of these fields

The suite is intentionally isolated from ``test_agent_tools_coverage.py`` so the
new behaviour stays focused and readable.
"""

from contextlib import ExitStack, contextmanager
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.subagent_invocation import (
    register_invoke_agent,
    register_invoke_agent_with_model,
)
from code_puppy.tools.subagent_usage_metrics import (
    _extract_usage_metrics,
    _safe_usage_metrics,
)


def _usage(**kwargs):
    """Build a stub usage object; ``details`` defaults to an empty dict."""
    kwargs.setdefault("details", {})
    return SimpleNamespace(**kwargs)


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


def _capture_invoke_default():
    """Capture the registered invoke_agent (no model override) callable."""
    mock_agent = MagicMock()
    captured = {}

    def capture_tool(func):
        captured["func"] = func
        return func

    mock_agent.tool = capture_tool
    register_invoke_agent(mock_agent)
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


async def _run_invoke(
    *,
    usage=None,
    usage_raises=False,
    run_raises=False,
    run_exc=None,
    partial_history=None,
    result_messages=None,
    capture=None,
    perf=None,
    use_default=False,
):
    """Drive _invoke_agent_impl with a mocked temp agent and return the output.

    ``use_default=True`` drives it through the plain ``invoke_agent`` tool
    (no model override, no usage instrumentation) instead of
    ``invoke_agent_with_model``.

    ``run_exc`` injects an arbitrary exception as the temp agent's run failure
    (e.g. ``asyncio.CancelledError()``); it takes precedence over
    ``run_raises``. ``partial_history`` seeds the config's in-flight history so
    the interruption/failure save path has progress to persist. ``capture``, a
    dict, is populated with handles to the patched ``emit_warning``,
    ``emit_info``, and ``_save_session_history`` mocks for assertions.
    """
    invoke = _capture_invoke_default() if use_default else _capture_invoke_with_model()
    mock_context = MagicMock()
    agent_config = _build_agent_config()
    if partial_history is not None:
        agent_config.get_message_history.return_value = partial_history

    mock_temp_agent = MagicMock()
    if run_exc is not None:
        mock_temp_agent.run = AsyncMock(side_effect=run_exc)
    elif run_raises:
        mock_temp_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        result = MagicMock()
        result.output = "subagent response"
        result.all_messages.return_value = (
            result_messages if result_messages is not None else ["updated-history"]
        )
        if usage_raises:
            result.usage = MagicMock(side_effect=RuntimeError("no usage"))
        else:
            result.usage = MagicMock(return_value=usage)
        mock_temp_agent.run = AsyncMock(return_value=result)

    with ExitStack() as stack:
        p = stack.enter_context
        p(
            patch(
                "code_puppy.tools.subagent_invocation.generate_group_id",
                return_value="test-group",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.get_message_bus"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.get_session_context",
                return_value="parent",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.set_session_context"))
        p(patch("code_puppy.tools.subagent_invocation.emit_info"))
        p(patch("code_puppy.tools.subagent_invocation.emit_error"))
        p(patch("code_puppy.tools.subagent_invocation.emit_success"))
        mock_warning = p(patch("code_puppy.tools.subagent_invocation.emit_warning"))
        mock_save = p(
            patch("code_puppy.tools.subagent_invocation._save_session_history")
        )
        if capture is not None:
            capture["warning"] = mock_warning
            capture["save"] = mock_save
        p(
            patch(
                "code_puppy.tools.subagent_invocation._load_session_history",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
                return_value="abc123",
            )
        )
        p(
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=agent_config,
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"default-model": {}, "override-model": {}},
            )
        )
        p(patch("code_puppy.model_factory.ModelFactory.get_model"))
        p(patch("code_puppy.model_factory.make_model_settings"))
        p(patch("code_puppy.agents._builder.load_puppy_rules", return_value=None))
        p(patch("code_puppy.callbacks.on_load_prompt", return_value=[]))
        mock_prepare = p(patch("code_puppy.model_utils.prepare_prompt_for_model"))
        mock_prepare.return_value = MagicMock(
            instructions="prepared instructions", user_prompt="prepared prompt"
        )
        p(
            patch(
                "code_puppy.agents._builder.autostart_bound_servers_async",
                new=AsyncMock(),
            )
        )
        # Disable MCP so no manager/servers are touched.
        p(patch("code_puppy.config.get_value", return_value="true"))
        p(patch("code_puppy.config.get_output_level", return_value="medium"))
        p(
            patch(
                "code_puppy.agents._compaction.make_history_processor",
                return_value=lambda messages: messages,
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation.Agent",
                return_value=mock_temp_agent,
            )
        )
        p(patch("code_puppy.tools.register_tools_for_agent"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_wrap_pydantic_agent",
                side_effect=lambda _cfg, agent, **_kwargs: agent,
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_agent_run_context",
                return_value=[],
            )
        )
        # Pass-through retry: run once, no backoff, so failures propagate fast.
        p(
            patch(
                "code_puppy.agents.retry_profiles.make_streaming_retry",
                new=_passthrough_retry,
            )
        )
        if perf is not None:
            p(
                patch(
                    "code_puppy.tools.subagent_invocation.time.perf_counter",
                    side_effect=perf,
                )
            )

        if use_default:
            return await invoke(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
            )
        return await invoke(
            mock_context,
            agent_name="test-agent",
            prompt="Hello",
            model_name="override-model",
        )


class TestExtractUsageMetrics:
    """Unit tests for the defensive, provider-aware usage-mapping helper."""

    def test_none_usage_yields_all_none(self):
        assert _extract_usage_metrics(None) == {
            "input_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "num_requests": None,
        }

    def test_modern_fields_no_cache(self):
        # No cache reported anywhere: cache buckets stay None, input untouched.
        usage = _usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            requests=2,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 10,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": 5,
            "total_tokens": 15,
            "num_requests": 2,
        }

    def test_cache_details_aliases_populate_buckets_without_normalized_attrs(self):
        # Some provider adapters expose cache counts only in details, not in
        # pydantic-ai's normalized cache_read/cache_write attributes.
        usage = _usage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            output_tokens=50,
            total_tokens=200,
            requests=1,
            details={
                "cache_read_tokens": 30,
                "cache_write_tokens": 20,
            },
        )

        assert _extract_usage_metrics(usage) == {
            "input_tokens": 100,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 20,
            "output_tokens": 50,
            "total_tokens": 200,
            "num_requests": 1,
        }

    def test_explicit_zero_cache_detail_is_preserved(self):
        usage = _usage(
            input_tokens=120,
            output_tokens=60,
            total_tokens=180,
            requests=1,
            details={"cached_tokens": 0},
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["cache_read_input_tokens"] == 0
        assert metrics["input_tokens"] == 120

    def test_anthropic_shape_populates_both_cache_buckets(self):
        # Anthropic folds base + cache_creation + cache_read into input_tokens.
        usage = _usage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            output_tokens=50,
            total_tokens=200,
            requests=1,
            cache_read_tokens=30,
            cache_write_tokens=20,
            details={
                "input_tokens": 100,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 30,
                "output_tokens": 50,
            },
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 100,  # cache subtracted back out
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 20,
            "output_tokens": 50,
            "total_tokens": 200,
            "num_requests": 1,
        }

    def test_openai_shape_cache_read_only(self):
        # OpenAI prompt_tokens already includes cached tokens; cached_tokens isn't copied
        # into details (nested prompt_tokens_details) — reads surface via cache_read_tokens.
        usage = _usage(
            input_tokens=120,  # 80 non-cached + 40 cached
            output_tokens=60,
            total_tokens=180,
            requests=1,
            cache_read_tokens=40,
            cache_write_tokens=0,
            details={"reasoning_tokens": 0},
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 80,
            "cache_read_input_tokens": 40,
            "cache_creation_input_tokens": None,
            "output_tokens": 60,
            "total_tokens": 180,
            "num_requests": 1,
        }

    def test_openai_genuine_zero_cache_read_is_none(self):
        # OpenAI's cache_read=0 is only the attribute default (indistinguishable from
        # "not reported"), so surface None — never a fabricated 0.
        usage = _usage(
            input_tokens=120,
            output_tokens=60,
            total_tokens=180,
            requests=1,
            cache_read_tokens=0,
            cache_write_tokens=0,
            details={"reasoning_tokens": 0},
        )
        metrics = _extract_usage_metrics(usage)
        assert metrics["cache_read_input_tokens"] is None
        assert metrics["input_tokens"] == 120

    def test_gemini_shape_cache_read_only(self):
        # Gemini promptTokenCount includes cached content; details carries the
        # cached_content_tokens key (only present when non-zero).
        usage = _usage(
            input_tokens=250,  # 200 non-cached + 50 cached
            output_tokens=70,
            total_tokens=320,
            requests=1,
            cache_read_tokens=50,
            cache_write_tokens=0,
            details={"cached_content_tokens": 50},
        )
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 200,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": None,
            "output_tokens": 70,
            "total_tokens": 320,
            "num_requests": 1,
        }

    def test_deprecated_fields_and_computed_total(self):
        # No total_tokens attr, no cache: total computed from the parts.
        usage = SimpleNamespace(request_tokens=7, response_tokens=3, requests=1)
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 7,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": 3,
            "total_tokens": 10,
            "num_requests": 1,
        }

    def test_zero_cache_is_reported_not_missing(self):
        # A provider genuinely reporting 0 (key present) keeps the 0.
        usage = _usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            requests=1,
            cache_read_tokens=0,
            details={"cache_read_input_tokens": 0},
        )
        metrics = _extract_usage_metrics(usage)
        assert metrics["cache_read_input_tokens"] == 0
        assert metrics["cache_creation_input_tokens"] is None
        assert metrics["input_tokens"] == 10

    def test_input_never_goes_negative(self):
        # Defensive: absurd cache larger than combined input floors at 0.
        usage = _usage(
            input_tokens=10,
            output_tokens=5,
            requests=1,
            details={"cache_read_input_tokens": 40},
        )
        assert _extract_usage_metrics(usage)["input_tokens"] == 0

    def test_bool_and_non_finite_are_rejected(self):
        usage = _usage(
            input_tokens=True, output_tokens=float("nan"), requests=float("inf")
        )
        metrics = _extract_usage_metrics(usage)
        assert metrics["input_tokens"] is None
        assert metrics["output_tokens"] is None
        assert metrics["num_requests"] is None


class TestUsageFallback:
    """Provider-zero usage falls back to completed message content."""

    def test_zero_run_usage_does_not_leak_zeroes(self):
        request_type = type("ModelRequest", (), {})
        response_type = type("ModelResponse", (), {})
        request = request_type()
        request.parts = [SimpleNamespace(content="system prompt and user task")]
        response = response_type()
        response.parts = [SimpleNamespace(content="useful sub-agent response")]
        result = SimpleNamespace(
            usage=lambda: _usage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                requests=0,
            ),
            all_messages=lambda: [request, response],
            output="useful sub-agent response",
        )

        metrics = _safe_usage_metrics(result)

        assert metrics["input_tokens"] > 0
        assert metrics["output_tokens"] > 0
        assert metrics["total_tokens"] == (
            metrics["input_tokens"] + metrics["output_tokens"]
        )
        assert metrics["num_requests"] == 1

    def test_reported_usage_wins_over_estimate(self):
        request_type = type("ModelRequest", (), {})
        response_type = type("ModelResponse", (), {})
        request = request_type()
        request.parts = [SimpleNamespace(content="a much longer prompt")]
        response = response_type()
        response.parts = [SimpleNamespace(content="a much longer response")]
        result = SimpleNamespace(
            usage=lambda: _usage(
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
                requests=1,
            ),
            all_messages=lambda: [request, response],
            output="ignored estimate",
        )

        assert _safe_usage_metrics(result)["input_tokens"] == 11
        assert _safe_usage_metrics(result)["output_tokens"] == 7
        assert _safe_usage_metrics(result)["total_tokens"] == 18


class TestInvokeReportsUsageAndLatency:
    """Integration-ish tests through the registered tool."""

    @pytest.mark.asyncio
    async def test_success_populates_all_fields(self):
        usage = _usage(
            input_tokens=120,
            output_tokens=60,
            total_tokens=180,
            requests=3,
            cache_read_tokens=40,
            cache_write_tokens=0,
            details={"reasoning_tokens": 0},
        )
        out = await _run_invoke(usage=usage)

        assert out.response == "subagent response"
        assert out.error is None
        assert out.input_tokens == 80
        assert out.cache_read_input_tokens == 40
        assert out.cache_creation_input_tokens is None
        assert out.output_tokens == 60
        assert out.total_tokens == 180
        assert out.num_requests == 3
        # Timestamps are UTC ISO-8601 and correctly ordered.
        assert out.start_time is not None and out.end_time is not None
        start = datetime.fromisoformat(out.start_time)
        end = datetime.fromisoformat(out.end_time)
        assert start.tzinfo is not None and end.tzinfo is not None
        assert start <= end
        assert isinstance(out.duration_ms, float)
        assert out.duration_ms >= 0.0

    @pytest.mark.asyncio
    async def test_zero_provider_usage_is_estimated_from_run_messages(self):
        request_type = type("ModelRequest", (), {})
        response_type = type("ModelResponse", (), {})
        request = request_type()
        request.parts = [SimpleNamespace(content="system prompt and user task")]
        response = response_type()
        response.parts = [SimpleNamespace(content="useful sub-agent response")]

        out = await _run_invoke(
            usage=_usage(input_tokens=0, output_tokens=0, total_tokens=0, requests=0),
            result_messages=[request, response],
        )

        assert out.input_tokens > 0
        assert out.output_tokens > 0
        assert out.total_tokens == out.input_tokens + out.output_tokens
        assert out.num_requests == 1

    @pytest.mark.asyncio
    async def test_success_anthropic_reports_creation_bucket(self):
        usage = _usage(
            input_tokens=150,
            output_tokens=50,
            total_tokens=200,
            requests=1,
            cache_read_tokens=30,
            cache_write_tokens=20,
            details={
                "input_tokens": 100,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 30,
                "output_tokens": 50,
            },
        )
        out = await _run_invoke(usage=usage)

        assert out.input_tokens == 100
        assert out.cache_read_input_tokens == 30
        assert out.cache_creation_input_tokens == 20

    @pytest.mark.asyncio
    async def test_success_duration_is_measured(self):
        usage = _usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1)
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
        assert out.cache_read_input_tokens is None
        assert out.cache_creation_input_tokens is None
        assert out.output_tokens is None
        assert out.total_tokens is None
        assert out.num_requests is None
        # Timing is still measured even when usage extraction fails.
        assert out.start_time is not None
        assert out.end_time is not None
        assert isinstance(out.duration_ms, float)
        assert out.duration_ms >= 0.0

    @pytest.mark.asyncio
    async def test_error_path_leaves_all_metrics_none(self):
        out = await _run_invoke(run_raises=True)

        assert out.response is None
        assert out.error is not None
        assert out.input_tokens is None
        assert out.cache_read_input_tokens is None
        assert out.cache_creation_input_tokens is None
        assert out.output_tokens is None
        assert out.total_tokens is None
        assert out.num_requests is None
        assert out.start_time is None
        assert out.end_time is None
        assert out.duration_ms is None


class TestInvokeAgentUnaffected:
    """Locks in that ``invoke_agent`` has ZERO functional/schema changes.

    ``invoke_agent`` must keep returning a plain ``AgentInvokeOutput`` -- the
    original five-field contract -- with no usage/timing fields present at
    all (not even as ``None`` attributes), and must not pay the cost of
    ``time.perf_counter()``/``datetime.now()``/``result.usage()`` calls.
    """

    @pytest.mark.asyncio
    async def test_success_returns_plain_agent_invoke_output(self):
        from code_puppy.tools.agent_tools import (
            AgentInvokeOutput,
            AgentInvokeWithModelOutput,
        )

        usage = _usage(input_tokens=120, output_tokens=60, total_tokens=180, requests=3)
        out = await _run_invoke(usage=usage, use_default=True)

        assert out.response == "subagent response"
        assert out.error is None
        assert type(out) is AgentInvokeOutput
        assert not isinstance(out, AgentInvokeWithModelOutput)
        # The usage/timing fields must not exist on this type at all.
        for field in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "output_tokens",
            "total_tokens",
            "num_requests",
            "start_time",
            "end_time",
            "duration_ms",
        ):
            assert not hasattr(out, field)

    @pytest.mark.asyncio
    async def test_error_path_returns_plain_agent_invoke_output(self):
        from code_puppy.tools.agent_tools import AgentInvokeWithModelOutput

        out = await _run_invoke(run_raises=True, use_default=True)

        assert out.response is None
        assert out.error is not None
        assert not isinstance(out, AgentInvokeWithModelOutput)

    @pytest.mark.asyncio
    async def test_usage_and_clock_are_never_touched(self):
        """invoke_agent must not pay for timing/usage instrumentation at all."""
        usage = _usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1)
        with patch(
            "code_puppy.tools.subagent_invocation.time.perf_counter"
        ) as mock_perf:
            out = await _run_invoke(usage=usage, use_default=True)

        assert out.response == "subagent response"
        mock_perf.assert_not_called()


class TestCancellationPersistence:
    """Ctrl-C (CancelledError) must persist partial work and re-raise.

    ``CancelledError`` derives from ``BaseException``, so the historical
    ``except Exception`` save path never ran on cancellation -- both the
    partial history and the transient session ID were lost. These lock in the
    minimal fix: save-then-re-raise, with a resume hint naming the exact
    session ID.
    """

    @pytest.mark.asyncio
    async def test_cancellation_saves_partial_and_reraises(self):
        from code_puppy.tools.subagent_invocation import drain_interrupted_subagents

        drain_interrupted_subagents()  # isolate module-level queue
        cap = {}
        with pytest.raises(asyncio.CancelledError):
            await _run_invoke(
                run_exc=asyncio.CancelledError(),
                partial_history=["m1", "m2"],
                capture=cap,
                use_default=True,
            )

        cap["save"].assert_called_once()
        save_kwargs = cap["save"].call_args.kwargs
        assert save_kwargs["session_id"] == "test-agent-session-abc123"
        assert save_kwargs["message_history"] == ["m1", "m2"]

        cap["warning"].assert_called_once()
        warn_text = cap["warning"].call_args.args[0]
        assert "interrupted" in warn_text
        assert "test-agent-session-abc123" in warn_text
        assert "resume" in warn_text.lower()

        # The parent agent must be able to learn about this interruption.
        records = drain_interrupted_subagents()
        assert len(records) == 1
        assert records[0] == {
            "agent_name": "test-agent",
            "session_id": "test-agent-session-abc123",
            "saved_count": 2,
        }

    @pytest.mark.asyncio
    async def test_grouped_cancellation_is_treated_as_interruption(self):
        """Async teardown can wrap CancelledError in a BaseExceptionGroup."""
        cap = {}
        grouped = BaseExceptionGroup("teardown", [asyncio.CancelledError()])
        with pytest.raises(BaseExceptionGroup):
            await _run_invoke(
                run_exc=grouped,
                partial_history=["m1"],
                capture=cap,
                use_default=True,
            )

        cap["save"].assert_called_once()
        cap["warning"].assert_called_once()
        assert "interrupted" in cap["warning"].call_args.args[0]

    @pytest.mark.asyncio
    async def test_zero_message_cancellation_reports_nothing_saved(self):
        """A cancel before any turn completes has no history to persist."""
        cap = {}
        with pytest.raises(asyncio.CancelledError):
            await _run_invoke(
                run_exc=asyncio.CancelledError(),
                partial_history=[],
                capture=cap,
                use_default=True,
            )

        cap["save"].assert_not_called()
        warn_text = cap["warning"].call_args.args[0]
        assert "no new messages" in warn_text
        assert "test-agent-session-abc123" in warn_text

    @pytest.mark.asyncio
    async def test_ordinary_failure_still_returns_error_output(self):
        """Non-cancellation crashes keep the existing failure-result contract."""
        from code_puppy.tools.subagent_invocation import drain_interrupted_subagents

        drain_interrupted_subagents()  # isolate module-level queue
        cap = {}
        out = await _run_invoke(
            run_raises=True,
            partial_history=["m1", "m2"],
            capture=cap,
            use_default=True,
        )

        assert out.response is None
        assert out.error is not None
        cap["save"].assert_called_once()
        cap["warning"].assert_not_called()
        # A crash is not an interruption: nothing to resume, no parent note.
        assert drain_interrupted_subagents() == []

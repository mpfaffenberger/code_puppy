"""Tests for per-run usage/latency reporting in subagent_invocation.

These cover the additive token-usage and timing fields on
``AgentInvokeWithModelOutput`` -- scoped EXCLUSIVELY to
``invoke_agent_with_model``. ``invoke_agent`` keeps returning the original,
unmodified ``AgentInvokeOutput`` with no usage/timing fields at all; that
contract is locked in by ``TestInvokeAgentUnaffected`` below.

- success path populates every new field (non-cached input_tokens, cache read /
  creation buckets, output_tokens, num_requests, start_time,
  end_time, duration_ms) with ``start_time <= end_time``
- token buckets are normalized per provider so cached tokens are not
  double-counted (Anthropic / OpenAI / Gemini shapes)
- availability is tracked PER FIELD: an ambiguous zero (the RunUsage dataclass
  default) reports as None, while a genuine zero -- fully cached input, or a
  key explicitly present in ``details`` -- is preserved
- no aggregate total is reported: the four buckets are billed at different
  rates, so summing them would be meaningless for cost
- missing/all-zero provider billing usage stays None and is never estimated
- a failing ``result.usage`` leaves token fields None but still times the run
- an error path (the sub-agent run raises) leaves all new fields None
- ``invoke_agent`` (no model override) never sees any of these fields

The suite is intentionally isolated from ``test_agent_tools_coverage.py`` so the
new behaviour stays focused and readable.
"""

import asyncio
from contextlib import ExitStack, contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.usage import RequestUsage, RunUsage

from code_puppy.agent_execution_context import get_executing_agent
from code_puppy.tools.subagent_invocation import (
    register_invoke_agent,
    register_invoke_agent_with_model,
)
from code_puppy.tools.subagent_usage_metrics import (
    _extract_token_buckets,
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
    capture=None,
    perf=None,
    use_default=False,
    new_messages=(),
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
    if capture is not None:
        capture["agent_config"] = agent_config
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
        result.all_messages.return_value = ["updated-history"]
        result.new_messages.return_value = new_messages
        if usage_raises:
            # `result.usage` is a property since pydantic-ai 1.107; simulate
            # a property that raises on attribute access. (Safe: each
            # MagicMock instance gets its own subclass, so no leak.)
            type(result).usage = PropertyMock(side_effect=RuntimeError("no usage"))
        else:
            result.usage = usage

        async def successful_run(*args, **kwargs):
            if capture is not None:
                capture["executing_agent"] = get_executing_agent()
            return result

        mock_temp_agent.run = AsyncMock(side_effect=successful_run)

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

    @pytest.mark.parametrize(
        "name,usage_kwargs,expected",
        [
            (
                "no cache reported anywhere",
                dict(input_tokens=10, output_tokens=5, requests=2),
                (10, None, None, 5),
            ),
            (
                "anthropic: both cache buckets, via details aliases",
                dict(
                    input_tokens=150,
                    output_tokens=50,
                    requests=1,
                    details={
                        "cache_creation_input_tokens": 20,
                        "cache_read_input_tokens": 30,
                    },
                ),
                (100, 30, 20, 50),
            ),
            (
                "openai: read-only, via the cache_read_tokens attribute",
                dict(
                    input_tokens=120, output_tokens=60, requests=1, cache_read_tokens=40
                ),
                (80, 40, None, 60),
            ),
            (
                "gemini: read-only, via the cached_content_tokens detail alias",
                dict(
                    input_tokens=250,
                    output_tokens=70,
                    requests=1,
                    details={"cached_content_tokens": 50},
                ),
                (200, 50, None, 70),
            ),
            (
                "explicit zero in details is a real reading, not a gap",
                dict(
                    input_tokens=120,
                    output_tokens=60,
                    requests=1,
                    details={"cached_tokens": 0},
                ),
                (120, 0, None, 60),
            ),
        ],
    )
    def test_provider_shapes_map_to_disjoint_buckets(
        self, name, usage_kwargs, expected
    ):
        metrics = _extract_usage_metrics(_usage(**usage_kwargs))

        assert (
            metrics["input_tokens"],
            metrics["cache_read_input_tokens"],
            metrics["cache_creation_input_tokens"],
            metrics["output_tokens"],
        ) == expected, name

    def test_none_usage_yields_all_none(self):
        assert _extract_usage_metrics(None) == {
            "input_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": None,
            "num_requests": None,
        }

    def test_cache_details_aliases_populate_buckets_without_normalized_attrs(self):
        usage = _usage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            output_tokens=50,
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
            "num_requests": 1,
        }

    def test_normalized_cache_aggregates_win_over_detail_aliases(self):
        usage = _usage(
            input_tokens=260,  # 200 base + 50 read + 10 creation
            output_tokens=40,
            requests=2,
            cache_read_tokens=50,
            cache_write_tokens=10,
            details={
                "cache_read_input_tokens": 20,
                "cached_content_tokens": 30,
                "cache_creation_input_tokens": 4,
                "cache_write_tokens": 6,
            },
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 200
        assert metrics["cache_read_input_tokens"] == 50
        assert metrics["cache_creation_input_tokens"] == 10

    def test_anthropic_shape_populates_both_cache_buckets(self):
        # Anthropic folds base + cache_creation + cache_read into input_tokens.
        usage = _usage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            output_tokens=50,
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
            "num_requests": 1,
        }

    def test_deprecated_fields_are_read_when_modern_attrs_are_absent(self):
        usage = SimpleNamespace(request_tokens=7, response_tokens=3, requests=1)
        assert _extract_usage_metrics(usage) == {
            "input_tokens": 7,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": 3,
            "num_requests": 1,
        }

    def test_input_never_goes_negative(self):
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

    def test_zero_requests_is_normalized_to_none(self):
        result = SimpleNamespace(
            usage=_usage(input_tokens=10, output_tokens=5, requests=0)
        )

        assert _safe_usage_metrics(result)["num_requests"] is None


class TestProviderOnlyUsage:
    def test_all_cached_input_preserves_real_zero(self):
        result = SimpleNamespace(
            usage=_usage(
                input_tokens=100,
                cache_read_tokens=100,
                output_tokens=10,
                requests=1,
            ),
        )

        metrics = _safe_usage_metrics(result)

        assert metrics["input_tokens"] == 0
        assert metrics["cache_read_input_tokens"] == 100
        assert metrics["output_tokens"] == 10

    def test_reported_usage_is_returned_unchanged(self):
        result = SimpleNamespace(
            usage=_usage(
                input_tokens=11,
                output_tokens=7,
                requests=1,
            ),
        )

        assert _safe_usage_metrics(result)["input_tokens"] == 11
        assert _safe_usage_metrics(result)["output_tokens"] == 7


class TestPerFieldAvailability:
    def test_positive_input_does_not_vouch_for_omitted_output(self):
        usage = _usage(input_tokens=500, output_tokens=0, requests=1)

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 500
        assert metrics["output_tokens"] is None

    def test_partial_usage_survives_safe_usage_metrics(self):
        result = SimpleNamespace(
            usage=_usage(input_tokens=500, output_tokens=0, requests=1),
        )

        metrics = _safe_usage_metrics(result)

        assert metrics["input_tokens"] == 500
        assert metrics["output_tokens"] is None
        assert metrics["num_requests"] == 1

    def test_explicit_zero_output_detail_is_preserved(self):
        usage = _usage(
            input_tokens=120,
            output_tokens=0,
            requests=1,
            details={"output_tokens": 0},
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 120
        assert metrics["output_tokens"] == 0

    def test_deprecated_alias_used_only_when_modern_attr_is_absent(self):
        usage = SimpleNamespace(
            request_tokens=7,
            response_tokens=3,
            requests=1,
            details={},
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 7
        assert metrics["output_tokens"] == 3

    def test_present_modern_zero_does_not_fall_through_to_alias(self):
        usage = _usage(
            input_tokens=0,
            request_tokens=7,
            output_tokens=0,
            response_tokens=3,
            requests=1,
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] is None
        assert metrics["output_tokens"] is None

    def test_input_is_never_sourced_from_details(self):
        usage = _usage(
            output_tokens=50,
            requests=1,
            cache_read_tokens=30,
            cache_write_tokens=20,
            details={"input_tokens": 100},
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] is None
        assert metrics["cache_read_input_tokens"] == 30
        assert metrics["cache_creation_input_tokens"] == 20
        assert metrics["output_tokens"] == 50


class TestNoAggregateTotalIsReported:
    _EXPECTED_KEYS = {
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "num_requests",
    }

    def test_metrics_dict_exposes_exactly_the_billable_buckets(self):
        usage = _usage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            output_tokens=50,
            requests=1,
            cache_read_tokens=30,
            cache_write_tokens=20,
        )

        metrics = _extract_usage_metrics(usage)

        assert set(metrics) == self._EXPECTED_KEYS
        assert metrics["input_tokens"] == 100
        assert metrics["cache_read_input_tokens"] == 30
        assert metrics["cache_creation_input_tokens"] == 20
        assert metrics["output_tokens"] == 50

    def test_upstream_total_property_is_ignored(self):
        usage = _usage(
            input_tokens=41,
            output_tokens=7,
            total_tokens=999,
            cache_read_tokens=30,
            requests=1,
        )

        assert "total_tokens" not in _extract_usage_metrics(usage)

    def test_empty_metrics_carry_no_total(self):
        assert set(_extract_usage_metrics(None)) == self._EXPECTED_KEYS

    def test_output_type_has_no_total_field(self):
        from code_puppy.tools.agent_tools import AgentInvokeWithModelOutput

        assert "total_tokens" not in AgentInvokeWithModelOutput.model_fields


class TestRealRunUsageShapes:
    def test_input_only_run_reports_no_output(self):
        usage = RunUsage(input_tokens=500, output_tokens=0, requests=1)

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 500
        assert metrics["output_tokens"] is None
        assert "total_tokens" not in metrics

    def test_unavailable_usage_sentinel_stays_unavailable(self):
        usage = RunUsage(requests=1)

        assert _extract_usage_metrics(usage) == {
            "input_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
            "output_tokens": None,
            "num_requests": 1,
        }

    def test_cached_run_splits_every_billable_bucket(self):
        usage = RunUsage(
            input_tokens=150,  # 100 base + 20 creation + 30 read
            cache_read_tokens=30,
            cache_write_tokens=20,
            output_tokens=50,
            requests=1,
        )

        metrics = _extract_usage_metrics(usage)

        assert metrics["input_tokens"] == 100
        assert metrics["cache_read_input_tokens"] == 30
        assert metrics["cache_creation_input_tokens"] == 20
        assert metrics["output_tokens"] == 50
        assert "total_tokens" not in metrics


class TestInvokeReportsUsageAndLatency:
    """Integration-ish tests through the registered tool."""

    @pytest.mark.asyncio
    async def test_success_populates_all_fields(self):
        usage = _usage(
            input_tokens=120,
            output_tokens=60,
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
    async def test_zero_provider_usage_stays_unavailable(self):
        out = await _run_invoke(
            usage=_usage(input_tokens=0, output_tokens=0, requests=1),
        )

        assert out.input_tokens is None
        assert out.output_tokens is None
        assert out.num_requests == 1

    @pytest.mark.asyncio
    async def test_run_scopes_the_loaded_agent_into_execution_context(self):
        capture = {}

        await _run_invoke(usage=_usage(), capture=capture)

        assert capture["executing_agent"] is capture["agent_config"]
        assert get_executing_agent() is None

    @pytest.mark.asyncio
    async def test_success_anthropic_reports_creation_bucket(self):
        usage = _usage(
            input_tokens=150,
            output_tokens=50,
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
        usage = _usage(input_tokens=1, output_tokens=1, requests=1)
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
        assert out.num_requests is None
        assert out.start_time is None
        assert out.end_time is None
        assert out.duration_ms is None


class TestInvokeAgentUnaffected:
    """Locks in that ``invoke_agent`` has ZERO functional/schema changes.

    ``invoke_agent`` must keep returning a plain ``AgentInvokeOutput`` -- the
    original five-field contract -- with no usage/timing fields present at
    all (not even as ``None`` attributes), and must not pay the cost of
    ``time.perf_counter()``/``datetime.now()``/``result.usage`` access.
    """

    @pytest.mark.asyncio
    async def test_success_returns_plain_agent_invoke_output(self):
        from code_puppy.tools.agent_tools import (
            AgentInvokeOutput,
            AgentInvokeWithModelOutput,
        )

        usage = _usage(input_tokens=120, output_tokens=60, requests=3)
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
        usage = _usage(input_tokens=1, output_tokens=1, requests=1)
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


class TestPerRequestWiring:
    @staticmethod
    def _response(input_tokens, output_tokens):
        return ModelResponse(
            parts=[TextPart(content="reply")],
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model_name="gpt-5.6-terra",
        )

    @pytest.mark.asyncio
    async def test_per_request_usage_comes_from_this_run_only(self):
        out = await _run_invoke(
            usage=_usage(input_tokens=100, output_tokens=50, requests=1),
            new_messages=[self._response(100, 50)],
        )

        assert [e.input_tokens for e in out.per_request_usage] == [100]
        assert [e.output_tokens for e in out.per_request_usage] == [50]
        assert out.per_request_usage[0].model_name == "gpt-5.6-terra"

    @pytest.mark.asyncio
    async def test_session_history_is_not_used_for_usage(self):
        out = await _run_invoke(
            usage=_usage(input_tokens=100, output_tokens=50, requests=1),
            new_messages=[self._response(100, 50)],
        )

        assert len(out.per_request_usage) == out.num_requests == 1

    @pytest.mark.asyncio
    async def test_error_path_reports_no_breakdown(self):
        out = await _run_invoke(run_raises=True)

        assert out.per_request_usage is None

    @pytest.mark.asyncio
    async def test_final_context_tokens_is_wired_from_this_run(self):
        out = await _run_invoke(
            usage=_usage(input_tokens=100, output_tokens=50, requests=2),
            new_messages=[self._response(100, 50), self._response(300, 25)],
        )

        assert out.final_context_tokens == 325

    @pytest.mark.asyncio
    async def test_final_context_tokens_none_on_error(self):
        out = await _run_invoke(run_raises=True)

        assert out.final_context_tokens is None

    @pytest.mark.asyncio
    async def test_plain_invoke_agent_has_no_context_field(self):
        out = await _run_invoke(use_default=True)

        assert not hasattr(out, "final_context_tokens")


class TestRealProviderAdapterShapes:
    def test_anthropic_folds_cache_into_input(self):
        raw = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 30,
        }
        usage = RequestUsage.extract(
            {"usage": raw},
            provider="anthropic",
            provider_url="https://api.anthropic.com",
            provider_fallback="anthropic",
        )

        assert usage.input_tokens == 150

        assert _extract_token_buckets(usage) == {
            "input_tokens": 100,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 20,
            "output_tokens": 50,
        }

    def test_openai_prompt_tokens_are_cache_inclusive(self):
        openai_chat = pytest.importorskip("pydantic_ai.models.openai")
        openai_provider = pytest.importorskip("pydantic_ai.providers.openai")
        chat_completion = pytest.importorskip("openai.types.chat.chat_completion")
        message_mod = pytest.importorskip("openai.types.chat.chat_completion_message")
        completion_usage = pytest.importorskip("openai.types.completion_usage")

        model = openai_chat.OpenAIChatModel(
            "gpt-4o", provider=openai_provider.OpenAIProvider(api_key="sk-test")
        )
        response = chat_completion.ChatCompletion(
            id="x",
            model="gpt-4o",
            object="chat.completion",
            created=0,
            choices=[
                chat_completion.Choice(
                    finish_reason="stop",
                    index=0,
                    message=message_mod.ChatCompletionMessage(
                        role="assistant", content="hi"
                    ),
                )
            ],
            usage=completion_usage.CompletionUsage(
                prompt_tokens=120,
                completion_tokens=60,
                total_tokens=180,
                prompt_tokens_details=completion_usage.PromptTokensDetails(
                    cached_tokens=40
                ),
            ),
        )

        usage = model._map_usage(response)

        assert usage.input_tokens == 120
        assert usage.cache_read_tokens == 40

        buckets = _extract_token_buckets(usage)
        assert buckets["input_tokens"] == 80
        assert buckets["cache_read_input_tokens"] == 40
        assert buckets["cache_creation_input_tokens"] is None

    def test_usage_is_a_property_not_a_callable(self):
        from pydantic_ai.usage import RunUsage

        result = SimpleNamespace(usage=RunUsage(input_tokens=10, output_tokens=5))

        assert _safe_usage_metrics(result)["input_tokens"] == 10

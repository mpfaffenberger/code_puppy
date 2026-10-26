import warnings

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage, RunUsage

from code_puppy.tools.agent_tools import SubagentRequestUsage
from code_puppy.tools.subagent_usage_metrics import (
    _extract_token_buckets,
    _extract_usage_metrics,
    build_invoke_output,
    extract_final_context_tokens,
    extract_per_request_usage,
)

LONG_CONTEXT_THRESHOLD = 128_000


def _response(usage: RequestUsage | None, model_name: str | None = "gpt-5.6-terra"):
    return ModelResponse(
        parts=[TextPart(content="reply")],
        usage=usage if usage is not None else RequestUsage(),
        model_name=model_name,
    )


def _history(*responses):
    messages = []
    for index, response in enumerate(responses):
        messages.append(ModelRequest(parts=[UserPromptPart(content=f"step {index}")]))
        messages.append(response)
    return messages


class TestPerRequestExtraction:
    def test_each_call_keeps_its_own_context_length(self):
        entries = extract_per_request_usage(
            _history(
                _response(RequestUsage(input_tokens=60_000, output_tokens=1_000)),
                _response(RequestUsage(input_tokens=130_000, output_tokens=2_000)),
                _response(RequestUsage(input_tokens=45_000, output_tokens=500)),
            )
        )

        assert [e.input_tokens for e in entries] == [60_000, 130_000, 45_000]
        assert [e.output_tokens for e in entries] == [1_000, 2_000, 500]

    def test_non_response_messages_are_skipped(self):
        history = _history(
            _response(RequestUsage(input_tokens=10, output_tokens=5)),
            _response(RequestUsage(input_tokens=20, output_tokens=7)),
        )

        assert len(history) == 4
        assert len(extract_per_request_usage(history)) == 2

    def test_cache_buckets_split_per_entry(self):
        entries = extract_per_request_usage(
            _history(
                _response(
                    RequestUsage(
                        input_tokens=150,
                        cache_read_tokens=30,
                        cache_write_tokens=20,
                        output_tokens=50,
                    )
                )
            )
        )

        entry = entries[0]
        assert entry.input_tokens == 100
        assert entry.cache_read_input_tokens == 30
        assert entry.cache_creation_input_tokens == 20
        assert entry.output_tokens == 50

    def test_no_entries_is_an_empty_list_not_none(self):
        assert extract_per_request_usage([]) == []

    def test_unreadable_history_is_none(self):
        assert extract_per_request_usage(None) is None

    def test_extraction_emits_no_deprecation_warnings(self):
        history = _history(
            _response(RequestUsage(input_tokens=100, output_tokens=50)),
            _response(RequestUsage()),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            extract_per_request_usage(history)

        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


class TestUnavailableUsagePerEntry:
    def test_entry_is_kept_when_every_bucket_is_unavailable(self):
        entries = extract_per_request_usage(
            _history(
                _response(RequestUsage(input_tokens=100, output_tokens=50)),
                _response(RequestUsage()),
            )
        )

        assert len(entries) == 2
        blank = entries[1]
        assert blank.input_tokens is None
        assert blank.output_tokens is None
        assert blank.model_name == "gpt-5.6-terra"

    def test_ambiguous_zero_is_none_but_model_name_survives(self):
        entries = extract_per_request_usage(
            _history(_response(RequestUsage(input_tokens=500, output_tokens=0)))
        )

        entry = entries[0]
        assert entry.input_tokens == 500
        assert entry.output_tokens is None
        assert entry.model_name == "gpt-5.6-terra"

    def test_missing_model_name_is_none(self):
        entries = extract_per_request_usage(
            _history(
                _response(
                    RequestUsage(input_tokens=10, output_tokens=5), model_name=None
                )
            )
        )

        assert entries[0].model_name is None
        assert entries[0].input_tokens == 10


class TestAggregateInvariant:
    def test_entries_sum_to_the_aggregate(self):
        shapes = [
            RequestUsage(input_tokens=60_000, output_tokens=1_000),
            RequestUsage(
                input_tokens=130_000,
                cache_read_tokens=30_000,
                output_tokens=2_000,
            ),
            RequestUsage(input_tokens=45_000, output_tokens=500),
        ]
        run = RunUsage()
        for shape in shapes:
            run.incr(shape)
        run.requests = len(shapes)

        entries = extract_per_request_usage(_history(*[_response(s) for s in shapes]))
        aggregate = _extract_usage_metrics(run)

        assert len(entries) == aggregate["num_requests"]
        assert sum(e.input_tokens for e in entries) == aggregate["input_tokens"]
        assert sum(e.output_tokens for e in entries) == aggregate["output_tokens"]
        assert (
            sum(e.cache_read_input_tokens or 0 for e in entries)
            == aggregate["cache_read_input_tokens"]
        )

    def test_aggregate_alone_cannot_distinguish_tiers(self):
        many_small = [RequestUsage(input_tokens=60_000, output_tokens=1_000)] * 3
        one_large = [RequestUsage(input_tokens=180_000, output_tokens=3_000)]

        def totals(shapes):
            run = RunUsage()
            for shape in shapes:
                run.incr(shape)
            return _extract_usage_metrics(run)["input_tokens"]

        assert totals(many_small) == totals(one_large) == 180_000

        small_entries = extract_per_request_usage(
            _history(*[_response(s) for s in many_small])
        )
        large_entries = extract_per_request_usage(
            _history(*[_response(s) for s in one_large])
        )

        assert all(e.input_tokens <= LONG_CONTEXT_THRESHOLD for e in small_entries)
        assert all(e.input_tokens > LONG_CONTEXT_THRESHOLD for e in large_entries)


class TestMixedModelRuns:
    def test_each_entry_records_the_model_that_served_it(self):
        entries = extract_per_request_usage(
            _history(
                _response(
                    RequestUsage(input_tokens=100, output_tokens=50),
                    model_name="gpt-5.6-luna",
                ),
                _response(
                    RequestUsage(input_tokens=200, output_tokens=80),
                    model_name="gpt-5.6-sol",
                ),
            )
        )

        assert [e.model_name for e in entries] == ["gpt-5.6-luna", "gpt-5.6-sol"]
        assert [e.input_tokens for e in entries] == [100, 200]

    def test_cost_is_derivable_across_tiers_and_models(self):
        rates = {  # (short_input, long_input) per 1M tokens
            "gpt-5.6-terra": (1.00, 2.00),
            "gpt-5.6-luna": (0.10, 0.20),
        }
        entries = extract_per_request_usage(
            _history(
                _response(
                    RequestUsage(input_tokens=60_000, output_tokens=1_000),
                    model_name="gpt-5.6-terra",
                ),
                _response(
                    RequestUsage(input_tokens=130_000, output_tokens=2_000),
                    model_name="gpt-5.6-terra",
                ),
                _response(
                    RequestUsage(input_tokens=200_000, output_tokens=500),
                    model_name="gpt-5.6-luna",
                ),
            )
        )

        cost = 0.0
        for entry in entries:
            short_rate, long_rate = rates[entry.model_name]
            tier = (
                long_rate if entry.input_tokens > LONG_CONTEXT_THRESHOLD else short_rate
            )
            cost += entry.input_tokens / 1_000_000 * tier

        assert round(cost, 4) == round(0.06 + 0.26 + 0.04, 4)


class TestOutputWiring:
    def test_entries_are_serialized_on_the_output_model(self):
        entries = [
            SubagentRequestUsage(
                model_name="gpt-5.6-terra", input_tokens=100, output_tokens=50
            )
        ]

        out = build_invoke_output(
            include_usage_metrics=True,
            response="ok",
            agent_name="tester",
            usage_metrics=_extract_usage_metrics(
                RunUsage(input_tokens=100, output_tokens=50, requests=1)
            ),
            per_request_usage=entries,
        )

        dumped = out.model_dump()["per_request_usage"]
        assert len(dumped) == 1
        assert dumped[0]["model_name"] == "gpt-5.6-terra"
        assert dumped[0]["input_tokens"] == 100
        assert "num_requests" not in dumped[0]

    def test_absent_breakdown_stays_none(self):
        out = build_invoke_output(
            include_usage_metrics=True,
            response="ok",
            agent_name="tester",
        )

        assert out.per_request_usage is None

    def test_invoke_agent_output_has_no_per_request_field(self):
        out = build_invoke_output(
            include_usage_metrics=False,
            response="ok",
            agent_name="tester",
        )

        assert not hasattr(out, "per_request_usage")


class TestResumedSessions:
    @staticmethod
    async def _turns(count):
        agent = Agent(TestModel())
        history = []
        results = []
        for turn in range(count):
            result = await agent.run(f"turn {turn}", message_history=history)
            history = result.all_messages()
            results.append(result)
        return results

    @pytest.mark.asyncio
    async def test_each_turn_reports_only_its_own_calls(self):
        for result in await self._turns(4):
            entries = extract_per_request_usage(result.new_messages())
            aggregate = _extract_usage_metrics(result.usage)

            assert len(entries) == aggregate["num_requests"] == 1
            assert entries[0].input_tokens == aggregate["input_tokens"]

    @pytest.mark.asyncio
    async def test_whole_session_history_would_overcount(self):
        final = (await self._turns(4))[-1]

        whole_session = extract_per_request_usage(final.all_messages())
        this_run = extract_per_request_usage(final.new_messages())

        assert len(whole_session) == 4
        assert len(this_run) == 1
        assert sum(e.input_tokens for e in whole_session) > sum(
            e.input_tokens for e in this_run
        )


class TestExtractorBoundary:
    def test_run_level_metrics_are_rejected(self):
        run_metrics = _extract_usage_metrics(
            RunUsage(input_tokens=100, output_tokens=50, requests=1)
        )

        assert "num_requests" in run_metrics
        with pytest.raises(ValidationError):
            SubagentRequestUsage(model_name="m", **run_metrics)

    def test_bucket_extractor_output_is_accepted_verbatim(self):
        buckets = _extract_token_buckets(
            RequestUsage(input_tokens=100, output_tokens=50)
        )

        assert "num_requests" not in buckets
        entry = SubagentRequestUsage(model_name="m", **buckets)
        assert entry.input_tokens == 100
        assert entry.output_tokens == 50


class TestFinalContextTokens:
    @staticmethod
    def _resp(input_tokens, output_tokens, cache_write=0, cache_read=0):
        return ModelResponse(
            parts=[TextPart(content="reply")],
            usage=RequestUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write,
                cache_read_tokens=cache_read,
            ),
        )

    def test_uses_last_call_not_the_running_total(self):
        history = [
            self._resp(60_000, 1_000),
            self._resp(130_000, 2_000),
            self._resp(45_000, 500),
        ]

        assert extract_final_context_tokens(history) == 45_500

    def test_cached_tokens_count_toward_occupancy(self):
        history = [self._resp(1_000, 200, cache_write=300, cache_read=500)]

        assert extract_final_context_tokens(history) == 1_200

        buckets = _extract_token_buckets(history[-1].usage)
        assert buckets["input_tokens"] + buckets["output_tokens"] == 400

    def test_partial_reporting_yields_none(self):
        input_only = ModelResponse(
            parts=[TextPart(content="r")],
            usage=RequestUsage(input_tokens=100),
        )

        assert extract_final_context_tokens([input_only]) is None

    def test_unavailable_history_yields_none(self):
        assert extract_final_context_tokens([]) is None
        assert extract_final_context_tokens(None) is None

    def test_requests_without_responses_are_ignored(self):
        history = [
            ModelRequest(parts=[UserPromptPart(content="ask")]),
            self._resp(500, 50),
            ModelRequest(parts=[UserPromptPart(content="again")]),
        ]

        assert extract_final_context_tokens(history) == 550

    @pytest.mark.asyncio
    async def test_real_run_reports_less_than_the_aggregate(self):
        agent = Agent(TestModel())
        result = await agent.run("hello")

        final_context = extract_final_context_tokens(result.new_messages())
        assert final_context is not None
        assert final_context > 0

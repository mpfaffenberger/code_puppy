"""Coverage for FallbackChainModel: permanent, sticky degradation through an
ordered model chain when the current model's budget (quota or context
window) is exhausted -- as opposed to RoundRobinModel (load distribution)
or the streaming-retry mechanism in agents/_runtime.py (same-model retry on
transient errors like a 429 rate-limit or a 5xx blip).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from code_puppy.fallback_chain_model import (
    DEFAULT_BUDGET_EXHAUSTED_SNIPPETS,
    DEFAULT_FALLBACK_CHAIN_MODELS,
    DEFAULT_FALLBACK_CHAIN_NAME,
    FallbackChainExhausted,
    FallbackChainModel,
    add_default_fallback_chain,
    is_budget_exhausted_error,
)


def _make_model(name: str, response=None, side_effect=None):
    """A minimal fake pydantic-ai Model with a mockable async request()."""
    model = MagicMock()
    model.model_name = name
    model.system = "test"
    model.base_url = None
    model.prepare_request = MagicMock(
        side_effect=lambda settings, params: (settings, params)
    )
    if side_effect is not None:
        model.request = AsyncMock(side_effect=side_effect)
    else:
        model.request = AsyncMock(return_value=response or MagicMock())
    return model


class TestDefaultFallbackChain:
    def test_default_model_order_is_exact(self):
        assert DEFAULT_FALLBACK_CHAIN_MODELS == (
            "claude-4-8-opus-long",
            "claude-5-sonnet",
            "gpt-5.6-luna",
        )

    @pytest.mark.parametrize("missing_name", DEFAULT_FALLBACK_CHAIN_MODELS)
    def test_alias_is_added_only_when_every_child_exists(self, missing_name):
        config = {
            name: {"type": "openai", "name": name}
            for name in DEFAULT_FALLBACK_CHAIN_MODELS
            if name != missing_name
        }

        assert add_default_fallback_chain(config) is False
        assert DEFAULT_FALLBACK_CHAIN_NAME not in config

    def test_alias_preserves_existing_definition(self):
        existing_alias = {
            "type": "round_robin",
            "models": ["existing-one", "existing-two"],
            "context_length": 1234,
        }
        config = {DEFAULT_FALLBACK_CHAIN_NAME: existing_alias}

        assert add_default_fallback_chain(config) is False
        assert config[DEFAULT_FALLBACK_CHAIN_NAME] is existing_alias

    def test_alias_uses_exact_order_and_smallest_child_context(self):
        config = {
            "claude-4-8-opus-long": {
                "type": "anthropic",
                "context_length": 1_000_000,
            },
            "claude-5-sonnet": {
                "type": "anthropic",
                "context_length": 200_000,
            },
            "gpt-5.6-luna": {
                "type": "openai",
                "context_length": 128_000,
            },
        }

        assert add_default_fallback_chain(config) is True
        assert config[DEFAULT_FALLBACK_CHAIN_NAME] == {
            "type": "fallback_chain",
            "models": list(DEFAULT_FALLBACK_CHAIN_MODELS),
            "context_length": 128_000,
        }


class TestIsBudgetExhaustedError:
    @pytest.mark.parametrize(
        "message",
        [
            "Error code: 400 - insufficient_quota",
            "This model's maximum context length is 128000 tokens",
            "You have exceeded your current quota, please check your plan",
            "context_length_exceeded",
            "monthly quota has been used up",
            "prompt is too long for this model",
        ],
    )
    def test_recognizes_known_exhaustion_phrasings(self, message):
        assert is_budget_exhausted_error(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "429 Too Many Requests",
            "rate limit exceeded, please retry",
            "503 Service Unavailable",
            "connection error",
            "invalid API key",
        ],
    )
    def test_does_not_flag_transient_or_unrelated_errors(self, message):
        """Plain rate-limit / transport errors must NOT trigger a permanent
        model switch -- those are the same-model streaming-retry mechanism's
        job (agents/_runtime.py), not this class's.
        """
        assert is_budget_exhausted_error(RuntimeError(message)) is False

    def test_checks_structured_body_not_just_top_level_message(self):
        """Providers often bury the real code a level deeper than the
        top-level exception message (OpenAI's ``error.code`` field)."""
        exc = ModelHTTPError(
            status_code=400,
            model_name="gpt-mega",
            body={"error": {"code": "insufficient_quota", "message": "nope"}},
        )
        assert is_budget_exhausted_error(exc) is True

    def test_walks_the_cause_chain(self):
        inner = RuntimeError("context_length_exceeded")
        outer = RuntimeError("wrapped")
        outer.__cause__ = inner
        assert is_budget_exhausted_error(outer) is True

    def test_custom_extra_snippets_extend_defaults(self):
        exc = RuntimeError("WALMART_LLM_GATEWAY: large-tier budget depleted")
        assert is_budget_exhausted_error(exc) is False
        assert (
            is_budget_exhausted_error(exc, extra_snippets=["budget depleted"]) is True
        )

    def test_default_snippets_are_all_lowercase(self):
        """The matcher lowercases input; source-of-truth snippets should be
        lowercase too so a future edit doesn't accidentally add a
        case-sensitive dead entry.
        """
        assert all(s == s.lower() for s in DEFAULT_BUDGET_EXHAUSTED_SNIPPETS)


class TestFallbackChainModelRequest:
    @pytest.mark.asyncio
    async def test_uses_first_model_when_healthy(self):
        good = _make_model("large", response="ok-large")
        backup = _make_model("free")
        chain = FallbackChainModel(good, backup)

        result = await chain.request([], None, MagicMock())

        assert result == "ok-large"
        good.request.assert_awaited_once()
        backup.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_and_completes_the_request(self):
        exhausted = _make_model("large", side_effect=RuntimeError("insufficient_quota"))
        healthy = _make_model("medium", response="ok-medium")
        chain = FallbackChainModel(exhausted, healthy)

        with patch("code_puppy.fallback_chain_model.emit_warning") as mock_warn:
            result = await chain.request([], None, MagicMock())

        assert result == "ok-medium"
        assert mock_warn.called
        assert "large" in mock_warn.call_args[0][0]
        assert "medium" in mock_warn.call_args[0][0]

    @pytest.mark.asyncio
    async def test_stays_on_the_fallback_model_for_subsequent_requests(self):
        """The switch is sticky -- once we've moved past model 0, we never
        try it again, even though a naive retry-from-scratch would.
        """
        exhausted = _make_model("large", side_effect=RuntimeError("insufficient_quota"))
        healthy = _make_model("medium", response="ok-medium")
        chain = FallbackChainModel(exhausted, healthy)

        with patch("code_puppy.fallback_chain_model.emit_warning"):
            await chain.request([], None, MagicMock())
            await chain.request([], None, MagicMock())
            await chain.request([], None, MagicMock())

        assert exhausted.request.await_count == 1  # only ever tried once
        assert healthy.request.await_count == 3

    @pytest.mark.asyncio
    async def test_default_chain_skips_two_quota_exhausted_models_and_sticks_to_third(
        self,
    ):
        """The catalog's Opus -> Sonnet -> Luna order is permanent after fallback."""
        opus = _make_model(
            "claude-4-8-opus-long",
            side_effect=RuntimeError("claude-4-8-opus-long quota exhausted"),
        )
        sonnet = _make_model(
            "claude-5-sonnet",
            side_effect=RuntimeError("claude-5-sonnet quota exceeded"),
        )
        luna = _make_model("gpt-5.6-luna", response="ok-luna")
        chain = FallbackChainModel(opus, sonnet, luna)

        with patch("code_puppy.fallback_chain_model.emit_warning") as mock_warn:
            first_result = await chain.request([], None, MagicMock())
            second_result = await chain.request([], None, MagicMock())

        assert [model.model_name for model in chain.models] == list(
            DEFAULT_FALLBACK_CHAIN_MODELS
        )
        assert first_result == second_result == "ok-luna"
        assert opus.request.await_count == 1
        assert sonnet.request.await_count == 1
        assert luna.request.await_count == 2
        assert mock_warn.call_count == 2
        assert chain.model_name.endswith("active=gpt-5.6-luna")

    @pytest.mark.asyncio
    async def test_exhausting_every_model_raises_fallback_chain_exhausted(self):
        first = _make_model("large", side_effect=RuntimeError("insufficient_quota"))
        second = _make_model(
            "free", side_effect=RuntimeError("context_length_exceeded")
        )
        chain = FallbackChainModel(first, second)

        with patch("code_puppy.fallback_chain_model.emit_warning"):
            with pytest.raises(FallbackChainExhausted):
                await chain.request([], None, MagicMock())

    @pytest.mark.asyncio
    async def test_non_budget_errors_propagate_immediately_without_switching(self):
        """A real bug/auth failure must surface as itself, not get masked
        by silently trying a different model.
        """
        broken = _make_model("large", side_effect=ValueError("bad api key"))
        backup = _make_model("free")
        chain = FallbackChainModel(broken, backup)

        with pytest.raises(ValueError, match="bad api key"):
            await chain.request([], None, MagicMock())

        backup.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_fallback_on_predicate_is_honoured(self):
        """A caller-supplied predicate fully replaces the default
        budget-exhaustion classifier."""
        model_a = _make_model("a", side_effect=RuntimeError("anything at all"))
        model_b = _make_model("b", response="ok-b")
        chain = FallbackChainModel(model_a, model_b, fallback_on=lambda exc: True)

        with patch("code_puppy.fallback_chain_model.emit_warning"):
            result = await chain.request([], None, MagicMock())

        assert result == "ok-b"

    def test_requires_at_least_one_model(self):
        with pytest.raises(ValueError):
            FallbackChainModel()

    @pytest.mark.asyncio
    async def test_child_specific_settings_follow_the_request_after_fallback(self):
        exhausted = _make_model("large", side_effect=RuntimeError("insufficient_quota"))
        healthy = _make_model("medium", response="ok-medium")
        first_settings = {"max_tokens": 1111}
        second_settings = {"max_tokens": 2222, "temperature": 0.2}
        chain = FallbackChainModel(
            exhausted,
            healthy,
            child_settings=[first_settings, second_settings],
        )

        with patch("code_puppy.fallback_chain_model.emit_warning"):
            result = await chain.request([], None, MagicMock())

        assert result == "ok-medium"
        assert exhausted.prepare_request.call_args.args[0] == first_settings
        assert healthy.prepare_request.call_args.args[0] == second_settings
        assert healthy.request.call_args.args[1] == second_settings

    @pytest.mark.parametrize("child_settings", [[], [None, None, None]])
    def test_child_settings_must_match_model_count(self, child_settings):
        with pytest.raises(
            ValueError, match="child_settings must match the number of models"
        ):
            FallbackChainModel(
                _make_model("large"),
                _make_model("medium"),
                child_settings=child_settings,
            )


class TestFallbackChainModelName:
    def test_model_name_reports_chain_and_active_model(self):
        chain = FallbackChainModel(_make_model("large"), _make_model("free"))
        assert chain.model_name == "fallback_chain:large,free:active=large"

    @pytest.mark.asyncio
    async def test_model_name_updates_after_a_switch(self):
        exhausted = _make_model("large", side_effect=RuntimeError("insufficient_quota"))
        healthy = _make_model("free", response="ok")
        chain = FallbackChainModel(exhausted, healthy)

        with patch("code_puppy.fallback_chain_model.emit_warning"):
            await chain.request([], None, MagicMock())

        assert chain.model_name == "fallback_chain:large,free:active=free"

    def test_system_and_base_url_delegate_to_the_active_model(self):
        active = _make_model("large")
        active.system = "anthropic"
        active.base_url = "https://api.example.com"
        chain = FallbackChainModel(active, _make_model("free"))

        assert chain.system == "anthropic"
        assert chain.base_url == "https://api.example.com"


class TestFallbackChainModelConcurrency:
    @pytest.mark.asyncio
    async def test_second_caller_sees_already_advanced_index_without_double_warning(
        self,
    ):
        """Simulates two in-flight requests both hitting exhaustion on model
        0 -- the second call to _advance_past_exhausted for the SAME
        exhausted index must be a no-op (index already moved), not a second
        warning/advance.
        """
        exhausted = _make_model("large")
        healthy = _make_model("free")
        chain = FallbackChainModel(exhausted, healthy)

        with patch("code_puppy.fallback_chain_model.emit_warning") as mock_warn:
            first = chain._advance_past_exhausted(0, RuntimeError("insufficient_quota"))
            second = chain._advance_past_exhausted(
                0, RuntimeError("insufficient_quota")
            )

        assert first is True
        assert second is True
        assert mock_warn.call_count == 1
        assert chain._current_index == 1


class TestFallbackChainModelRequestStream:
    @pytest.mark.asyncio
    async def test_streams_from_first_model_when_healthy(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def good_stream(*_a, **_kw):
            yield "stream-large"

        good = _make_model("large")
        good.request_stream = good_stream
        backup = _make_model("free")

        chain = FallbackChainModel(good, backup)
        async with chain.request_stream([], None, MagicMock()) as response:
            assert response == "stream-large"

    @pytest.mark.asyncio
    async def test_falls_back_to_next_model_on_stream_exhaustion(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def dead_stream(*_a, **_kw):
            raise RuntimeError("context_length_exceeded")
            yield  # pragma: no cover - unreachable, satisfies generator shape

        @asynccontextmanager
        async def healthy_stream(*_a, **_kw):
            yield "stream-free"

        exhausted = _make_model("large")
        exhausted.request_stream = dead_stream
        healthy = _make_model("free")
        healthy.request_stream = healthy_stream

        chain = FallbackChainModel(exhausted, healthy)
        with patch("code_puppy.fallback_chain_model.emit_warning"):
            async with chain.request_stream([], None, MagicMock()) as response:
                assert response == "stream-free"
        assert chain.model_name.endswith("active=free")

    @pytest.mark.asyncio
    async def test_stream_exhaustion_of_entire_chain_raises(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def dead_stream(*_a, **_kw):
            raise RuntimeError("insufficient_quota")
            yield  # pragma: no cover - unreachable, satisfies generator shape

        first = _make_model("large")
        first.request_stream = dead_stream
        second = _make_model("free")
        second.request_stream = dead_stream

        chain = FallbackChainModel(first, second)
        with patch("code_puppy.fallback_chain_model.emit_warning"):
            with pytest.raises(FallbackChainExhausted):
                async with chain.request_stream([], None, MagicMock()):
                    pass  # pragma: no cover - exhausted before yielding

    @pytest.mark.asyncio
    async def test_stream_non_budget_error_propagates_without_switching(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def broken_stream(*_a, **_kw):
            raise ValueError("bad api key")
            yield  # pragma: no cover - unreachable, satisfies generator shape

        broken = _make_model("large")
        broken.request_stream = broken_stream
        backup = _make_model("free")

        chain = FallbackChainModel(broken, backup)
        with pytest.raises(ValueError, match="bad api key"):
            async with chain.request_stream([], None, MagicMock()):
                pass  # pragma: no cover - never reached, error raised first

        assert chain.model_name.endswith("active=large")  # no switch happened

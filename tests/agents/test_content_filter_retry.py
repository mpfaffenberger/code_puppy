"""Tests for Azure content-filter false-positive detection and auto-retry.

Covers:
  - ``is_content_filter_response`` pattern matching (positive & negative)
  - ``_retry_on_content_filter`` auto-retry behaviour inside the agent run loop
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.content_filter_retry import (
    CONTENT_FILTER_RETRY_DELAY,
    CONTENT_FILTER_RETRY_PROMPT,
    MAX_CONTENT_FILTER_RETRIES,
    _MAX_REFUSAL_LENGTH,
    _REFUSAL_PATTERNS,
    is_content_filter_response,
)


# ---------------------------------------------------------------------------
# is_content_filter_response — detection tests
# ---------------------------------------------------------------------------


class TestIsContentFilterResponse:
    """Unit tests for the detection heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "I'm sorry, but I cannot assist with that request.",
            "I'm sorry, but I can't assist with that.",
            "I'm sorry, but I cannot help with that.",
            "I'm sorry, but I can't help with that request.",
            "I cannot assist with that request.",
            "Sorry, but I can't help with that.",
            "I'm not able to assist with that.",
            "I'm unable to help with that request.",
            "  I'm sorry, but I cannot assist with that.  ",  # whitespace
            "I'M SORRY, BUT I CANNOT ASSIST WITH THAT REQUEST.",  # uppercase
        ],
    )
    def test_detects_known_refusal_patterns(self, text: str):
        assert is_content_filter_response(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            # Legitimate short responses that should NOT trigger
            "Hello! How can I help you today?",
            "Sure, I'd be happy to help with that.",
            "Here's the code you requested.",
            "",
            # None value
            None,
            # Long response that happens to contain the phrase buried inside
            "Here's a 500-word essay. " * 20
            + "I'm sorry, but I cannot assist with that."
            + " More text follows. " * 10,
        ],
    )
    def test_ignores_non_filter_responses(self, text):
        assert is_content_filter_response(text) is False

    def test_length_boundary(self):
        """Responses longer than _MAX_REFUSAL_LENGTH are never matched."""
        # Pad a known refusal to exactly the limit → should still match
        base = "I'm sorry, but I cannot assist with that."
        padded_at_limit = base + " " * (_MAX_REFUSAL_LENGTH - len(base))
        assert len(padded_at_limit.strip()) <= _MAX_REFUSAL_LENGTH
        assert is_content_filter_response(padded_at_limit) is True

        # One char over → no match
        padded_over = base + "x" * (_MAX_REFUSAL_LENGTH - len(base) + 1)
        assert is_content_filter_response(padded_over) is False

    def test_all_patterns_are_lowercase(self):
        """Invariant: every pattern string is already lowercased."""
        for p in _REFUSAL_PATTERNS:
            assert p == p.lower(), f"Pattern should be lowercase: {p!r}"


# ---------------------------------------------------------------------------
# _retry_on_content_filter — retry logic tests
# ---------------------------------------------------------------------------


def _make_result(output: str, messages=None):
    """Build a lightweight stand-in for a pydantic-ai RunResult."""
    return SimpleNamespace(
        output=output,
        all_messages=lambda: messages or [],
    )


class TestRetryOnContentFilter:
    """Integration-style tests for the retry wrapper.

    We replicate the nested-function structure from base_agent so we can
    test in isolation without instantiating the full agent.
    """

    @staticmethod
    def _build_retry_harness(
        streaming_retry_side_effects,
        set_history_mock=None,
        get_history_mock=None,
    ):
        """Build a self-contained ``_retry_on_content_filter`` callable.

        ``streaming_retry_side_effects`` is a list of RunResult-like objects
        that ``_run_with_streaming_retry`` returns on successive calls.
        """
        call_count = 0

        async def fake_streaming_retry(factory):
            nonlocal call_count
            result = streaming_retry_side_effects[call_count]
            call_count += 1
            return result

        _set_history = set_history_mock or MagicMock()
        _get_history = get_history_mock or MagicMock(return_value=[])

        # Minimal stand-ins for closure variables the real function captures
        class FakeSelf:
            set_message_history = _set_history
            get_message_history = _get_history

        fake_self = FakeSelf()
        usage_limits = None
        stream_handler = None
        kwargs: dict = {}
        pydantic_agent = MagicMock()

        from code_puppy.content_filter_retry import (
            CONTENT_FILTER_RETRY_DELAY,
            CONTENT_FILTER_RETRY_PROMPT,
            MAX_CONTENT_FILTER_RETRIES,
            is_content_filter_response,
        )
        from code_puppy.messaging import emit_warning

        async def _retry_on_content_filter(result_):
            for cf_attempt in range(MAX_CONTENT_FILTER_RETRIES):
                output = getattr(result_, "output", None) or ""
                if not is_content_filter_response(output):
                    return result_
                emit_warning(
                    f"⚡ Azure content filter false-positive detected, "
                    f"auto-retrying ({cf_attempt + 1}/{MAX_CONTENT_FILTER_RETRIES})…"
                )
                if hasattr(result_, "all_messages"):
                    fake_self.set_message_history(list(result_.all_messages()))
                await asyncio.sleep(CONTENT_FILTER_RETRY_DELAY)
                result_ = await fake_streaming_retry(
                    lambda: pydantic_agent.run(
                        CONTENT_FILTER_RETRY_PROMPT,
                        message_history=fake_self.get_message_history(),
                        usage_limits=usage_limits,
                        event_stream_handler=stream_handler,
                        **kwargs,
                    )
                )
            return result_

        return _retry_on_content_filter, fake_self, lambda: call_count

    @pytest.mark.asyncio
    async def test_passthrough_when_no_filter(self):
        """Normal responses are returned immediately, no retry."""
        good = _make_result("Here's your code!")
        retry_fn, _, get_calls = self._build_retry_harness([good])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_fn(good)

        assert result.output == "Here's your code!"
        assert get_calls() == 0  # no extra calls

    @pytest.mark.asyncio
    async def test_retries_on_content_filter_then_succeeds(self):
        """Content filter response triggers retry; second attempt succeeds."""
        filtered = _make_result(
            "I'm sorry, but I cannot assist with that request."
        )
        good = _make_result("Here's the real answer!")
        retry_fn, fake_self, get_calls = self._build_retry_harness([good])

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with patch("code_puppy.messaging.emit_warning"):
                result = await retry_fn(filtered)

        assert result.output == "Here's the real answer!"
        assert get_calls() == 1
        fake_self.set_message_history.assert_called_once()
        mock_sleep.assert_awaited_once_with(CONTENT_FILTER_RETRY_DELAY)

    @pytest.mark.asyncio
    async def test_exhausts_retries_returns_last(self):
        """If every retry is also filtered, returns the last result."""
        filtered1 = _make_result(
            "I'm sorry, but I cannot assist with that request."
        )
        filtered2 = _make_result(
            "I'm sorry, but I can't help with that."
        )
        # Both retries are also filtered
        retry_fn, _, get_calls = self._build_retry_harness(
            [filtered1, filtered2]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("code_puppy.messaging.emit_warning"):
                result = await retry_fn(filtered1)

        # Should have retried MAX_CONTENT_FILTER_RETRIES times
        assert get_calls() == MAX_CONTENT_FILTER_RETRIES
        # Returns the last (still-filtered) result rather than crashing
        assert is_content_filter_response(result.output)

    @pytest.mark.asyncio
    async def test_history_updated_before_retry(self):
        """Message history is saved before each retry attempt."""
        msgs = [{"role": "assistant", "content": "sorry"}]
        filtered = _make_result(
            "I'm sorry, but I cannot assist with that request.",
            messages=msgs,
        )
        good = _make_result("All good now!")
        set_hist = MagicMock()
        retry_fn, _, _ = self._build_retry_harness(
            [good], set_history_mock=set_hist
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("code_puppy.messaging.emit_warning"):
                await retry_fn(filtered)

        set_hist.assert_called_once_with(msgs)

    @pytest.mark.asyncio
    async def test_result_with_no_output_attr_passthrough(self):
        """Objects without an ``output`` attribute pass through safely."""
        weird = SimpleNamespace(data="something")
        retry_fn, _, get_calls = self._build_retry_harness([])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_fn(weird)

        assert result is weird
        assert get_calls() == 0

    @pytest.mark.asyncio
    async def test_none_result_passthrough(self):
        """A ``None`` result (e.g. cancelled task) passes through."""
        retry_fn, _, get_calls = self._build_retry_harness([])

        # None doesn't have .output so getattr returns ""
        none_result = SimpleNamespace(output=None)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_fn(none_result)

        assert result.output is None
        assert get_calls() == 0

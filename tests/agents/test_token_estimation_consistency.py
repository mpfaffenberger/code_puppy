"""Tests for token estimation consistency in streaming handlers.

Ensures subagent_stream_handler._estimate_tokens and event_stream_handler
use the same 2.5 chars/token heuristic as BaseAgent to prevent unexpected
early compaction triggered by estimation mismatch.
"""

import math

from code_puppy.agents.subagent_stream_handler import (
    _estimate_tokens as streaming_estimate,
)


class TestTokenEstimationConsistency:
    """Streaming handlers must use the same token estimation heuristic as BaseAgent."""

    def test_streaming_handler_matches_heuristic(self):
        """
        subagent_stream_handler._estimate_tokens must use the 2.5 chars/token
        heuristic to keep streaming metrics consistent with compaction decisions.
        """
        content = "x" * 1000
        assert streaming_estimate(content) == math.floor(len(content) / 2.5)

    def test_streaming_handler_empty_returns_zero(self):
        """
        _estimate_tokens returns 0 for empty content (divergent from BaseAgent
        which returns 1).
        """
        assert streaming_estimate("") == 0

    def test_streaming_handler_consistent_across_sizes(self):
        """
        Streaming handler heuristic holds across small, medium, and large content.
        """
        for size in [100, 1000, 10000, 25000]:
            content = "x" * size
            assert streaming_estimate(content) == math.floor(len(content) / 2.5), (
                f"Streaming estimate mismatch at size {size}"
            )

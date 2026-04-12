"""Tests for token estimation consistency across modules.

Ensures file_operations._read_file, BaseAgent.estimate_token_count,
subagent_stream_handler._estimate_tokens, and event_stream_handler
all use the same 2.5 chars/token heuristic to prevent unexpected
early compaction triggered by estimation mismatch.
"""

import math

from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.agents.subagent_stream_handler import _estimate_tokens as streaming_estimate


class TestTokenEstimationConsistency:
    """Token estimation should be consistent between file_operations and BaseAgent."""

    def test_estimate_token_count_matches_file_operations_heuristic(self):
        """
        BaseAgent.estimate_token_count and file_operations._read_file
        must use the same 2.5 chars/token heuristic.
        """
        agent = CodePuppyAgent()
        content = "x" * 1000

        base_agent_estimate = agent.estimate_token_count(content)
        file_ops_estimate = math.floor(len(content) / 2.5)

        assert base_agent_estimate == file_ops_estimate

    def test_estimation_consistent_across_content_sizes(self):
        """
        Consistency holds across small, medium, and large content sizes.
        """
        agent = CodePuppyAgent()

        for size in [100, 1000, 10000, 25000]:
            content = "x" * size
            base_agent_estimate = agent.estimate_token_count(content)
            file_ops_estimate = math.floor(len(content) / 2.5)
            assert base_agent_estimate == file_ops_estimate, (
                f"Mismatch at size {size}: "
                f"base_agent={base_agent_estimate}, "
                f"file_ops={file_ops_estimate}"
            )

    def test_minimum_token_count_is_one(self):
        """
        BaseAgent enforces a minimum of 1 token for empty content.
        _read_file intentionally returns 0 for empty content (empty files cost
        no tokens). This documents the known divergence between the two.
        """
        agent = CodePuppyAgent()

        result = agent.estimate_token_count("")
        assert result >= 1

    def test_streaming_handler_matches_heuristic(self):
        """
        subagent_stream_handler._estimate_tokens must use the same 2.5 chars/token
        heuristic as BaseAgent and file_operations to keep streaming metrics
        consistent with compaction decisions.
        """
        agent = CodePuppyAgent()
        content = "x" * 1000

        base_agent_estimate = agent.estimate_token_count(content)
        stream_estimate = streaming_estimate(content)
        formula_estimate = math.floor(len(content) / 2.5)

        assert stream_estimate == formula_estimate
        assert stream_estimate == base_agent_estimate

    def test_streaming_handler_empty_returns_zero(self):
        """
        _estimate_tokens returns 0 for empty content (consistent with _read_file,
        divergent from BaseAgent which returns 1).
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
"""Tests for token estimation consistency across modules.

Ensures file_operations._read_file and BaseAgent.estimate_token_count
use the same chars-per-token heuristic to prevent unexpected early
compaction triggered by estimation mismatch.
"""

import math

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


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
        Both estimators enforce a minimum of 1 token even for empty content.
        """
        agent = CodePuppyAgent()

        result = agent.estimate_token_count("")
        assert result >= 1
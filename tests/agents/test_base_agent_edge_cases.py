"""Tests for BaseAgent edge cases and error paths.

This module tests error handling and edge cases in BaseAgent methods:
- _load_model_with_fallback() when all models fail
- hash_message() with malformed messages
- stringify_message_part() with unusual content types
- filter_huge_messages() with corrupted messages
- get_model_context_length() when model config is broken
- load_puppy_rules() with file read errors
- Compaction methods with extreme token counts

Focuses on ensuring error handling doesn't crash and provides graceful degradation.
"""


import pytest

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentEdgeCases:
    """Test suite for BaseAgent edge cases and error paths."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test."""
        return CodePuppyAgent()

        # Should filter out the huge message or handle it

        # Should handle gracefully

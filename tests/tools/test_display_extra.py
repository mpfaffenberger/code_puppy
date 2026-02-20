"""Extra tests for display.py line 39 (subagent skip)."""

from unittest.mock import patch


class TestDisplaySubagentSkip:
    @patch("code_puppy.tools.display.get_subagent_verbose", return_value=False)
    @patch("code_puppy.tools.display.is_subagent", return_value=True)
    def test_skips_for_subagent(self, mock_sub, mock_verbose):
        from code_puppy.tools.display import display_non_streamed_result

        # Should return early without doing anything
        result = display_non_streamed_result("test content")
        assert result is None

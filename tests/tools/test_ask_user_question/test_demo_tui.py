"""Tests for ask_user_question demo_tui module."""

from unittest.mock import patch

from code_puppy.tools.ask_user_question.models import AskUserQuestionOutput


class TestDemoTuiMain:
    def test_main_calls_ask_user_question(self):
        mock_output = AskUserQuestionOutput(
            answers=[], cancelled=True, error=None, timed_out=False
        )
        with patch(
            "code_puppy.tools.ask_user_question.demo_tui.ask_user_question",
            return_value=mock_output,
        ) as mock_ask:
            from code_puppy.tools.ask_user_question.demo_tui import main

            main()
            mock_ask.assert_called_once()
            args = mock_ask.call_args[0][0]
            assert isinstance(args, list)
            assert len(args) == 1
            assert args[0]["header"] == "Database"

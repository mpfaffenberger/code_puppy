"""Tests for model_picker_completion.py to achieve 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.document import Document


class TestLoadModelNames:
    def test_returns_model_list(self):
        from code_puppy.command_line.model_picker_completion import load_model_names

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4": {}, "claude-3": {}},
        ):
            result = load_model_names()
            assert "gpt-4" in result
            assert "claude-3" in result


class TestGetActiveModel:
    def test_returns_model_name(self):
        from code_puppy.command_line.model_picker_completion import get_active_model

        with patch(
            "code_puppy.command_line.model_picker_completion.get_global_model_name",
            return_value="gpt-4",
        ):
            assert get_active_model() == "gpt-4"


class TestSetActiveModel:
    def test_delegates_to_set_model(self):
        from code_puppy.command_line.model_picker_completion import set_active_model

        with patch(
            "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
        ) as mock_set:
            set_active_model("gpt-4")
            mock_set.assert_called_once_with("gpt-4")


class TestModelNameCompleter:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_no_trigger(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4": {}},
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/other "), None))
            assert completions == []

    def test_shows_all_models(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}, "claude-3": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/model "), None))
            assert len(completions) == 2
            # Check that the active model has "(selected)" meta
            metas = {c.text: str(c.display_meta) for c in completions}
            assert "selected" in metas["gpt-4"]
            assert "selected" not in metas["claude-3"]

    def test_filters_by_prefix(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}, "claude-3": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/model cl"), None))
            assert len(completions) == 1
            assert completions[0].text == "claude-3"


class TestFindMatchingModel:
    def test_exact_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("gpt-4", ["gpt-4", "claude-3"]) == "gpt-4"

    def test_case_insensitive(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("GPT-4", ["gpt-4"]) == "gpt-4"

    def test_input_starts_with_model(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert (
            _find_matching_model("gpt-4 tell me a joke", ["gpt-4", "gpt-4o"]) == "gpt-4"
        )

    def test_prefix_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("gpt", ["gpt-4", "claude-3"]) == "gpt-4"

    def test_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("xyz", ["gpt-4", "claude-3"]) is None

    def test_longest_model_wins(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        # "gpt-4-turbo hello" should match "gpt-4-turbo" not "gpt-4"
        assert (
            _find_matching_model("gpt-4-turbo hello", ["gpt-4", "gpt-4-turbo"])
            == "gpt-4-turbo"
        )


class TestUpdateModelInInput:
    def test_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ) as mock_set,
        ):
            result = update_model_in_input("/model gpt-4")
            mock_set.assert_called_once_with("gpt-4")
            # After stripping the command and model, should be empty or None
            assert result is not None  # Empty string after strip

    def test_m_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ) as mock_set,
        ):
            update_model_in_input("/m gpt-4")
            mock_set.assert_called_once_with("gpt-4")

    def test_no_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        assert update_model_in_input("hello world") is None

    def test_model_command_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input("/model xyz") is None

    def test_m_command_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input("/m xyz") is None

    def test_model_with_trailing_text(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            result = update_model_in_input("/model gpt-4 tell me a joke")
            assert result is not None
            assert "tell me a joke" in result


class TestGetInputWithModelCompletion:
    @pytest.mark.asyncio
    async def test_basic(self):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(
                return_value=self._make_coro("hello world")
            )
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion()
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_with_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(
                return_value=self._make_coro("/model gpt-4 hello")
            )
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion()
            assert "hello" in result

    @pytest.mark.asyncio
    async def test_with_history_file(self, tmp_path):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        hfile = str(tmp_path / "history.txt")
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(return_value=self._make_coro("test"))
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion(history_file=hfile)
            assert result == "test"

    @staticmethod
    async def _make_coro(value):
        return value

    def test_model_idx_not_found(self):
        """Cover the return None when idx == -1 for /model."""
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            # Create a case where text.find won't match the pattern
            # This happens when original text has different spacing
            result = update_model_in_input("  /model  gpt-4")
            # The cmd extracted is "/model", rest is "gpt-4"
            # Pattern is "/model gpt-4" but original has extra spaces
            # Actually let me trace: content = "/model  gpt-4" (stripped)
            # content.lower().startswith("/model ") -> True
            # model_cmd = "/model", rest = " gpt-4".strip() = "gpt-4"
            # pattern = "/model gpt-4", text = "  /model  gpt-4"
            # text.find("/model gpt-4") -> -1 because of double space
            assert result is None

    def test_m_idx_not_found(self):
        """Cover the return None when idx == -1 for /m."""
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            result = update_model_in_input("  /m  gpt-4")
            assert result is None

    def test_m_with_trailing_text(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            result = update_model_in_input("/m gpt-4 tell me a joke")
            assert result is not None
            assert "tell me a joke" in result

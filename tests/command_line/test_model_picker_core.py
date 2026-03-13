"""Tests for model picker functions in core_commands.py."""

import pytest
from unittest.mock import patch, MagicMock


class TestModelPickerConstants:
    """Test the shared constants module."""

    def test_constants_are_defined(self):
        from code_puppy.command_line.model_picker_constants import (
            CURRENT_MODEL_PREFIX,
            CURRENT_MODEL_SUFFIX,
            OTHER_MODEL_PREFIX,
        )

        assert CURRENT_MODEL_PREFIX == "✓ "
        assert OTHER_MODEL_PREFIX == "  "
        assert CURRENT_MODEL_SUFFIX == " (current)"

    def test_prefix_lengths_match(self):
        """Both prefixes should be the same length for alignment."""
        from code_puppy.command_line.model_picker_constants import (
            CURRENT_MODEL_PREFIX,
            OTHER_MODEL_PREFIX,
        )

        assert len(CURRENT_MODEL_PREFIX) == len(OTHER_MODEL_PREFIX)


class TestBuildModelChoices:
    """Test the build_model_choices function."""

    def test_marks_current_model(self):
        from code_puppy.command_line.core_commands import build_model_choices

        choices = build_model_choices(["gpt-4", "claude-3"], "gpt-4")

        assert len(choices) == 2
        assert "✓" in choices[0]  # gpt-4 is current
        assert "(current)" in choices[0]
        assert "✓" not in choices[1]  # claude-3 is not current
        assert "(current)" not in choices[1]

    def test_all_models_not_current(self):
        from code_puppy.command_line.core_commands import build_model_choices

        choices = build_model_choices(["gpt-4", "claude-3"], "gemini")

        for choice in choices:
            assert "✓" not in choice
            assert "(current)" not in choice

    def test_empty_model_list(self):
        from code_puppy.command_line.core_commands import build_model_choices

        choices = build_model_choices([], "gpt-4")
        assert choices == []

    def test_single_model_is_current(self):
        from code_puppy.command_line.core_commands import build_model_choices

        choices = build_model_choices(["gpt-4"], "gpt-4")

        assert len(choices) == 1
        assert "✓ gpt-4 (current)" == choices[0]

    def test_preserves_model_order(self):
        from code_puppy.command_line.core_commands import build_model_choices

        models = ["alpha", "beta", "gamma"]
        choices = build_model_choices(models, "beta")

        assert "alpha" in choices[0]
        assert "beta" in choices[1]
        assert "gamma" in choices[2]


class TestParseModelChoice:
    """Test the parse_model_choice function."""

    def test_parse_current_model(self):
        from code_puppy.command_line.core_commands import parse_model_choice

        result = parse_model_choice("✓ gpt-4 (current)")
        assert result == "gpt-4"

    def test_parse_non_current_model(self):
        from code_puppy.command_line.core_commands import parse_model_choice

        result = parse_model_choice("  claude-3")
        assert result == "claude-3"

    def test_parse_model_with_hyphens(self):
        from code_puppy.command_line.core_commands import parse_model_choice

        result = parse_model_choice("✓ gpt-4-turbo-preview (current)")
        assert result == "gpt-4-turbo-preview"

    def test_parse_model_with_numbers(self):
        from code_puppy.command_line.core_commands import parse_model_choice

        result = parse_model_choice("  claude-3.5-sonnet")
        assert result == "claude-3.5-sonnet"

    def test_roundtrip_current_model(self):
        """Build then parse should return original model name."""
        from code_puppy.command_line.core_commands import (
            build_model_choices,
            parse_model_choice,
        )

        models = ["gpt-4", "claude-3"]
        choices = build_model_choices(models, "gpt-4")

        # Parse the current model choice
        parsed = parse_model_choice(choices[0])
        assert parsed == "gpt-4"

    def test_roundtrip_non_current_model(self):
        """Build then parse should return original model name."""
        from code_puppy.command_line.core_commands import (
            build_model_choices,
            parse_model_choice,
        )

        models = ["gpt-4", "claude-3"]
        choices = build_model_choices(models, "gpt-4")

        # Parse the non-current model choice
        parsed = parse_model_choice(choices[1])
        assert parsed == "claude-3"

    def test_roundtrip_all_models(self):
        """All models should roundtrip correctly."""
        from code_puppy.command_line.core_commands import (
            build_model_choices,
            parse_model_choice,
        )

        models = ["gpt-4", "claude-3", "gemini-pro", "llama-2"]
        current = "claude-3"
        choices = build_model_choices(models, current)

        for i, model in enumerate(models):
            parsed = parse_model_choice(choices[i])
            assert parsed == model, f"Model {model} did not roundtrip correctly"


class TestInteractiveModelPicker:
    """Test the interactive_model_picker function."""

    def test_returns_selected_model(self):
        from code_puppy.command_line.core_commands import interactive_model_picker

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4", "claude-3"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                return_value="  claude-3",
            ),
            patch("rich.console.Console"),
        ):
            result = interactive_model_picker()
            assert result == "claude-3"

    def test_returns_current_model_when_selected(self):
        from code_puppy.command_line.core_commands import interactive_model_picker

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4", "claude-3"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                return_value="✓ gpt-4 (current)",
            ),
            patch("rich.console.Console"),
        ):
            result = interactive_model_picker()
            assert result == "gpt-4"

    def test_returns_none_on_keyboard_interrupt(self):
        from code_puppy.command_line.core_commands import interactive_model_picker

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                side_effect=KeyboardInterrupt(),
            ),
            patch("rich.console.Console"),
        ):
            result = interactive_model_picker()
            assert result is None

    def test_returns_none_on_eof_error(self):
        from code_puppy.command_line.core_commands import interactive_model_picker

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                side_effect=EOFError(),
            ),
            patch("rich.console.Console"),
        ):
            result = interactive_model_picker()
            assert result is None

    def test_returns_none_when_arrow_select_returns_none(self):
        from code_puppy.command_line.core_commands import interactive_model_picker

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                return_value=None,
            ),
            patch("rich.console.Console"),
        ):
            result = interactive_model_picker()
            assert result is None

    def test_always_resets_awaiting_user_input(self):
        """Verify set_awaiting_user_input(False) is called even on error."""
        from code_puppy.command_line.core_commands import interactive_model_picker

        mock_set_awaiting = MagicMock()

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input",
                mock_set_awaiting,
            ),
            patch(
                "code_puppy.messaging.emit_info"
            ),
            patch(
                "code_puppy.messaging.emit_error"
            ),
            patch(
                "code_puppy.tools.common.arrow_select",
                side_effect=KeyboardInterrupt(),
            ),
            patch("rich.console.Console"),
        ):
            interactive_model_picker()

        # Should be called with True first, then False
        calls = mock_set_awaiting.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] is True
        assert calls[1][0][0] is False


class TestProcessModelCommand:
    """Test the _process_model_command helper function."""

    def test_returns_none_when_prefix_not_matched(self):
        from code_puppy.command_line.model_picker_completion import (
            _process_model_command,
        )

        result = _process_model_command(
            "hello world", "hello world", "/model ", ["gpt-4"]
        )
        assert result is None

    def test_returns_none_when_model_not_found(self):
        from code_puppy.command_line.model_picker_completion import (
            _process_model_command,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion.set_active_model"
        ):
            result = _process_model_command(
                "/model xyz", "/model xyz", "/model ", ["gpt-4"]
            )
            assert result is None

    def test_sets_model_and_returns_remaining_text(self):
        from code_puppy.command_line.model_picker_completion import (
            _process_model_command,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion.set_active_model"
        ) as mock_set:
            result = _process_model_command(
                "/model gpt-4 hello", "/model gpt-4 hello", "/model ", ["gpt-4"]
            )
            mock_set.assert_called_once_with("gpt-4")
            assert result == "hello"

    def test_handles_m_command(self):
        from code_puppy.command_line.model_picker_completion import (
            _process_model_command,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion.set_active_model"
        ) as mock_set:
            result = _process_model_command(
                "/m gpt-4", "/m gpt-4", "/m ", ["gpt-4"]
            )
            mock_set.assert_called_once_with("gpt-4")
            assert result == ""


class TestUpdateModelInInputRefactored:
    """Test the refactored update_model_in_input function."""

    def test_model_command_works(self):
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
            assert result == ""

    def test_m_command_works(self):
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
            result = update_model_in_input("/m gpt-4")
            mock_set.assert_called_once_with("gpt-4")
            assert result == ""

    def test_model_preferred_over_m(self):
        """When input starts with /model, it should use /model not /m."""
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
            # /model should be matched, not /m
            result = update_model_in_input("/model gpt-4 hello")
            mock_set.assert_called_once_with("gpt-4")
            assert "hello" in result

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

    def test_no_command_returns_none(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        assert update_model_in_input("hello world") is None

    def test_invalid_model_returns_none(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input("/model xyz") is None
            assert update_model_in_input("/m xyz") is None

"""Tests for the model_utils module."""

from code_puppy.model_utils import (
    CLAUDE_CODE_INSTRUCTIONS,
    PreparedPrompt,
    get_claude_code_instructions,
    is_claude_code_model,
    prepare_prompt_for_model,
)


class TestIsClaudeCodeModel:
    """Tests for is_claude_code_model function."""

    def test_claude_code_prefix_returns_true(self):
        """Models starting with 'claude-code' should return True."""
        assert is_claude_code_model("claude-code-sonnet") is True
        assert is_claude_code_model("claude-code-opus") is True
        assert is_claude_code_model("claude-code-haiku") is True
        assert is_claude_code_model("claude-code-claude-3-5-sonnet") is True

    def test_non_claude_code_returns_false(self):
        """Models not starting with 'claude-code' should return False."""
        assert is_claude_code_model("gpt-4") is False
        assert is_claude_code_model("claude-3-sonnet") is False
        assert is_claude_code_model("gemini-pro") is False
        assert is_claude_code_model("anthropic-claude") is False

    def test_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_claude_code_model("") is False

    def test_partial_match_returns_false(self):
        """Partial matches should return False."""
        assert is_claude_code_model("code-claude") is False
        assert is_claude_code_model("my-claude-code-model") is False


class TestPreparePromptForModel:
    """Tests for prepare_prompt_for_model function."""

    def test_claude_code_swaps_instructions(self):
        """Claude-code models should get the fixed instruction string."""
        result = prepare_prompt_for_model(
            "claude-code-sonnet", "You are a helpful assistant.", "Hello world"
        )

        assert result.instructions == CLAUDE_CODE_INSTRUCTIONS
        assert result.is_claude_code is True

    def test_claude_code_prepends_system_to_user(self):
        """Claude-code models should prepend system prompt to user prompt."""
        result = prepare_prompt_for_model(
            "claude-code-sonnet", "You are a helpful assistant.", "Hello world"
        )

        assert result.user_prompt == "You are a helpful assistant.\n\nHello world"

    def test_claude_code_no_prepend_when_disabled(self):
        """When prepend_system_to_user=False, don't modify user prompt."""
        result = prepare_prompt_for_model(
            "claude-code-sonnet",
            "You are a helpful assistant.",
            "Hello world",
            prepend_system_to_user=False,
        )

        assert result.user_prompt == "Hello world"
        assert result.instructions == CLAUDE_CODE_INSTRUCTIONS

    def test_non_claude_code_keeps_original_instructions(self):
        """Non-claude-code models should keep original instructions."""
        result = prepare_prompt_for_model(
            "gpt-4", "You are a helpful assistant.", "Hello world"
        )

        assert result.instructions == "You are a helpful assistant."
        assert result.is_claude_code is False

    def test_non_claude_code_keeps_original_prompt(self):
        """Non-claude-code models should keep original user prompt."""
        result = prepare_prompt_for_model(
            "gpt-4", "You are a helpful assistant.", "Hello world"
        )

        assert result.user_prompt == "Hello world"

    def test_empty_system_prompt_no_prepend(self):
        """Empty system prompt should not add extra newlines."""
        result = prepare_prompt_for_model("claude-code-sonnet", "", "Hello world")

        # With empty system prompt, user prompt should remain unchanged
        assert result.user_prompt == "Hello world"

    def test_empty_user_prompt(self):
        """Empty user prompt should work correctly."""
        result = prepare_prompt_for_model(
            "claude-code-sonnet", "You are a helpful assistant.", ""
        )

        assert result.user_prompt == "You are a helpful assistant.\n\n"

    def test_returns_prepared_prompt_dataclass(self):
        """Function should return a PreparedPrompt dataclass."""
        result = prepare_prompt_for_model("gpt-4", "System prompt", "User prompt")

        assert isinstance(result, PreparedPrompt)
        assert hasattr(result, "instructions")
        assert hasattr(result, "user_prompt")
        assert hasattr(result, "is_claude_code")


class TestGetClaudeCodeInstructions:
    """Tests for get_claude_code_instructions function."""

    def test_returns_correct_string(self):
        """Should return the CLAUDE_CODE_INSTRUCTIONS constant."""
        result = get_claude_code_instructions()
        assert result == CLAUDE_CODE_INSTRUCTIONS
        assert "Claude Code" in result
        assert "Anthropic" in result


class TestPreparedPromptDataclass:
    """Tests for the PreparedPrompt dataclass."""

    def test_dataclass_creation(self):
        """PreparedPrompt should be creatable with all fields."""
        prompt = PreparedPrompt(
            instructions="test instructions",
            user_prompt="test user prompt",
            is_claude_code=True,
        )

        assert prompt.instructions == "test instructions"
        assert prompt.user_prompt == "test user prompt"
        assert prompt.is_claude_code is True

    def test_dataclass_equality(self):
        """Two PreparedPrompts with same values should be equal."""
        prompt1 = PreparedPrompt(
            instructions="test", user_prompt="hello", is_claude_code=False
        )
        prompt2 = PreparedPrompt(
            instructions="test", user_prompt="hello", is_claude_code=False
        )

        assert prompt1 == prompt2

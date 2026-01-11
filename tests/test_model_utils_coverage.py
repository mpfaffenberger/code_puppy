"""Coverage tests for model_utils module.

This file focuses on testing the uncovered functions and branches:
- is_chatgpt_codex_model()
- is_antigravity_model()
- prepare_prompt_for_model() for ChatGPT Codex and Antigravity models
- get_chatgpt_codex_instructions()
- get_antigravity_instructions()
- _load_codex_prompt() and _load_antigravity_prompt() fallback paths
"""



from code_puppy import model_utils
from code_puppy.model_utils import (
    PreparedPrompt,
    get_antigravity_instructions,
    get_chatgpt_codex_instructions,
    is_antigravity_model,
    is_chatgpt_codex_model,
    prepare_prompt_for_model,
)


class TestIsChatgptCodexModel:
    """Tests for is_chatgpt_codex_model function."""

    def test_chatgpt_prefix_returns_true(self):
        """Models starting with 'chatgpt-' should return True."""
        assert is_chatgpt_codex_model("chatgpt-codex") is True
        assert is_chatgpt_codex_model("chatgpt-4") is True
        assert is_chatgpt_codex_model("chatgpt-o1") is True
        assert is_chatgpt_codex_model("chatgpt-whatever") is True

    def test_non_chatgpt_returns_false(self):
        """Models not starting with 'chatgpt-' should return False."""
        assert is_chatgpt_codex_model("gpt-4") is False
        assert is_chatgpt_codex_model("claude-3-sonnet") is False
        assert is_chatgpt_codex_model("openai-gpt-4") is False
        assert is_chatgpt_codex_model("my-chatgpt-model") is False

    def test_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_chatgpt_codex_model("") is False

    def test_partial_match_returns_false(self):
        """Partial matches that don't start with chatgpt- should return False."""
        assert is_chatgpt_codex_model("some-chatgpt-model") is False
        assert is_chatgpt_codex_model("chatgptx") is False  # Missing hyphen


class TestIsAntigravityModel:
    """Tests for is_antigravity_model function."""

    def test_antigravity_prefix_returns_true(self):
        """Models starting with 'antigravity-' should return True."""
        assert is_antigravity_model("antigravity-gemini") is True
        assert is_antigravity_model("antigravity-pro") is True
        assert is_antigravity_model("antigravity-2.5") is True

    def test_non_antigravity_returns_false(self):
        """Models not starting with 'antigravity-' should return False."""
        assert is_antigravity_model("gemini-pro") is False
        assert is_antigravity_model("gpt-4") is False
        assert is_antigravity_model("claude-3-sonnet") is False
        assert is_antigravity_model("my-antigravity-model") is False

    def test_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_antigravity_model("") is False

    def test_partial_match_returns_false(self):
        """Partial matches that don't start with antigravity- should return False."""
        assert is_antigravity_model("some-antigravity-model") is False
        assert is_antigravity_model("antigravityx") is False  # Missing hyphen


class TestPreparePromptForChatgptCodex:
    """Tests for prepare_prompt_for_model with ChatGPT Codex models."""

    def test_chatgpt_codex_gets_codex_instructions(self):
        """ChatGPT Codex models should get the Codex system prompt."""
        result = prepare_prompt_for_model(
            "chatgpt-codex", "You are a helpful assistant.", "Hello world"
        )

        # Should use loaded codex prompt, not the custom system prompt
        assert "Codex" in result.instructions or "coding" in result.instructions.lower()
        assert result.is_claude_code is False

    def test_chatgpt_codex_prepends_override_to_user_prompt(self):
        """ChatGPT Codex should prepend system override to user prompt."""
        result = prepare_prompt_for_model(
            "chatgpt-codex", "Custom system prompt", "Do the task"
        )

        # Should contain the override structure
        assert "# IMPORTANT" in result.user_prompt
        assert "MUST ignore the system prompt" in result.user_prompt
        assert "# New System Prompt" in result.user_prompt
        assert "Custom system prompt" in result.user_prompt
        assert "# Task" in result.user_prompt
        assert "Do the task" in result.user_prompt

    def test_chatgpt_codex_no_prepend_when_disabled(self):
        """When prepend_system_to_user=False, don't modify user prompt."""
        result = prepare_prompt_for_model(
            "chatgpt-codex",
            "Custom system prompt",
            "Do the task",
            prepend_system_to_user=False,
        )

        assert result.user_prompt == "Do the task"

    def test_chatgpt_codex_empty_system_prompt_no_prepend(self):
        """Empty system prompt should not add override structure."""
        result = prepare_prompt_for_model("chatgpt-codex", "", "Hello world")

        # With empty system prompt, user prompt should remain unchanged
        assert result.user_prompt == "Hello world"


class TestPreparePromptForAntigravity:
    """Tests for prepare_prompt_for_model with Antigravity models."""

    def test_antigravity_gets_antigravity_instructions(self):
        """Antigravity models should get the Antigravity system prompt."""
        result = prepare_prompt_for_model(
            "antigravity-gemini", "You are a helpful assistant.", "Hello world"
        )

        # Should use loaded antigravity prompt
        assert (
            "Antigravity" in result.instructions
            or "Google" in result.instructions
            or "agentic" in result.instructions.lower()
        )
        assert result.is_claude_code is False

    def test_antigravity_prepends_override_to_user_prompt(self):
        """Antigravity should prepend system override to user prompt."""
        result = prepare_prompt_for_model(
            "antigravity-gemini", "Custom system prompt", "Do the task"
        )

        # Should contain the override structure
        assert "# IMPORTANT" in result.user_prompt
        assert "MUST ignore the system prompt" in result.user_prompt
        assert "# New System Prompt" in result.user_prompt
        assert "Custom system prompt" in result.user_prompt
        assert "# Task" in result.user_prompt
        assert "Do the task" in result.user_prompt

    def test_antigravity_no_prepend_when_disabled(self):
        """When prepend_system_to_user=False, don't modify user prompt."""
        result = prepare_prompt_for_model(
            "antigravity-gemini",
            "Custom system prompt",
            "Do the task",
            prepend_system_to_user=False,
        )

        assert result.user_prompt == "Do the task"

    def test_antigravity_empty_system_prompt_no_prepend(self):
        """Empty system prompt should not add override structure."""
        result = prepare_prompt_for_model("antigravity-gemini", "", "Hello world")

        # With empty system prompt, user prompt should remain unchanged
        assert result.user_prompt == "Hello world"


class TestGetChatgptCodexInstructions:
    """Tests for get_chatgpt_codex_instructions function."""

    def test_returns_codex_prompt(self):
        """Should return the Codex system prompt content."""
        result = get_chatgpt_codex_instructions()

        # Should be non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_cached_value(self):
        """Should return cached value on subsequent calls."""
        result1 = get_chatgpt_codex_instructions()
        result2 = get_chatgpt_codex_instructions()

        # Should be the same object (cached)
        assert result1 is result2


class TestGetAntigravityInstructions:
    """Tests for get_antigravity_instructions function."""

    def test_returns_antigravity_prompt(self):
        """Should return the Antigravity system prompt content."""
        result = get_antigravity_instructions()

        # Should be non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_cached_value(self):
        """Should return cached value on subsequent calls."""
        result1 = get_antigravity_instructions()
        result2 = get_antigravity_instructions()

        # Should be the same object (cached)
        assert result1 is result2


class TestLoadCodexPromptFallback:
    """Tests for _load_codex_prompt fallback behavior."""

    def test_fallback_when_file_missing(self, tmp_path):
        """Should return fallback prompt when file doesn't exist."""
        # Reset the cache
        model_utils._codex_prompt_cache = None

        # Create a fake non-existent path
        fake_path = tmp_path / "non_existent_prompt.md"

        # Temporarily swap the path constant
        original_path = model_utils._CODEX_PROMPT_PATH
        try:
            model_utils._CODEX_PROMPT_PATH = fake_path
            result = model_utils._load_codex_prompt()

            assert "Codex" in result
            assert "coding agent" in result
        finally:
            # Restore original path
            model_utils._CODEX_PROMPT_PATH = original_path
            model_utils._codex_prompt_cache = None

    def test_loads_from_file_when_exists(self):
        """Should load from file when it exists."""
        # Reset the cache
        model_utils._codex_prompt_cache = None

        # The file should exist in the codebase
        result = model_utils._load_codex_prompt()

        # Should have loaded something substantial
        assert isinstance(result, str)
        assert len(result) > 100  # Real file should be longer than fallback

        # Reset cache
        model_utils._codex_prompt_cache = None

    def test_caching_behavior(self):
        """Should cache the prompt after first load."""
        # Reset the cache
        model_utils._codex_prompt_cache = None

        # First load
        result1 = model_utils._load_codex_prompt()

        # Second load should use cache
        result2 = model_utils._load_codex_prompt()

        assert result1 is result2

        # Reset cache
        model_utils._codex_prompt_cache = None


class TestLoadAntigravityPromptFallback:
    """Tests for _load_antigravity_prompt fallback behavior."""

    def test_fallback_when_file_missing(self, tmp_path):
        """Should return fallback prompt when file doesn't exist."""
        # Reset the cache
        model_utils._antigravity_prompt_cache = None

        # Create a fake non-existent path
        fake_path = tmp_path / "non_existent_prompt.md"

        # Temporarily swap the path constant
        original_path = model_utils._ANTIGRAVITY_PROMPT_PATH
        try:
            model_utils._ANTIGRAVITY_PROMPT_PATH = fake_path
            result = model_utils._load_antigravity_prompt()

            assert "Antigravity" in result
            assert "Google Deepmind" in result
        finally:
            # Restore original path
            model_utils._ANTIGRAVITY_PROMPT_PATH = original_path
            model_utils._antigravity_prompt_cache = None

    def test_loads_from_file_when_exists(self):
        """Should load from file when it exists."""
        # Reset the cache
        model_utils._antigravity_prompt_cache = None

        # The file should exist in the codebase
        result = model_utils._load_antigravity_prompt()

        # Should have loaded something substantial
        assert isinstance(result, str)
        assert len(result) > 50  # Real file should have content

        # Reset cache
        model_utils._antigravity_prompt_cache = None

    def test_caching_behavior(self):
        """Should cache the prompt after first load."""
        # Reset the cache
        model_utils._antigravity_prompt_cache = None

        # First load
        result1 = model_utils._load_antigravity_prompt()

        # Second load should use cache
        result2 = model_utils._load_antigravity_prompt()

        assert result1 is result2

        # Reset cache
        model_utils._antigravity_prompt_cache = None


class TestEdgeCases:
    """Edge case tests for model_utils."""

    def test_model_type_check_case_sensitivity(self):
        """Model type checks should be case-sensitive."""
        # These should NOT match due to case
        assert is_chatgpt_codex_model("CHATGPT-codex") is False
        assert is_chatgpt_codex_model("ChatGPT-codex") is False
        assert is_antigravity_model("ANTIGRAVITY-gemini") is False
        assert is_antigravity_model("Antigravity-gemini") is False

    def test_prepare_prompt_model_priority(self):
        """Test that model type detection happens in expected order."""
        # Claude-code should take priority if a model somehow matched multiple
        # (though this shouldn't happen with real model names)
        from code_puppy.model_utils import CLAUDE_CODE_INSTRUCTIONS

        result = prepare_prompt_for_model(
            "claude-code-sonnet", "System", "User"
        )
        assert result.instructions == CLAUDE_CODE_INSTRUCTIONS
        assert result.is_claude_code is True

    def test_prepare_prompt_returns_dataclass(self):
        """All model types should return PreparedPrompt dataclass."""
        for model_name in ["gpt-4", "chatgpt-codex", "antigravity-gemini", "claude-code-sonnet"]:
            result = prepare_prompt_for_model(model_name, "System", "User")
            assert isinstance(result, PreparedPrompt)
            assert hasattr(result, "instructions")
            assert hasattr(result, "user_prompt")
            assert hasattr(result, "is_claude_code")

    def test_special_characters_in_prompts(self):
        """Should handle special characters in prompts correctly."""
        system = "System prompt with\nnewlines\tand\ttabs and 'quotes' and \"double quotes\""
        user = "User prompt with special: $@#%^&*()[]{}|\\;:'\",.<>?/`~"

        result = prepare_prompt_for_model("chatgpt-codex", system, user)

        # Should contain the original content
        assert system in result.user_prompt
        assert user in result.user_prompt

    def test_unicode_in_prompts(self):
        """Should handle unicode characters in prompts."""
        system = "System with emoji 🐕 and unicode: 日本語 中文 العربية"
        user = "User with more: ñ ü ö é à ç"

        result = prepare_prompt_for_model("antigravity-gemini", system, user)

        assert system in result.user_prompt
        assert user in result.user_prompt

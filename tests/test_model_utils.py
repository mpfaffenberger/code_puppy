"""Tests for the model_utils module.

Claude-code-specific behavior lives in the ``claude_code_oauth`` plugin now,
so we import those bits from the plugin and also import its
``register_callbacks`` module to ensure the ``prepare_model_prompt`` callback
is registered for tests that exercise the dispatcher.
"""

import pytest

# Importing register_callbacks triggers plugin registration at module scope.
import code_puppy.plugins.claude_code_oauth.register_callbacks  # noqa: F401
from code_puppy.callbacks import (
    clear_callbacks,
    get_callbacks,
    register_callback,
    unregister_callback,
)
from code_puppy.model_utils import (
    PreparedPrompt,
    get_default_extended_thinking,
    get_glm_version,
    prepare_prompt_for_model,
    should_use_anthropic_thinking_summary,
    supports_glm_reasoning_effort,
    supports_glm_thinking,
)
from code_puppy.plugins.claude_code_oauth.prompt_handler import (
    CLAUDE_CODE_INSTRUCTIONS,
    get_claude_code_instructions,
    is_claude_code_model,
    prepare_claude_code_prompt,
)


@pytest.fixture(autouse=True)
def _isolate_prompt_callbacks():
    """Guarantee test isolation for prompt-related callback phases.

    Two problems we're solving at once:

    1. Other test modules call ``clear_callbacks()`` which wipes plugin regs
       — so we re-register the claude-code ``prepare_model_prompt`` handler
       before each test so the dispatcher has something to dispatch to.
    2. Other test modules (e.g. agent_skills) import their plugin's
       ``register_callbacks`` which leaks an augmenter into the
       ``get_model_system_prompt`` phase. Now that augmenters are actually
       honored end-to-end, that leak would clobber tests expecting an
       un-augmented prompt. Snapshot + restore both phases per test.
    """
    snapshot_get = get_callbacks("get_model_system_prompt")  # returns a copy
    snapshot_prepare = get_callbacks("prepare_model_prompt")  # returns a copy

    # Start each test with a clean ``get_model_system_prompt`` slate so
    # leaked augmenters from other modules can't pollute the assertions.
    clear_callbacks("get_model_system_prompt")

    if prepare_claude_code_prompt not in get_callbacks("prepare_model_prompt"):
        register_callback("prepare_model_prompt", prepare_claude_code_prompt)

    try:
        yield
    finally:
        clear_callbacks("get_model_system_prompt")
        for cb in snapshot_get:
            register_callback("get_model_system_prompt", cb)
        clear_callbacks("prepare_model_prompt")
        for cb in snapshot_prepare:
            register_callback("prepare_model_prompt", cb)


class TestIsClaudeCodeModel:
    """Tests for is_claude_code_model function (lives in the plugin now)."""

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
    """Tests for prepare_prompt_for_model function.

    Claude-code behavior is delivered by the claude_code_oauth plugin via
    the ``prepare_model_prompt`` hook; these tests verify the end-to-end
    dispatch still produces the expected shape.
    """

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

    def test_augmenter_callback_mutations_are_threaded_forward(self):
        """Regression: augmenter plugins returning ``handled=False`` with
        mutated ``instructions`` must have those mutations preserved in the
        returned PreparedPrompt. agent_skills relies on this contract to
        inject the available-skills block into the system prompt.
        """

        def _augmenter(model_name, default_system_prompt, user_prompt):
            return {
                "instructions": f"{default_system_prompt}\n\n## Available Skills\n- foo: bar",
                "user_prompt": user_prompt,
                "handled": False,
            }

        register_callback("get_model_system_prompt", _augmenter)
        try:
            result = prepare_prompt_for_model(
                "gpt-4", "You are a helpful assistant.", "Hello"
            )
        finally:
            # Belt + suspenders — the autouse fixture also restores state.
            unregister_callback("get_model_system_prompt", _augmenter)

        assert "## Available Skills" in result.instructions
        assert "- foo: bar" in result.instructions
        assert result.user_prompt == "Hello"
        assert result.is_claude_code is False

    def test_handled_true_short_circuits_remaining_augmenters(self):
        """A ``handled=True`` result must win outright — later augmenters in
        the chain shouldn't get a chance to mutate the prompt.
        """
        calls: list[str] = []

        def _taker(model_name, default_system_prompt, user_prompt):
            calls.append("taker")
            return {
                "instructions": "TAKEN OVER",
                "user_prompt": user_prompt,
                "handled": True,
            }

        def _augmenter(model_name, default_system_prompt, user_prompt):
            calls.append("augmenter")
            return {
                "instructions": f"{default_system_prompt}\nAUGMENTED",
                "user_prompt": user_prompt,
                "handled": False,
            }

        # Register taker first so it appears first in the dispatch order.
        register_callback("get_model_system_prompt", _taker)
        register_callback("get_model_system_prompt", _augmenter)
        try:
            result = prepare_prompt_for_model("gpt-4", "orig", "hello")
        finally:
            unregister_callback("get_model_system_prompt", _taker)
            unregister_callback("get_model_system_prompt", _augmenter)

        assert result.instructions == "TAKEN OVER"
        # Both callbacks still fire (the dispatcher collects all results),
        # but only the taker's output is honored.
        assert "taker" in calls


class TestGetClaudeCodeInstructions:
    """Tests for get_claude_code_instructions function (in the plugin now)."""

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


class TestGetDefaultExtendedThinking:
    """Tests for get_default_extended_thinking."""

    def test_opus_4_6_returns_adaptive(self):
        assert get_default_extended_thinking("claude-opus-4-6") == "adaptive"

    def test_4_6_opus_returns_adaptive(self):
        assert get_default_extended_thinking("claude-4-6-opus") == "adaptive"

    def test_case_insensitive(self):
        assert get_default_extended_thinking("Claude-Opus-4-6") == "adaptive"
        assert get_default_extended_thinking("CLAUDE-4-6-OPUS") == "adaptive"

    def test_non_opus_46_returns_enabled(self):
        assert get_default_extended_thinking("claude-sonnet-4-20250514") == "enabled"
        assert get_default_extended_thinking("claude-opus-4-5") == "enabled"
        assert get_default_extended_thinking("claude-4-5-opus") == "enabled"

    def test_non_anthropic_returns_enabled(self):
        assert get_default_extended_thinking("gpt-4o") == "enabled"
        assert get_default_extended_thinking("gemini-2.5-pro") == "enabled"

    def test_substring_match_in_longer_name(self):
        assert get_default_extended_thinking("anthropic-opus-4-6-preview") == "adaptive"
        assert get_default_extended_thinking("claude-4-6-opus-20250701") == "adaptive"

    def test_sonnet_5_returns_adaptive(self):
        # Sonnet 5 defaults to adaptive thinking just like Opus; classic
        # "enabled" thinking is deprecated for it.
        assert get_default_extended_thinking("claude-sonnet-5") == "adaptive"
        assert (
            get_default_extended_thinking("claude-code-claude-sonnet-5") == "adaptive"
        )
        assert get_default_extended_thinking("Claude-Sonnet-5") == "adaptive"
        # Older single-digit sonnet must stay on enabled.
        assert get_default_extended_thinking("claude-sonnet-4-20250514") == "enabled"


class TestShouldUseAnthropicThinkingSummary:
    """Tests for should_use_anthropic_thinking_summary."""

    def test_opus_4_7_models_return_true(self):
        assert should_use_anthropic_thinking_summary("claude-opus-4-7") is True
        assert should_use_anthropic_thinking_summary("Claude-Opus-4-7-Latest") is True
        assert should_use_anthropic_thinking_summary("claude-4-7-opus-20250701") is True

    def test_sonnet_5_models_return_true(self):
        assert should_use_anthropic_thinking_summary("claude-sonnet-5") is True
        assert (
            should_use_anthropic_thinking_summary("claude-code-claude-sonnet-5") is True
        )

    def test_other_models_return_false(self):
        assert should_use_anthropic_thinking_summary("claude-opus-4-6") is False
        assert should_use_anthropic_thinking_summary("claude-sonnet-4") is False
        assert should_use_anthropic_thinking_summary("claude-sonnet-4-6") is False
        assert should_use_anthropic_thinking_summary("gpt-5") is False


class TestGlmHelpers:
    """Tests for the GLM/Zhipu version-detection helpers."""

    def test_get_glm_version_extracts_from_messy_aliases(self):
        assert get_glm_version("zai-glm-5.1-api") == 5.1
        assert get_glm_version("GLM-4.5-AIR-CODING") == 4.5
        assert get_glm_version("lilac-zai-org-glm-5.1") == 5.1
        assert get_glm_version("glm-4.7-chat") == 4.7
        assert get_glm_version("GLM-5.2-Turbo") == 5.2

    def test_get_glm_version_none_for_non_glm(self):
        assert get_glm_version("gpt-5") is None
        assert get_glm_version("claude-opus-4-6") is None

    def test_supports_glm_thinking_from_4_5(self):
        assert supports_glm_thinking("glm-4.5") is True
        assert supports_glm_thinking("glm-4.5v") is True
        assert supports_glm_thinking("glm-4.6") is True
        assert supports_glm_thinking("glm-4.7") is True
        assert supports_glm_thinking("zai-glm-5.1-api") is True
        assert supports_glm_thinking("GLM-5.2-Turbo") is True
        assert supports_glm_thinking("GLM-5V-Turbo") is True

    def test_supports_glm_thinking_false_below_4_5_and_non_glm(self):
        assert supports_glm_thinking("glm-4.4") is False
        assert supports_glm_thinking("gpt-5") is False

    def test_supports_glm_reasoning_effort_5_2_plus_only(self):
        assert supports_glm_reasoning_effort("glm-5.2") is True
        assert supports_glm_reasoning_effort("GLM-5.2-Turbo") is True
        assert supports_glm_reasoning_effort("glm-5.1") is False
        assert supports_glm_reasoning_effort("glm-4.7") is False
        assert supports_glm_reasoning_effort("gpt-5") is False

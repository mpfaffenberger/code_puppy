"""
Comprehensive tests for the shell safety plugin.

Tests cover command assessment, caching, risk level comparison,
and safety thresholds.
"""

from code_puppy.plugins.shell_safety.agent_shell_safety import ShellSafetyAgent
from code_puppy.plugins.shell_safety.command_cache import (
    CachedAssessment,
    CommandSafetyCache,
    cache_assessment,
    get_cache_stats,
    get_cached_assessment,
)
from code_puppy.plugins.shell_safety.register_callbacks import (
    RISK_LEVELS,
    compare_risk_levels,
    is_oauth_model,
    shell_safety_callback,
)


class TestOAuthModelDetection:
    """Test OAuth model detection."""

    def test_is_oauth_model_anthropic(self):
        """Test detection of Anthropic OAuth models."""
        assert is_oauth_model("claude-code-123")
        assert is_oauth_model("claude-code-v1.0")
        assert is_oauth_model("claude-code-latest")

    def test_is_oauth_model_openai(self):
        """Test detection of OpenAI OAuth models."""
        assert is_oauth_model("chatgpt-4")
        assert is_oauth_model("chatgpt-gpt4")
        assert is_oauth_model("chatgpt-pro")

    def test_is_oauth_model_google(self):
        """Test detection of Google OAuth models."""
        assert is_oauth_model("gemini-oauth")
        assert is_oauth_model("gemini-oauth-pro")

    def test_is_not_oauth_model(self):
        """Test detection of non-OAuth models."""
        assert not is_oauth_model("claude-opus-4")
        assert not is_oauth_model("gpt-4")
        assert not is_oauth_model("gemini-pro")
        assert not is_oauth_model("local-llm")

    def test_is_oauth_model_none(self):
        """Test with None model name."""
        assert not is_oauth_model(None)

    def test_is_oauth_model_empty_string(self):
        """Test with empty string model name."""
        assert not is_oauth_model("")

    def test_is_oauth_model_case_sensitive(self):
        """Test that model name is case-sensitive."""
        assert is_oauth_model("claude-code-123")
        assert not is_oauth_model("CLAUDE-CODE-123")
        assert not is_oauth_model("Claude-Code-123")


class TestRiskLevelComparison:
    """Test risk level comparison logic."""

    def test_all_risk_levels_defined(self):
        """Test that all risk levels are defined."""
        expected_levels = {"none", "low", "medium", "high", "critical"}
        assert set(RISK_LEVELS.keys()) == expected_levels

    def test_risk_levels_numeric_ordering(self):
        """Test that risk levels have correct numeric ordering."""
        assert RISK_LEVELS["none"] == 0
        assert RISK_LEVELS["low"] == 1
        assert RISK_LEVELS["medium"] == 2
        assert RISK_LEVELS["high"] == 3
        assert RISK_LEVELS["critical"] == 4

    def test_compare_risk_below_threshold(self):
        """Test risk below threshold is allowed."""
        assert not compare_risk_levels("low", "medium")
        assert not compare_risk_levels("none", "low")

    def test_compare_risk_at_threshold(self):
        """Test risk at threshold is allowed."""
        assert not compare_risk_levels("medium", "medium")
        assert not compare_risk_levels("low", "low")

    def test_compare_risk_above_threshold(self):
        """Test risk above threshold is blocked."""
        assert compare_risk_levels("high", "medium")
        assert compare_risk_levels("critical", "high")

    def test_compare_risk_none_defaults_to_high(self):
        """Test that None risk defaults to high (fail-safe)."""
        # high > low (3 > 1)
        assert compare_risk_levels(None, "low")
        # high == high (3 == 3)
        assert not compare_risk_levels(None, "high")

    def test_compare_risk_unknown_level(self):
        """Test unknown risk levels default to critical."""
        assert compare_risk_levels("unknown", "high")
        assert not compare_risk_levels("unknown", "critical")

    def test_compare_risk_all_combinations(self):
        """Test all valid risk level combinations."""
        levels = ["none", "low", "medium", "high", "critical"]
        for assessed in levels:
            for threshold in levels:
                result = compare_risk_levels(assessed, threshold)
                # Result should be True only when assessed > threshold
                expected = RISK_LEVELS[assessed] > RISK_LEVELS[threshold]
                assert result == expected, f"{assessed} vs {threshold} failed"


class TestCommandSafetyCache:
    """Test command safety caching."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = CommandSafetyCache()
        assert cache._max_size == 200
        assert len(cache._cache) == 0

    def test_cache_custom_max_size(self):
        """Test cache with custom max size."""
        cache = CommandSafetyCache(max_size=100)
        assert cache._max_size == 100

    def test_cache_put_and_get(self):
        """Test putting and getting from cache."""
        cache = CommandSafetyCache()
        assessment = CachedAssessment(risk="low", reasoning="Safe command")

        cache.put("ls", None, assessment)

        retrieved = cache.get("ls", None)
        assert retrieved is not None
        assert retrieved.risk == "low"
        assert retrieved.reasoning == "Safe command"

    def test_cache_get_nonexistent(self):
        """Test getting nonexistent entry from cache."""
        cache = CommandSafetyCache()
        result = cache.get("rm -rf /", None)
        assert result is None

    def test_cache_key_with_cwd(self):
        """Test cache keys with working directory."""
        cache = CommandSafetyCache()
        assessment1 = CachedAssessment(risk="low", reasoning="In /tmp")
        assessment2 = CachedAssessment(risk="high", reasoning="In /")

        cache.put("rm file", "/tmp", assessment1)
        cache.put("rm file", "/", assessment2)

        assert cache.get("rm file", "/tmp").reasoning == "In /tmp"
        assert cache.get("rm file", "/").reasoning == "In /"

    def test_cache_whitespace_normalization(self):
        """Test that cache normalizes whitespace."""
        cache = CommandSafetyCache()
        assessment = CachedAssessment(risk="low", reasoning="Safe")

        cache.put("  ls -la  ", None, assessment)

        # Whitespace should be stripped
        retrieved = cache.get("ls -la", None)
        assert retrieved is not None

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = CommandSafetyCache(max_size=3)

        # Add 3 commands (fill cache)
        for i in range(3):
            assessment = CachedAssessment(risk="low", reasoning=f"Cmd {i}")
            cache.put(f"cmd{i}", None, assessment)

        assert len(cache._cache) == 3

        # Add 4th command (should evict oldest)
        assessment = CachedAssessment(risk="low", reasoning="Cmd 3")
        cache.put("cmd3", None, assessment)

        assert len(cache._cache) == 3
        # cmd0 should be evicted
        assert cache.get("cmd0", None) is None

    def test_cache_lru_promotion(self):
        """Test that accessing an item promotes it in LRU."""
        cache = CommandSafetyCache(max_size=3)

        # Add 3 items
        for i in range(3):
            assessment = CachedAssessment(risk="low", reasoning=f"Cmd {i}")
            cache.put(f"cmd{i}", None, assessment)

        # Access cmd0 to promote it
        cache.get("cmd0", None)

        # Add cmd3 (should evict cmd1, not cmd0)
        assessment = CachedAssessment(risk="low", reasoning="Cmd 3")
        cache.put("cmd3", None, assessment)

        assert cache.get("cmd0", None) is not None
        assert cache.get("cmd1", None) is None

    def test_cache_clear(self):
        """Test clearing the cache."""
        cache = CommandSafetyCache()
        assessment = CachedAssessment(risk="low", reasoning="Safe")
        cache.put("ls", None, assessment)

        assert cache.get("ls", None) is not None

        cache.clear()

        assert cache.get("ls", None) is None
        assert len(cache._cache) == 0

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = CommandSafetyCache()
        assessment = CachedAssessment(risk="low", reasoning="Safe")
        cache.put("ls", None, assessment)

        # Hit
        cache.get("ls", None)
        # Miss
        cache.get("rm", None)

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert "50.0%" in stats["hit_rate"]

    def test_cache_update_existing_key(self):
        """Test updating an existing cache entry."""
        cache = CommandSafetyCache()
        assessment1 = CachedAssessment(risk="low", reasoning="Safe")
        assessment2 = CachedAssessment(risk="high", reasoning="Unsafe")

        cache.put("ls", None, assessment1)
        assert cache.get("ls", None).risk == "low"

        cache.put("ls", None, assessment2)
        assert cache.get("ls", None).risk == "high"
        assert len(cache._cache) == 1  # Still only one entry


class TestGlobalCacheFunctions:
    """Test global cache functions."""

    def test_cache_assessment_and_retrieve(self):
        """Test caching and retrieving assessments."""
        # Clear cache first
        import code_puppy.plugins.shell_safety.command_cache as cache_module

        cache_module._cache.clear()

        cache_assessment("test_cmd", None, "low", "Safe command")

        cached = get_cached_assessment("test_cmd", None)
        assert cached is not None
        assert cached.risk == "low"
        assert cached.reasoning == "Safe command"

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        import code_puppy.plugins.shell_safety.command_cache as cache_module

        cache_module._cache.clear()

        stats = get_cache_stats()
        assert isinstance(stats, dict)
        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats


class TestShellSafetyAgent:
    """Test ShellSafetyAgent configuration."""

    def test_agent_properties(self):
        """Test agent metadata properties."""
        agent = ShellSafetyAgent()
        assert agent.name == "shell_safety_checker"
        assert agent.display_name == "Shell Safety Checker 🛡️"
        assert "safety" in agent.description.lower()

    def test_agent_system_prompt(self):
        """Test agent system prompt."""
        agent = ShellSafetyAgent()
        prompt = agent.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Check for key concepts
        assert "Risk" in prompt or "risk" in prompt
        assert "none" in prompt
        assert "critical" in prompt

    def test_agent_no_tools(self):
        """Test that safety agent uses no tools."""
        agent = ShellSafetyAgent()
        tools = agent.get_available_tools()
        assert tools == []


class TestShellSafetyCallbackDecision:
    """Test shell safety callback decision logic."""

    def test_callback_function_exists(self):
        """Test that callback function is defined."""
        assert callable(shell_safety_callback)

    def test_callback_has_correct_signature(self):
        """Test that callback has expected parameters."""
        import inspect

        sig = inspect.signature(shell_safety_callback)
        params = list(sig.parameters.keys())
        # Should accept context, command, cwd, timeout
        assert "context" in params
        assert "command" in params
        assert "cwd" in params
        assert "timeout" in params


class TestCachedAssessmentDataclass:
    """Test CachedAssessment dataclass."""

    def test_cached_assessment_creation(self):
        """Test creating a cached assessment."""
        assessment = CachedAssessment(risk="low", reasoning="Safe command")
        assert assessment.risk == "low"
        assert assessment.reasoning == "Safe command"

    def test_cached_assessment_with_none_values(self):
        """Test cached assessment with None values."""
        assessment = CachedAssessment(risk=None, reasoning=None)
        assert assessment.risk is None
        assert assessment.reasoning is None

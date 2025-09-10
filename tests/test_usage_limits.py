"""
Tests for rate limiting functionality in code-puppy.

This test file verifies that the custom usage limits are properly configured
and applied throughout the application.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.usage import UsageLimits

import code_puppy.agent as agent_module
import code_puppy.config as config_module


class TestUsageLimits:
    """Test suite for usage limits functionality."""

    def test_get_custom_usage_limits_returns_correct_limit(self):
        """Test that get_custom_usage_limits returns UsageLimits with configurable request_limit."""
        usage_limits = agent_module.get_custom_usage_limits()

        assert isinstance(usage_limits, UsageLimits)
        assert usage_limits.request_limit == 100  # Default value
        assert usage_limits.request_tokens_limit is None  # Default
        assert usage_limits.response_tokens_limit is None  # Default
        assert usage_limits.total_tokens_limit is None  # Default

    @patch("code_puppy.config.get_message_limit")
    def test_get_custom_usage_limits_uses_configured_limit(self, mock_get_message_limit):
        """Test that get_custom_usage_limits uses the configured message limit."""
        mock_get_message_limit.return_value = 200
        usage_limits = agent_module.get_custom_usage_limits()

        assert isinstance(usage_limits, UsageLimits)
        assert usage_limits.request_limit == 200
        mock_get_message_limit.return_value = 50
        usage_limits = agent_module.get_custom_usage_limits()

        assert usage_limits.request_limit == 50

    def test_get_custom_usage_limits_consistency(self):
        """Test that multiple calls return equivalent objects."""
        limits1 = agent_module.get_custom_usage_limits()
        limits2 = agent_module.get_custom_usage_limits()

        # Should have same values
        assert limits1.request_limit == limits2.request_limit
        assert limits1.request_tokens_limit == limits2.request_tokens_limit
        assert limits1.response_tokens_limit == limits2.response_tokens_limit
        assert limits1.total_tokens_limit == limits2.total_tokens_limit

    def test_usage_limits_import_available(self):
        """Test that UsageLimits is properly imported and accessible."""
        # This ensures the import is working correctly
        assert hasattr(agent_module, "UsageLimits")
        assert agent_module.UsageLimits == UsageLimits

    def test_main_imports_custom_usage_limits(self):
        """Test that main.py can import and use custom usage limits."""
        # Test that the import works
        from code_puppy.main import get_custom_usage_limits

        # Test that it returns the correct type and value
        limits = get_custom_usage_limits()
        assert isinstance(limits, UsageLimits)
        assert limits.request_limit == 100

    def test_tui_imports_custom_usage_limits(self):
        """Test that TUI interface can import and use custom usage limits."""
        # Test that the import works in the TUI context
        from code_puppy.tui.app import get_custom_usage_limits

        # Test that it returns the correct type and value
        limits = get_custom_usage_limits()
        assert isinstance(limits, UsageLimits)
        assert limits.request_limit == 100

    def test_usage_limits_default_vs_custom(self):
        """Test that our custom limits differ from the default."""
        default_limits = UsageLimits()  # Default constructor
        custom_limits = agent_module.get_custom_usage_limits()

        # Default should be 50, custom should be 100
        assert default_limits.request_limit == 50
        assert custom_limits.request_limit == 100

        # Other limits should be the same (None by default)
        assert default_limits.request_tokens_limit == custom_limits.request_tokens_limit
        assert (
            default_limits.response_tokens_limit == custom_limits.response_tokens_limit
        )
        assert default_limits.total_tokens_limit == custom_limits.total_tokens_limit

    def test_usage_limits_has_token_limits(self):
        """Test the has_token_limits method behavior."""
        limits = agent_module.get_custom_usage_limits()

        # Should return False since we only set request_limit, not token limits
        assert not limits.has_token_limits()

        # Test with token limits set
        limits_with_tokens = UsageLimits(request_limit=100, request_tokens_limit=1000)
        assert limits_with_tokens.has_token_limits()

    def test_usage_limits_configuration_values(self):
        """Test specific configuration values of usage limits."""
        limits = agent_module.get_custom_usage_limits()

        # Test all the specific values we expect
        assert limits.request_limit == 100, "Request limit should be 100"
        assert limits.request_tokens_limit is None, (
            "Request tokens limit should be None (unlimited)"
        )
        assert limits.response_tokens_limit is None, (
            "Response tokens limit should be None (unlimited)"
        )
        assert limits.total_tokens_limit is None, (
            "Total tokens limit should be None (unlimited)"
        )

        # Test that it's a proper UsageLimits instance
        assert isinstance(limits, UsageLimits)
        assert hasattr(limits, "request_limit")
        assert hasattr(limits, "has_token_limits")

    def disabled_test_agent_creation_with_mocked_dependencies(self):
        """Test that agent creation works with mocked dependencies."""
        with (
            patch("code_puppy.config.get_model_name", return_value="test-model"),
            patch("code_puppy.agent.ModelFactory.load_config", return_value={}),
            patch("code_puppy.agent.ModelFactory.get_model") as mock_get_model,
            patch("code_puppy.agent.get_system_prompt", return_value="test prompt"),
            patch("code_puppy.agent.register_all_tools"),
            patch("code_puppy.agent._load_mcp_servers", return_value=[]),
            patch("code_puppy.agent.emit_info"),
            patch("code_puppy.agent.emit_system_message"),
            patch("code_puppy.agent.Agent") as mock_agent_class,
        ):
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_agent_instance = MagicMock()
            mock_agent_class.return_value = mock_agent_instance

            # Test agent creation
            agent = agent_module.reload_code_generation_agent()

            # Verify Agent was called with correct parameters
            mock_agent_class.assert_called_once()
            call_kwargs = mock_agent_class.call_args.kwargs

            assert call_kwargs["model"] == mock_model
            assert call_kwargs["output_type"] == agent_module.AgentResponse
            assert call_kwargs["retries"] == 3
            assert "instructions" in call_kwargs
            assert "mcp_servers" in call_kwargs

            # Verify the agent instance is returned
            assert agent == mock_agent_instance


class TestUsageLimitsIntegration:
    """Integration tests for usage limits across the application."""

    def test_all_entry_points_use_custom_limits(self):
        """Test that all main entry points import and can use custom limits."""
        # Test that the function is available in all modules that need it
        from code_puppy.agent import get_custom_usage_limits
        from code_puppy.main import get_custom_usage_limits as main_get_limits
        from code_puppy.tui.app import get_custom_usage_limits as tui_get_limits

        # All should be the same function
        assert get_custom_usage_limits is main_get_limits
        assert get_custom_usage_limits is tui_get_limits

        # All should return the same type of object
        limits1 = get_custom_usage_limits()
        limits2 = main_get_limits()
        limits3 = tui_get_limits()

        assert (
            limits1.request_limit
            == limits2.request_limit
            == limits3.request_limit
            == 100
        )

    def test_usage_limits_backwards_compatibility(self):
        """Test that the usage limits change doesn't break existing functionality."""
        # Ensure that UsageLimits can be created with our parameters
        limits = UsageLimits(request_limit=100)
        assert limits.request_limit == 100

        # Ensure it has all expected methods
        assert hasattr(limits, "has_token_limits")
        assert callable(limits.has_token_limits)

        # Test that it behaves as expected
        assert not limits.has_token_limits()  # No token limits set

        # Test with token limits
        limits_with_tokens = UsageLimits(
            request_limit=100,
            request_tokens_limit=1000,
            response_tokens_limit=2000,
            total_tokens_limit=3000,
        )
        assert limits_with_tokens.has_token_limits()
        assert limits_with_tokens.request_limit == 100
        assert limits_with_tokens.request_tokens_limit == 1000
        assert limits_with_tokens.response_tokens_limit == 2000
        assert limits_with_tokens.total_tokens_limit == 3000

    def test_usage_limits_function_signature(self):
        """Test that the get_custom_usage_limits function has the expected signature."""
        import inspect

        # Test that the function exists and is callable
        assert callable(agent_module.get_custom_usage_limits)

        # Test function signature
        sig = inspect.signature(agent_module.get_custom_usage_limits)
        assert len(sig.parameters) == 0  # Should take no parameters

        # Test return type annotation if present
        if sig.return_annotation != inspect.Signature.empty:
            assert sig.return_annotation == UsageLimits

    def test_usage_limits_in_code_structure(self):
        """Test that usage limits are properly integrated into the code structure."""
        # Test that the function is defined in the agent module
        assert hasattr(agent_module, "get_custom_usage_limits")

        # Test that it's imported in main and tui modules
        import code_puppy.main as main_module
        import code_puppy.tui.app as tui_module

        assert hasattr(main_module, "get_custom_usage_limits")
        assert hasattr(tui_module, "get_custom_usage_limits")

        # Test that they all reference the same function
        assert (
            main_module.get_custom_usage_limits is agent_module.get_custom_usage_limits
        )
        assert (
            tui_module.get_custom_usage_limits is agent_module.get_custom_usage_limits
        )


class TestUsageLimitsRealWorld:
    """Real-world scenario tests for usage limits."""

    def test_usage_limits_rate_increase_verification(self):
        """Verify that the rate limit has been increased from default 50 to 100."""
        # This is the core test that verifies our change worked
        default_limits = UsageLimits()
        custom_limits = agent_module.get_custom_usage_limits()

        # Verify the change
        assert default_limits.request_limit == 50, "Default should be 50"
        assert custom_limits.request_limit == 100, "Custom should be 100"

        # Verify the increase
        assert custom_limits.request_limit > default_limits.request_limit
        assert custom_limits.request_limit == default_limits.request_limit * 2

    def test_usage_limits_object_properties(self):
        """Test that the UsageLimits object has all expected properties."""
        limits = agent_module.get_custom_usage_limits()

        # Test that all expected attributes exist
        assert hasattr(limits, "request_limit")
        assert hasattr(limits, "request_tokens_limit")
        assert hasattr(limits, "response_tokens_limit")
        assert hasattr(limits, "total_tokens_limit")
        assert hasattr(limits, "has_token_limits")

        # Test attribute types
        assert isinstance(limits.request_limit, int)
        assert limits.request_tokens_limit is None or isinstance(
            limits.request_tokens_limit, int
        )
        assert limits.response_tokens_limit is None or isinstance(
            limits.response_tokens_limit, int
        )
        assert limits.total_tokens_limit is None or isinstance(
            limits.total_tokens_limit, int
        )

    def test_usage_limits_edge_cases(self):
        """Test edge cases for usage limits."""
        # Test that we can create limits with different values
        test_limits = UsageLimits(request_limit=200)
        assert test_limits.request_limit == 200

        # Test that we can create limits with all parameters
        full_limits = UsageLimits(
            request_limit=100,
            request_tokens_limit=5000,
            response_tokens_limit=10000,
            total_tokens_limit=15000,
        )
        assert full_limits.request_limit == 100
        assert full_limits.request_tokens_limit == 5000
        assert full_limits.response_tokens_limit == 10000
        assert full_limits.total_tokens_limit == 15000
        assert full_limits.has_token_limits()

    def test_usage_limits_documentation(self):
        """Test that the get_custom_usage_limits function has proper documentation."""
        func = agent_module.get_custom_usage_limits

        # Test that the function has a docstring
        assert func.__doc__ is not None
        assert len(func.__doc__.strip()) > 0

        # Test that the docstring mentions the key information
        docstring = func.__doc__.lower()
        assert "usage" in docstring or "limit" in docstring
        assert "100" in docstring or "request" in docstring


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__])

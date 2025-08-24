"""
Integration test to demonstrate the rate limiting change from 50 to 100 requests.

This test creates a simple demonstration that shows the rate limit has been
successfully increased and is being applied correctly.
"""

import pytest
from pydantic_ai.usage import UsageLimits

from code_puppy.agent import get_custom_usage_limits


class TestRateLimitIntegration:
    """Integration tests demonstrating the rate limit change."""

    def test_rate_limit_increase_demonstration(self):
        """Demonstrate that the rate limit has been increased from 50 to 100."""
        # Get the default limits (what pydantic-ai uses by default)
        default_limits = UsageLimits()

        # Get our custom limits
        custom_limits = get_custom_usage_limits()

        # Demonstrate the change
        print("\nRate Limit Comparison:")
        print(
            f"Default pydantic-ai rate limit: {default_limits.request_limit} requests"
        )
        print(f"Code-puppy custom rate limit: {custom_limits.request_limit} requests")
        print(
            f"Increase: {custom_limits.request_limit - default_limits.request_limit} requests ({((custom_limits.request_limit / default_limits.request_limit) - 1) * 100:.0f}% increase)"
        )

        # Verify the change
        assert default_limits.request_limit == 50, "Default should be 50"
        assert custom_limits.request_limit == 100, "Custom should be 100"
        assert custom_limits.request_limit == default_limits.request_limit * 2, (
            "Should be doubled"
        )

    def test_usage_limits_applied_consistently(self):
        """Test that the same usage limits are applied across all entry points."""
        from code_puppy.agent import get_custom_usage_limits as agent_limits
        from code_puppy.main import get_custom_usage_limits as main_limits
        from code_puppy.tui.app import get_custom_usage_limits as tui_limits

        # All should return the same function
        assert agent_limits is main_limits is tui_limits

        # All should return the same values
        agent_result = agent_limits()
        main_result = main_limits()
        tui_result = tui_limits()

        assert (
            agent_result.request_limit
            == main_result.request_limit
            == tui_result.request_limit
            == 100
        )

    def test_usage_limits_can_be_passed_to_agent_run(self):
        """Test that our custom usage limits can be passed to agent.run method."""
        # This is a simple test to verify the usage limits object is compatible
        custom_limits = get_custom_usage_limits()

        # Test that the object has the expected interface
        assert hasattr(custom_limits, "request_limit")
        assert custom_limits.request_limit == 100

        # Test that it's a proper UsageLimits object that can be used with pydantic-ai
        assert isinstance(custom_limits, UsageLimits)

        # Test that we can create similar objects (proving compatibility)
        similar_limits = UsageLimits(request_limit=100)
        assert similar_limits.request_limit == custom_limits.request_limit

    def test_usage_limits_object_validation(self):
        """Test that our custom usage limits object is valid and functional."""
        limits = get_custom_usage_limits()

        # Test basic properties
        assert isinstance(limits, UsageLimits)
        assert limits.request_limit == 100

        # Test that it has the expected methods
        assert hasattr(limits, "has_token_limits")
        assert callable(limits.has_token_limits)

        # Test method behavior
        assert not limits.has_token_limits()  # We only set request_limit

        # Test that we can create similar objects
        similar_limits = UsageLimits(request_limit=100)
        assert similar_limits.request_limit == limits.request_limit

    def test_rate_limit_configuration_documentation(self):
        """Test that the rate limit configuration is properly documented."""
        func = get_custom_usage_limits

        # Check that the function has documentation
        assert func.__doc__ is not None
        assert len(func.__doc__.strip()) > 0

        # Check that the documentation mentions key concepts
        doc_lower = func.__doc__.lower()
        assert any(word in doc_lower for word in ["usage", "limit", "request", "rate"])

        # Check that it mentions the specific value
        assert "100" in func.__doc__

    def test_backwards_compatibility_with_pydantic_ai(self):
        """Test that our changes are backwards compatible with pydantic-ai."""
        # Test that we can still create default UsageLimits
        default_limits = UsageLimits()
        assert default_limits.request_limit == 50

        # Test that we can create custom UsageLimits with various parameters
        custom_limits_1 = UsageLimits(request_limit=100)
        custom_limits_2 = UsageLimits(request_limit=200, request_tokens_limit=5000)
        custom_limits_3 = UsageLimits(
            request_limit=150,
            request_tokens_limit=3000,
            response_tokens_limit=4000,
            total_tokens_limit=7000,
        )

        # Verify they all work as expected
        assert custom_limits_1.request_limit == 100
        assert custom_limits_2.request_limit == 200
        assert custom_limits_2.request_tokens_limit == 5000
        assert custom_limits_3.request_limit == 150
        assert custom_limits_3.has_token_limits()

    def test_rate_limit_change_summary(self):
        """Provide a summary of the rate limit change for documentation purposes."""
        default_limits = UsageLimits()
        custom_limits = get_custom_usage_limits()

        # Create a summary of the change
        summary = {
            "original_limit": default_limits.request_limit,
            "new_limit": custom_limits.request_limit,
            "increase_amount": custom_limits.request_limit
            - default_limits.request_limit,
            "increase_percentage": (
                (custom_limits.request_limit / default_limits.request_limit) - 1
            )
            * 100,
            "change_description": f"Rate limit increased from {default_limits.request_limit} to {custom_limits.request_limit} requests per minute",
        }

        # Verify the summary
        assert summary["original_limit"] == 50
        assert summary["new_limit"] == 100
        assert summary["increase_amount"] == 50
        assert summary["increase_percentage"] == 100.0

        # Print summary for documentation
        print("\n=== Rate Limit Change Summary ===")
        print(f"Original limit: {summary['original_limit']} requests/minute")
        print(f"New limit: {summary['new_limit']} requests/minute")
        print(
            f"Increase: +{summary['increase_amount']} requests/minute ({summary['increase_percentage']:.0f}% increase)"
        )
        print(f"Description: {summary['change_description']}")
        print("=" * 35)


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v", "-s"])  # -s to show print statements

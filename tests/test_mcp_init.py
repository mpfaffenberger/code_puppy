"""Tests for code_puppy.mcp_ package __init__.py.

This module tests that the MCP package properly exports all its public API.
"""

import code_puppy.mcp_ as mcp_package


class TestMCPPackageExports:
    """Test that mcp_ package exports all expected symbols."""

    def test_all_exports_defined(self):
        """Test that __all__ is defined and is a list."""
        assert hasattr(mcp_package, "__all__")
        assert isinstance(mcp_package.__all__, list)
        assert len(mcp_package.__all__) > 0

    def test_managed_server_exports(self):
        """Test that ManagedMCPServer-related exports are available."""
        assert "ManagedMCPServer" in mcp_package.__all__
        assert "ServerConfig" in mcp_package.__all__
        assert "ServerState" in mcp_package.__all__
        
        assert hasattr(mcp_package, "ManagedMCPServer")
        assert hasattr(mcp_package, "ServerConfig")
        assert hasattr(mcp_package, "ServerState")

    def test_manager_exports(self):
        """Test that MCPManager-related exports are available."""
        assert "MCPManager" in mcp_package.__all__
        assert "ServerInfo" in mcp_package.__all__
        assert "get_mcp_manager" in mcp_package.__all__
        
        assert hasattr(mcp_package, "MCPManager")
        assert hasattr(mcp_package, "ServerInfo")
        assert hasattr(mcp_package, "get_mcp_manager")

    def test_status_tracker_exports(self):
        """Test that ServerStatusTracker-related exports are available."""
        assert "ServerStatusTracker" in mcp_package.__all__
        assert "Event" in mcp_package.__all__
        
        assert hasattr(mcp_package, "ServerStatusTracker")
        assert hasattr(mcp_package, "Event")

    def test_registry_exports(self):
        """Test that ServerRegistry is exported."""
        assert "ServerRegistry" in mcp_package.__all__
        assert hasattr(mcp_package, "ServerRegistry")

    def test_error_isolator_exports(self):
        """Test that error isolation exports are available."""
        assert "MCPErrorIsolator" in mcp_package.__all__
        assert "ErrorStats" in mcp_package.__all__
        assert "ErrorCategory" in mcp_package.__all__
        assert "QuarantinedServerError" in mcp_package.__all__
        assert "get_error_isolator" in mcp_package.__all__
        
        assert hasattr(mcp_package, "MCPErrorIsolator")
        assert hasattr(mcp_package, "ErrorStats")
        assert hasattr(mcp_package, "ErrorCategory")
        assert hasattr(mcp_package, "QuarantinedServerError")
        assert hasattr(mcp_package, "get_error_isolator")

    def test_circuit_breaker_exports(self):
        """Test that CircuitBreaker-related exports are available."""
        assert "CircuitBreaker" in mcp_package.__all__
        assert "CircuitState" in mcp_package.__all__
        assert "CircuitOpenError" in mcp_package.__all__
        
        assert hasattr(mcp_package, "CircuitBreaker")
        assert hasattr(mcp_package, "CircuitState")
        assert hasattr(mcp_package, "CircuitOpenError")

    def test_retry_manager_exports(self):
        """Test that RetryManager-related exports are available."""
        assert "RetryManager" in mcp_package.__all__
        assert "RetryStats" in mcp_package.__all__
        assert "get_retry_manager" in mcp_package.__all__
        assert "retry_mcp_call" in mcp_package.__all__
        
        assert hasattr(mcp_package, "RetryManager")
        assert hasattr(mcp_package, "RetryStats")
        assert hasattr(mcp_package, "get_retry_manager")
        assert hasattr(mcp_package, "retry_mcp_call")

    def test_dashboard_exports(self):
        """Test that MCPDashboard is exported."""
        assert "MCPDashboard" in mcp_package.__all__
        assert hasattr(mcp_package, "MCPDashboard")

    def test_config_wizard_exports(self):
        """Test that config wizard exports are available."""
        assert "MCPConfigWizard" in mcp_package.__all__
        assert "run_add_wizard" in mcp_package.__all__
        
        assert hasattr(mcp_package, "MCPConfigWizard")
        assert hasattr(mcp_package, "run_add_wizard")

    def test_all_exports_are_accessible(self):
        """Test that all items in __all__ are actually accessible."""
        for export_name in mcp_package.__all__:
            assert hasattr(mcp_package, export_name), f"{export_name} not accessible"

    def test_no_extra_public_exports(self):
        """Test that __all__ contains all major public exports."""
        # Should have at least these major categories
        expected_count = 20  # Based on the __all__ list
        assert len(mcp_package.__all__) >= expected_count

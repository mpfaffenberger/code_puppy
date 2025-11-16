"""Tests for network proxy server."""

import unittest

from code_puppy.sandbox.network_proxy import NetworkProxyServer


class TestNetworkProxyServer(unittest.TestCase):
    """Test cases for NetworkProxyServer."""

    def setUp(self):
        """Set up test fixtures."""
        self.proxy = NetworkProxyServer(port=9051)  # Use different port for testing

    def test_initialization(self):
        """Test proxy server initialization."""
        self.assertEqual(self.proxy.port, 9051)
        self.assertIsInstance(self.proxy.allowed_domains, set)
        self.assertFalse(self.proxy.is_running())

    def test_default_allowed_domains(self):
        """Test that default safe domains are pre-allowed."""
        # Check for common safe domains
        self.assertIn("github.com", self.proxy.allowed_domains)
        self.assertIn("pypi.org", self.proxy.allowed_domains)
        self.assertIn("npmjs.com", self.proxy.allowed_domains)

    def test_add_allowed_domain(self):
        """Test adding a domain to the allowlist."""
        self.proxy.add_allowed_domain("example.com")
        self.assertIn("example.com", self.proxy.allowed_domains)

    def test_add_allowed_domain_case_insensitive(self):
        """Test that domain matching is case-insensitive."""
        self.proxy.add_allowed_domain("Example.COM")
        self.assertIn("example.com", self.proxy.allowed_domains)

    def test_remove_allowed_domain(self):
        """Test removing a domain from the allowlist."""
        self.proxy.add_allowed_domain("test.com")
        self.assertIn("test.com", self.proxy.allowed_domains)

        self.proxy.remove_allowed_domain("test.com")
        self.assertNotIn("test.com", self.proxy.allowed_domains)

    async def test_is_domain_allowed_for_allowed_domain(self):
        """Test domain check for allowed domain."""
        self.proxy.add_allowed_domain("example.com")
        result = await self.proxy._is_domain_allowed("example.com")
        self.assertTrue(result)

    async def test_is_domain_allowed_for_disallowed_domain(self):
        """Test domain check for disallowed domain without callback."""
        # Without approval callback, should deny
        result = await self.proxy._is_domain_allowed("evil.com")
        self.assertFalse(result)

    async def test_is_domain_allowed_with_approval_callback(self):
        """Test domain check with approval callback."""
        # Mock approval callback that approves the domain
        async def mock_approval(domain):
            return domain == "approved.com"

        self.proxy.approval_callback = mock_approval

        # Test approved domain
        result = await self.proxy._is_domain_allowed("approved.com")
        self.assertTrue(result)
        self.assertIn("approved.com", self.proxy.allowed_domains)

        # Test rejected domain
        result = await self.proxy._is_domain_allowed("rejected.com")
        self.assertFalse(result)
        self.assertNotIn("rejected.com", self.proxy.allowed_domains)

    async def test_is_domain_allowed_wildcard_match(self):
        """Test wildcard domain matching."""
        self.proxy.add_allowed_domain("*.example.com")

        # Should match subdomain
        result = await self.proxy._is_domain_allowed("api.example.com")
        self.assertTrue(result)

        # Should not match parent domain
        result = await self.proxy._is_domain_allowed("example.com")
        self.assertFalse(result)

    async def test_start_stop_proxy(self):
        """Test starting and stopping the proxy server."""
        await self.proxy.start()
        self.assertTrue(self.proxy.is_running())

        await self.proxy.stop()
        self.assertFalse(self.proxy.is_running())

    def test_proxy_not_running_initially(self):
        """Test that proxy is not running when created."""
        proxy = NetworkProxyServer(port=9052)
        self.assertFalse(proxy.is_running())


class TestNetworkProxyIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for network proxy (async tests)."""

    async def test_start_and_stop_server(self):
        """Test starting and stopping the server."""
        proxy = NetworkProxyServer(port=0)  # Use random available port
        await proxy.start()

        try:
            self.assertTrue(proxy.is_running())
            self.assertIsNotNone(proxy.server)
        finally:
            await proxy.stop()

        self.assertFalse(proxy.is_running())


if __name__ == "__main__":
    unittest.main()

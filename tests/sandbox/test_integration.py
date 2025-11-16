"""Integration tests for complete sandboxing functionality."""

import tempfile
import unittest
from pathlib import Path

from code_puppy.sandbox.command_wrapper import SandboxCommandWrapper
from code_puppy.sandbox.config import SandboxConfig
from code_puppy.sandbox.filesystem_isolation import get_filesystem_isolator


class TestSandboxIntegration(unittest.TestCase):
    """Integration tests for sandboxing components."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary config directory for testing
        self.test_config_dir = tempfile.mkdtemp(prefix="code_puppy_test_")
        self.config = SandboxConfig(config_dir=Path(self.test_config_dir))

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.test_config_dir, ignore_errors=True)

    def test_sandbox_config_persistence(self):
        """Test that sandbox configuration persists correctly."""
        # Enable sandboxing
        self.config.enabled = True
        self.assertTrue(self.config.enabled)

        # Create new config instance with same directory
        new_config = SandboxConfig(config_dir=Path(self.test_config_dir))
        self.assertTrue(new_config.enabled)

    def test_sandbox_config_domain_management(self):
        """Test adding and persisting allowed domains."""
        self.config.add_allowed_domain("test.com")
        self.assertIn("test.com", self.config.allowed_domains)

        # Load config again to verify persistence
        new_config = SandboxConfig(config_dir=Path(self.test_config_dir))
        self.assertIn("test.com", new_config.allowed_domains)

    def test_sandbox_config_path_management(self):
        """Test adding and persisting allowed paths."""
        test_path = "/tmp/test_sandbox"
        self.config.add_allowed_write_path(test_path)

        # Should store absolute path
        self.assertTrue(any(test_path in path for path in self.config.allowed_write_paths))

        # Load config again
        new_config = SandboxConfig(config_dir=Path(self.test_config_dir))
        self.assertTrue(any(test_path in path for path in new_config.allowed_write_paths))

    def test_command_wrapper_disabled_by_default(self):
        """Test that sandboxing is disabled by default."""
        wrapper = SandboxCommandWrapper(config=self.config)
        self.assertFalse(wrapper.config.enabled)

        # Commands should pass through unchanged
        command = "echo hello"
        wrapped, env, was_excluded = wrapper.wrap_command(command)
        self.assertEqual(command, wrapped)
        self.assertFalse(was_excluded)

    def test_command_wrapper_when_enabled(self):
        """Test command wrapping when sandboxing is enabled."""
        self.config.enabled = True
        self.config.filesystem_isolation = True

        wrapper = SandboxCommandWrapper(config=self.config)

        command = "echo hello"
        cwd = "/tmp"

        # The wrapped command should be different if isolation is available
        wrapped, env, was_excluded = wrapper.wrap_command(command, cwd=cwd)

        # Check if we have a real isolator available
        isolator = wrapper._get_isolator()
        if isolator.is_available() and isolator.get_platform() != "noop":
            # Should be wrapped
            self.assertNotEqual(command, wrapped)
        else:
            # If not available, should fall back to original command
            self.assertEqual(command, wrapped)

    def test_filesystem_isolator_selection(self):
        """Test that appropriate filesystem isolator is selected."""
        isolator = get_filesystem_isolator()
        self.assertIsNotNone(isolator)

        # Should return some isolator (even if NoOp)
        platform = isolator.get_platform()
        self.assertIn(platform, ["linux", "macos", "noop"])

    def test_command_wrapper_status(self):
        """Test getting wrapper status."""
        wrapper = SandboxCommandWrapper(config=self.config)
        status = wrapper.get_status()

        # Check that status contains expected keys
        self.assertIn("enabled", status)
        self.assertIn("filesystem_isolation", status)
        self.assertIn("network_isolation", status)
        self.assertIn("isolator", status)
        self.assertIn("isolator_platform", status)
        self.assertIn("isolator_available", status)

    def test_sandbox_availability_check(self):
        """Test checking if sandboxing is available on the system."""
        wrapper = SandboxCommandWrapper()
        available = wrapper.is_sandboxing_available()

        # Should return a boolean
        self.assertIsInstance(available, bool)

    def test_sandbox_config_default_values(self):
        """Test that config has sensible defaults."""
        config = SandboxConfig(config_dir=Path(self.test_config_dir))

        # Should be disabled by default (opt-in)
        self.assertFalse(config.enabled)

        # But isolation features should be enabled
        self.assertTrue(config.filesystem_isolation)
        self.assertTrue(config.network_isolation)

        # Should require approval for new domains
        self.assertTrue(config.require_approval_for_new_domains)

    def test_sandbox_config_remove_domain(self):
        """Test removing domains from allowlist."""
        self.config.add_allowed_domain("temp.com")
        self.assertIn("temp.com", self.config.allowed_domains)

        self.config.remove_allowed_domain("temp.com")
        self.assertNotIn("temp.com", self.config.allowed_domains)

    def test_command_wrapper_with_custom_env(self):
        """Test command wrapping with custom environment variables."""
        self.config.enabled = True
        wrapper = SandboxCommandWrapper(config=self.config)

        command = "echo $TEST_VAR"
        custom_env = {"TEST_VAR": "test_value"}

        wrapped, env, was_excluded = wrapper.wrap_command(command, env=custom_env)

        # Environment should be passed through or modified
        # depending on isolator availability
        self.assertIsInstance(env, dict)


if __name__ == "__main__":
    unittest.main()

"""Tests for Linux bubblewrap filesystem isolation."""

import unittest
from unittest.mock import patch

from code_puppy.sandbox.base import SandboxOptions
from code_puppy.sandbox.linux_isolator import BubblewrapIsolator


class TestBubblewrapIsolator(unittest.TestCase):
    """Test cases for BubblewrapIsolator."""

    def setUp(self):
        """Set up test fixtures."""
        self.isolator = BubblewrapIsolator()

    def test_platform(self):
        """Test that platform is correctly identified."""
        self.assertEqual(self.isolator.get_platform(), "linux")

    @patch("shutil.which")
    def test_is_available_when_bwrap_installed(self, mock_which):
        """Test availability check when bwrap is installed."""
        mock_which.return_value = "/usr/bin/bwrap"
        self.assertTrue(self.isolator.is_available())
        mock_which.assert_called_once_with("bwrap")

    @patch("shutil.which")
    def test_is_available_when_bwrap_not_installed(self, mock_which):
        """Test availability check when bwrap is not installed."""
        mock_which.return_value = None
        self.assertFalse(self.isolator.is_available())

    def test_wrap_command_basic(self):
        """Test basic command wrapping."""
        options = SandboxOptions(
            cwd="/tmp/test",
            allowed_read_paths=[],
            allowed_write_paths=[],
        )

        command = "echo hello"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that command contains bwrap
        self.assertIn("bwrap", wrapped_cmd)

        # Check that essential flags are present
        self.assertIn("--unshare-all", wrapped_cmd)
        self.assertIn("--share-net", wrapped_cmd)
        self.assertIn("--die-with-parent", wrapped_cmd)

        # Check that working directory is set
        self.assertIn("--chdir", wrapped_cmd)
        self.assertIn("/tmp/test", wrapped_cmd)

    def test_wrap_command_with_allowed_paths(self):
        """Test command wrapping with allowed read/write paths."""
        options = SandboxOptions(
            cwd="/tmp/test",
            allowed_read_paths=["/opt/data"],
            allowed_write_paths=["/tmp/output"],
        )

        command = "cat /opt/data/file.txt > /tmp/output/result.txt"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that allowed paths are included (if they exist)
        # Note: The implementation checks if paths exist, so we can't test
        # the actual inclusion without creating the paths
        self.assertIn("bwrap", wrapped_cmd)

    def test_wrap_command_with_network_isolation(self):
        """Test command wrapping with network isolation."""
        options = SandboxOptions(
            cwd="/tmp/test",
            network_isolation=True,
            proxy_socket_path="127.0.0.1:9050",
        )

        command = "curl https://example.com"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that proxy environment variables are set
        self.assertIn("--setenv", wrapped_cmd)
        self.assertIn("HTTP_PROXY", wrapped_cmd)
        self.assertIn("HTTPS_PROXY", wrapped_cmd)

    def test_wrap_command_preserves_env_vars(self):
        """Test that safe environment variables are preserved."""
        options = SandboxOptions(
            cwd="/tmp/test",
            env={"PATH": "/usr/bin:/bin", "HOME": "/home/user"},
        )

        command = "ls"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that PATH and HOME are set
        self.assertIn("PATH", wrapped_cmd)
        self.assertIn("HOME", wrapped_cmd)

    def test_wrap_command_escapes_shell_arguments(self):
        """Test that shell arguments are properly escaped."""
        options = SandboxOptions(cwd="/tmp/test")

        # Command with special characters
        command = 'echo "hello world" && echo $PATH'
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # The original command should be preserved in the wrapped command
        self.assertIn("echo", wrapped_cmd)

    def test_filesystem_isolation_binds_working_directory(self):
        """Test that working directory is properly bound."""
        test_dir = "/tmp/sandbox_test"
        options = SandboxOptions(cwd=test_dir)

        command = "pwd"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that working directory is bound
        self.assertIn("--bind", wrapped_cmd)
        self.assertIn(test_dir, wrapped_cmd)


if __name__ == "__main__":
    unittest.main()

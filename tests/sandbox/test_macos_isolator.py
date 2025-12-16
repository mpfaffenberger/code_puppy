"""Tests for macOS sandbox-exec filesystem isolation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code_puppy.sandbox.base import SandboxOptions
from code_puppy.sandbox.macos_isolator import SandboxExecIsolator


class TestSandboxExecIsolator(unittest.TestCase):
    """Test cases for SandboxExecIsolator."""

    def setUp(self):
        """Set up test fixtures."""
        self.isolator = SandboxExecIsolator()

    def test_platform(self):
        """Test that platform is correctly identified."""
        self.assertEqual(self.isolator.get_platform(), "macos")

    @patch("shutil.which")
    def test_is_available_when_sandbox_exec_installed(self, mock_which):
        """Test availability check when sandbox-exec is installed."""
        mock_which.return_value = "/usr/bin/sandbox-exec"
        self.assertTrue(self.isolator.is_available())
        mock_which.assert_called_once_with("sandbox-exec")

    @patch("shutil.which")
    def test_is_available_when_sandbox_exec_not_installed(self, mock_which):
        """Test availability check when sandbox-exec is not installed."""
        mock_which.return_value = None
        self.assertFalse(self.isolator.is_available())

    def test_generate_sandbox_profile_basic(self):
        """Test basic sandbox profile generation."""
        options = SandboxOptions(cwd="/tmp/test")

        profile = self.isolator._generate_sandbox_profile(options)

        # Check that profile contains essential directives
        self.assertIn("(version 1)", profile)
        # With broad read scope (default), we don't deny by default
        self.assertIn("(allow process-exec*)", profile)
        self.assertIn("(allow network*)", profile)

        # Check that working directory is allowed
        self.assertIn("/tmp/test", profile)

    def test_generate_sandbox_profile_with_allowed_paths(self):
        """Test profile generation with allowed read/write paths."""
        options = SandboxOptions(
            cwd="/tmp/test",
            allowed_read_paths=["/opt/data"],
            allowed_write_paths=["/tmp/output"],
            read_scope="restricted",  # Use restricted mode to test specific paths
        )

        profile = self.isolator._generate_sandbox_profile(options)

        # Check that allowed paths are included in profile
        self.assertIn("/opt/data", profile)
        self.assertIn("/tmp/output", profile)
        self.assertIn("(allow file-read*", profile)
        self.assertIn("(allow file*", profile)

    def test_generate_sandbox_profile_blocks_sensitive_paths(self):
        """Test that sensitive paths are explicitly denied."""
        options = SandboxOptions(cwd="/tmp/test")

        profile = self.isolator._generate_sandbox_profile(options)

        # Check that sensitive paths are denied
        self.assertIn("/.ssh", profile)
        self.assertIn("/.aws", profile)
        self.assertIn("/.gnupg", profile)
        self.assertIn("(deny file*", profile)

    def test_wrap_command_basic(self):
        """Test basic command wrapping."""
        options = SandboxOptions(cwd="/tmp/test")

        command = "echo hello"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that command contains sandbox-exec
        self.assertIn("sandbox-exec", wrapped_cmd)

        # Check that profile file reference is included
        self.assertIn("-f", wrapped_cmd)

        # Check that HOME parameter is set
        self.assertIn("-D", wrapped_cmd)
        self.assertIn("HOME=", wrapped_cmd)

    def test_wrap_command_creates_profile_file(self):
        """Test that a profile file is created."""
        options = SandboxOptions(cwd="/tmp/test")

        command = "ls"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Extract profile path from wrapped command
        # The profile should be in a temp directory
        profile_dir = Path(tempfile.gettempdir()) / "code_puppy_sandbox"
        self.assertTrue(profile_dir.exists())

    def test_wrap_command_with_network_isolation(self):
        """Test command wrapping with network isolation."""
        options = SandboxOptions(
            cwd="/tmp/test",
            network_isolation=True,
            proxy_socket_path="127.0.0.1:9050",
        )

        command = "curl https://example.com"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that proxy environment variables are set in env dict
        self.assertIn("HTTP_PROXY", env)
        self.assertIn("HTTPS_PROXY", env)
        self.assertEqual(env["HTTP_PROXY"], "socks5://localhost:9050")

    def test_wrap_command_preserves_home_env(self):
        """Test that HOME environment variable is preserved."""
        test_home = "/Users/testuser"
        options = SandboxOptions(
            cwd="/tmp/test", env={"HOME": test_home}
        )

        command = "echo $HOME"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that HOME is in the parameter definition
        self.assertIn(f"HOME={test_home}", wrapped_cmd)

    def test_wrap_command_uses_sh(self):
        """Test that commands are executed via /bin/sh."""
        options = SandboxOptions(cwd="/tmp/test")

        command = "echo test"
        wrapped_cmd, env = self.isolator.wrap_command(command, options)

        # Check that /bin/sh is used
        self.assertIn("/bin/sh", wrapped_cmd)
        self.assertIn("-c", wrapped_cmd)


if __name__ == "__main__":
    unittest.main()

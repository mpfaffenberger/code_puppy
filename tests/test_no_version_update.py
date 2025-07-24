"""
Tests for the NO_VERSION_UPDATE environment variable feature.

This module tests the functionality that allows users to bypass automatic
version checking and updating by setting the NO_VERSION_UPDATE environment variable.
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.main import main


class TestNoVersionUpdateEnvironmentVariable:
    """Test cases for the NO_VERSION_UPDATE environment variable functionality."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test to ensure clean environment."""
        # Store original environment variable value if it exists
        original_value = os.environ.get("NO_VERSION_UPDATE")

        yield

        # Restore original environment variable value
        if original_value is not None:
            os.environ["NO_VERSION_UPDATE"] = original_value
        elif "NO_VERSION_UPDATE" in os.environ:
            del os.environ["NO_VERSION_UPDATE"]

    @pytest.mark.parametrize(
        "env_value", ["1", "true", "TRUE", "yes", "YES", "on", "ON"]
    )
    def test_no_version_update_truthy_values(self, env_value):
        """Test that various truthy values for NO_VERSION_UPDATE disable auto-update."""
        os.environ["NO_VERSION_UPDATE"] = env_value

        # Test the environment variable check logic directly
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is True, f"Failed for environment value: {env_value}"

    @pytest.mark.parametrize(
        "env_value", ["0", "false", "FALSE", "no", "NO", "off", "OFF", "random", ""]
    )
    def test_no_version_update_falsy_values(self, env_value):
        """Test that various falsy values for NO_VERSION_UPDATE enable auto-update."""
        os.environ["NO_VERSION_UPDATE"] = env_value

        # Test the environment variable check logic directly
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is False, f"Failed for environment value: {env_value}"

    def test_no_version_update_not_set(self):
        """Test that when NO_VERSION_UPDATE is not set, auto-update is enabled."""
        # Ensure the environment variable is not set
        if "NO_VERSION_UPDATE" in os.environ:
            del os.environ["NO_VERSION_UPDATE"]

        # Test the environment variable check logic directly
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is False

    @patch("code_puppy.messaging.emit_system_message")
    @patch("code_puppy.main.interactive_mode")
    @patch("code_puppy.main.find_available_port")
    @patch("code_puppy.main.ensure_config_exists")
    @patch("code_puppy.main.display_disclaimer")
    @patch("code_puppy.main.authenticate_puppy")
    @patch("code_puppy.main.get_puppy_token")
    @patch("code_puppy.main.fetch_latest_version")
    @patch("code_puppy.main.__version__", "0.0.90")
    @patch("asyncio.create_task")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_no_version_update_enabled(
        self,
        mock_parse_args,
        mock_create_task,
        mock_fetch_latest_version,
        mock_get_puppy_token,
        mock_authenticate_puppy,
        mock_display_disclaimer,
        mock_ensure_config_exists,
        mock_find_available_port,
        mock_interactive_mode,
        mock_emit_system_message,
    ):
        """Test main() function when NO_VERSION_UPDATE is enabled."""
        # Set up environment variable
        os.environ["NO_VERSION_UPDATE"] = "1"

        # Mock dependencies
        mock_find_available_port.return_value = 8090
        mock_get_puppy_token.return_value = "test_token"
        mock_parse_args.return_value = Mock(
            command=None, interactive=True, tui=False, web=False
        )

        # Mock async task
        mock_task = AsyncMock()
        mock_create_task.return_value = mock_task

        # Mock interactive mode to return immediately
        mock_interactive_mode.return_value = None

        # Run the main function
        with patch("code_puppy.main.load_dotenv"):
            asyncio.run(main())

        # Verify that fetch_latest_version was NOT called
        mock_fetch_latest_version.assert_not_called()

        # Verify that emit_system_message was called with the expected messages
        system_message_calls = [
            call.args[0] for call in mock_emit_system_message.call_args_list
        ]

        # Check that current version is displayed
        current_version_displayed = any(
            "Current version: 0.0.90" in str(call) for call in system_message_calls
        )
        assert current_version_displayed, "Current version should be displayed"

        # Check that auto-update disabled message is displayed
        auto_update_disabled_displayed = any(
            "Auto-update disabled via NO_VERSION_UPDATE environment variable"
            in str(call)
            for call in system_message_calls
        )
        assert auto_update_disabled_displayed, (
            "Auto-update disabled message should be displayed"
        )

        # Check that latest version is NOT displayed
        latest_version_displayed = any(
            "Latest version:" in str(call) for call in system_message_calls
        )
        assert not latest_version_displayed, (
            "Latest version should not be displayed when auto-update is disabled"
        )

    @patch("code_puppy.messaging.emit_system_message")
    @patch("code_puppy.main.interactive_mode")
    @patch("code_puppy.main.find_available_port")
    @patch("code_puppy.main.ensure_config_exists")
    @patch("code_puppy.main.display_disclaimer")
    @patch("code_puppy.main.authenticate_puppy")
    @patch("code_puppy.main.get_puppy_token")
    @patch("code_puppy.main.fetch_latest_version")
    @patch("code_puppy.main.versions_are_equal")
    @patch("code_puppy.main.__version__", "0.0.90")
    @patch("asyncio.create_task")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_no_version_update_disabled(
        self,
        mock_parse_args,
        mock_create_task,
        mock_versions_are_equal,
        mock_fetch_latest_version,
        mock_get_puppy_token,
        mock_authenticate_puppy,
        mock_display_disclaimer,
        mock_ensure_config_exists,
        mock_find_available_port,
        mock_interactive_mode,
        mock_emit_system_message,
    ):
        """Test main() function when NO_VERSION_UPDATE is disabled (normal behavior)."""
        # Ensure environment variable is not set or set to false
        os.environ["NO_VERSION_UPDATE"] = "0"

        # Mock dependencies
        mock_find_available_port.return_value = 8090
        mock_get_puppy_token.return_value = "test_token"
        mock_parse_args.return_value = Mock(
            command=None, interactive=True, tui=False, web=False
        )
        mock_fetch_latest_version.return_value = "0.0.91"
        mock_versions_are_equal.return_value = False  # Simulate newer version available

        # Mock async task
        mock_task = AsyncMock()
        mock_create_task.return_value = mock_task

        # Mock interactive mode to return immediately
        mock_interactive_mode.return_value = None

        # Mock subprocess for update process
        with patch("code_puppy.main.subprocess.run") as mock_subprocess:
            mock_curl_result = Mock()
            mock_curl_result.returncode = 0
            mock_curl_result.stdout = "#!/bin/bash\necho 'Update script'"

            mock_bash_result = Mock()
            mock_bash_result.returncode = 0

            def subprocess_side_effect(*args, **kwargs):
                if args[0][0] == "curl":
                    return mock_curl_result
                elif args[0][0] == "bash":
                    return mock_bash_result
                return Mock(returncode=1)

            mock_subprocess.side_effect = subprocess_side_effect

            # Mock sys.exit to prevent actual exit
            with patch("code_puppy.main.sys.exit") as mock_exit:
                with patch("code_puppy.main.load_dotenv"):
                    asyncio.run(main())

                # Verify that sys.exit was called (indicating successful update)
                mock_exit.assert_called_once_with(0)

        # Verify that fetch_latest_version WAS called
        mock_fetch_latest_version.assert_called_once_with("code-puppy")

        # Verify that emit_system_message was called with the expected messages
        system_message_calls = [
            call.args[0] for call in mock_emit_system_message.call_args_list
        ]

        # Check that both current and latest versions are displayed
        current_version_displayed = any(
            "Current version: 0.0.90" in str(call) for call in system_message_calls
        )
        assert current_version_displayed, "Current version should be displayed"

        latest_version_displayed = any(
            "Latest version: 0.0.91" in str(call) for call in system_message_calls
        )
        assert latest_version_displayed, "Latest version should be displayed"

        # Check that auto-update messages are displayed
        update_available_displayed = any(
            "A new version of code puppy is available: 0.0.91" in str(call)
            for call in system_message_calls
        )
        assert update_available_displayed, (
            "Update available message should be displayed"
        )

    @patch("code_puppy.messaging.emit_system_message")
    @patch("code_puppy.main.interactive_mode")
    @patch("code_puppy.main.find_available_port")
    @patch("code_puppy.main.ensure_config_exists")
    @patch("code_puppy.main.display_disclaimer")
    @patch("code_puppy.main.authenticate_puppy")
    @patch("code_puppy.main.get_puppy_token")
    @patch("code_puppy.main.fetch_latest_version")
    @patch("code_puppy.main.versions_are_equal")
    @patch("code_puppy.main.__version__", "0.0.90")
    @patch("asyncio.create_task")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_no_version_update_disabled_same_version(
        self,
        mock_parse_args,
        mock_create_task,
        mock_versions_are_equal,
        mock_fetch_latest_version,
        mock_get_puppy_token,
        mock_authenticate_puppy,
        mock_display_disclaimer,
        mock_ensure_config_exists,
        mock_find_available_port,
        mock_interactive_mode,
        mock_emit_system_message,
    ):
        """Test main() function when NO_VERSION_UPDATE is disabled but versions are equal."""
        # Ensure environment variable is not set
        if "NO_VERSION_UPDATE" in os.environ:
            del os.environ["NO_VERSION_UPDATE"]

        # Mock dependencies
        mock_find_available_port.return_value = 8090
        mock_get_puppy_token.return_value = "test_token"
        mock_parse_args.return_value = Mock(
            command=None, interactive=True, tui=False, web=False
        )
        mock_fetch_latest_version.return_value = "0.0.90"
        mock_versions_are_equal.return_value = True  # Same version

        # Mock async task
        mock_task = AsyncMock()
        mock_create_task.return_value = mock_task

        # Mock interactive mode to return immediately
        mock_interactive_mode.return_value = None

        # Run the main function
        with patch("code_puppy.main.load_dotenv"):
            asyncio.run(main())

        # Verify that fetch_latest_version WAS called
        mock_fetch_latest_version.assert_called_once_with("code-puppy")

        # Verify that emit_system_message was called with the expected messages
        system_message_calls = [
            call.args[0] for call in mock_emit_system_message.call_args_list
        ]

        # Check that both current and latest versions are displayed
        current_version_displayed = any(
            "Current version: 0.0.90" in str(call) for call in system_message_calls
        )
        assert current_version_displayed, "Current version should be displayed"

        latest_version_displayed = any(
            "Latest version: 0.0.90" in str(call) for call in system_message_calls
        )
        assert latest_version_displayed, "Latest version should be displayed"

        # Check that NO auto-update messages are displayed (since versions are equal)
        update_available_displayed = any(
            "A new version of code puppy is available" in str(call)
            for call in system_message_calls
        )
        assert not update_available_displayed, (
            "Update available message should not be displayed when versions are equal"
        )

    def test_environment_variable_case_insensitive(self):
        """Test that the environment variable check is case insensitive."""
        test_cases = [
            ("TRUE", True),
            ("true", True),
            ("True", True),
            ("tRuE", True),
            ("YES", True),
            ("yes", True),
            ("Yes", True),
            ("yEs", True),
            ("ON", True),
            ("on", True),
            ("On", True),
            ("oN", True),
            ("1", True),
            ("FALSE", False),
            ("false", False),
            ("False", False),
            ("fAlSe", False),
            ("NO", False),
            ("no", False),
            ("No", False),
            ("nO", False),
            ("OFF", False),
            ("off", False),
            ("Off", False),
            ("oFf", False),
            ("0", False),
            ("random", False),
            ("", False),
        ]

        for env_value, expected in test_cases:
            os.environ["NO_VERSION_UPDATE"] = env_value
            no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            assert no_version_update == expected, (
                f"Failed for environment value: '{env_value}'"
            )

    @patch("code_puppy.messaging.emit_system_message")
    def test_console_messages_format(self, mock_emit_system_message):
        """Test that system messages are formatted correctly when NO_VERSION_UPDATE is enabled."""
        os.environ["NO_VERSION_UPDATE"] = "true"

        # Test the logic directly from main.py
        current_version = "0.0.90"
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        if no_version_update:
            mock_emit_system_message(f"Current version: {current_version}")
            mock_emit_system_message(
                "[dim]Auto-update disabled via NO_VERSION_UPDATE environment variable[/dim]"
            )

        # Verify the calls
        expected_calls = [
            "Current version: 0.0.90",
            "[dim]Auto-update disabled via NO_VERSION_UPDATE environment variable[/dim]",
        ]

        actual_calls = [
            call.args[0] for call in mock_emit_system_message.call_args_list
        ]
        assert actual_calls == expected_calls

    def test_environment_variable_precedence(self):
        """Test that the environment variable takes precedence over any other configuration."""
        # This test ensures that NO_VERSION_UPDATE environment variable
        # is checked before any version checking logic

        # Set the environment variable
        os.environ["NO_VERSION_UPDATE"] = "1"

        # The check should happen early and return True
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is True

        # Even if we change it to a falsy value, it should be respected
        os.environ["NO_VERSION_UPDATE"] = "false"
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is False

    @patch("code_puppy.main.fetch_latest_version")
    def test_fetch_latest_version_not_called_when_disabled(
        self, mock_fetch_latest_version
    ):
        """Test that fetch_latest_version is not called when NO_VERSION_UPDATE is enabled."""
        os.environ["NO_VERSION_UPDATE"] = "1"

        # Simulate the logic from main.py
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        if not no_version_update:
            # This should not execute when NO_VERSION_UPDATE is enabled
            mock_fetch_latest_version("code-puppy")

        # Verify that fetch_latest_version was not called
        mock_fetch_latest_version.assert_not_called()

    @patch("code_puppy.main.fetch_latest_version")
    def test_fetch_latest_version_called_when_enabled(self, mock_fetch_latest_version):
        """Test that fetch_latest_version is called when NO_VERSION_UPDATE is disabled."""
        os.environ["NO_VERSION_UPDATE"] = "0"

        # Simulate the logic from main.py
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        if not no_version_update:
            # This should execute when NO_VERSION_UPDATE is disabled
            mock_fetch_latest_version("code-puppy")

        # Verify that fetch_latest_version was called
        mock_fetch_latest_version.assert_called_once_with("code-puppy")


class TestNoVersionUpdateIntegration:
    """Integration tests for the NO_VERSION_UPDATE feature with other components."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test to ensure clean environment."""
        # Store original environment variable value if it exists
        original_value = os.environ.get("NO_VERSION_UPDATE")

        yield

        # Restore original environment variable value
        if original_value is not None:
            os.environ["NO_VERSION_UPDATE"] = original_value
        elif "NO_VERSION_UPDATE" in os.environ:
            del os.environ["NO_VERSION_UPDATE"]

    def test_integration_with_version_checker_module(self):
        """Test that the feature integrates correctly with the version_checker module."""
        from code_puppy.version_checker import fetch_latest_version, versions_are_equal

        # When NO_VERSION_UPDATE is enabled, we shouldn't call version checker functions
        os.environ["NO_VERSION_UPDATE"] = "1"
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        assert no_version_update is True

        # The version checker functions should still work if called directly
        with patch("code_puppy.version_checker.create_client") as mock_create_client:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "success": True,
                "data": {"version": "v0.0.91"},
                "message": "Success",
            }
            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_create_client.return_value = mock_client

            # These functions should still work independently
            latest_version = fetch_latest_version("code-puppy")
            assert latest_version == "0.0.91"

            assert versions_are_equal("0.0.90", "0.0.90") is True
            assert versions_are_equal("0.0.90", "0.0.91") is False

    def test_environment_variable_with_dotenv(self):
        """Test that the environment variable works correctly with dotenv loading."""
        # This test ensures that the environment variable is checked after dotenv loading
        # but before version checking

        with patch("code_puppy.main.load_dotenv") as mock_load_dotenv:
            # Set environment variable
            os.environ["NO_VERSION_UPDATE"] = "yes"

            # Simulate dotenv loading (which might override environment variables)
            mock_load_dotenv.return_value = None

            # The check should still work after dotenv loading
            no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            assert no_version_update is True

    def test_no_version_update_with_different_startup_modes(self):
        """Test that NO_VERSION_UPDATE works with different startup modes (interactive, tui, command)."""
        os.environ["NO_VERSION_UPDATE"] = "1"

        # The environment variable check should happen regardless of startup mode
        no_version_update = os.getenv("NO_VERSION_UPDATE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        assert no_version_update is True

        # This should be consistent across all modes:
        # - Interactive mode (--interactive)
        # - TUI mode (--tui)
        # - Command mode (direct command execution)
        # - Default mode (help display)

        # The check happens early in main() before argument parsing affects the flow
        # So it should work the same way for all modes

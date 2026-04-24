from unittest.mock import mock_open, patch

import pytest

from code_puppy.config import (
    clear_agent_pinned_model,
    get_agent_pinned_model,
    get_compaction_strategy,
    get_compaction_threshold,
    get_threshold_compaction_archive_retention_count,
    get_threshold_compaction_archive_retention_days,
    get_threshold_compaction_emergency_trigger_ratio,
    get_threshold_compaction_growth_history_window,
    get_threshold_compaction_predicted_growth_floor_ratio,
    get_threshold_compaction_recent_raw_floor_ratio,
    get_threshold_compaction_soft_trigger_ratio,
    get_threshold_compaction_target_ratio,
    get_use_dbos,
    load_mcp_server_configs,
    set_agent_pinned_model,
)


class TestConfigExtendedPart2:
    """Test advanced configuration functions in code_puppy/config.py"""

    @pytest.fixture
    def mock_config_file(self):
        """Mock config file operations"""
        with patch("code_puppy.config.CONFIG_FILE", "/mock/config/puppy.cfg"):
            yield

    def test_agent_pinned_model_get_set(self, mock_config_file):
        """Test getting and setting agent-specific pinned models"""
        agent_name = "test-agent"
        model_name = "gpt-4"

        # Test getting non-existent pinned model
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = None
            result = get_agent_pinned_model(agent_name)
            assert result is None
            mock_get.assert_called_once_with(f"agent_model_{agent_name}")

        # Test setting pinned model
        with patch("code_puppy.config.set_config_value") as mock_set:
            set_agent_pinned_model(agent_name, model_name)
            mock_set.assert_called_once_with(f"agent_model_{agent_name}", model_name)

        # Test getting existing pinned model
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = model_name
            result = get_agent_pinned_model(agent_name)
            assert result == model_name
            mock_get.assert_called_once_with(f"agent_model_{agent_name}")

    def test_clear_agent_pinned_model(self, mock_config_file):
        """Test clearing agent-specific pinned models"""
        agent_name = "test-agent"

        with patch("code_puppy.config.set_config_value") as mock_set:
            clear_agent_pinned_model(agent_name)
            mock_set.assert_called_once_with(f"agent_model_{agent_name}", "")

    def test_get_compaction_strategy(self, mock_config_file):
        """Test getting compaction strategy configuration"""
        # Test default strategy
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = None
            result = get_compaction_strategy()
            assert result == "truncation"  # Default value
            mock_get.assert_called_once_with("compaction_strategy")

        # Test valid strategies
        for strategy in ["summarization", "truncation", "threshold"]:
            with patch("code_puppy.config.get_value") as mock_get:
                mock_get.return_value = strategy.upper()  # Test case normalization
                result = get_compaction_strategy()
                assert result == strategy.lower()

        # Test invalid strategy falls back to default
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "invalid_strategy"
            result = get_compaction_strategy()
            assert result == "truncation"  # Default fallback

    def test_get_compaction_threshold(self, mock_config_file):
        """Test getting compaction threshold configuration"""
        # Test default threshold
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = None
            result = get_compaction_threshold()
            assert result == 0.85  # Default value
            mock_get.assert_called_once_with("compaction_threshold")

        # Test valid threshold
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "0.75"
            result = get_compaction_threshold()
            assert result == 0.75

        # Test threshold clamping - minimum
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "0.3"  # Below minimum
            result = get_compaction_threshold()
            assert result == 0.5  # Clamped to minimum

        # Test threshold clamping - maximum
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "0.98"  # Above maximum
            result = get_compaction_threshold()
            assert result == 0.95  # Clamped to maximum

        # Test invalid value falls back to default
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "invalid"
            result = get_compaction_threshold()
            assert result == 0.85  # Default fallback

    def test_threshold_compaction_config_defaults(self, mock_config_file):
        defaults = {
            "threshold_compaction_soft_trigger_ratio": 0.825,
            "threshold_compaction_emergency_trigger_ratio": 0.9,
            "threshold_compaction_target_ratio": 0.575,
            "threshold_compaction_recent_raw_floor_ratio": 0.2,
            "threshold_compaction_predicted_growth_floor_ratio": 0.06,
            "threshold_compaction_growth_history_window": 10,
            "threshold_compaction_archive_retention_days": 30,
            "threshold_compaction_archive_retention_count": 500,
        }

        def fake_get(key):
            assert key in defaults
            return None

        with patch("code_puppy.config.get_value", side_effect=fake_get):
            assert get_threshold_compaction_soft_trigger_ratio() == 0.825
            assert get_threshold_compaction_emergency_trigger_ratio() == 0.9
            assert get_threshold_compaction_target_ratio() == 0.575
            assert get_threshold_compaction_recent_raw_floor_ratio() == 0.2
            assert get_threshold_compaction_predicted_growth_floor_ratio() == 0.06
            assert get_threshold_compaction_growth_history_window() == 10
            assert get_threshold_compaction_archive_retention_days() == 30
            assert get_threshold_compaction_archive_retention_count() == 500

    def test_threshold_compaction_config_clamps(self, mock_config_file):
        values = {
            "threshold_compaction_soft_trigger_ratio": "0.1",
            "threshold_compaction_emergency_trigger_ratio": "2.0",
            "threshold_compaction_target_ratio": "0.95",
            "threshold_compaction_recent_raw_floor_ratio": "0.01",
            "threshold_compaction_predicted_growth_floor_ratio": "0.9",
            "threshold_compaction_growth_history_window": "0",
            "threshold_compaction_archive_retention_days": "0",
            "threshold_compaction_archive_retention_count": "0",
        }

        with patch("code_puppy.config.get_value", side_effect=values.get):
            assert get_threshold_compaction_soft_trigger_ratio() == 0.5
            assert get_threshold_compaction_emergency_trigger_ratio() == 0.98
            assert get_threshold_compaction_target_ratio() == 0.9
            assert get_threshold_compaction_recent_raw_floor_ratio() == 0.05
            assert get_threshold_compaction_predicted_growth_floor_ratio() == 0.5
            assert get_threshold_compaction_growth_history_window() == 1
            assert get_threshold_compaction_archive_retention_days() == 1
            assert get_threshold_compaction_archive_retention_count() == 1

    def test_get_use_dbos(self, mock_config_file):
        """Test getting DBOS usage flag"""
        # Test default (True - DBOS enabled by default)
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = None
            result = get_use_dbos()
            assert result is True
            mock_get.assert_called_once_with("enable_dbos")

        # Test various true values
        true_values = ["1", "true", "yes", "on", "TRUE", "Yes"]
        for val in true_values:
            with patch("code_puppy.config.get_value") as mock_get:
                mock_get.return_value = val
                result = get_use_dbos()
                assert result is True

        # Test various false values
        false_values = ["0", "false", "no", "off", "", "random"]
        for val in false_values:
            with patch("code_puppy.config.get_value") as mock_get:
                mock_get.return_value = val
                result = get_use_dbos()
                assert result is False

    def test_load_mcp_server_configs(self):
        """Test loading MCP server configurations"""
        mock_servers = {
            "server1": "http://localhost:3001",
            "server2": {"command": "node", "args": ["server.js"]},
        }
        mock_config_data = {"mcp_servers": mock_servers}

        # Test successful loading
        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", "/mock/mcp_servers.json"),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "builtins.open",
                mock_open(
                    read_data='{"mcp_servers": {"server1": "http://localhost:3001"}}'
                ),
            ),
        ):
            with patch("json.loads", return_value=mock_config_data):
                result = load_mcp_server_configs()
                assert result == mock_servers

        # Test file not exists
        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", "/mock/mcp_servers.json"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            result = load_mcp_server_configs()
            assert result == {}

        # Test error handling
        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", "/mock/mcp_servers.json"),
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", side_effect=IOError("Permission denied")),
            patch("code_puppy.messaging.message_queue.emit_error") as mock_emit_error,
        ):
            result = load_mcp_server_configs()
            assert result == {}
            mock_emit_error.assert_called_once()
            assert "Failed to load MCP servers" in mock_emit_error.call_args[0][0]

    def test_agent_pinned_model_integration(self, mock_config_file):
        """Test integration of agent pinned model functions"""
        agent_name = "integration-agent"
        model_name = "claude-3-sonnet"

        # Mock the underlying config operations
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.config.get_value") as mock_get,
        ):
            # Initially no pinned model
            mock_get.return_value = None
            assert get_agent_pinned_model(agent_name) is None

            # Set a pinned model
            set_agent_pinned_model(agent_name, model_name)
            mock_set.assert_called_with(f"agent_model_{agent_name}", model_name)

            # Get the pinned model
            mock_get.return_value = model_name
            assert get_agent_pinned_model(agent_name) == model_name

            # Clear the pinned model
            clear_agent_pinned_model(agent_name)
            mock_set.assert_called_with(f"agent_model_{agent_name}", "")

    def test_compaction_config_edge_cases(self, mock_config_file):
        """Test edge cases for compaction configuration"""
        # Test compaction strategy with whitespace (note: actual implementation doesn't strip)
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "  summarization  "
            result = get_compaction_strategy()
            # The actual implementation doesn't strip whitespace, so it falls back to default
            assert result == "truncation"  # Default fallback for non-exact match

        # Test compaction strategy with exact match
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "summarization"
            result = get_compaction_strategy()
            assert result == "summarization"

        # Test compaction threshold with extreme values
        test_cases = [
            ("0", 0.5),  # Below minimum
            ("1.0", 0.95),  # Above maximum
            ("-0.1", 0.5),  # Negative
            ("2.0", 0.95),  # Above 1.0
        ]

        for input_val, expected in test_cases:
            with patch("code_puppy.config.get_value") as mock_get:
                mock_get.return_value = input_val
                result = get_compaction_threshold()
                assert result == expected

    def test_config_value_types(self, mock_config_file):
        """Test that config values handle different types correctly"""
        # Test with integer values for threshold
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "1"
            result = get_compaction_threshold()
            assert isinstance(result, float)
            assert result == 0.95  # Clamped to maximum

        # Test with float values for threshold
        with patch("code_puppy.config.get_value") as mock_get:
            mock_get.return_value = "0.7"
            result = get_compaction_threshold()
            assert isinstance(result, float)
            assert result == 0.7

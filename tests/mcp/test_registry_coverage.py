"""
Additional coverage tests for ServerRegistry.

These tests target specific uncovered lines in registry.py
to achieve higher coverage.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.mcp_.managed_server import ServerConfig
from code_puppy.mcp_.registry import ServerRegistry


class TestRegisterDuplicateId:
    """Test registration with duplicate server ID."""

    def test_register_duplicate_id_raises_error(self):
        """Test that registering a server with an existing ID raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                
                # Register first server with explicit ID
                config1 = ServerConfig(
                    id="duplicate-id",
                    name="server1",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config1)
                
                # Try to register second server with same ID
                config2 = ServerConfig(
                    id="duplicate-id",
                    name="server2",
                    type="stdio",
                    enabled=True,
                    config={"command": "cat"},
                )
                with pytest.raises(ValueError, match="already exists"):
                    registry.register(config2)


class TestUpdateValidationErrors:
    """Test update with validation failures."""

    def test_update_with_invalid_config_raises_error(self):
        """Test that update with invalid config raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                
                # Register a valid server
                config = ServerConfig(
                    id="test-id",
                    name="valid-server",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)
                
                # Try to update with invalid config (empty name)
                invalid_config = ServerConfig(
                    id="test-id",
                    name="",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                with pytest.raises(ValueError, match="Validation failed"):
                    registry.update("test-id", invalid_config)


class TestValidationEdgeCases:
    """Test validation edge cases for complete coverage."""

    def test_validate_invalid_server_name_special_chars(self):
        """Test validation fails for names with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="server@name!",  # Invalid special chars
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                errors = registry.validate_config(config)
                assert any("alphanumeric" in e for e in errors)

    def test_validate_empty_server_type(self):
        """Test validation fails for empty server type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="",  # Empty type
                    enabled=True,
                    config={"command": "echo"},
                )
                errors = registry.validate_config(config)
                assert any("type is required" in e for e in errors)

    def test_validate_config_not_dictionary(self):
        """Test validation fails when config is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config="not-a-dict",  # type: ignore - intentionally wrong type
                )
                errors = registry.validate_config(config)
                assert any("must be a dictionary" in e for e in errors)

    def test_validate_http_url_empty_string(self):
        """Test validation fails for empty URL string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "   "},  # Whitespace only
                )
                errors = registry.validate_config(config)
                assert any("non-empty string" in e for e in errors)

    def test_validate_http_url_not_string(self):
        """Test validation fails for non-string URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": 12345},  # Not a string
                )
                errors = registry.validate_config(config)
                assert any("non-empty string" in e for e in errors)

    def test_validate_negative_timeout(self):
        """Test validation fails for negative timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "https://example.com", "timeout": -5},
                )
                errors = registry.validate_config(config)
                assert any("Timeout must be positive" in e for e in errors)

    def test_validate_invalid_timeout_type(self):
        """Test validation fails for non-numeric timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "https://example.com", "timeout": "invalid"},
                )
                errors = registry.validate_config(config)
                assert any("Timeout must be a number" in e for e in errors)

    def test_validate_negative_read_timeout(self):
        """Test validation fails for negative read_timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "https://example.com", "read_timeout": -10},
                )
                errors = registry.validate_config(config)
                assert any("Read timeout must be positive" in e for e in errors)

    def test_validate_invalid_read_timeout_type(self):
        """Test validation fails for non-numeric read_timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "https://example.com", "read_timeout": "bad"},
                )
                errors = registry.validate_config(config)
                assert any("Read timeout must be a number" in e for e in errors)

    def test_validate_headers_not_dictionary(self):
        """Test validation fails when headers is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="http",
                    enabled=True,
                    config={"url": "https://example.com", "headers": ["not", "dict"]},
                )
                errors = registry.validate_config(config)
                assert any("Headers must be a dictionary" in e for e in errors)

    def test_validate_stdio_command_empty(self):
        """Test validation fails for empty stdio command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "   "},  # Whitespace only
                )
                errors = registry.validate_config(config)
                assert any("non-empty string" in e for e in errors)

    def test_validate_stdio_command_not_string(self):
        """Test validation fails for non-string stdio command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": 12345},
                )
                errors = registry.validate_config(config)
                assert any("non-empty string" in e for e in errors)

    def test_validate_args_not_list_or_string(self):
        """Test validation fails when args is not a list or string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "args": 12345},
                )
                errors = registry.validate_config(config)
                assert any("Args must be a list or string" in e for e in errors)

    def test_validate_args_list_with_non_strings(self):
        """Test validation fails when args list contains non-strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "args": ["valid", 123, "also-valid"]},
                )
                errors = registry.validate_config(config)
                assert any("All args must be strings" in e for e in errors)

    def test_validate_env_not_dictionary(self):
        """Test validation fails when env is not a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "env": "not-a-dict"},
                )
                errors = registry.validate_config(config)
                assert any("Environment variables must be a dictionary" in e for e in errors)

    def test_validate_env_values_not_strings(self):
        """Test validation fails when env values are not strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "env": {"VAR1": "valid", "VAR2": 123}},
                )
                errors = registry.validate_config(config)
                assert any("All environment variables must be strings" in e for e in errors)

    def test_validate_cwd_not_string(self):
        """Test validation fails when cwd is not a string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "cwd": 12345},
                )
                errors = registry.validate_config(config)
                assert any("Working directory must be a string" in e for e in errors)


class TestPersistException:
    """Test _persist() exception handling."""

    def test_persist_raises_on_write_error(self):
        """Test that _persist raises exception when write fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            registry = ServerRegistry(storage_path=str(storage_path))
            
            # Add a server so we have something to persist
            config = ServerConfig(
                id="test",
                name="test",
                type="stdio",
                enabled=True,
                config={"command": "echo"},
            )
            registry._servers["test"] = config
            
            # Make the directory read-only to cause write failure
            with patch.object(Path, 'replace', side_effect=PermissionError("Write denied")):
                with pytest.raises(PermissionError):
                    registry._persist()


class TestLoadEdgeCases:
    """Test _load() edge cases for complete coverage."""

    def test_load_empty_file(self):
        """Test loading from empty file starts with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Create empty file
            storage_path.touch()
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_invalid_json_format_not_dict(self):
        """Test loading file with non-dict JSON starts with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write a JSON array instead of object
            with open(storage_path, "w") as f:
                json.dump(["not", "a", "dict"], f)
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_config_entry_not_dictionary(self):
        """Test loading skips entries that are not dictionaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write entry that is not a dict
            with open(storage_path, "w") as f:
                json.dump({"server1": "not-a-dict"}, f)
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_config_missing_required_fields(self):
        """Test loading skips entries missing required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write entry missing 'config' field
            with open(storage_path, "w") as f:
                json.dump({
                    "server1": {
                        "id": "server1",
                        "name": "test",
                        "type": "stdio",
                        # Missing 'config' field
                    }
                }, f)
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_config_fails_validation(self):
        """Test loading skips entries that fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write entry with invalid config (no command for stdio)
            with open(storage_path, "w") as f:
                json.dump({
                    "server1": {
                        "id": "server1",
                        "name": "test",
                        "type": "stdio",
                        "enabled": True,
                        "config": {},  # Missing required 'command'
                    }
                }, f)
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_config_exception_during_parse(self):
        """Test loading handles exception during config parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write valid JSON but entry will cause ServerConfig to fail
            with open(storage_path, "w") as f:
                json.dump({
                    "server1": {
                        "id": "server1",
                        "name": "test",
                        "type": "stdio",
                        "enabled": "not-a-bool",  # This should work but let's mock failure
                        "config": {"command": "echo"},
                    }
                }, f)
            
            # Mock ServerConfig to raise an exception
            with patch("code_puppy.mcp_.registry.ServerConfig", side_effect=Exception("Parse error")):
                registry = ServerRegistry(storage_path=str(storage_path))
                assert len(registry._servers) == 0

    def test_load_invalid_json_syntax(self):
        """Test loading file with invalid JSON syntax starts with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write invalid JSON
            with open(storage_path, "w") as f:
                f.write("{invalid json syntax")
            
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_load_generic_exception(self):
        """Test loading handles generic exceptions gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"
            # Write valid JSON
            with open(storage_path, "w") as f:
                json.dump({"server1": {"id": "1", "name": "t", "type": "stdio", "config": {"command": "e"}}}, f)
            
            # Mock open to raise an exception after exists() check
            original_open = open
            call_count = [0]
            
            def mock_open_with_error(*args, **kwargs):
                call_count[0] += 1
                if "r" in args[1] if len(args) > 1 else kwargs.get("mode", "r") == "r":
                    if call_count[0] > 0:  # Fail on read
                        raise IOError("Read error")
                return original_open(*args, **kwargs)
            
            with patch("builtins.open", side_effect=IOError("Read error")):
                registry = ServerRegistry(storage_path=str(storage_path))
                assert len(registry._servers) == 0


class TestSseValidation:
    """Test SSE-specific validation for coverage."""

    def test_validate_sse_url_empty(self):
        """Test SSE validation with empty URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="sse",
                    enabled=True,
                    config={"url": ""},
                )
                errors = registry.validate_config(config)
                assert any("non-empty string" in e for e in errors)

    def test_validate_sse_negative_timeout(self):
        """Test SSE validation with negative timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="sse",
                    enabled=True,
                    config={"url": "https://example.com", "timeout": -1},
                )
                errors = registry.validate_config(config)
                assert any("Timeout must be positive" in e for e in errors)

    def test_validate_sse_invalid_headers(self):
        """Test SSE validation with invalid headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="valid-name",
                    type="sse",
                    enabled=True,
                    config={"url": "https://example.com", "headers": "not-a-dict"},
                )
                errors = registry.validate_config(config)
                assert any("Headers must be a dictionary" in e for e in errors)

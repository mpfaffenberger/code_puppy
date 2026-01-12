"""
Comprehensive tests for ServerRegistry CRUD operations and validation.

Tests cover server registration, retrieval, updates, deletion, validation,
persistence, and thread-safety.
"""

import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.mcp_.managed_server import ServerConfig
from code_puppy.mcp_.registry import ServerRegistry


class TestServerRegistryBasic:
    """Test basic registry functionality."""

    def test_initialization_default_storage(self):
        """Test registry initialization with default storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                assert registry._storage_path == Path(tmpdir) / "mcp_registry.json"
                assert registry._servers == {}

    def test_initialization_custom_storage(self):
        """Test registry initialization with custom storage path."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            registry = ServerRegistry(storage_path=tmp.name)
            assert registry._storage_path == Path(tmp.name)

    def test_register_new_server(self):
        """Test registering a new server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="",
                    name="test-server",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo", "args": ["hello"]},
                )
                server_id = registry.register(config)
                assert server_id
                assert server_id in registry._servers
                assert registry._servers[server_id].name == "test-server"

    def test_register_generates_id(self):
        """Test that register generates ID if not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                server_id = registry.register(config)
                assert server_id != ""
                assert len(server_id) > 0

    def test_register_duplicate_name_fails(self):
        """Test that registering duplicate name fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config1 = ServerConfig(
                    id="id1",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config1)

                config2 = ServerConfig(
                    id="id2",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "cat"},
                )
                with pytest.raises(ValueError, match="already exists"):
                    registry.register(config2)

    def test_register_invalid_config_fails(self):
        """Test that registering invalid config fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                # No name
                config = ServerConfig(
                    id="",
                    name="",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                with pytest.raises(ValueError, match="Validation failed"):
                    registry.register(config)

    def test_get_by_id(self):
        """Test retrieving server by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test-id",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)
                retrieved = registry.get("test-id")
                assert retrieved is not None
                assert retrieved.name == "test"

    def test_get_nonexistent_returns_none(self):
        """Test getting nonexistent server returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                assert registry.get("nonexistent") is None

    def test_get_by_name(self):
        """Test retrieving server by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="id1",
                    name="my-server",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)
                retrieved = registry.get_by_name("my-server")
                assert retrieved is not None
                assert retrieved.id == "id1"

    def test_get_by_name_nonexistent(self):
        """Test get_by_name with nonexistent name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                assert registry.get_by_name("nonexistent") is None

    def test_list_all(self):
        """Test listing all servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                for i in range(3):
                    config = ServerConfig(
                        id=f"id{i}",
                        name=f"server{i}",
                        type="stdio",
                        enabled=True,
                        config={"command": "echo"},
                    )
                    registry.register(config)

                all_servers = registry.list_all()
                assert len(all_servers) == 3

    def test_exists(self):
        """Test checking if server exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test-id",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)
                assert registry.exists("test-id")
                assert not registry.exists("nonexistent")

    def test_unregister_existing(self):
        """Test unregistering existing server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test-id",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)
                result = registry.unregister("test-id")
                assert result is True
                assert not registry.exists("test-id")

    def test_unregister_nonexistent(self):
        """Test unregistering nonexistent server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                result = registry.unregister("nonexistent")
                assert result is False

    def test_update_existing(self):
        """Test updating existing server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config1 = ServerConfig(
                    id="test-id",
                    name="original",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config1)

                config2 = ServerConfig(
                    id="test-id",
                    name="updated",
                    type="stdio",
                    enabled=False,
                    config={"command": "cat"},
                )
                result = registry.update("test-id", config2)
                assert result is True
                updated = registry.get("test-id")
                assert updated.name == "updated"
                assert updated.enabled is False

    def test_update_nonexistent(self):
        """Test updating nonexistent server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="nonexistent",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                result = registry.update("nonexistent", config)
                assert result is False


class TestServerRegistryValidation:
    """Test configuration validation."""

    def test_validate_valid_stdio_config(self):
        """Test validation of valid stdio configuration."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "echo", "args": ["hello"]},
        )
        errors = registry.validate_config(config)
        assert errors == []

    def test_validate_stdio_missing_command(self):
        """Test stdio validation with missing command."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="stdio",
            enabled=True,
            config={},
        )
        errors = registry.validate_config(config)
        assert any("command" in e for e in errors)

    def test_validate_http_valid(self):
        """Test validation of valid HTTP configuration."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="http",
            enabled=True,
            config={"url": "https://example.com"},
        )
        errors = registry.validate_config(config)
        assert errors == []

    def test_validate_http_missing_url(self):
        """Test HTTP validation with missing URL."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="http",
            enabled=True,
            config={},
        )
        errors = registry.validate_config(config)
        assert any("url" in e for e in errors)

    def test_validate_http_invalid_url(self):
        """Test HTTP validation with invalid URL."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="http",
            enabled=True,
            config={"url": "not-a-url"},
        )
        errors = registry.validate_config(config)
        assert any("http" in e or "https" in e for e in errors)

    def test_validate_invalid_server_type(self):
        """Test validation with invalid server type."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="invalid-type",
            enabled=True,
            config={},
        )
        errors = registry.validate_config(config)
        assert any("type" in e for e in errors)

    def test_validate_empty_name(self):
        """Test validation with empty name."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="",
            type="stdio",
            enabled=True,
            config={"command": "echo"},
        )
        errors = registry.validate_config(config)
        assert any("name" in e for e in errors)

    def test_validate_valid_timeout_values(self):
        """Test validation of valid timeout values."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="http",
            enabled=True,
            config={
                "url": "https://example.com",
                "timeout": 30.5,
            },
        )
        errors = registry.validate_config(config)
        # Should be valid
        assert not any("timeout" in e for e in errors)

    def test_validate_http_with_read_timeout(self):
        """Test validation of read timeout parameter."""
        registry = ServerRegistry()
        config = ServerConfig(
            id="test",
            name="test",
            type="http",
            enabled=True,
            config={
                "url": "https://example.com",
                "read_timeout": 15.0,
            },
        )
        errors = registry.validate_config(config)
        assert errors == []


class TestServerRegistryThreadSafety:
    """Test thread-safety of registry operations."""

    def test_concurrent_register(self):
        """Test concurrent registration of servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                results = []

                def register_server(i):
                    config = ServerConfig(
                        id=f"id{i}",
                        name=f"server{i}",
                        type="stdio",
                        enabled=True,
                        config={"command": "echo"},
                    )
                    server_id = registry.register(config)
                    results.append(server_id)

                threads = [
                    threading.Thread(target=register_server, args=(i,))
                    for i in range(5)
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                assert len(results) == 5
                assert len(registry._servers) == 5

    def test_concurrent_read_write(self):
        """Test concurrent reads and writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)

                results = []

                def read_server():
                    for _ in range(10):
                        results.append(registry.get("test"))

                threads = [threading.Thread(target=read_server) for _ in range(3)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                assert len(results) == 30
                assert all(r is not None for r in results)


class TestServerRegistryPersistence:
    """Test persistence functionality."""

    def test_persist_and_load(self):
        """Test saving and loading from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "registry.json"

            # Create and populate registry
            registry1 = ServerRegistry(storage_path=str(storage_path))
            config = ServerConfig(
                id="test",
                name="test-server",
                type="stdio",
                enabled=True,
                config={"command": "echo"},
            )
            registry1.register(config)

            # Create new registry and load from disk
            registry2 = ServerRegistry(storage_path=str(storage_path))
            assert len(registry2._servers) == 1
            assert registry2.exists("test")
            assert registry2.get("test").name == "test-server"

    def test_load_missing_file(self):
        """Test loading from nonexistent file starts with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "nonexistent.json"
            registry = ServerRegistry(storage_path=str(storage_path))
            assert len(registry._servers) == 0

    def test_persist_creates_directory(self):
        """Test that persist creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "deep" / "nested" / "path" / "registry.json"
            registry = ServerRegistry(storage_path=str(storage_path))
            config = ServerConfig(
                id="test",
                name="test",
                type="stdio",
                enabled=True,
                config={"command": "echo"},
            )
            registry.register(config)
            assert storage_path.exists()


class TestServerRegistryEdgeCases:
    """Test edge cases and error conditions."""

    def test_update_with_duplicate_name(self):
        """Test update fails if new name already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()

                # Register two servers
                config1 = ServerConfig(
                    id="id1",
                    name="server1",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                config2 = ServerConfig(
                    id="id2",
                    name="server2",
                    type="stdio",
                    enabled=True,
                    config={"command": "cat"},
                )
                registry.register(config1)
                registry.register(config2)

                # Try to rename id1 to server2's name
                config1_renamed = ServerConfig(
                    id="id1",
                    name="server2",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                with pytest.raises(ValueError):
                    registry.update("id1", config1_renamed)

    def test_list_all_empty_registry(self):
        """Test list_all on empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                assert registry.list_all() == []

    def test_list_all_returns_copy(self):
        """Test that list_all returns independent list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="test",
                    type="stdio",
                    enabled=True,
                    config={"command": "echo"},
                )
                registry.register(config)

                list1 = registry.list_all()
                list2 = registry.list_all()
                assert list1 is not list2
                assert len(list1) == len(list2)

    def test_register_with_headers(self):
        """Test registering HTTP server with custom headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="test",
                    type="http",
                    enabled=True,
                    config={
                        "url": "https://example.com",
                        "headers": {"Authorization": "Bearer token"},
                    },
                )
                server_id = registry.register(config)
                assert server_id

    def test_sse_server_registration(self):
        """Test registering SSE server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmpdir):
                registry = ServerRegistry()
                config = ServerConfig(
                    id="test",
                    name="sse-server",
                    type="sse",
                    enabled=True,
                    config={"url": "https://example.com/stream"},
                )
                server_id = registry.register(config)
                assert server_id

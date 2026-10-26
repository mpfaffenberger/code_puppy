"""Focused edge-case coverage for :mod:`code_puppy.mcp_.registry`."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.mcp_.managed_server import ServerConfig
from code_puppy.mcp_.registry import ServerRegistry


@pytest.fixture
def registry(tmp_path):
    with patch("code_puppy.mcp_.registry.config.DATA_DIR", tmp_path):
        yield ServerRegistry()


def server(**overrides):
    values = {
        "id": "test",
        "name": "valid-name",
        "type": "stdio",
        "enabled": True,
        "config": {"command": "echo"},
    }
    values.update(overrides)
    return ServerConfig(**values)


def test_register_duplicate_id_raises_error(registry):
    registry.register(server(id="duplicate-id", name="server1"))
    with pytest.raises(ValueError, match="already exists"):
        registry.register(server(id="duplicate-id", name="server2"))


def test_update_with_invalid_config_raises_error(registry):
    registry.register(server(id="test-id"))
    with pytest.raises(ValueError, match="Validation failed"):
        registry.update("test-id", server(id="test-id", name=""))


VALIDATION_CASES = [
    pytest.param({"name": "server@name!"}, "alphanumeric", id="special-name"),
    pytest.param({"type": ""}, "type is required", id="empty-type"),
    pytest.param({"config": "not-a-dict"}, "must be a dictionary", id="config-type"),
    pytest.param(
        {"type": "http", "config": {"url": "   "}},
        "non-empty string",
        id="empty-http-url",
    ),
    pytest.param(
        {"type": "http", "config": {"url": 12345}},
        "non-empty string",
        id="http-url-type",
    ),
    pytest.param(
        {"type": "http", "config": {"url": "https://example.com", "timeout": -5}},
        "Timeout must be positive",
        id="negative-timeout",
    ),
    pytest.param(
        {
            "type": "http",
            "config": {"url": "https://example.com", "timeout": "invalid"},
        },
        "Timeout must be a number",
        id="timeout-type",
    ),
    pytest.param(
        {
            "type": "http",
            "config": {"url": "https://example.com", "read_timeout": -10},
        },
        "Read timeout must be positive",
        id="negative-read-timeout",
    ),
    pytest.param(
        {
            "type": "http",
            "config": {"url": "https://example.com", "read_timeout": "bad"},
        },
        "Read timeout must be a number",
        id="read-timeout-type",
    ),
    pytest.param(
        {
            "type": "http",
            "config": {"url": "https://example.com", "headers": ["not", "dict"]},
        },
        "Headers must be a dictionary",
        id="headers-type",
    ),
    pytest.param(
        {"config": {"command": "   "}}, "non-empty string", id="empty-command"
    ),
    pytest.param({"config": {"command": 12345}}, "non-empty string", id="command-type"),
    pytest.param(
        {"config": {"command": "echo", "args": 12345}},
        "Args must be a list or string",
        id="args-type",
    ),
    pytest.param(
        {"config": {"command": "echo", "args": ["valid", 123]}},
        "All args must be strings",
        id="args-item-type",
    ),
    pytest.param(
        {"config": {"command": "echo", "env": "not-a-dict"}},
        "Environment variables must be a dictionary",
        id="env-type",
    ),
    pytest.param(
        {"config": {"command": "echo", "env": {"VAR1": "valid", "VAR2": 123}}},
        "All environment variables must be strings",
        id="env-value-type",
    ),
    pytest.param(
        {"config": {"command": "echo", "cwd": 12345}},
        "Working directory must be a string",
        id="cwd-type",
    ),
    pytest.param(
        {"type": "sse", "config": {"url": ""}},
        "non-empty string",
        id="empty-sse-url",
    ),
    pytest.param(
        {"type": "sse", "config": {"url": "https://example.com", "timeout": -1}},
        "Timeout must be positive",
        id="sse-negative-timeout",
    ),
    pytest.param(
        {
            "type": "sse",
            "config": {"url": "https://example.com", "headers": "not-a-dict"},
        },
        "Headers must be a dictionary",
        id="sse-headers-type",
    ),
]


@pytest.mark.parametrize(("overrides", "message"), VALIDATION_CASES)
def test_validation_edge_cases(registry, overrides, message):
    errors = registry.validate_config(server(**overrides))
    assert any(message in error for error in errors)


def test_persist_raises_on_write_error(tmp_path):
    registry = ServerRegistry(storage_path=str(tmp_path / "registry.json"))
    registry._servers["test"] = server()
    with patch.object(Path, "replace", side_effect=PermissionError("Write denied")):
        with pytest.raises(PermissionError):
            registry._persist()


LOAD_CASES = [
    pytest.param("", id="empty-file"),
    pytest.param(["not", "a", "dict"], id="non-dict-root"),
    pytest.param({"server1": "not-a-dict"}, id="non-dict-entry"),
    pytest.param(
        {"server1": {"id": "server1", "name": "test", "type": "stdio"}},
        id="missing-fields",
    ),
    pytest.param(
        {
            "server1": {
                "id": "server1",
                "name": "test",
                "type": "stdio",
                "enabled": True,
                "config": {},
            }
        },
        id="invalid-config",
    ),
    pytest.param("{invalid json syntax", id="invalid-json"),
]


@pytest.mark.parametrize("contents", LOAD_CASES)
def test_invalid_loads_produce_empty_registry(tmp_path, contents):
    storage_path = tmp_path / "registry.json"
    if isinstance(contents, str):
        storage_path.write_text(contents)
    else:
        storage_path.write_text(json.dumps(contents))
    assert not ServerRegistry(storage_path=str(storage_path))._servers


def test_load_config_exception_during_parse(tmp_path):
    storage_path = tmp_path / "registry.json"
    storage_path.write_text(
        json.dumps(
            {
                "server1": {
                    "id": "server1",
                    "name": "test",
                    "type": "stdio",
                    "enabled": "not-a-bool",
                    "config": {"command": "echo"},
                }
            }
        )
    )
    with patch(
        "code_puppy.mcp_.registry.ServerConfig", side_effect=Exception("Parse error")
    ):
        assert not ServerRegistry(storage_path=str(storage_path))._servers


def test_load_read_error_is_handled(tmp_path):
    storage_path = tmp_path / "registry.json"
    storage_path.write_text("{}")
    with patch("builtins.open", side_effect=OSError("Read error")):
        assert not ServerRegistry(storage_path=str(storage_path))._servers

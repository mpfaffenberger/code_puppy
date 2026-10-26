"""Regression tests for bounded MCP reads and serialized wizard writes."""

import hashlib
import json
from unittest.mock import Mock

import pytest

from code_puppy import atomic_io, atomic_json, config
from code_puppy.command_line.mcp.trust_command import TrustCommand
from code_puppy.mcp_ import config_wizard, project_config
from code_puppy.mcp_.managed_server import ServerConfig


def oversized_config(tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_bytes(
        b'{"mcp_servers":{"large":"http://localhost"}}'
        + b" " * atomic_io.DEFAULT_MAX_BYTES
    )
    return path


def test_startup_rejects_real_oversized_config(tmp_path, monkeypatch):
    path = oversized_config(tmp_path)
    monkeypatch.setattr(config, "MCP_SERVERS_FILE", str(path))
    monkeypatch.setattr(project_config, "load_project_mcp_server_configs", lambda: {})
    assert config.load_mcp_server_configs() == {}


def test_trust_display_rejects_real_oversized_config(tmp_path):
    assert TrustCommand._safe_load_servers(oversized_config(tmp_path)) == {}


def test_project_parser_rejects_real_oversized_config(tmp_path, monkeypatch):
    path = oversized_config(tmp_path)
    monkeypatch.setattr(
        project_config, "get_project_mcp_servers_file", lambda root: path
    )
    monkeypatch.setattr(
        project_config, "get_trust_status", lambda *args: project_config.TRUSTED
    )
    assert project_config.load_project_mcp_server_configs(tmp_path) == {}


def test_trust_hash_does_not_read_oversized_file_in_full(tmp_path, monkeypatch):
    path = oversized_config(tmp_path)
    original_read_bytes = type(path).read_bytes
    full_reads = []

    def record_read(candidate):
        full_reads.append(candidate)
        return original_read_bytes(candidate)

    monkeypatch.setattr(type(path), "read_bytes", record_read)
    assert project_config.compute_mcp_file_hash(path) is None
    assert full_reads == [], "Trust hashing buffers the oversized config before parsing"


def test_wizard_respects_shared_store_lock(tmp_path, monkeypatch):
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"mcp_servers": {"existing": {"command": "existing"}}}))
    monkeypatch.setattr(config, "MCP_SERVERS_FILE", str(path))
    server = ServerConfig(
        id="wizard", name="wizard", type="stdio", config={"command": "wizard"}
    )
    monkeypatch.setattr(
        config_wizard.MCPConfigWizard, "run_wizard", lambda *args: server
    )
    monkeypatch.setattr(config_wizard, "get_mcp_manager", lambda: Mock())
    monkeypatch.setattr(atomic_json, "_LOCK_TIMEOUT_SECONDS", 0.01)
    original = path.read_bytes()
    with atomic_io.path_lock(str(path)):
        assert config_wizard.run_add_wizard() is False
        assert path.read_bytes() == original

    assert config_wizard.run_add_wizard() is True
    saved = json.loads(path.read_text())["mcp_servers"]
    assert saved == {
        "existing": {"command": "existing"},
        "wizard": {"command": "wizard"},
    }


@pytest.mark.parametrize("raise_on_error", [False, True])
def test_oversized_startup_config_preserves_error_policy(
    tmp_path, monkeypatch, raise_on_error
):
    monkeypatch.setattr(config, "MCP_SERVERS_FILE", str(oversized_config(tmp_path)))
    monkeypatch.setattr(project_config, "load_project_mcp_server_configs", lambda: {})
    if raise_on_error:
        with pytest.raises(atomic_io.ContentTooLarge):
            config.load_mcp_server_configs(raise_on_error=True)
    else:
        assert config.load_mcp_server_configs() == {}


@pytest.mark.parametrize("contents", [b"", b"{}", b'{"mcp_servers":{}}'])
def test_hash_matches_existing_content_address(tmp_path, contents):
    path = tmp_path / "mcp_servers.json"
    path.write_bytes(contents)
    assert (
        project_config.compute_mcp_file_hash(path)
        == hashlib.sha256(contents).hexdigest()
    )


def test_missing_config_has_no_trust_hash(tmp_path):
    assert project_config.compute_mcp_file_hash(tmp_path / "missing.json") is None


def test_previously_trusted_oversized_config_fails_closed(tmp_path, monkeypatch):
    path = oversized_config(tmp_path)
    monkeypatch.setattr(project_config, "TRUST_STORE_FILE", tmp_path / "trusted.json")
    monkeypatch.setattr(
        project_config, "get_project_mcp_servers_file", lambda root: path
    )
    project_config.TRUST_STORE_FILE.write_text(
        json.dumps({"projects": {str(tmp_path.resolve()): {"hash": "old-hash"}}})
    )
    assert project_config.get_trust_status(tmp_path, path) == project_config.CHANGED
    assert project_config.load_project_mcp_server_configs(tmp_path) == {}
    assert project_config.trust_project_mcp(tmp_path) is False

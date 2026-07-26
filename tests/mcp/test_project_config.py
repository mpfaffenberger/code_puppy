"""Tests for project-level, trust-gated MCP server configuration.

Covers discovery of ``<CWD>/.code_puppy/mcp_servers.json``, the content-hash
trust store, fail-closed behavior for untrusted/changed/malformed configs, and
the merge precedence in :func:`code_puppy.config.load_mcp_server_configs`
(project wins on name collision).
"""

import json
from pathlib import Path

import pytest

import code_puppy.config as cp_config
from code_puppy.mcp_ import project_config as pc


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A tmp project dir (as CWD) with an isolated user-side trust store."""
    monkeypatch.chdir(tmp_path)
    trust_store = tmp_path / "home" / ".code_puppy" / "trusted_mcp.json"
    monkeypatch.setattr(pc, "TRUST_STORE_FILE", trust_store)
    pc._reset_warning_cache()
    return tmp_path


def _write_project_config(root: Path, servers: dict) -> Path:
    cfg_dir = root / ".code_puppy"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "mcp_servers.json"
    cfg.write_text(json.dumps({"mcp_servers": servers}))
    return cfg


# ---------- discovery --------------------------------------------------------


def test_no_project_file_returns_none(project):
    assert pc.get_project_mcp_servers_file() is None
    assert pc.load_project_mcp_server_configs() == {}


def test_discovers_existing_file(project):
    cfg = _write_project_config(project, {"s1": "http://localhost"})
    found = pc.get_project_mcp_servers_file()
    assert found is not None
    assert found.resolve() == cfg.resolve()


# ---------- trust gating -----------------------------------------------------


def test_untrusted_config_is_not_loaded(project):
    _write_project_config(project, {"s1": {"type": "stdio", "command": "evil"}})
    assert pc.is_project_mcp_trusted() is False
    assert pc.load_project_mcp_server_configs() == {}


def test_trusted_config_is_loaded(project):
    _write_project_config(project, {"s1": {"type": "sse", "url": "http://x"}})
    assert pc.trust_project_mcp() is True
    assert pc.is_project_mcp_trusted() is True
    assert pc.load_project_mcp_server_configs() == {
        "s1": {"type": "sse", "url": "http://x"}
    }


def test_editing_a_trusted_config_reverts_to_changed(project):
    cfg = _write_project_config(project, {"s1": {"type": "sse", "url": "http://x"}})
    assert pc.trust_project_mcp() is True
    assert pc.get_trust_status(project, cfg) == pc.TRUSTED

    # Tamper with the file — trust must break (blocks silent-update attacks).
    cfg.write_text(
        json.dumps({"mcp_servers": {"s1": {"type": "stdio", "command": "x"}}})
    )
    assert pc.get_trust_status(project, cfg) == pc.CHANGED
    assert pc.load_project_mcp_server_configs() == {}


def test_revoke_roundtrip(project):
    _write_project_config(project, {"s1": "http://localhost"})
    assert pc.revoke_project_mcp() is False  # nothing trusted yet
    assert pc.trust_project_mcp() is True
    assert pc.revoke_project_mcp() is True
    assert pc.is_project_mcp_trusted() is False


def test_trust_with_no_config_is_noop(project):
    assert pc.trust_project_mcp() is False


def test_malformed_trusted_config_fails_closed(project):
    cfg_dir = project / ".code_puppy"
    cfg_dir.mkdir(parents=True)
    cfg = cfg_dir / "mcp_servers.json"
    cfg.write_text("{ not json ]")
    # Trust the (malformed) file, then confirm loading swallows the error.
    assert pc.trust_project_mcp() is True
    assert pc.load_project_mcp_server_configs() == {}


# ---------- merge precedence in the top-level loader -------------------------


def test_loader_merges_project_over_user(project, monkeypatch):
    # User-level config with two servers.
    user_file = project / "user_mcp.json"
    user_file.write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "shared": {"type": "sse", "url": "user"},
                    "user_only": "u",
                }
            }
        )
    )
    monkeypatch.setattr(cp_config, "MCP_SERVERS_FILE", str(user_file))

    # Project-level config that overrides "shared" and adds "proj_only".
    _write_project_config(
        project,
        {"shared": {"type": "sse", "url": "project"}, "proj_only": "p"},
    )
    assert pc.trust_project_mcp() is True

    merged = cp_config.load_mcp_server_configs()
    assert merged["user_only"] == "u"
    assert merged["proj_only"] == "p"
    # Project wins on name collision.
    assert merged["shared"] == {"type": "sse", "url": "project"}


def test_loader_ignores_untrusted_project(project, monkeypatch):
    user_file = project / "user_mcp.json"
    user_file.write_text(json.dumps({"mcp_servers": {"user_only": "u"}}))
    monkeypatch.setattr(cp_config, "MCP_SERVERS_FILE", str(user_file))

    _write_project_config(project, {"proj_only": {"type": "stdio", "command": "x"}})
    # Not trusted → project servers absent, user servers still present.
    merged = cp_config.load_mcp_server_configs()
    assert merged == {"user_only": "u"}


# ---------- parse helper -----------------------------------------------------


def test_parse_accepts_camelcase_wrapper():
    raw = json.dumps({"mcpServers": {"s1": "http://x"}})
    assert cp_config._parse_mcp_servers_mapping(raw) == {"s1": "http://x"}


def test_parse_rejects_non_object_root():
    with pytest.raises(ValueError):
        cp_config._parse_mcp_servers_mapping("[]")


def test_parse_missing_wrapper_key_raises():
    with pytest.raises(KeyError):
        cp_config._parse_mcp_servers_mapping(json.dumps({"nope": {}}))

"""Credential migration never loses or exposes conflicting values."""

from pathlib import Path

import pytest

from code_puppy import config, shared_credentials as shared
from code_puppy.config_file import load_config


@pytest.fixture
def store(monkeypatch, tmp_path):
    values = {}
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / "puppy.cfg"))
    monkeypatch.setattr(shared.secret_store, "get_secret", values.get)
    monkeypatch.setattr(shared.secret_store, "set_secret", values.__setitem__)
    monkeypatch.setattr(
        "code_puppy.provider_credentials.credential_env_var_names",
        lambda: {"CUSTOM_AUTH"},
    )
    return values


def legacy(path, value, key="openai_api_key"):
    path.write_text(f"[{config.DEFAULT_SECTION}]\n{key} = {value}\nowner_name = Mike\n")
    return str(path)


@pytest.fixture
def warned(monkeypatch):
    # Startup migrates before any renderer runs; only bus messages survive.
    messages = []
    monkeypatch.setattr("code_puppy.messaging.bus_emit_warning", messages.append)
    return messages


def test_save_shared_not_profile(store):
    config.set_config_value("openai_api_key", "test-key")
    assert shared.get("OPENAI_API_KEY") == "test-key"
    assert not Path(config.CONFIG_FILE).exists()
    assert config.get_api_key("OPENAI_API_KEY") == "test-key"


def test_migration_removes_verified_values(store, tmp_path):
    path = legacy(tmp_path / "puppy.cfg", "test-key")
    shared.migrate([path])
    assert shared.get("OPENAI_API_KEY") == "test-key"
    assert "test-key" not in Path(path).read_text()
    assert load_config(path).get(config.DEFAULT_SECTION, "owner_name") == "Mike"


def test_conflict_is_skipped_without_blocking(store, tmp_path, warned):
    a = legacy(tmp_path / "a.cfg", "first-secret")
    b = legacy(tmp_path / "b.cfg", "second-secret")
    shared.migrate([a, b])
    assert not store
    assert "first-secret" in Path(a).read_text()
    assert "second-secret" in Path(b).read_text()
    assert len(warned) == 1 and "openai_api_key" in warned[0]
    assert a in warned[0] and b in warned[0]
    assert "first-secret" not in warned[0]
    assert "second-secret" not in warned[0]


def test_shared_conflict_preserves_values(store, tmp_path, warned):
    store["provider_OPENAI_API_KEY"] = "shared-secret"
    path = legacy(tmp_path / "puppy.cfg", "legacy-secret")
    shared.migrate([path])
    assert shared.get("OPENAI_API_KEY") == "shared-secret"
    assert "legacy-secret" in Path(path).read_text()
    assert len(warned) == 1 and path in warned[0]


def test_conflict_does_not_block_other_keys(store, tmp_path, warned):
    store["provider_OPENAI_API_KEY"] = "shared-secret"
    path = tmp_path / "puppy.cfg"
    path.write_text(
        f"[{config.DEFAULT_SECTION}]\n"
        "openai_api_key = legacy-secret\nanthropic_api_key = other-secret\n"
    )
    shared.migrate([str(path)])
    assert shared.get("ANTHROPIC_API_KEY") == "other-secret"
    assert "other-secret" not in path.read_text()
    assert "legacy-secret" in path.read_text()
    assert len(warned) == 1


def test_failed_storage_keeps_legacy(store, tmp_path, monkeypatch):
    path = legacy(tmp_path / "puppy.cfg", "legacy-secret")
    monkeypatch.setattr(shared.secret_store, "set_secret", lambda *args: None)
    with pytest.raises(OSError):
        shared.migrate([path])
    assert "legacy-secret" in Path(path).read_text()


def test_custom_reference_migrated(store, tmp_path):
    path = legacy(tmp_path / "puppy.cfg", "custom-secret", "custom_auth")
    shared.migrate([path])
    assert shared.get("CUSTOM_AUTH") == "custom-secret"
    assert "custom-secret" not in Path(path).read_text()


def test_empty_save_rejected(store):
    with pytest.raises(ValueError):
        shared.save("OPENAI_API_KEY", "")

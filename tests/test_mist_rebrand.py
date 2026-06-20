import configparser

import mist
from code_puppy import config
from code_puppy.agents.agent_code_puppy import CodePuppyAgent, MistAgent
from code_puppy.branding import DISTRIBUTION_NAME, PRODUCT_EMOJI, PRODUCT_NAME
from code_puppy.plugins.puppy_kennel import config as memory_config


def _point_storage(monkeypatch, legacy_root, mist_root):
    for name in (
        "_LEGACY_CONFIG_DIR",
        "_LEGACY_DATA_DIR",
        "_LEGACY_CACHE_DIR",
        "_LEGACY_STATE_DIR",
    ):
        monkeypatch.setattr(config, name, str(legacy_root))
    for name in ("CONFIG_DIR", "DATA_DIR", "CACHE_DIR", "STATE_DIR"):
        monkeypatch.setattr(config, name, str(mist_root))
    monkeypatch.setattr(config, "CONFIG_FILE", str(mist_root / "mist.cfg"))


def test_public_mist_facade_and_agent_identity():
    assert mist.PRODUCT_NAME == PRODUCT_NAME == "Mist"
    assert mist.PRODUCT_EMOJI == PRODUCT_EMOJI == "🫧"
    assert mist.DISTRIBUTION_NAME == DISTRIBUTION_NAME == "mist-agent"
    agent = MistAgent()
    assert agent.name == "mist"
    assert agent.display_name == "Mist 🫧"
    assert CodePuppyAgent is MistAgent


def test_legacy_storage_and_config_are_migrated_additively(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".code_puppy"
    mist_root = tmp_path / ".mist"
    legacy_root.mkdir()
    (legacy_root / "models.json").write_text('{"legacy": true}', encoding="utf-8")
    (legacy_root / "puppy.cfg").write_text(
        "[puppy]\n"
        "puppy_name = Scout\n"
        "puppy_token = legacy-secret\n"
        "owner_name = Riley\n"
        "default_agent = code-puppy\n",
        encoding="utf-8",
    )
    _point_storage(monkeypatch, legacy_root, mist_root)

    config._migrate_legacy_storage()

    assert legacy_root.exists()
    assert (mist_root / "models.json").read_text(encoding="utf-8") == '{"legacy": true}'
    migrated = configparser.ConfigParser()
    migrated.read(mist_root / "mist.cfg")
    assert migrated["mist"]["mist_name"] == "Scout"
    assert migrated["mist"]["owner_name"] == "Riley"
    assert migrated["mist"]["mist_token"] == "legacy-secret"
    assert migrated["mist"]["default_agent"] == "mist"


def test_mist_memory_environment_keys_take_precedence(monkeypatch):
    monkeypatch.setenv("PUPPY_KENNEL_ROOT", "/legacy-memory")
    monkeypatch.setenv("MIST_MEMORY_ROOT", "/mist-memory")

    assert (
        memory_config._env("MIST_MEMORY_ROOT", "PUPPY_KENNEL_ROOT", "fallback")
        == "/mist-memory"
    )


def test_migration_never_overwrites_existing_mist_storage(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".code_puppy"
    mist_root = tmp_path / ".mist"
    legacy_root.mkdir()
    mist_root.mkdir()
    (legacy_root / "models.json").write_text("legacy", encoding="utf-8")
    (legacy_root / "legacy-only.json").write_text("copied", encoding="utf-8")
    (mist_root / "models.json").write_text("current", encoding="utf-8")
    _point_storage(monkeypatch, legacy_root, mist_root)

    config._migrate_legacy_storage()

    assert (mist_root / "models.json").read_text(encoding="utf-8") == "current"
    assert (mist_root / "legacy-only.json").read_text(encoding="utf-8") == "copied"

"""Carrying a 0.0.x setup over to 1.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_puppy import api_keys, migrate
from code_puppy.legacy_store import LegacyStore
from code_puppy.migrate import runner, sources, translate

CATALOG = {
    "sonnet": {"type": "anthropic", "name": "claude-sonnet-5"},
    "gpt": {"type": "openai", "name": "gpt-6"},
    "local": {
        "type": "custom_openai",
        "name": "glm",
        "custom_endpoint": {"url": "http://localhost:8000/v1"},
    },
    "proxied": {
        "type": "openai",
        "name": "gpt-6",
        "custom_endpoint": {"url": "https://proxy.example/v1"},
    },
}

PUPPY_CFG = """\
[puppy]
puppy_name = Boodler
owner_name = Mike
model = sonnet
message_limit = 250
yolo_mode = false
enable_speculative_code_mode = true
OPENAI_API_KEY = sk-legacy-openai
lilac_api_key = lilac-secret
temperature = 0.2
"""

MCP_SERVERS = {
    "mcp_servers": {
        "docs": {
            "type": "stdio",
            "command": "uvx",
            "args": ["docs-mcp"],
            "env": {"A": "1"},
        },
        "remote": {
            "type": "http",
            "url": "https://mcp.example/mcp",
            "headers": {"X": "y"},
        },
        "broken": {"type": "carrier-pigeon", "url": "coo://"},
        "nocommand": {"type": "stdio"},
    }
}


@pytest.fixture
def legacy_home(home: Path, installed_distribution: None) -> Path:
    """A home directory that 0.0.x has used."""
    root = home / ".code_puppy"
    root.mkdir()
    (root / "puppy.cfg").write_text(PUPPY_CFG, encoding="utf-8")
    (root / "mcp_servers.json").write_text(json.dumps(MCP_SERVERS), encoding="utf-8")
    (root / "extra_models.json").write_text(json.dumps(CATALOG), encoding="utf-8")
    return root


# --- translate: pure -------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sonnet", "anthropic:claude-sonnet-5"),
        ("gpt", "openai:gpt-6"),
        ("local", None),  # no built-in provider for the type
        ("proxied", None),  # a custom endpoint is not the stock provider
        ("unknown", None),
    ],
)
def test_model_reference(name: str, expected: str | None) -> None:
    assert translate.model_reference(name, CATALOG) == expected


def test_settings_translation() -> None:
    result = translate.settings(
        {
            "model": "sonnet",
            "message_limit": "250",
            "yolo_mode": "false",
            "enable_speculative_code_mode": "TRUE",
            "puppy_name": "Boodler",
            "owner_name": "Mike",
        },
        CATALOG,
    )
    assert result.values == {
        "model": "anthropic:claude-sonnet-5",
        "run.request_limit": 250,
        "run.permissions": "read-only",
        "run.speculative_code_mode": True,
        "run.instructions": "Your name is Boodler. Your user's name is Mike.",
    }
    assert result.notes == []


def test_settings_translation_reports_what_it_cannot_carry() -> None:
    result = translate.settings({"model": "local", "message_limit": "lots"}, CATALOG)
    assert result.values == {}
    assert len(result.notes) == 2 and "/model" in result.notes[0]


def test_secrets_are_split_from_preferences() -> None:
    config = {
        "openai_api_key": "sk",
        "empty_api_key": " ",
        "gh_token": "t",
        "model": "m",
    }
    assert translate.api_keys(config) == {"OPENAI_API_KEY": "sk", "GH_TOKEN": "t"}
    assert translate.preferences(config) == {"model": "m"}


def test_mcp_servers_become_deferred() -> None:
    server, _ = translate.mcp_server({"command": "uvx", "args": ["x"], "timeout": 30})
    assert server == {
        "type": "stdio",
        "defer_loading": True,
        "command": "uvx",
        "args": ["x"],
        "timeout": 30.0,
    }
    assert translate.mcp_server({"type": "pigeon"}) == (
        None,
        "unknown transport 'pigeon'",
    )


# --- sources ----------------------------------------------------------------


def test_sources_read_missing_and_malformed_files_as_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.write_text("{not json", encoding="utf-8")
    assert sources.read_config(tmp_path / "nope.cfg") == {}
    assert sources.read_config(bad) == {}
    assert sources.read_mcp_servers(bad) == {}
    assert sources.read_models((bad, tmp_path / "nope.json")) == {}


def test_fingerprint_tracks_file_contents(legacy_home: Path) -> None:
    files = sources.legacy_files()
    first = files.fingerprint()
    assert first and first == files.fingerprint()
    (legacy_home / "puppy.cfg").write_text(PUPPY_CFG + "x = 1\n", encoding="utf-8")
    assert files.fingerprint() != first


# --- runner: against real 1.0 stores ----------------------------------------


def test_plan_describes_without_revealing_secrets(legacy_home: Path) -> None:
    plan = runner.build_plan()
    text = "\n".join(plan.describe())
    assert "OPENAI_API_KEY" in text and "sk-legacy-openai" not in text
    assert "lilac-secret" not in text
    assert sorted(plan.servers) == ["docs", "remote"]
    assert sum("Skipped MCP server" in note for note in plan.notes) == 2


def test_apply_writes_every_store(legacy_home: Path) -> None:
    from pydantic_clai2.config.api_keys import load_keys
    from pydantic_clai2.config.settings_store import SettingsStore
    from pydantic_clai2.mcp.store import MCPStore

    result = runner.apply(runner.build_plan())

    settings = SettingsStore().load()
    assert settings.model == "anthropic:claude-sonnet-5"
    assert settings.request_limit == 250
    assert settings.permissions == "read-only"
    assert settings.speculative_code_mode is True
    assert settings.instructions == "Your name is Boodler. Your user's name is Mike."

    keys = {name: key.get_secret_value() for name, key in load_keys().items()}
    assert keys == {
        "OPENAI_API_KEY": "sk-legacy-openai",
        "LILAC_API_KEY": "lilac-secret",
    }

    servers = MCPStore().load().servers
    assert sorted(servers) == ["docs", "remote"]
    assert servers["docs"].defer_loading is True and servers["docs"].command == "uvx"

    legacy = LegacyStore()
    assert legacy.get("temperature") == "0.2" and legacy.get("puppy_name") == "Boodler"
    assert legacy.get("openai_api_key") is None  # secrets are not copied in the clear
    assert result.summary() == "5 settings, 2 API keys, 2 MCP servers"


def test_legacy_files_are_never_modified(legacy_home: Path) -> None:
    before = {path.name: path.read_bytes() for path in legacy_home.iterdir()}
    runner.apply(runner.build_plan())
    for name, content in before.items():
        assert (legacy_home / name).read_bytes() == content


def test_second_run_changes_nothing_and_keeps_user_choices(legacy_home: Path) -> None:
    from pydantic_clai2.config.settings_store import SettingsStore

    assert migrate.auto()  # first start reports what it brought over
    SettingsStore().set("run.request_limit", 999)  # the user changes a migrated value
    assert migrate.auto() == []  # same legacy files: nothing to do

    again = runner.apply(runner.build_plan())  # an explicit re-run
    assert not again.changed
    assert SettingsStore().load().request_limit == 999


def test_auto_runs_again_when_legacy_files_change(legacy_home: Path) -> None:
    migrate.auto()
    servers = {
        "mcp_servers": {**MCP_SERVERS["mcp_servers"], "extra": {"command": "npx"}}
    }
    (legacy_home / "mcp_servers.json").write_text(json.dumps(servers), encoding="utf-8")
    lines = migrate.auto()
    assert lines and "1 MCP server" in lines[0]


def test_auto_is_silent_without_legacy_files(
    home: Path, installed_distribution: None
) -> None:
    assert migrate.auto() == []
    assert not (home / ".code_puppy" / "puppy.db").exists()


def test_cli_dry_run_writes_nothing(
    legacy_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert migrate.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run: nothing was written." in out and "sk-legacy-openai" not in out
    assert sorted(p.name for p in legacy_home.iterdir()) == [
        "extra_models.json",
        "mcp_servers.json",
        "puppy.cfg",
    ]


def test_cli_applies_and_reports(
    legacy_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert migrate.main([]) == 0
    assert "Wrote: 5 settings, 2 API keys, 2 MCP servers." in capsys.readouterr().out


# --- saved keys reach providers ---------------------------------------------


def test_saved_keys_are_exported_unless_already_set(legacy_home: Path) -> None:
    runner.apply(runner.build_plan())
    environ = {"OPENAI_API_KEY": "from-the-shell"}
    assert api_keys.export_saved_keys(environ) == ["LILAC_API_KEY"]
    assert environ == {
        "OPENAI_API_KEY": "from-the-shell",
        "LILAC_API_KEY": "lilac-secret",
    }


def test_export_does_nothing_without_saved_keys(
    home: Path, installed_distribution: None
) -> None:
    environ: dict[str, str] = {}
    assert api_keys.export_saved_keys(environ) == [] and environ == {}

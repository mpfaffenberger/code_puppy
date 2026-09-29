"""Safety config: YOLO precedence and the dangerous-command guard allowlist.

These read paths used to be exercised only by mirrored plugin tests; the
guards live in plugins, but the config contract they rely on is core's.
"""

from __future__ import annotations

import pytest

from code_puppy import config as cp_config


@pytest.fixture
def cli_yolo(monkeypatch):
    """Set the process-local CLI override; monkeypatch restores it."""
    monkeypatch.setattr(cp_config, "_cli_yolo_override", None)
    return cp_config.set_cli_yolo_override


@pytest.mark.parametrize(
    "cli, saved, expected",
    [
        (None, None, True),  # default is YOLO on
        (None, "false", False),
        (False, "true", False),  # CLI beats puppy.cfg both ways
        (True, "false", True),
    ],
)
def test_yolo_mode_cli_override_beats_config(cli_yolo, cli, saved, expected):
    if saved is not None:
        cp_config.set_config_value("yolo_mode", saved)
    cli_yolo(cli)
    assert cp_config.get_cli_yolo_override() is cli
    assert cp_config.get_yolo_mode() is expected


def test_guard_is_on_unless_explicitly_disabled():
    assert cp_config.get_disable_dangerous_command_guard() is False
    cp_config.set_config_value("disable_dangerous_command_guard", "true")
    assert cp_config.get_disable_dangerous_command_guard() is True


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ""),
        (None, ""),
        ("  Git   Reset\t--Hard ", "git reset --hard"),
        ("--force", "--force"),
    ],
)
def test_normalize_guard_pattern_name(raw, expected):
    assert cp_config.normalize_guard_pattern_name(raw) == expected


def test_allowlist_is_empty_when_unset():
    assert cp_config.get_dangerous_command_guard_allowlist() == set()
    assert cp_config.is_dangerous_command_allowlisted("git reset --hard") is False


def test_allowlist_parses_sloppy_entries_and_matches_normalized():
    cp_config.set_config_value(
        "dangerous_command_guard_allow", " Git  Reset --HARD, ,--force,, "
    )
    assert cp_config.get_dangerous_command_guard_allowlist() == {
        "git reset --hard",
        "--force",
    }
    assert cp_config.is_dangerous_command_allowlisted("git reset --hard")
    assert cp_config.is_dangerous_command_allowlisted("  --FORCE ")
    assert not cp_config.is_dangerous_command_allowlisted("rm -rf")
    assert not cp_config.is_dangerous_command_allowlisted("")

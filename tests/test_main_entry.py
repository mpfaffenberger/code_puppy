"""``pup``'s entry point: the splash covers startup, and every opt-out is honoured."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from code_puppy import distribution, main

NO_SPLASH = main.NO_SPLASH_VARIABLES


@pytest.fixture(autouse=True)
def splash_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NO_SPLASH:
        monkeypatch.delenv(name, raising=False)


def settings(database: Path, rows: dict[str, object]) -> Path:
    """A settings database holding ``rows``, as pax stores them."""
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT)"
        )
        connection.executemany(
            "INSERT INTO settings VALUES (?, ?)",
            [(key, json.dumps(value)) for key, value in rows.items()],
        )
    connection.close()
    return database


def test_a_bare_launch_without_settings_wants_the_splash(tmp_path: Path) -> None:
    assert main.splash_wanted(["pup"], tmp_path / "config.db") is True


@pytest.mark.parametrize("argv", [["pup", "-p", "hi"], ["pup", "config", "show"]])
def test_any_argument_skips_the_splash(tmp_path: Path, argv: list[str]) -> None:
    assert main.splash_wanted(argv, tmp_path / "config.db") is False


@pytest.mark.parametrize("variable", NO_SPLASH)
def test_an_environment_variable_turns_it_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "1")
    assert main.splash_wanted(["pup"], tmp_path / "config.db") is False


@pytest.mark.parametrize(
    ("rows", "wanted"),
    [
        ({"display.splash": False}, False),
        ({"display.splash": True}, True),
        ({"display.theme": "dark"}, True),
    ],
)
def test_the_saved_setting_decides(
    tmp_path: Path, rows: dict[str, object], wanted: bool
) -> None:
    database = settings(tmp_path / "config.db", rows)
    assert main.splash_wanted(["pup"], database) is wanted


def test_an_unreadable_settings_file_skips_the_splash(tmp_path: Path) -> None:
    database = tmp_path / "config.db"
    database.write_bytes(b"not a database")
    assert main.splash_wanted(["pup"], database) is False


@pytest.fixture
def launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[list[object], list[object]]:
    """A bare ``pup`` launch with the splash and the runtime recorded, not run.

    Returns the events in order, and the splashes created.
    """
    from pydantic_ai_pax.cli import cli

    events: list[object] = []
    splashes: list[object] = []

    class RecordingSplash:
        def __init__(self, *, enabled: bool) -> None:
            events.append(("splash", enabled))
            splashes.append(self)

        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    def run(*, splash: object) -> None:
        events.append("run")
        assert splash is splashes[0]

    monkeypatch.setattr("code_puppy.splash.Splash", RecordingSplash)
    monkeypatch.setattr(distribution, "install", lambda: events.append("install"))
    monkeypatch.setattr(main, "_migrate_legacy_setup", lambda: events.append("migrate"))
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "argv", ["pup"])
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "")
    monkeypatch.chdir(tmp_path)
    return events, splashes


def test_the_splash_covers_startup_and_reaches_pax(
    launch: tuple[list[object], list[object]],
) -> None:
    events, _ = launch
    main.main_entry()

    assert events == [("splash", True), "start", "install", "migrate", "run", "stop"]


def test_the_splash_stops_when_startup_fails(
    launch: tuple[list[object], list[object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    events, _ = launch

    def broken() -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(main, "_migrate_legacy_setup", broken)
    with pytest.raises(RuntimeError):
        main.main_entry()

    assert events == [("splash", True), "start", "install", "stop"]


def test_an_opt_out_reaches_the_splash(
    launch: tuple[list[object], list[object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    events, _ = launch
    monkeypatch.setenv(NO_SPLASH[0], "1")
    main.main_entry()

    assert events[0] == ("splash", False)

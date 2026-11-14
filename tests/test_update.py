"""`/update` for Code Puppy: which versions are offered, and how they install."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from pydantic_clai2.cli.self_update import Installed

from code_puppy import update

FILE = [{"yanked": False}]
RELEASES: dict[str, list[dict[str, Any]]] = {
    "0.0.969": FILE,
    "0.0.970": FILE,
    "0.0.971": [{"yanked": True}],
    "0.0.972": [],
    "1.0.0rc1": FILE,
    "1.0.0rc2": FILE,
    "not-a-version": FILE,
}


def test_newest_release_skips_prereleases_yanked_and_empty() -> None:
    assert update.newest_release(RELEASES, prereleases=False) == "0.0.970"
    assert update.newest_release(RELEASES, prereleases=True) == "1.0.0rc2"
    assert update.newest_release({}, prereleases=True) is None


@pytest.mark.parametrize(
    ("channel", "running", "expected"),
    [
        ("stable", "0.0.969", False),
        ("stable", "1.0.0rc1", True),
        ("main", "0.0.969", True),
        ("stable", "garbage", False),
    ],
)
def test_follows_prereleases(channel: str, running: str, expected: bool) -> None:
    assert update.follows_prereleases(channel, running) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("running", "target", "offered"),
    [
        ("0.0.969", "0.0.970", True),
        ("1.0.0rc1", "1.0.0rc2", True),
        ("1.0.0rc2", "1.0.0", True),
        ("1.0.0rc1", "1.0.0rc1", False),
        # The newest stable release is older than a running release candidate.
        ("1.0.0rc1", "0.0.970", False),
    ],
)
def test_find_update_never_offers_a_downgrade(
    running: str, target: str, offered: bool
) -> None:
    found = update.find_update("stable", Installed(version=running), target)
    assert (found is not None) is offered
    if found is not None:
        assert found.label == target


def _pypi(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == "https://pypi.org/pypi/code-puppy/json"
    return httpx.Response(200, content=json.dumps({"releases": RELEASES}))


@pytest.mark.parametrize(
    ("channel", "running", "expected"),
    [
        ("stable", "0.0.969", "0.0.970"),
        ("main", "0.0.969", "1.0.0rc2"),
        ("stable", "1.0.0rc1", "1.0.0rc2"),
    ],
)
def test_latest_reads_pypi(channel: str, running: str, expected: str) -> None:
    found = update.latest(
        channel, transport=httpx.MockTransport(_pypi), running=running
    )  # type: ignore[arg-type]
    assert found == expected


def test_latest_reports_an_empty_project() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"releases": {}})
    )
    with pytest.raises(ValueError, match="no installable"):
        update.latest("stable", transport=transport, running="0.0.969")


def test_install_command_pins_the_exact_version() -> None:
    found = update.PuppyUpdate(channel="stable", target="1.0.0rc2")
    assert found.command(uv="uv") == [
        "uv",
        "tool",
        "install",
        "--force",
        "--compile-bytecode",
        "code-puppy==1.0.0rc2",
    ]
    assert found.overrides() == ""


def test_launch_names_prefer_the_command_that_ran() -> None:
    assert update.launch_names(argv0="/bin/code-puppy", windows=False) == [
        "code-puppy",
        "pup",
    ]
    assert update.launch_names(argv0="/x/python", windows=False) == [
        "pup",
        "code-puppy",
    ]
    assert update.launch_names(argv0="C:/t/pup.exe", windows=True) == [
        "pup.exe",
        "code-puppy.exe",
    ]


def test_windows_script_waits_installs_and_reports() -> None:
    script = update.after_exit_script(
        ["uv", "tool", "install", "code-puppy==1.0.0"], pid=42
    )
    lines = script.splitlines()
    assert lines[0] == "Wait-Process -Id 42 -ErrorAction SilentlyContinue"
    assert "code-puppy==1.0.0" in lines[2]
    assert "Updated Code Puppy. Start pup again." in script


class Recorder:
    """Stands in for uv and for the Windows hand-off."""

    def __init__(self, *, code: int = 0) -> None:
        self.code = code
        self.commands: list[list[str]] = []
        self.scripts: list[str] = []

    async def run(self, command: Sequence[str], output: object) -> int:
        self.commands.append(list(command))
        return self.code

    def hand_off(self, script: str) -> None:
        self.scripts.append(script)


def _updates(
    recorder: Recorder,
    *,
    running: str = "1.0.0rc1",
    target: str = "1.0.0rc2",
    uv: str | None = "/usr/bin/uv",
    windows: bool = False,
    relaunch: str | None = "/tools/bin/pup",
) -> update.PuppyUpdates:
    async def locate(uv: str) -> str | None:
        return relaunch

    return update.PuppyUpdates(
        channel=lambda: "stable",
        current=Installed(version=running, tool=True),
        fetch=lambda channel: target,
        find_uv=lambda: uv,
        windows=windows,
        run=recorder.run,
        hand_off=recorder.hand_off,
        locate=locate,
    )


async def test_command_reports_when_already_newest() -> None:
    recorder = Recorder()
    updates = _updates(recorder, target="1.0.0rc1")
    assert (
        await updates.command([])
        == "Code Puppy 1.0.0rc1 is the newest on the stable channel."
    )
    assert recorder.commands == [] and not updates.restart_required


async def test_command_installs_and_restarts() -> None:
    recorder = Recorder()
    updates = _updates(recorder)
    message = await updates.command(["now"])
    assert recorder.commands == [
        [
            "/usr/bin/uv",
            "tool",
            "install",
            "--force",
            "--compile-bytecode",
            "code-puppy==1.0.0rc2",
        ]
    ]
    assert message == "Updated Code Puppy to 1.0.0rc2 (stable). Restarting..."
    assert updates.restart_required and updates.relaunch == "/tools/bin/pup"


async def test_command_exits_when_the_new_executable_is_not_found() -> None:
    updates = _updates(Recorder(), relaunch=None)
    assert (await updates.command([])).endswith("Exiting; start pup again to use it.")
    assert updates.restart_required and updates.relaunch is None


async def test_command_reports_a_failed_install() -> None:
    updates = _updates(Recorder(code=2))
    assert await updates.command([]) == "uv exited with status 2; see its output above."
    assert updates.failed and not updates.restart_required


async def test_command_prints_the_manual_install_without_uv() -> None:
    recorder = Recorder()
    updates = _updates(recorder, uv=None)
    message = await updates.command([])
    assert "uv tool install --force --compile-bytecode code-puppy==1.0.0rc2" in message
    assert updates.failed and recorder.commands == []


async def test_command_hands_off_on_windows() -> None:
    recorder = Recorder()
    updates = _updates(recorder, windows=True)
    message = await updates.command([])
    assert "in a new window once Code Puppy exits" in message
    assert len(recorder.scripts) == 1 and "code-puppy==1.0.0rc2" in recorder.scripts[0]
    assert updates.restart_required and recorder.commands == []


async def test_command_rejects_unknown_arguments() -> None:
    with pytest.raises(ValueError, match="Usage: /update"):
        await _updates(Recorder()).command(["later"])


async def test_cli_update_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert await update.cli_update("stable", updates=_updates(Recorder())) == 0
    assert "Updated Code Puppy to 1.0.0rc2" in capsys.readouterr().out
    assert await update.cli_update("stable", updates=_updates(Recorder(code=1))) == 1

    def offline(channel: str) -> str:
        raise httpx.ConnectError("no network")

    broken = _updates(Recorder())
    broken.fetch = offline
    assert await update.cli_update("stable", updates=broken) == 1
    assert (
        "Could not check for a newer Code Puppy: no network" in capsys.readouterr().err
    )


def test_status_row_notice_uses_code_puppys_rules(installed_distribution: None) -> None:
    """The inherited background check must go through Code Puppy's `find_update`."""
    updates = update.PuppyUpdates(
        channel=lambda: "stable",
        current=Installed(version="1.0.0rc1", tool=True),
        fetch=lambda channel: "0.0.970",
        spawn=lambda work: work(),
    )
    assert updates.segment() == ""  # an older stable release is not an update
    newer = update.PuppyUpdates(
        channel=lambda: "stable",
        current=Installed(version="1.0.0rc1", tool=True),
        fetch=lambda channel: "1.0.0rc2",
        spawn=lambda work: work(),
    )
    assert newer.segment() == "update 1.0.0rc2: /update"

"""``/update``, ``pup update`` and ``pup --update`` for Code Puppy.

Works like pydantic-ai-pax's updater, which supplies the machinery (background
check, status-row notice, update menu, ``uv tool install``, restart into the
new build, the Windows install-after-exit window). This module supplies what
is specific to Code Puppy: which package to look up, which versions count as
newer, and what to tell the user.

Channels (``/set updates.channel stable|main``):

* ``stable`` follows stable PyPI releases of ``code-puppy``.
* ``main`` also follows pre-releases (release candidates).

Two rules differ from pax on purpose:

* A running pre-release follows pre-releases on either channel. Someone testing
  ``1.0.0rc1`` keeps getting release candidates and lands on ``1.0.0`` when it
  ships, without having to change a setting first.
* An older version is never offered. On ``stable`` the newest stable release
  can be *older* than a running release candidate; "different" is not "newer".
"""

from __future__ import annotations

import os
import shlex
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anyio import CancelScope, run_process, to_thread
from packaging.version import InvalidVersion, Version
from pydantic_ai_pax.cli.self_update import (
    TIMEOUT,
    Installed,
    Update,
    Updates,
    powershell,
)
from pydantic_ai_pax.config import UpdateChannel
from pydantic_ai_pax.plugins import InstallProgress, UpdateStage

from code_puppy.identity import COMMANDS, DISPLAY_NAME, DISTRIBUTION

if TYPE_CHECKING:
    import httpx

PYPI_URL = f"https://pypi.org/pypi/{DISTRIBUTION}/json"


def installed() -> Installed:
    """The running Code Puppy; ``uv tool install`` leaves a receipt in the environment."""
    return Installed(
        version=metadata.version(DISTRIBUTION),
        tool=Path(sys.prefix, "uv-receipt.toml").is_file(),
    )


def follows_prereleases(channel: UpdateChannel, running: str) -> bool:
    """Whether release candidates are offered: on ``main``, or to a running pre-release."""
    if channel == "main":
        return True
    try:
        return Version(running).is_prerelease
    except InvalidVersion:
        return False


def newest_release(
    releases: Mapping[str, Sequence[Mapping[str, Any]]], *, prereleases: bool
) -> str | None:
    """The highest installable version in PyPI's ``releases`` table.

    A version counts when it has at least one file that is not yanked.
    """
    best: Version | None = None
    for text, files in releases.items():
        try:
            version = Version(text)
        except InvalidVersion:
            continue
        if not any(not item.get("yanked") for item in files):
            continue
        if version.is_prerelease and not prereleases:
            continue
        if best is None or version > best:
            best = version
    return None if best is None else str(best)


def latest(
    channel: UpdateChannel,
    *,
    transport: httpx.BaseTransport | None = None,
    running: str | None = None,
) -> str:
    """The newest Code Puppy on ``channel``, read from PyPI."""
    import httpx

    with httpx.Client(
        transport=transport, timeout=TIMEOUT, follow_redirects=True
    ) as client:
        project = client.get(PYPI_URL).raise_for_status().json()
    running = metadata.version(DISTRIBUTION) if running is None else running
    found = newest_release(
        project.get("releases", {}),
        prereleases=follows_prereleases(channel, running),
    )
    if found is None:
        raise ValueError(f"PyPI lists no installable {DISTRIBUTION} release")
    return found


@dataclass(frozen=True, kw_only=True)
class PuppyUpdate(Update):
    """A newer Code Puppy: always a PyPI version, on either channel."""

    @property
    def label(self) -> str:
        return self.target

    def overrides(self) -> str:
        """Nothing to override: every Code Puppy build installs from PyPI."""
        return ""

    def command(self, *, uv: str, overrides: Path | None = None) -> list[str]:
        """The ``uv tool install`` that replaces the current install.

        The exact pin is what lets uv pick a release candidate without
        ``--prerelease allow``, which would loosen every dependency too.
        """
        return [
            uv,
            "tool",
            "install",
            "--force",
            "--compile-bytecode",
            f"{DISTRIBUTION}=={self.target}",
        ]


def find_update(
    channel: UpdateChannel, current: Installed, target: str
) -> PuppyUpdate | None:
    """Offer ``target`` only when it is newer than what runs."""
    try:
        newer = Version(target) > Version(current.version)
    except InvalidVersion:
        newer = target != current.version
    return PuppyUpdate(channel=channel, target=target) if newer else None


def launch_names(
    *, argv0: str | None = None, windows: bool = os.name == "nt"
) -> list[str]:
    """Executable names to restart into: the command the user ran first."""
    ran = Path(sys.argv[0] if argv0 is None else argv0).stem
    ordered = [ran, *COMMANDS] if ran in COMMANDS else list(COMMANDS)
    names = list(dict.fromkeys(ordered))
    return [f"{name}.exe" for name in names] if windows else names


def command_name() -> str:
    """The command the user ran, wherever pax would name its own ``pax``."""
    return launch_names(windows=False)[0]


async def tool_executable(uv: str) -> str | None:
    """The ``pup`` that ``uv tool install`` just wrote to uv's tool bin directory."""
    result = await run_process([uv, "tool", "dir", "--bin"], check=False)
    if result.returncode != 0:
        return None
    folder = Path(result.stdout.decode().strip())
    for name in launch_names():
        path = folder / name
        if await to_thread.run_sync(path.is_file):
            return str(path)
    return None


def after_exit_script(command: Sequence[str], *, pid: int) -> str:
    """A PowerShell script that waits for Code Puppy to exit, then installs.

    Windows refuses to replace files a running program uses, so the install
    cannot run inside Code Puppy. The window stays open to show uv's result.
    """
    lines = [
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue",
        # The `pup.exe` launcher exits just after the Python process it started.
        "Start-Sleep -Seconds 1",
        powershell(command),
        "$code = $LASTEXITCODE",
        f"if ($code -eq 0) {{ 'Updated {DISPLAY_NAME}. Start {COMMANDS[0]} again.' }} "
        'else { "uv exited with status $code." }',
        "Read-Host 'Press Enter to close'",
    ]
    return "\n".join(lines)


@dataclass(kw_only=True)
class PuppyUpdates(Updates):
    """pax's ``Updates`` with Code Puppy's lookup, version rules and wording."""

    current: Installed = field(default_factory=installed)
    fetch: Callable[[UpdateChannel], str] = latest
    locate: Callable[[str], Awaitable[str | None]] = tool_executable

    async def command(self, args: list[str]) -> str:
        """Install the newest Code Puppy with ``uv tool install``; in a session, restart into it.

        ``/update now`` in a session, where bare ``/update`` opens the menu;
        ``pup --update`` passes no arguments.
        """
        if args not in ([], ["now"]):
            raise ValueError(
                f"Usage: /update opens the update menu; /update now installs the "
                f"newest {DISPLAY_NAME}. Pick the channel with /set updates.channel "
                "stable|main (main includes release candidates)."
            )
        channel = self.channel()
        target = await to_thread.run_sync(self.fetch, channel)
        update = find_update(channel, self.current, target)
        if update is None:
            return (
                f"{DISPLAY_NAME} {self.current.label} is the newest on the "
                f"{channel} channel."
            )
        uv = await to_thread.run_sync(self.find_uv)
        command = update.command(uv=uv or "uv")
        if uv is None:
            self.failed = True
            shown = powershell(command) if self.windows else shlex.join(command)
            return (
                f"{DISPLAY_NAME} {update.label} is available on the {channel} "
                f"channel. {DISPLAY_NAME} updates itself only when uv is on PATH. "
                f"To update by hand, run:\n{shown}"
            )
        if self.windows:
            self.hand_off(after_exit_script(command, pid=os.getpid()))
            self.restart_required = True
            return (
                f"Installing {DISPLAY_NAME} {update.label} ({channel}) in a new "
                f"window once {DISPLAY_NAME} exits. Exiting; start {COMMANDS[0]} "
                "again when it finishes."
            )
        return await self._install(update, uv=uv, command=command, channel=channel)

    async def _install(
        self,
        update: PuppyUpdate,
        *,
        uv: str,
        command: Sequence[str],
        channel: UpdateChannel,
    ) -> str:
        report = self.report()

        async def tell(stage: UpdateStage, text: str = "") -> None:
            if report is not None:
                await report(
                    InstallProgress(stage=stage, target=update.label, text=text)
                )

        async def line(text: str) -> None:
            await tell("output", text)

        # Cancelling uv halfway could leave the environment half replaced.
        code: int | None = None
        try:
            # Read before uv runs: afterwards a first-time import would load
            # the new build's module into the old build's process.
            served = self.serving()
            with CancelScope(shield=True):
                await tell("installing")
                capture = report is not None and self.capture()
                code = await self.run(command, line if capture else None)
        finally:
            if code != 0:  # Also when uv could not run at all.
                await tell("failed")
        if code != 0:
            self.failed = True
            return f"uv exited with status {code}; see its output above."
        self.restart_required = True
        self.relaunch = await self.locate(uv)
        self.web = served if self.relaunch is not None else None
        await tell("installed" if self.relaunch is None else "restarting")
        done = f"Updated {DISPLAY_NAME} to {update.label} ({channel})."
        if self.relaunch is None:
            return f"{done} Exiting; start {COMMANDS[0]} again to use it."
        return f"{done} Restarting..."


async def cli_update(
    channel: UpdateChannel, *, updates: PuppyUpdates | None = None
) -> int:
    """``pup --update`` and ``pup update``: install, print how it went, and exit.

    No shell runs, so nothing restarts: the next ``pup`` is the new build. On
    Windows the install starts in its own window once this process has exited,
    which is immediately. Exits 1 when the check failed, or uv failed or is
    missing.
    """
    import httpx

    async def no_relaunch(uv: str) -> None:
        return None

    if updates is None:
        updates = PuppyUpdates(channel=lambda: channel, locate=no_relaunch)
    try:
        print(await updates.command([]))
    except (httpx.HTTPError, ValueError) as exc:
        # Offline, rate-limited, or an unexpected release listing.
        print(f"Could not check for a newer {DISPLAY_NAME}: {exc}", file=sys.stderr)
        return 1
    return 1 if updates.failed else 0

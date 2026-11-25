"""Entry point for ``pup`` and ``code-puppy``.

Import-light until the splash is up: the heavy agent and UI imports run while
it animates. The order below is load-bearing; see ``distribution``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from code_puppy import identity

NO_SPLASH_VARIABLES = ("CODE_PUPPY_NO_SPLASH", "CLAI_NO_SPLASH")


def _load_dotenv() -> None:
    """Take the credentials in the project's ``.env``, and nothing else; never fatal.

    A ``.env`` is read from whatever directory ``pup`` was started in, so in a
    cloned repository it is the repository's file. 0.0.x read only names
    shaped like a credential from it, and so does this: a name that redirects
    where Code Puppy sends its requests (``*_BASE_URL``, ``*_ENDPOINT``,
    ``HTTPS_PROXY``) or where it reads its own settings and plugins
    (``XDG_CONFIG_HOME``, ``CODE_PUPPY_*``) is left in the file. Set those in
    the environment yourself, where the repository cannot write them.

    A variable the user already set always wins, as ``load_dotenv`` has it.
    """
    from dotenv import dotenv_values, find_dotenv

    from code_puppy.api_keys import is_credential_name

    dotenv_path = ".env"
    try:
        dotenv_path = find_dotenv(usecwd=True)
        # Named pipes must not block startup.
        if not Path(dotenv_path).is_file():
            return
        found = dotenv_values(dotenv_path)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Ignoring `.env` at {dotenv_path!r}: {exc}", file=sys.stderr)
        return
    for name, value in found.items():
        if value and is_credential_name(name) and not os.environ.get(name):
            os.environ[name] = value


def splash_wanted(argv: list[str], database: Path) -> bool:
    """Bare interactive launches animate, unless the user turned the splash off."""
    if len(argv) != 1 or any(os.getenv(name) for name in NO_SPLASH_VARIABLES):
        return False
    if not database.exists():
        return True
    try:
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = 'display.splash'"
            ).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, ValueError):
        return False
    return row is None or json.loads(row[0]) is True


def _migrate_legacy_setup() -> None:
    """Carry a 0.0.x setup over on first start, then expose saved API keys.

    Must never block startup.
    """
    from code_puppy import api_keys, migrate

    try:
        for line in migrate.auto():
            # stderr: `pup -p ...` output is often piped, and must stay clean.
            print(line, file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - a bad legacy file must not stop pup
        print(
            f"Could not bring over the 0.0.x setup ({type(exc).__name__}: {exc}). "
            f"Run `{identity.COMMANDS[0]} migrate` to retry.",
            file=sys.stderr,
        )
    try:
        api_keys.export_saved_keys()
    except Exception as exc:  # noqa: BLE001 - a locked keyring must not stop pup
        print(
            f"Could not read saved API keys ({type(exc).__name__}: {exc}).",
            file=sys.stderr,
        )


def _own_command(argv: list[str]) -> int | None:
    """Run a subcommand that belongs to Code Puppy rather than the runtime."""
    if argv[1:2] != ["migrate"]:
        return None
    from code_puppy import distribution, migrate

    distribution.install()
    return migrate.main(argv[2:])


_PROACTOR_RESET_WINERROR = 10054


def _finish_reset_proactor_transport(transport: object) -> None:
    """Finish socket close and server detach skipped if ``shutdown()`` raises WinError 10054."""
    sock: object = getattr(transport, "_sock", None)
    close = getattr(sock, "close", None)
    if callable(close):
        try:
            close()
        except OSError:
            pass
    setattr(transport, "_sock", None)
    server: object = getattr(transport, "_server", None)
    detach = getattr(server, "_detach", None)
    if callable(detach):
        detach(transport)
        setattr(transport, "_server", None)
    setattr(transport, "_called_connection_lost", True)


@contextmanager
def quiet_windows_proactor_reset() -> Iterator[None]:
    """Silence CPython's Windows Proactor ``WinError 10054`` socket-teardown race.

    Removable once ``pydantic-ai-pax`` includes this guard upstream.
    """
    if sys.platform != "win32":
        yield
        return

    from asyncio import proactor_events

    transport_cls = getattr(proactor_events, "_ProactorBasePipeTransport", None)
    original = cast(
        Callable[[object, BaseException | None], None] | None,
        getattr(transport_cls, "_call_connection_lost", None),
    )
    if transport_cls is None or original is None:
        yield
        return

    def wrapped(self: object, exc: BaseException | None) -> None:
        try:
            original(self, exc)
        except ConnectionResetError as err:
            if (
                getattr(err, "winerror", None) == _PROACTOR_RESET_WINERROR
                and not getattr(self, "_called_connection_lost", True)
                and getattr(self, "_sock", None) is not None
            ):
                _finish_reset_proactor_transport(self)
                return
            raise

    setattr(transport_cls, "_call_connection_lost", wrapped)
    try:
        yield
    finally:
        setattr(transport_cls, "_call_connection_lost", original)


def main_entry() -> None:
    """Start Code Puppy: pydantic-ai-pax with Code Puppy's identity installed."""
    _load_dotenv()
    code = _own_command(sys.argv)
    if code is not None:
        raise SystemExit(code)

    from code_puppy import distribution

    distribution.install_splash()
    from pydantic_ai_pax.ui.rendering.splash import Splash

    os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
    splash = Splash(
        enabled=splash_wanted(sys.argv, identity.config_dir() / "config.db")
    )
    splash.start()
    try:
        distribution.install()
        _migrate_legacy_setup()
        from pydantic_ai_pax.__main__ import quiet_telemetry_logs
        from pydantic_ai_pax.cli.cli import run

        with (
            warnings.catch_warnings(),
            quiet_telemetry_logs(),
            quiet_windows_proactor_reset(),
        ):
            if not sys.warnoptions:
                # Library warnings are advice for whoever wired the agent, not
                # the person at the prompt, and stderr output tears through the
                # live display. `-W` or `PYTHONWARNINGS` restores them.
                warnings.simplefilter("ignore", Warning)
            run(splash=splash)
    finally:
        splash.stop()


if __name__ == "__main__":
    main_entry()

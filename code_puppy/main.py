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
from pathlib import Path

from code_puppy import identity

NO_SPLASH_VARIABLES = ("CODE_PUPPY_NO_SPLASH", "CLAI_NO_SPLASH")


def _load_dotenv() -> None:
    """Load the project's ``.env`` so settings and keys see it; never fatal."""
    from dotenv import find_dotenv, load_dotenv

    dotenv_path = ".env"
    try:
        dotenv_path = find_dotenv(usecwd=True)
        # Named pipes must not block startup.
        if Path(dotenv_path).is_file():
            load_dotenv(dotenv_path)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Ignoring `.env` at {dotenv_path!r}: {exc}", file=sys.stderr)


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


def main_entry() -> None:
    """Start Code Puppy: pydantic-clai2 with Code Puppy's identity installed."""
    _load_dotenv()

    from code_puppy import distribution

    distribution.install_splash()
    from pydantic_clai2.ui.rendering.splash import Splash

    os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
    splash = Splash(
        enabled=splash_wanted(sys.argv, identity.config_dir() / "config.db")
    )
    splash.start()
    try:
        distribution.install()
        from pydantic_clai2.__main__ import quiet_telemetry_logs
        from pydantic_clai2.cli.cli import run

        with warnings.catch_warnings(), quiet_telemetry_logs():
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

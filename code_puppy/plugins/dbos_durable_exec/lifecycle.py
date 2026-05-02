"""DBOS launch/destroy lifecycle, lifted from cli_runner.py."""

from __future__ import annotations

import os
import time

from code_puppy import __version__ as current_version
from code_puppy.messaging import emit_error

from .config import DBOS_DATABASE_URL


def on_startup() -> None:
    """Initialize and launch DBOS for durable execution."""
    try:
        from dbos import DBOS, DBOSConfig
    except ImportError:
        emit_error("DBOS not installed; durable execution disabled.")
        return

    dbos_app_version = os.environ.get(
        "DBOS_APP_VERSION", f"{current_version}-{int(time.time() * 1000)}"
    )
    dbos_config: DBOSConfig = {
        "name": "dbos-code-puppy",
        "system_database_url": DBOS_DATABASE_URL,
        "run_admin_server": False,
        "conductor_key": os.environ.get("DBOS_CONDUCTOR_KEY"),
        "log_level": os.environ.get("DBOS_LOG_LEVEL", "ERROR"),
        "application_version": dbos_app_version,
    }
    try:
        DBOS(config=dbos_config)
        DBOS.launch()
    except Exception as e:
        emit_error(f"Error initializing DBOS: {e}")


def on_shutdown() -> None:
    """Tear DBOS down. Best-effort, never raises."""
    try:
        from dbos import DBOS
    except ImportError:
        return
    try:
        DBOS.destroy()
    except Exception:
        pass

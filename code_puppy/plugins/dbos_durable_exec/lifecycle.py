"""DBOS launch/destroy lifecycle, lifted from cli_runner.py."""

from __future__ import annotations

import os
import time
import traceback

from code_puppy import __version__ as current_version
from code_puppy.messaging import emit_error, emit_info

from .config import DBOS_DATABASE_URL, is_enabled


def on_startup() -> None:
    """Initialize and launch DBOS for durable execution."""
    # Diagnostics: surface plugin-level decisions in the log so CI/users can
    # debug why DBOS may not be initializing. Cheap; one line each.
    emit_info(
        f"[dbos_durable_exec] startup: enabled={is_enabled()} url={DBOS_DATABASE_URL}"
    )
    try:
        from dbos import DBOS, DBOSConfig
    except ImportError:
        emit_error(
            "[dbos_durable_exec] dbos package not installed; durable exec disabled."
        )
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
        emit_info(f"Initializing DBOS with database at: {DBOS_DATABASE_URL}")
        DBOS(config=dbos_config)
        DBOS.launch()
        emit_info("[dbos_durable_exec] DBOS.launch() completed successfully")
    except Exception as e:
        emit_error(
            f"[dbos_durable_exec] Error initializing DBOS: {e}\n{traceback.format_exc()}"
        )


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

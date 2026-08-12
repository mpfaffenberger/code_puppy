"""DBOS launch/destroy lifecycle, lifted from cli_runner.py."""

from __future__ import annotations

import os
import time
import traceback

from code_puppy import __version__ as current_version
from code_puppy.config import DATA_DIR
from code_puppy.messaging import emit_error, emit_info

from .config import _DEFAULT_SQLITE_FILE, DBOS_DATABASE_URL
from .startup_lock import enable_sqlite_wal, interprocess_lock

# Flipped True only after a successful DBOS.launch(). Other modules (wrapper/runtime)
# MUST check this — `dbos` importable != launched. Stays False in pytest (import w/o
# on_startup), so the wrapper passes through unmodified.
_LAUNCHED = False


def is_launched() -> bool:
    """True iff this plugin successfully called DBOS.launch()."""
    return _LAUNCHED


def on_startup() -> None:
    """Initialize and launch DBOS for durable execution."""
    global _LAUNCHED
    try:
        from dbos import DBOS, DBOSConfig
    except ImportError:
        # Shouldn't happen — hook only registers when dbos is importable; kept
        # defensive in case install state shifts between module-load and startup.
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
        # Multiple instances share one SQLite system DB; DBOS.launch() migration +
        # recovery take SQLite's single-writer lock, so racers collide unless serialized.
        # We: (1) flip to WAL (persistent) so concurrent access rarely blocks, and
        # (2) hold a cross-process file lock so launch/migration runs one process at a
        # time — late starters wait instead of crashing.
        if DBOS_DATABASE_URL.startswith("sqlite"):
            enable_sqlite_wal(_DEFAULT_SQLITE_FILE)
        launch_lock = os.path.join(DATA_DIR, "dbos_store.launch.lock")
        with interprocess_lock(launch_lock, timeout=60.0):
            DBOS(config=dbos_config)
            DBOS.launch()
        _LAUNCHED = True
    except Exception as e:
        emit_error(
            f"[dbos_durable_exec] Error initializing DBOS: {e}\n{traceback.format_exc()}"
        )


def on_shutdown() -> None:
    """Tear DBOS down. Best-effort, never raises."""
    global _LAUNCHED
    try:
        from dbos import DBOS
    except ImportError:
        return
    try:
        DBOS.destroy()
    except Exception:
        pass
    finally:
        _LAUNCHED = False

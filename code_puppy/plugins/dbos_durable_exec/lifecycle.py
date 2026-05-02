"""DBOS launch/destroy lifecycle, lifted from cli_runner.py."""

from __future__ import annotations

import os
import time
import traceback

from code_puppy import __version__ as current_version
from code_puppy.messaging import emit_error, emit_info

from .config import DBOS_DATABASE_URL

# Module-level flag flipped True only after a successful DBOS.launch().
# Other plugin modules (e.g. wrapper.py, runtime.py) MUST check this before
# attempting to use DBOS — having `dbos` importable is not the same as
# having DBOS launched. In test environments where the plugin is imported
# but on_startup() is never called (pytest process, not the spawned CLI),
# this stays False and the wrapper passes through unmodified.
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
        # Should not happen — register_callbacks.py only registers this hook
        # when dbos is importable. Kept defensive in case install state
        # changes between module-load and startup.
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

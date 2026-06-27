"""Entry point for running the FastAPI server."""

import logging
import os
import sys

import uvicorn

from code_puppy.api.app import create_app
from code_puppy.logging_setup import configure_backend_logging


def _resolve_log_level() -> tuple[int, str]:
    """Resolve env log levels to (backend_logging_level_int, uvicorn_level_str)."""
    raw = (
        (os.getenv("BACKEND_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "INFO")
        .strip()
        .upper()
    )
    level_int = getattr(logging, raw, logging.INFO)
    # Uvicorn wants lower-case level names
    uvicorn_level = (
        raw.lower()
        if raw.lower() in {"critical", "error", "warning", "info", "debug", "trace"}
        else "info"
    )
    return level_int, uvicorn_level


# Configure logging (honors BACKEND_LOG_* and LOG_LEVEL fallback)
_level_int, _uvicorn_level = _resolve_log_level()
try:
    _level_int = configure_backend_logging(level=_level_int)
except Exception as exc:
    print(
        f"[code_puppy.api.main] configure_backend_logging failed: {exc}",
        file=sys.stderr,
    )
    _fallback_handler = logging.StreamHandler(sys.stdout)
    _fallback_handler.setLevel(_level_int)
    _fallback_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.basicConfig(
        level=_level_int,
        handlers=[_fallback_handler],
        force=True,
    )

for name in [
    "code_puppy",
    "code_puppy.api",
    "code_puppy.api.websocket",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "httpx",
]:
    logging.getLogger(name).setLevel(_level_int)

app = create_app()


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the FastAPI server.

    Args:
        host: The host address to bind to. Defaults to localhost.
        port: The port number to listen on. Defaults to 8765.
    """
    # Force stdout to be unbuffered
    sys.stdout.reconfigure(line_buffering=True)

    if (os.getenv("DEBUG_IMPORTS") or "").strip() == "1":
        import code_puppy
        from code_puppy.agents import base_agent as _base_agent

        print("\n=== DEBUG_IMPORTS=1 ===", flush=True)
        print(f"code_puppy package: {code_puppy.__file__}", flush=True)
        print(f"base_agent module:  {_base_agent.__file__}", flush=True)
        print("sys.path (first 10):", flush=True)
        for p in sys.path[:10]:
            print(f"  - {p}", flush=True)
        print("=======================\n", flush=True)

    print(
        f"🐶 Starting Code Puppy API server (LOG_LEVEL={logging.getLevelName(_level_int)})...",
        flush=True,
    )
    uvicorn.run(app, host=host, port=port, log_level=_uvicorn_level)


if __name__ == "__main__":
    main()

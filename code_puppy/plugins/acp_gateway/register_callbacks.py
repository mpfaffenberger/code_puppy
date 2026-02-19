"""ACP Gateway plugin callbacks.

Starts the ACP agent during Code Puppy startup using the official
``agent-client-protocol`` SDK.  The SDK handles all transport concerns
(stdio JSON-RPC) — we just provide the CodePuppyAgent implementation.

Supports two modes:
  - stdio: ACP agent over stdin/stdout (default for subprocess orchestration)
  - http:  Reserved for future use (not yet implemented with new SDK)
"""

import asyncio
import logging
import threading

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

# Background thread reference for clean shutdown
_acp_thread: threading.Thread | None = None
_acp_shutdown_event: threading.Event | None = None


async def _start_stdio() -> None:
    """Start the ACP stdio agent in a background thread.

    The SDK's ``run_agent()`` blocks on stdin, so we run it in a
    daemon thread to avoid blocking Code Puppy's main loop.
    """
    global _acp_thread

    def _run() -> None:
        from code_puppy.plugins.acp_gateway.agent import run_code_puppy_agent

        asyncio.run(run_code_puppy_agent())

    _acp_thread = threading.Thread(
        target=_run,
        name="acp-gateway-stdio",
        daemon=True,
    )
    _acp_thread.start()

    logger.info("\U0001f436 ACP Gateway (stdio) started \u2014 reading from stdin")


async def _on_startup() -> None:
    """Start the ACP agent based on configured transport."""
    from code_puppy.plugins.acp_gateway.config import ACPConfig

    config = ACPConfig.from_env()

    if not config.enabled:
        logger.info("ACP Gateway is disabled via ACP_ENABLED=false")
        return

    try:
        import acp  # noqa: F401
    except ImportError:
        logger.warning(
            "agent-client-protocol is not installed \u2014 ACP Gateway disabled. "
            "Install it with: pip install agent-client-protocol"
        )
        return

    try:
        if config.transport == "stdio":
            await _start_stdio()
        else:
            # HTTP transport not yet implemented with the new SDK.
            # For now, fall back to stdio with a warning.
            logger.warning(
                "HTTP transport not yet implemented with agent-client-protocol SDK. "
                "Falling back to stdio transport."
            )
            await _start_stdio()
    except Exception:
        logger.exception("Failed to start ACP Gateway (%s)", config.transport)


async def _on_shutdown() -> None:
    """Stop the ACP background thread."""
    global _acp_thread, _acp_shutdown_event

    if _acp_shutdown_event is not None:
        logger.info("Shutting down ACP Gateway...")
        _acp_shutdown_event.set()

    if _acp_thread is not None and _acp_thread.is_alive():
        _acp_thread.join(timeout=5.0)
        logger.info("ACP Gateway stopped")


# ---------- Register with Code Puppy's callback system --------------------
register_callback("startup", _on_startup)
register_callback("shutdown", _on_shutdown)
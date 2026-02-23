"""ACP Gateway plugin callbacks.

Starts the ACP agent during Code Puppy startup using the official
``agent-client-protocol`` SDK.  The SDK handles all transport concerns
(stdio JSON-RPC) — we just provide the CodePuppyAgent implementation.

Supports two modes:
  - stdio: ACP agent over stdin/stdout (default for subprocess orchestration)
  - http:  Reserved for future use (not yet implemented with new SDK)
"""

from __future__ import annotations

import asyncio
import logging
import threading

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

# Background thread + event loop references for clean shutdown
_acp_thread: threading.Thread | None = None
_acp_loop: asyncio.AbstractEventLoop | None = None


async def _start_stdio() -> None:
    """Start the ACP stdio agent in a background thread.

    The SDK's ``run_agent()`` blocks on stdin, so we run it in a
    daemon thread with its own event loop.  We store the loop reference
    so ``_on_shutdown`` can stop it gracefully.
    """
    global _acp_thread, _acp_loop

    def _run() -> None:
        global _acp_loop
        _acp_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_acp_loop)
        try:
            from code_puppy.plugins.acp_gateway.agent import run_code_puppy_agent

            _acp_loop.run_until_complete(run_code_puppy_agent())
        except asyncio.CancelledError:
            logger.info("ACP Gateway event loop cancelled")
        finally:
            # Clean up pending tasks
            pending = asyncio.all_tasks(_acp_loop)
            for task in pending:
                task.cancel()
            if pending:
                _acp_loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            _acp_loop.close()
            logger.info("ACP Gateway event loop closed")

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

    # Install session-aware path resolution for multi-session CWD isolation
    from code_puppy.plugins.acp_gateway.session_context import install_session_aware_abspath
    install_session_aware_abspath()

    # Install concurrency gates for multi-session tool safety
    from code_puppy.plugins.acp_gateway.tool_concurrency import install_gates
    install_gates()

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
    """Stop the ACP background thread gracefully.

    Signals the background event loop to stop, cancels pending tasks,
    and waits for the thread to finish.
    """
    global _acp_thread, _acp_loop

    if _acp_loop is not None and _acp_loop.is_running():
        logger.info("Shutting down ACP Gateway...")
        # Schedule loop.stop() from the main thread into the ACP loop
        _acp_loop.call_soon_threadsafe(_acp_loop.stop)

    if _acp_thread is not None and _acp_thread.is_alive():
        _acp_thread.join(timeout=5.0)
        if _acp_thread.is_alive():
            logger.warning("ACP Gateway thread did not stop within 5s")
        else:
            logger.info("ACP Gateway stopped")


# ---------- Register with Code Puppy's callback system --------------------
register_callback("startup", _on_startup)
register_callback("shutdown", _on_shutdown)

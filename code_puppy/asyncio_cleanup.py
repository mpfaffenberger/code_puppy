"""Filters for harmless third-party errors emitted during asyncio shutdown."""

from __future__ import annotations

import asyncio
from typing import Any


_ASYNCGEN_SHUTDOWN_MESSAGE = (
    "an error occurred during closing of asynchronous generator"
)
_HTTP_CORE_SHUTDOWN_ERRORS = {
    "aclose(): asynchronous generator is already running",
    "generator didn't stop after athrow()",
}
_HANDLER_MARKER = "_code_puppy_httpcore2_shutdown_filter"


def _is_httpcore2_shutdown_noise(context: dict[str, Any]) -> bool:
    """Return whether *context* is the known httpcore2 asyncgen cleanup race."""
    message = context.get("message", "")
    exception = context.get("exception")
    asyncgen = context.get("asyncgen")

    if not isinstance(message, str) or not message.startswith(
        _ASYNCGEN_SHUTDOWN_MESSAGE
    ):
        return False
    if not isinstance(exception, RuntimeError):
        return False
    if str(exception) not in _HTTP_CORE_SHUTDOWN_ERRORS:
        return False

    code = getattr(asyncgen, "ag_code", None)
    filename = getattr(code, "co_filename", "")
    if not isinstance(filename, str):
        return False
    normalized_filename = filename.replace("\\", "/")
    return "/httpcore2/" in normalized_filename


def install_httpcore2_shutdown_filter() -> None:
    """Silence a harmless httpcore2 finalizer race without hiding other errors.

    Python closes all remaining asynchronous generators when ``asyncio.run()``
    tears down its loop. A partially consumed httpcore2 response has nested
    generators which may then close concurrently. The parent and child both
    try to close the same iterator, producing a scary traceback after Code
    Puppy has otherwise exited successfully.

    Keep the filter deliberately narrow and delegate every other event to the
    handler that was installed before this one, or asyncio's default handler.
    """
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    if getattr(previous_handler, _HANDLER_MARKER, False):
        return

    def handler(
        event_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        if _is_httpcore2_shutdown_noise(context):
            return
        if previous_handler is not None:
            previous_handler(event_loop, context)
        else:
            event_loop.default_exception_handler(context)

    setattr(handler, _HANDLER_MARKER, True)
    loop.set_exception_handler(handler)

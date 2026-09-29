"""Tests for narrowly filtering known asyncio shutdown noise."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from code_puppy.asyncio_cleanup import install_httpcore2_shutdown_filter


def _context(
    *,
    message: str = "an error occurred during closing of asynchronous generator <agen>",
    error: BaseException | None = None,
    filename: str = "/venv/site-packages/httpcore2/_async/connection_pool.py",
) -> dict:
    asyncgen = SimpleNamespace(ag_code=SimpleNamespace(co_filename=filename))
    return {
        "message": message,
        "exception": error or RuntimeError("generator didn't stop after athrow()"),
        "asyncgen": asyncgen,
    }


def _install_on(loop: MagicMock):
    with patch(
        "code_puppy.asyncio_cleanup.asyncio.get_running_loop", return_value=loop
    ):
        install_httpcore2_shutdown_filter()
    return loop.set_exception_handler.call_args.args[0]


def _previous_handler() -> MagicMock:
    handler = MagicMock()
    setattr(handler, "_code_puppy_httpcore2_shutdown_filter", False)
    return handler


def test_silences_known_httpcore2_asyncgen_errors():
    previous_handler = _previous_handler()
    loop = MagicMock()
    loop.get_exception_handler.return_value = previous_handler
    handler = _install_on(loop)

    for error_message in (
        "generator didn't stop after athrow()",
        "aclose(): asynchronous generator is already running",
    ):
        handler(loop, _context(error=RuntimeError(error_message)))

    previous_handler.assert_not_called()
    loop.default_exception_handler.assert_not_called()


def test_delegates_unrelated_errors_to_existing_handler():
    previous_handler = _previous_handler()
    loop = MagicMock()
    loop.get_exception_handler.return_value = previous_handler
    handler = _install_on(loop)
    context = _context(error=ValueError("real bug"))

    handler(loop, context)

    previous_handler.assert_called_once_with(loop, context)


def test_requires_httpcore2_generator_source():
    previous_handler = _previous_handler()
    loop = MagicMock()
    loop.get_exception_handler.return_value = previous_handler
    handler = _install_on(loop)
    context = _context(filename="/project/our_code.py")

    handler(loop, context)

    previous_handler.assert_called_once_with(loop, context)


def test_uses_default_handler_when_no_handler_was_installed():
    loop = MagicMock()
    loop.get_exception_handler.return_value = None
    handler = _install_on(loop)
    context = _context(message="Task exception was never retrieved")

    handler(loop, context)

    loop.default_exception_handler.assert_called_once_with(context)


def test_delegates_malformed_context_instead_of_crashing():
    previous_handler = _previous_handler()
    loop = MagicMock()
    loop.get_exception_handler.return_value = previous_handler
    handler = _install_on(loop)
    context = {"message": None}

    handler(loop, context)

    previous_handler.assert_called_once_with(loop, context)


def test_install_is_idempotent():
    loop = MagicMock()
    existing_handler = MagicMock()
    setattr(existing_handler, "_code_puppy_httpcore2_shutdown_filter", True)
    loop.get_exception_handler.return_value = existing_handler

    with patch(
        "code_puppy.asyncio_cleanup.asyncio.get_running_loop", return_value=loop
    ):
        install_httpcore2_shutdown_filter()

    loop.set_exception_handler.assert_not_called()

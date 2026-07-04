"""herdr integration -- report code-puppy's state to a herdr pane.

This built-in plugin is a no-op unless code-puppy is running inside a
`herdr <https://herdr.dev>`_ pane (detected via the ``HERDR_ENV`` /
``HERDR_SOCKET_PATH`` / ``HERDR_PANE_ID`` environment variables herdr
injects). When it is, it reports semantic agent state -- ``working`` /
``blocked`` / ``idle`` -- over herdr's local socket so herdr's sidebar
can roll code-puppy up alongside every other agent in the fleet.

Because the integration ships with code-puppy and self-activates, there
is nothing to install on the herdr side: ``herdr integration install``
is not needed for code-puppy.

Callback -> state mapping (see reporter.py for the arbitration rules):

* ``startup`` / ``session_end`` / ``shutdown`` .......... idle
* ``user_prompt_submit`` / ``agent_run_start`` ......... working
* ``pre_tool_call`` (non-ask) / ``post_tool_call`` ..... working
* ``pre_tool_call`` (ask_user_question) / permission ... blocked
* ``interactive_turn_end`` / ``interactive_turn_cancel`` idle
* ``agent_run_cancel`` ................................. idle
* ``agent_run_end`` ................................... idle (depth 0)

Handlers are plain sync functions that swallow every argument: the
callback dispatcher passes hook args positionally and runs sync
callbacks happily from both async and worker-thread contexts, so
signature-proofing with ``*args`` is the robust choice.
"""

from __future__ import annotations

import logging

from code_puppy.callbacks import register_callback

from .client import HerdrClient
from .reporter import HerdrReporter

logger = logging.getLogger(__name__)

_client = HerdrClient()
_reporter = HerdrReporter(_client)


def _arg(args: tuple, index: int):
    return args[index] if len(args) > index else None


def _on_startup(*_args, **_kw) -> None:
    _reporter.on_startup()


def _on_user_prompt(*args, **_kw) -> None:
    # (prompt, session_id=None)
    _reporter.on_user_prompt(_arg(args, 1))


def _on_run_start(*args, **_kw) -> None:
    # (agent_name, model_name, session_id=None)
    _reporter.on_run_start(_arg(args, 2))


def _on_run_end(*args, **_kw) -> None:
    # (agent_name, model_name, session_id=None, ...)
    _reporter.on_run_end(_arg(args, 2))


def _on_run_cancel(*_args, **_kw) -> None:
    _reporter.on_run_cancel()


def _on_turn_end(*_args, **_kw) -> None:
    _reporter.on_turn_end()


def _on_pre_tool_call(*args, **_kw) -> None:
    # (tool_name, tool_args, context=None)
    tool_name = _arg(args, 0) or ""
    _reporter.on_tool_call(str(tool_name))


def _on_post_tool_call(*_args, **_kw) -> None:
    _reporter.on_tool_done()


def _on_file_permission(*_args, **_kw):
    # SYNC callback. code-puppy treats every non-None result as a
    # grant/deny vote (``any(not r for r in results if r is not None)``),
    # so we MUST return None -- we only observe, never veto.
    _reporter.on_permission_prompt()
    return None


def _on_shutdown(*_args, **_kw) -> None:
    _reporter.on_shutdown()


if _reporter.active:
    register_callback("startup", _on_startup)
    register_callback("user_prompt_submit", _on_user_prompt)
    register_callback("agent_run_start", _on_run_start)
    register_callback("agent_run_end", _on_run_end)
    register_callback("agent_run_cancel", _on_run_cancel)
    register_callback("interactive_turn_end", _on_turn_end)
    register_callback("interactive_turn_cancel", _on_turn_end)
    register_callback("pre_tool_call", _on_pre_tool_call)
    register_callback("post_tool_call", _on_post_tool_call)
    register_callback("file_permission", _on_file_permission)
    register_callback("session_end", _on_shutdown)
    register_callback("shutdown", _on_shutdown)
    logger.debug("herdr plugin active for pane %s", _client._pane_id)
else:
    logger.debug("herdr plugin inactive (not running inside a herdr pane)")


__all__ = ["HerdrClient", "HerdrReporter"]

"""herdr integration -- report code-puppy's state to a herdr pane.

This built-in plugin is a no-op unless code-puppy is running inside a
`herdr <https://herdr.dev>`_ pane (detected via the ``HERDR_ENV`` /
``HERDR_SOCKET_PATH`` / ``HERDR_PANE_ID`` environment variables herdr
injects). When it is, it reports semantic agent state -- ``working`` /
``blocked`` / ``idle`` -- over herdr's local socket so herdr's sidebar
can roll code-puppy up alongside every other agent in the fleet.

code-puppy reports its state **authoritatively**: herdr never infers it from
the screen. State is a pure function of two facts the plugin observes
directly (see reporter.py):

* run depth, from ``agent_run_start`` / ``agent_run_end`` -> ``working``
* awaiting-human, from the ``awaiting_user_input`` callback -> ``blocked``

The ``awaiting_user_input`` callback is the key: it fires from the single
process-wide choke-point (``command_runner.set_awaiting_user_input``) that
*every* interactive wait already passes through -- shell-command approval,
file-permission approval, ``ask_user_question``, and every menu/picker -- so
one hook captures every block. There is no per-prompt special-casing and
nothing for herdr to guess.

Callback -> effect:

* ``startup`` / ``session_end`` / ``shutdown`` ......... resync (-> idle)
* ``user_prompt_submit`` .............................. capture session id
* ``agent_run_start`` / ``agent_run_end`` ............. run-depth +/- 1
* ``agent_run_cancel`` / ``interactive_turn_end`` ..... reset -> idle
* ``interactive_turn_cancel`` ......................... reset -> idle
* ``awaiting_user_input`` ............................. blocked <-> not

Handlers are plain sync functions that swallow every argument: the callback
dispatcher passes hook args positionally and runs sync callbacks happily
from both async and worker-thread contexts, so ``*args`` is the robust
choice.
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


def _on_awaiting_user_input(*args, **_kw) -> None:
    # (awaiting: bool)
    _reporter.on_awaiting_user_input(bool(_arg(args, 0)))


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
    register_callback("awaiting_user_input", _on_awaiting_user_input)
    register_callback("session_end", _on_shutdown)
    register_callback("shutdown", _on_shutdown)
    logger.debug("herdr plugin active for pane %s", _client._pane_id)
else:
    logger.debug("herdr plugin inactive (not running inside a herdr pane)")


__all__ = ["HerdrClient", "HerdrReporter"]

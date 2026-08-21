"""Opt-in Logfire observability wiring.

Code Puppy ships with zero telemetry. Setting ``enable_logfire`` (via
``/set enable_logfire true`` or the ``CODE_PUPPY_ENABLE_LOGFIRE`` env var)
opts the *user* into sending their own traces to their own Logfire
project. Even then, nothing leaves the machine unless a Logfire write
token is present (``LOGFIRE_TOKEN`` or a prior ``logfire auth``) --
``send_to_logfire="if-token-present"`` guarantees that.

``logfire`` is a hard dependency, but everything here still fails soft --
a broken install must degrade to "no telemetry", never to a dead CLI.
"""

from __future__ import annotations

import os

from code_puppy.config import get_enable_logfire

_TRUTHY = ("1", "true", "yes", "on")
_logfire_active = False


def logfire_opted_in() -> bool:
    """Return whether the user opted into Logfire instrumentation.

    The ``CODE_PUPPY_ENABLE_LOGFIRE`` env var wins over the persisted
    ``enable_logfire`` config key so headless/CI runs can opt in without
    touching ``puppy.cfg``.
    """
    env = os.environ.get("CODE_PUPPY_ENABLE_LOGFIRE", "").strip().lower()
    if env in _TRUTHY:
        return True
    return get_enable_logfire()


def configure_logfire() -> bool:
    """Configure Logfire and instrument pydantic-ai when opted in.

    Returns True when instrumentation is live. A missing package or a
    misconfiguration must never break the CLI, so every failure path
    emits a warning and returns False instead of raising.
    """
    global _logfire_active
    _logfire_active = False

    if not logfire_opted_in():
        return False

    from code_puppy.i18n import t
    from code_puppy.messaging import emit_system_message, emit_warning

    try:
        import logfire
    except ImportError:
        emit_warning(t("logfire.missing_package"))
        return False

    try:
        logfire.configure(
            service_name="code-puppy",
            send_to_logfire="if-token-present",
            console=False,
        )
        logfire.instrument_pydantic_ai()
    except Exception as exc:
        emit_warning(t("logfire.configure_failed", error=str(exc)))
        return False

    _logfire_active = True
    emit_system_message(t("logfire.enabled"))
    return True


def emit_cancellation(group_id: str) -> None:
    """Emit an agent cancellation event when Logfire is active."""
    if not _logfire_active:
        return

    try:
        import logfire

        logfire.info("Agent run cancelled", group_id=group_id)
    except Exception:
        # Observability must never interfere with cancelling an agent run.
        return

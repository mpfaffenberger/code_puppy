"""Session model selection + config options exposed to the ACP client.

Everything is delivered as ACP **config options** (``session/set_config_option``)
-- clients (Zed, opencode, oh-my-pi) bind each bottom-bar dropdown to a config
option by its ``category``, so this is the shape that actually populates them:

* **Model picker** — a ``select`` option tagged ``category="model"``:
  ``{id: "model", category: "model", type: "select", ...}``. Backed by
  ``model_picker_completion.load_model_names`` + ``config.get_global_model_name``
  / ``set_model_name``. Changing it rebinds the live session's model.
* **Mode picker** — a ``select`` option tagged ``category="mode"``. Code Puppy
  has exactly one operating mode, so this is a single "Default" entry; we still
  send it so the client's mode dropdown reads "Default" instead of an empty
  "Unknown" control. (ACP's top-level ``SessionModeState`` is a *different*
  mechanism that Zed 1.7.2 does not bind that dropdown to -- config options are
  what work across clients.)
* **Streaming toggle** — an On/Off ``select`` option. (A boolean option would
  be more natural, but Zed 1.7.2 renders only ``select`` options in its bottom
  bar -- a boolean shows as "Unknown" -- so every control here is a select.) We
  deliberately expose only this safe setting; we do **not** expose a
  yolo/approval-bypass toggle (permissions must stay client-driven).

All accessors are best-effort and degrade to "nothing to offer" on error.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from acp.schema import (
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
)

logger = logging.getLogger(__name__)

# Config-option ids. ``MODEL_OPTION_ID`` is public because ``agent.py`` keys
# its "rebind the live model" behaviour off it.
MODEL_OPTION_ID = "model"
MODE_OPTION_ID = "mode"
_STREAMING_ID = "enable_streaming"
_STREAMING_ON = "on"
_STREAMING_OFF = "off"

# Code Puppy has exactly one operating mode. We still advertise it as a
# category="mode" select so the client's mode dropdown shows "Default" rather
# than an empty "Unknown" control. (Model selection is the separate
# category="model" option; ACP clients bind each dropdown to its category.)
_DEFAULT_MODE_ID = "default"


def _mode_option() -> SessionConfigOptionSelect:
    """Advertise Code Puppy's single "Default" mode as a category=mode select.

    There is nothing to switch between, but a one-item option keeps the
    client's mode dropdown meaningful instead of blank.
    """
    return SessionConfigOptionSelect(
        id=MODE_OPTION_ID,
        name="Mode",
        category="mode",
        type="select",
        current_value=_DEFAULT_MODE_ID,
        options=[
            SessionConfigSelectOption(
                value=_DEFAULT_MODE_ID,
                name="Default",
                description="Standard Code Puppy session",
            )
        ],
    )


def _model_choices() -> Tuple[List[str], Optional[str]]:
    """Return ``(available_model_names, current_selection)`` from config.

    ``current`` is coerced into the available list so a picker always has a
    valid selection. Returns ``([], None)`` when there are no models to offer.
    """
    from code_puppy.command_line.model_picker_completion import load_model_names
    from code_puppy.config import get_global_model_name

    names = list(load_model_names() or [])
    if not names:
        return [], None
    current = get_global_model_name()
    return names, (current if current in names else names[0])


def _model_option() -> Optional[SessionConfigOptionSelect]:
    """Build the model picker as a ``category="model"`` select option.

    Returns ``None`` when there are no models to offer.
    """
    names, current = _model_choices()
    if not names or current is None:
        return None
    return SessionConfigOptionSelect(
        id=MODEL_OPTION_ID,
        name="Model",
        category="model",
        type="select",
        current_value=current,
        options=[SessionConfigSelectOption(value=n, name=n) for n in names],
    )


def set_model(model_id: str) -> bool:
    """Switch the active model. Returns ``True`` on success."""
    try:
        from code_puppy.config import set_model_name

        set_model_name(model_id)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("ACP: set_model failed", exc_info=True)
        return False


def config_options() -> List[Any]:
    """Build the config-option list for a session (model picker + streaming).

    Order matters for presentation: the model picker leads. Either entry is
    omitted if it can't be built, so a config hiccup never sinks the session.
    """
    opts: List[Any] = []
    try:
        model_opt = _model_option()
        if model_opt is not None:
            opts.append(model_opt)
    except Exception:  # noqa: BLE001
        logger.debug("ACP: could not build model option", exc_info=True)
    try:
        opts.append(_mode_option())
    except Exception:  # noqa: BLE001
        logger.debug("ACP: could not build mode option", exc_info=True)
    try:
        from code_puppy.config import get_enable_streaming

        # A select (On/Off), not a boolean: Zed 1.7.2 only renders select-type
        # config options in its bottom bar; a boolean shows as "Unknown".
        opts.append(
            SessionConfigOptionSelect(
                id=_STREAMING_ID,
                name="Streaming responses",
                type="select",
                current_value=_STREAMING_ON
                if get_enable_streaming()
                else _STREAMING_OFF,
                options=[
                    SessionConfigSelectOption(value=_STREAMING_ON, name="On"),
                    SessionConfigSelectOption(value=_STREAMING_OFF, name="Off"),
                ],
                description="Stream model output token-by-token.",
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug("ACP: could not build streaming option", exc_info=True)
    return opts


def apply_config_option(config_id: str, value: Any) -> List[Any]:
    """Apply a config-option change and return the refreshed option list."""
    try:
        if config_id == MODEL_OPTION_ID:
            set_model(str(value))
        elif config_id == _STREAMING_ID:
            from code_puppy.config import set_config_value

            set_config_value("enable_streaming", "true" if _as_bool(value) else "false")
    except Exception:  # noqa: BLE001
        logger.debug("ACP: apply_config_option failed", exc_info=True)
    return config_options()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")

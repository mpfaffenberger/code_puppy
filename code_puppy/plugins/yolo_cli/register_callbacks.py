"""Runtime-only ``--yolo true|false`` CLI override."""

from __future__ import annotations

import argparse
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.config import set_yolo_mode_override


def _parse_boolean(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError(
        f"invalid boolean value: {value!r} (expected 'true' or 'false')"
    )


def _register_cli_args(parser: Any) -> None:
    parser.add_argument(
        "--yolo",
        type=_parse_boolean,
        default=None,
        metavar="{true,false}",
        help=(
            "Enable or disable YOLO mode for this run; overrides puppy.cfg "
            "without changing it (accepted values: true, false)"
        ),
    )


def _handle_cli_args(args: Any) -> None:
    value = getattr(args, "yolo", None)
    if value is not None:
        set_yolo_mode_override(value)
    return None


register_callback("register_cli_args", _register_cli_args)
register_callback("handle_cli_args", _handle_cli_args)

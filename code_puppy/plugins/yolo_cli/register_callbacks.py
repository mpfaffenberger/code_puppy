"""Expose a runtime-only YOLO override through the CLI."""

from __future__ import annotations

import argparse
from typing import Any, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import set_cli_yolo_override


def _parse_bool(value: str) -> bool:
    """Parse the explicit boolean syntax used by ``--yolo``."""
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected 'true' or 'false'")


def _register_cli_args(parser: Any) -> None:
    parser.add_argument(
        "--yolo",
        type=_parse_bool,
        default=None,
        metavar="{true,false}",
        help=(
            "Override YOLO mode for this run without changing puppy.cfg "
            "(/set yolo_mode takes precedence)"
        ),
    )


def _handle_cli_args(args: Any) -> Optional[dict]:
    set_cli_yolo_override(getattr(args, "yolo", None))
    return None


register_callback("register_cli_args", _register_cli_args)
register_callback("handle_cli_args", _handle_cli_args)

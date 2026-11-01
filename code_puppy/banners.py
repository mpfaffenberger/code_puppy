"""Banner contract: one definition per tool call, tool result or plugin notice.

The terminal renders a ``Banner`` as Rich markup and ACP sends ``to_wire()``,
so titles and labels cannot drift between the two. Wire names are fixed by the
ACP-05 spec; keep ``Banner.to_wire`` keys in sync with it.

Depends on: config.get_banner_color() for the terminal colour; i18n.t() for labels.
Called by: tools and plugins via banner_for_call / banner_for_result / emit_notice.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from rich.markup import escape

from code_puppy import config
from code_puppy.i18n import t

logger = logging.getLogger(__name__)

_TARGET_LIMIT = 60
_SUMMARY_LIMIT = 300
_BUILTINS_MODULE = "code_puppy.banner_defs"


@dataclass(frozen=True)
class Banner:
    event: str
    name: str
    label: str
    kind: str
    title: str
    target: str | None = None
    target_type: str | None = None
    status: str | None = None
    details: str | None = None
    error: str | None = None
    duration_ms: float | None = None
    exit_code: int | None = None
    v: int = 1

    def to_wire(self) -> dict[str, Any]:
        wire = {
            "v": self.v,
            "event": self.event,
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "title": self.title,
            "target": self.target,
            "targetType": self.target_type,
            "status": self.status,
            "details": self.details,
            "error": self.error,
            "durationMs": self.duration_ms,
            "exitCode": self.exit_code,
        }
        return {key: value for key, value in wire.items() if value is not None}

    def to_markup(self) -> str:
        # Mirrors RichConsoleRenderer._format_banner byte-for-byte so terminal output
        # does not change when banners are sourced from this contract.
        color = config.get_banner_color(self.name)
        markup = (
            f"[bold white on {color}] {escape(self.label)} [/bold white on {color}]"
        )
        if self.target:
            markup += f" {escape(self.target)}"
        if self.event == "plugin_notice" and self.details:
            markup += f" [dim]{escape(self.details)}[/dim]"
        return markup


@dataclass(frozen=True)
class BannerDef:
    name: str
    label: str
    kind: str
    target_args: tuple[str, ...] = ()
    target_type: str | None = None
    label_key: str | None = None

    def resolved_label(self) -> str:
        return t(self.label_key) if self.label_key else self.label


_definitions: dict[str, BannerDef] = {}
_builtins_loaded = False


def register_banner_def(tool_name: str, definition: BannerDef) -> None:
    _definitions[tool_name] = definition


def _ensure_builtins() -> None:
    # Lazy: banner_defs registers through this module, so a top-level import would cycle.
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    try:
        from code_puppy import banner_defs
    except ImportError:
        logger.debug("%s unavailable; using fallback banners", _BUILTINS_MODULE)
        return
    banner_defs.register_builtin_banner_defs()


def get_banner_def(tool_name: str) -> BannerDef:
    _ensure_builtins()
    return _definitions.get(
        tool_name,
        BannerDef(name=tool_name, label=tool_name.upper(), kind="other"),
    )


def has_banner_def(tool_name: str) -> bool:
    _ensure_builtins()
    return tool_name in _definitions


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _display_target(target: str, target_type: str | None) -> str:
    if target_type == "path":
        return _cut(os.path.basename(target) or target, _TARGET_LIMIT)
    if target_type == "command":
        lines = target.strip().splitlines()
        first_line = lines[0] if lines else ""
        return _cut(first_line, _TARGET_LIMIT)
    return _cut(target, _TARGET_LIMIT)


def _title(label: str, target: str | None, target_type: str | None) -> str:
    if not target:
        return label
    display = _display_target(target, target_type)
    return f"{label} {display}" if display else label


def _first_target(definition: BannerDef, tool_args: Any) -> str | None:
    args = tool_args if isinstance(tool_args, dict) else {}
    for key in definition.target_args:
        value = args.get(key)
        if value is not None and str(value):
            return str(value)
    return None


def _tool_banner(event: str, tool_name: str, tool_args: Any, **fields: Any) -> Banner:
    try:
        definition = get_banner_def(tool_name)
        label = definition.resolved_label()
        target = _first_target(definition, tool_args)
        return Banner(
            event=event,
            name=definition.name,
            label=label,
            kind=definition.kind,
            title=_title(label, target, definition.target_type),
            target=target,
            target_type=definition.target_type,
            **fields,
        )
    except Exception:
        logger.debug("banner build failed for %s", tool_name, exc_info=True)
        return Banner(
            event=event,
            name=tool_name,
            label=tool_name.upper(),
            kind="other",
            title=tool_name.upper(),
            **fields,
        )


def banner_for_call(tool_name: str, tool_args: Any) -> Banner:
    return _tool_banner("tool_call", tool_name, tool_args, status="in_progress")


def banner_for_result(
    tool_name: str, tool_args: Any, result: Any, duration_ms: float | None = None
) -> Banner:
    status, error = result_status(result)
    return _tool_banner(
        "tool_result",
        tool_name,
        tool_args,
        status=status,
        error=error,
        duration_ms=duration_ms,
        exit_code=_exit_code(result),
    )


def notice(
    name: str,
    label: str,
    *,
    details: str | None = None,
    target: str | None = None,
) -> Banner:
    target_type = "text" if target else None
    return Banner(
        event="plugin_notice",
        name=name,
        label=label,
        kind="other",
        title=_title(label, target, target_type),
        target=target,
        target_type=target_type,
        status="info",
        details=details,
    )


def emit_notice(banner: Banner) -> None:
    # Two independent steps: a failing terminal must not hide the callback, and the reverse.
    try:
        from rich.text import Text

        from code_puppy.messaging.message_queue import emit_info

        emit_info(Text.from_markup(banner.to_markup()))
    except Exception:
        logger.debug("banner terminal render failed", exc_info=True)
    try:
        from code_puppy import callbacks

        callbacks.on_banner_notice(banner.to_wire())
    except Exception:
        logger.debug("banner_notice callbacks failed", exc_info=True)


def _field(result: Any, key: str) -> Any:
    try:
        if isinstance(result, dict):
            return result.get(key)
        return getattr(result, key, None)
    except Exception:
        return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _exit_code(result: Any) -> int | None:
    value = _field(result, "exit_code")
    return value if _is_int(value) else None


def _exception_text(error: BaseException) -> str:
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _one_line(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return _cut(first, _SUMMARY_LIMIT)


def _failure_summary(result: Any) -> str:
    error = _field(result, "error")
    if error:
        return _one_line(str(error))
    stderr_lines = [
        line.strip() for line in str(_field(result, "stderr") or "").splitlines()
    ]
    stderr_lines = [line for line in stderr_lines if line]
    if stderr_lines:
        return _one_line(stderr_lines[-1])
    exit_code = _exit_code(result)
    if exit_code:
        return f"exit code {exit_code}"
    if _field(result, "timeout") is True:
        return "timed out"
    return "tool reported failure"


def _classify(result: Any) -> tuple[str, str | None]:
    if isinstance(result, BaseException):
        return "failed", _one_line(_exception_text(result))
    if _field(result, "error"):
        return "failed", _failure_summary(result)
    if _field(result, "success") is False:
        return "failed", _failure_summary(result)
    exit_code = _exit_code(result)
    if exit_code is not None and exit_code != 0:
        return "failed", _failure_summary(result)
    if _field(result, "timeout") is True:
        return "failed", _failure_summary(result)
    return "completed", None


def result_status(result: Any) -> tuple[str, str | None]:
    try:
        return _classify(result)
    except Exception:
        logger.debug("result_status failed", exc_info=True)
        return "completed", None


def _result_body(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, BaseException):
        return _exception_text(result)
    if isinstance(result, BaseModel):
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, default=str)
    return str(result)


def result_text(result: Any, limit: int = 4000) -> str:
    try:
        body = _result_body(result)
        status, summary = result_status(result)
        if status == "failed" and summary:
            if not body:
                body = summary
            elif body != summary:
                body = f"{summary}\n\n{body}"
        return _cut(body, limit)
    except Exception:
        logger.debug("result_text failed", exc_info=True)
        try:
            return repr(result)
        except Exception:
            return ""

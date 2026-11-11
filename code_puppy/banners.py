"""Banner contract: one definition per tool call, tool result or plugin notice.

The terminal renders a ``Banner`` as Rich markup and ACP sends ``to_wire()``,
so titles and labels cannot drift between the two. Wire names are the contract
with ACP clients; keep ``Banner.to_wire`` keys in sync with the ACP plugin
(``code_puppy_core_plugins/acp/README.md``).

Depends on: config.get_banner_color() for the terminal colour; i18n.t() for labels.
Called by: tools and plugins via banner_for_call / banner_for_result / emit_notice.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from rich.markup import escape

from code_puppy import config
from code_puppy.i18n import t

logger = logging.getLogger(__name__)

_TARGET_LIMIT = 60
_SUMMARY_LIMIT = 300


def banner_markup(color: str, text: str) -> str:
    """Rich markup for a banner label; ``text`` must already be escaped."""
    return f"[bold white on {color}] {text} [/bold white on {color}]"


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
        # Label, target and details are rich-escaped: they may be plugin text.
        markup = banner_markup(config.get_banner_color(self.name), escape(self.label))
        if self.target:
            display = _display_target(self.target, self.target_type)
            markup += f" {escape(display)}"
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
_builtins_loading = False
_builtins_lock = threading.RLock()


def register_banner_def(tool_name: str, definition: BannerDef) -> None:
    # Load builtins first so a plugin's explicit def is never overwritten by a later lazy load.
    _ensure_builtins()
    _definitions[tool_name] = definition


def _ensure_builtins() -> None:
    # Lazy: banner_defs registers through this module, so a top-level import would cycle.
    global _builtins_loaded, _builtins_loading
    if _builtins_loaded:
        return
    # Other threads wait on the lock until the registry is complete. The loading flag
    # stops same-thread re-entry from register_banner_def; a failure leaves both flags
    # unset so every lookup retries and raises instead of silently falling back.
    with _builtins_lock:
        if _builtins_loaded or _builtins_loading:
            return
        _builtins_loading = True
        try:
            from code_puppy import banner_defs

            banner_defs.register_builtin_banner_defs()
            _builtins_loaded = True
        finally:
            _builtins_loading = False


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
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _report_failure(error: Exception, context: str) -> None:
    """Record an unexpected banner failure in errors.log; callers keep their fallback.

    Use for true exceptions only; expected probing stays at DEBUG. ``context`` must be
    static: never put tool arguments or results in it.
    """
    logger.debug("%s failed", context, exc_info=True)
    try:
        from code_puppy.error_logging import log_error

        log_error(error, context=context)
    except Exception:
        logger.debug("banner failure could not be logged", exc_info=True)


def _display_target(target: str, target_type: str | None) -> str:
    lines = target.strip().splitlines()
    first_line = lines[0] if lines else ""
    if target_type == "path":
        first_line = os.path.basename(first_line) or first_line
    return _cut(first_line, _TARGET_LIMIT)


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
    except Exception as error:
        _report_failure(error, "code_puppy.banners::_tool_banner")
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
    except Exception as error:
        _report_failure(error, "code_puppy.banners::emit_notice terminal render")
    try:
        from code_puppy import callbacks

        callbacks.on_banner_notice(banner.to_wire())
    except Exception as error:
        _report_failure(error, "code_puppy.banners::emit_notice banner_notice phase")


def _field(result: Any, key: str) -> Any:
    try:
        if isinstance(result, dict):
            return result.get(key)
        return getattr(result, key, None)
    except Exception:
        return None


def _error_field(result: Any) -> Any:
    # An `error` method (a Logger, SDK response objects) is not a failure marker.
    error = _field(result, "error")
    return None if callable(error) else error


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


def _last_stderr_line(result: Any) -> str:
    lines = [line.strip() for line in str(_field(result, "stderr") or "").splitlines()]
    return next((line for line in reversed(lines) if line), "")


def _failure_summary(result: Any) -> str:
    # Checked before `error`: shell tools put boilerplate in `error` for non-zero exits.
    exit_code = _exit_code(result)
    stderr_line = _last_stderr_line(result)
    if exit_code is not None and exit_code != 0:
        summary = f"exit code {exit_code}"
        return _cut(
            f"{summary}: {stderr_line}" if stderr_line else summary, _SUMMARY_LIMIT
        )
    error = _error_field(result)
    if error:
        return _one_line(str(error))
    if stderr_line:
        return _cut(stderr_line, _SUMMARY_LIMIT)
    if _field(result, "timeout") is True:
        return "timed out"
    return "tool reported failure"


def _classify(result: Any) -> tuple[str, str | None]:
    if isinstance(result, BaseException):
        return "failed", _one_line(_exception_text(result))
    if _error_field(result):
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
    except Exception as error:
        _report_failure(error, "code_puppy.banners::result_status")
        if isinstance(result, BaseException):
            return "failed", type(result).__name__
        return "completed", None


def _has_field(result: Any, key: str) -> bool:
    if isinstance(result, dict):
        return key in result
    try:
        return hasattr(result, key)
    except Exception:
        return False


def _match_lines(matches: Any) -> list[str]:
    if not isinstance(matches, (list, tuple)):
        return []
    lines = []
    for row in matches:
        path = _field(row, "file_path")
        if not isinstance(path, str) or not path:
            continue
        text = _field(row, "line_content")
        lines.append(f"{path}:{_field(row, 'line_number')}: {text or ''}")
    return lines


def _readable_body(result: Any) -> str:
    parts = []
    content = _field(result, "content")
    if isinstance(content, str) and content:
        parts.append(content)
    stdout = _field(result, "stdout")
    if isinstance(stdout, str) and stdout.rstrip("\n"):
        parts.append(stdout.rstrip("\n"))
    stderr = _field(result, "stderr")
    if isinstance(stderr, str) and stderr.rstrip("\n"):
        parts.append("stderr:\n" + stderr.rstrip("\n"))
    match_lines = _match_lines(_field(result, "matches"))
    if match_lines:
        parts.append("\n".join(match_lines))
    return "\n".join(parts)


def _json_fallback(result: Any) -> str:
    data = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    if isinstance(data, dict):
        data = {key: value for key, value in data.items() if key != "error"}
        if not data:
            return ""
    return json.dumps(data, ensure_ascii=False, default=str)


_READABLE_FIELDS = ("content", "stdout", "stderr", "matches")


def _result_body(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, BaseException):
        return _exception_text(result)
    if any(_has_field(result, key) for key in _READABLE_FIELDS):
        return _readable_body(result)
    if isinstance(result, (dict, list, BaseModel)):
        return _json_fallback(result)
    return str(result)


def result_text(result: Any, limit: int = 4000) -> str:
    try:
        body = _result_body(result)
        status, summary = result_status(result)
        if status == "failed" and summary:
            if not body:
                body = summary
            elif not body.startswith(summary):
                body = f"{summary}\n\n{body}"
        return _cut(body, limit)
    except Exception as error:
        _report_failure(error, "code_puppy.banners::result_text")
        try:
            return _cut(repr(result), limit)
        except Exception:
            return ""

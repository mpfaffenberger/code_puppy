"""Per-server MCP capability wiring.

Turns a server's ``capabilities`` config block into ``MCPToolset`` kwargs.

Sampling and elicitation are out of scope: they are server-initiated requests
needing an open back-channel, and carry a consent and UI surface this does not.
Everything here is a one-way notification or handshake data.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy.mcp_.mcp_logs import write_log

# MCP severity order (RFC 5424). Filtering is client-side, so it behaves the
# same whatever the server supports.
_LEVELS: List[str] = [
    "debug",
    "info",
    "notice",
    "warning",
    "error",
    "critical",
    "alert",
    "emergency",
]
_LEVEL_INDEX: Dict[str, int] = {name: i for i, name in enumerate(_LEVELS)}

DEFAULT_MIN_LOG_LEVEL = "info"


def _expand(value: str) -> str:
    """Expand ``$VAR``/``${VAR}``, plus ``${PWD}`` (not a real env var on Windows)."""
    if "${PWD}" in value or "$PWD" in value:
        cwd = os.getcwd()
        value = value.replace("${PWD}", cwd).replace("$PWD", cwd)
    return os.path.expandvars(value)


def normalize_root(entry: str) -> Optional[str]:
    """Convert a configured root to a ``file://`` URI; ``None`` if unresolvable.

    Plain paths are accepted for convenience; existing URIs pass through.
    """
    expanded = _expand(entry).strip()
    if not expanded:
        return None
    if "://" in expanded:
        return expanded
    try:
        return Path(expanded).expanduser().resolve().as_uri()
    except (ValueError, OSError):
        return None


@dataclass
class CapabilityConfig:
    """Parsed ``capabilities`` block for one server.

    Logging and progress default on (they only write to the log file);
    ``instructions`` is opt-in because it costs prompt tokens.
    """

    logging: bool = True
    min_log_level: str = DEFAULT_MIN_LOG_LEVEL
    progress: bool = True
    instructions: bool = False
    roots: List[str] = field(default_factory=list)
    cache_prompts: bool = True
    cache_resources: bool = True

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "CapabilityConfig":
        """Parse from a server's raw config.

        Bad keys and values fall back to defaults — the JSON is hand-edited,
        so a typo must not take a working server offline.
        """
        raw = config.get("capabilities")
        if not isinstance(raw, dict):
            return cls()

        def _flag(key: str, default: bool) -> bool:
            value = raw.get(key, default)
            return bool(value) if isinstance(value, bool) else default

        level = raw.get("min_log_level", DEFAULT_MIN_LOG_LEVEL)
        if not isinstance(level, str) or level.lower() not in _LEVEL_INDEX:
            level = DEFAULT_MIN_LOG_LEVEL

        roots_raw = raw.get("roots", [])
        roots = (
            [r for r in roots_raw if isinstance(r, str)]
            if isinstance(roots_raw, list)
            else []
        )

        return cls(
            logging=_flag("logging", True),
            min_log_level=level.lower(),
            progress=_flag("progress", True),
            instructions=_flag("instructions", False),
            roots=roots,
            cache_prompts=_flag("cache_prompts", True),
            cache_resources=_flag("cache_resources", True),
        )


def _render_log_data(data: Any) -> str:
    """Flatten a notification's ``data`` to one line.

    fastmcp sends ``{"msg": ..., "extra": ...}``, which bare ``repr`` renders
    unreadably.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and "msg" in data:
        msg = data["msg"]
        text = msg if isinstance(msg, str) else repr(msg)
        extra = data.get("extra")
        return f"{text} {extra!r}" if extra else text
    return repr(data)


def make_log_handler(server_name: str, min_level: str = DEFAULT_MIN_LOG_LEVEL):
    """Route server logs into the per-server file that ``/mcp logs`` reads."""
    threshold = _LEVEL_INDEX.get(min_level, _LEVEL_INDEX[DEFAULT_MIN_LOG_LEVEL])

    async def handler(params: Any) -> None:
        level = (getattr(params, "level", "info") or "info").lower()
        if _LEVEL_INDEX.get(level, _LEVEL_INDEX["info"]) < threshold:
            return
        message = _render_log_data(getattr(params, "data", ""))
        logger = getattr(params, "logger", None)
        if logger:
            message = f"[{logger}] {message}"
        write_log(server_name, message, level=level.upper())

    return handler


def make_progress_handler(server_name: str):
    """Log progress notifications, so slow tool calls are distinguishable from hung ones.

    Logged rather than rendered: a live progress bar would mean touching
    ``command_line/``, which ``AGENTS.md`` reserves for plugins.
    """

    async def handler(
        progress: float, total: Optional[float], message: Optional[str]
    ) -> None:
        if total:
            text = f"progress {progress:g}/{total:g} ({progress / total * 100:.0f}%)"
        else:
            text = f"progress {progress:g}"
        if message:
            text = f"{text} - {message}"
        write_log(server_name, text, level="DEBUG")

    return handler


def build_capability_kwargs(config: Dict[str, Any], server_name: str) -> Dict[str, Any]:
    """Map a server's ``capabilities`` block onto ``MCPToolset`` kwargs.

    Returns only what is enabled, so callers can merge over their defaults.
    ``log_level`` is never emitted; ``min_log_level`` filters client-side.
    """
    caps = CapabilityConfig.from_config(config)
    kwargs: Dict[str, Any] = {
        "cache_prompts": caps.cache_prompts,
        "cache_resources": caps.cache_resources,
    }

    if caps.instructions:
        kwargs["include_instructions"] = True
    if caps.logging:
        kwargs["log_handler"] = make_log_handler(server_name, caps.min_log_level)
    if caps.progress:
        kwargs["progress_handler"] = make_progress_handler(server_name)

    if caps.roots:
        resolved = [uri for uri in (normalize_root(r) for r in caps.roots) if uri]
        if resolved:
            kwargs["roots"] = resolved

    return kwargs

"""Per-server MCP capability wiring (stateless-session subset).

Code Puppy has historically consumed exactly one MCP capability — tools.
``MCPToolset`` already speaks the rest of the client protocol; this module
turns the per-server ``capabilities`` config block into the constructor
kwargs that switch those on.

Deliberately **not** supported: ``sampling`` and ``elicitation``. Those are
server-initiated *requests*, and SEP-2575 made MCP stateless — a modern
session holds no connection for the server to issue a request back over, so
pydantic-ai refuses them and warns ``"will never be called"`` at connect
time. Logging and progress survive the same negotiation because they are
one-way *notifications* that ride the response stream. Supporting sampling
or elicitation would mean pinning the whole connection to the legacy
protocol era (a pre-built ``fastmcp.Client(mode="legacy")``), which is a
protocol downgrade rather than a feature flag, so it is out of scope here.

The other consequence of statelessness: ``logging/setLevel`` does not exist
on a modern session. The server sends **every** level and leaves filtering
to the client, so ``min_level`` below is applied in ``make_log_handler``
rather than being negotiated with the server.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy.mcp_.mcp_logs import write_log

# MCP severity ordering (RFC 5424, as used by the MCP logging capability).
# Index = severity; higher is more severe. Used for client-side filtering
# because a stateless session has no `logging/setLevel` to filter server-side.
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
    """Expand ``$VAR``/``${VAR}`` plus a synthetic ``${PWD}``.

    ``PWD`` is not a real environment variable on Windows, but it is the
    obvious way for a user to write "the directory I launched in" in
    ``servers.json``, so it is resolved explicitly before falling through to
    the normal environment.
    """
    if "${PWD}" in value or "$PWD" in value:
        cwd = os.getcwd()
        value = value.replace("${PWD}", cwd).replace("$PWD", cwd)
    return os.path.expandvars(value)


def normalize_root(entry: str) -> Optional[str]:
    """Turn a configured root into a ``file://`` URI.

    The MCP roots capability is specified in terms of URIs, but writing
    ``file:///C:/Users/...`` by hand in JSON is miserable, so plain paths are
    accepted and converted. Entries that are already URIs pass through
    untouched. Returns ``None`` for entries that cannot be resolved, so a
    single bad path degrades that root instead of failing server startup.
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

    Defaults are chosen so that an existing ``servers.json`` with no
    ``capabilities`` key keeps today's behavior for anything the user can
    see in the agent's context (``instructions`` stays off, because server
    instructions are injected into the prompt and cost tokens), while
    observability that only lands in the existing rotated log file
    (``logging``, ``progress``) is on — those write through ``write_log``,
    the same sink ``/mcp logs`` already reads.
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
        """Build from a server's raw config dict.

        Unknown keys are ignored rather than rejected: ``servers.json`` is
        hand-edited, and a typo should not take a working server offline.
        An out-of-range ``min_log_level`` falls back to the default for the
        same reason.
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
    """Flatten a log notification's ``data`` into one readable line.

    ``data`` is typed ``Any`` by the protocol. FastMCP's ``ctx.info(...)``
    helpers send a structured ``{"msg": ..., "extra": ...}`` payload, so a
    bare ``repr`` renders the useful case as
    ``{'msg': 'almost done', 'extra': None}``. Unwrap that shape, keeping
    ``extra`` only when it carries something.
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
    """Route MCP ``notifications/message`` into the per-server log file.

    Filtering happens here because a stateless session ignores
    ``logging/setLevel`` — the server sends everything regardless.
    """
    threshold = _LEVEL_INDEX.get(min_level, _LEVEL_INDEX[DEFAULT_MIN_LOG_LEVEL])

    async def handler(params: Any) -> None:
        level = (getattr(params, "level", "info") or "info").lower()
        if _LEVEL_INDEX.get(level, _LEVEL_INDEX["info"]) < threshold:
            return
        data = getattr(params, "data", "")
        logger = getattr(params, "logger", None)
        message = _render_log_data(data)
        if logger:
            message = f"[{logger}] {message}"
        # write_log is sync file I/O; the volume here is a handful of lines
        # per tool call, so it is not worth a thread hop.
        write_log(server_name, message, level=level.upper())

    return handler


def make_progress_handler(server_name: str):
    """Record ``notifications/progress`` in the per-server log file.

    No TUI surface: rendering a live progress bar would mean touching
    ``code_puppy/command_line/``, which ``AGENTS.md`` reserves for plugins.
    Logging it still answers the question this capability exists to answer —
    "is this 40-second tool call actually making progress, or is it hung?" —
    and ``/mcp logs`` already tails the file.
    """

    async def handler(
        progress: float, total: Optional[float], message: Optional[str]
    ) -> None:
        if total:
            pct = (progress / total) * 100 if total else 0.0
            text = f"progress {progress:g}/{total:g} ({pct:.0f}%)"
        else:
            text = f"progress {progress:g}"
        if message:
            text = f"{text} - {message}"
        write_log(server_name, text, level="DEBUG")

    return handler


def build_capability_kwargs(config: Dict[str, Any], server_name: str) -> Dict[str, Any]:
    """Map a server's ``capabilities`` block onto ``MCPToolset`` kwargs.

    Returns only the kwargs this config actually enables, so callers can
    merge the result over their existing defaults without clobbering them.

    ``log_level`` is intentionally never emitted: on a stateless session
    pydantic-ai warns that it was "not applied", and emitting it would make
    every enterprise stdio server log a spurious warning at startup.
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

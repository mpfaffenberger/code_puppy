"""Turn 0.0.x values into their 1.0 form. Pure functions: no files, no stores."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import JsonValue

TRUTHY = frozenset({"1", "true", "yes", "on"})
SECRET_SUFFIXES = ("_api_key", "_token", "_secret")

PROVIDER_PREFIXES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
}
"""0.0.x model ``type`` to the 1.0 ``provider:`` prefix.

Only types whose provider ships with the runtime are listed. Anything else
(custom endpoints, OAuth-backed models, round-robin) is reported, not guessed:
a wrong model name would fail on the user's first prompt.
"""

MCP_TYPES = ("stdio", "http", "sse")
MCP_FIELDS = {
    "stdio": ("command", "args", "env", "cwd"),
    "http": ("url", "headers"),
    "sse": ("url", "headers"),
}


@dataclass(kw_only=True)
class Translation:
    """What a batch of legacy values became, and what could not be carried over."""

    values: dict[str, JsonValue] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def is_truthy(value: str) -> bool:
    """A 0.0.x boolean. ``config`` reads them back for plugins through this too."""
    return value.strip().lower() in TRUTHY


def is_secret(key: str) -> bool:
    """Whether a ``puppy.cfg`` key holds an API key rather than a preference."""
    return key.lower().endswith(SECRET_SUFFIXES)


def model_reference(name: str, catalog: Mapping[str, Mapping[str, Any]]) -> str | None:
    """A 0.0.x model name as a ``provider:model`` string, when it maps cleanly."""
    entry = catalog.get(name)
    if entry is None:
        return None
    prefix = PROVIDER_PREFIXES.get(str(entry.get("type", "")))
    model = entry.get("name") or name
    if prefix is None or entry.get("custom_endpoint") or not isinstance(model, str):
        return None
    return f"{prefix}:{model}"


NAME_KEYS = ("puppy_name", "owner_name")


def names(config: Mapping[str, str]) -> dict[str, str]:
    """The puppy and owner names 0.0.x put in its system prompt, as personality settings."""
    return {
        key: config[key].strip() for key in NAME_KEYS if config.get(key, "").strip()
    }


def settings(
    config: Mapping[str, str], catalog: Mapping[str, Mapping[str, Any]]
) -> Translation:
    """``puppy.cfg`` preferences as 1.0 settings, keyed as ``/set`` names them."""
    result = Translation()
    model = config.get("model", "").strip()
    if model:
        reference = model_reference(model, catalog)
        if reference is None:
            result.notes.append(
                f"Model {model!r} has no direct 1.0 equivalent; pick one with /model."
            )
        else:
            result.values["model"] = reference
    limit = config.get("message_limit", "").strip()
    if limit:
        try:
            request_limit = int(limit)
        except ValueError:
            # `str.isdigit()` accepts characters `int()` does not, such as "²".
            request_limit = 0
        if request_limit > 0:
            result.values["run.request_limit"] = request_limit
        else:
            result.notes.append(
                f"Ignored message_limit {limit!r}: not a positive number."
            )
    if "yolo_mode" in config:
        yolo = is_truthy(config["yolo_mode"])
        result.values["run.permissions"] = "full" if yolo else "read-only"
    if "enable_speculative_code_mode" in config:
        result.values["run.speculative_code_mode"] = is_truthy(
            config["enable_speculative_code_mode"]
        )
    return result


def api_keys(config: Mapping[str, str]) -> dict[str, str]:
    """API keys 0.0.x kept in ``puppy.cfg``, named as environment variables."""
    return {
        key.upper(): value
        for key, value in config.items()
        if is_secret(key) and value.strip()
    }


def preferences(config: Mapping[str, str]) -> dict[str, str]:
    """Every non-secret ``puppy.cfg`` key, kept for 0.0.x plugins that read them."""
    return {key: value for key, value in config.items() if not is_secret(key)}


def mcp_server(raw: Mapping[str, Any]) -> tuple[dict[str, JsonValue] | None, str]:
    """A 0.0.x MCP server entry in the 1.0 shape, or ``None`` and the reason.

    Servers are migrated with ``defer_loading`` on: their tools stay out of the
    prompt until the model asks for the server.
    """
    kind = raw.get("type") or raw.get("transport")
    if kind is None and "command" in raw:
        kind = "stdio"
    if kind not in MCP_TYPES:
        return None, f"unknown transport {kind!r}"
    server: dict[str, JsonValue] = {"type": kind, "defer_loading": True}
    for name in MCP_FIELDS[kind]:
        if raw.get(name) is not None:
            server[name] = raw[name]
    if raw.get("enabled") is False:
        server["enabled"] = False
    timeout = raw.get("timeout")
    if (
        isinstance(timeout, (int, float))
        and not isinstance(timeout, bool)
        and timeout > 0
    ):
        server["timeout"] = float(timeout)
    return server, ""

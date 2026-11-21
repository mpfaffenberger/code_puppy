"""Carry a 0.0.x setup over to 1.0: plan it, show it, apply it once.

Rules the migration keeps:

* **Non-destructive.** 0.0.x files are only read.
* **Never overrides a 1.0 choice.** A setting, key or MCP server that already
  exists in 1.0 is left alone, so running twice changes nothing.
* **Runs once per legacy state.** The hash of the legacy files is recorded;
  the automatic run at startup does nothing until those files change.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import JsonValue, TypeAdapter, ValidationError

from code_puppy import identity
from code_puppy.legacy_store import LegacyStore
from code_puppy.migrate import sources, translate

if TYPE_CHECKING:
    from pydantic_ai_pax.config.settings_store import SettingsStore

MIGRATED_KEY = "migrated_fingerprint"


@dataclass(kw_only=True)
class Plan:
    """Everything the legacy files would contribute to a fresh 1.0 setup."""

    fingerprint: str = ""
    settings: dict[str, JsonValue] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    servers: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    """Puppy and owner names, which become the personality plugin's settings."""
    notes: list[str] = field(default_factory=list)

    def describe(self) -> list[str]:
        """Human-readable lines. Key *names* only: values are never printed."""
        lines = [
            f"  setting  {key} = {value!r}" for key, value in self.settings.items()
        ]
        lines += [f"  api key  {name}" for name in self.keys]
        lines += [
            f"  mcp      {name} ({server.type})"
            for name, server in self.servers.items()
        ]
        lines += [f"  persona  {key} = {value!r}" for key, value in self.names.items()]
        if self.preferences:
            lines.append(
                f"  legacy   {len(self.preferences)} puppy.cfg keys kept for 0.0.x plugins"
            )
        lines += [f"  note     {note}" for note in self.notes]
        return lines


@dataclass(kw_only=True)
class Result:
    """What an apply actually wrote; everything else already existed."""

    settings: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    servers: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(
            self.settings or self.keys or self.servers or self.preferences or self.names
        )

    def summary(self) -> str:
        counts = [
            (len(self.settings), "setting"),
            (len(self.keys), "API key"),
            (len(self.servers), "MCP server"),
            (len(self.names), "name"),
            (len(self.preferences), "legacy preference"),
        ]
        parts = [f"{n} {noun}{'s' if n != 1 else ''}" for n, noun in counts if n]
        return ", ".join(parts) or "nothing new"


def build_plan(files: sources.LegacyFiles | None = None) -> Plan:
    """Read the legacy files and translate them; writes nothing."""
    from pydantic_ai_pax.mcp.settings import Server

    files = files or sources.legacy_files()
    config = sources.read_config(files.config)
    translated = translate.settings(config, sources.read_models(files.models))
    plan = Plan(
        fingerprint=files.fingerprint(),
        settings=translated.values,
        keys=translate.api_keys(config),
        preferences=translate.preferences(config),
        names=translate.names(config),
        notes=translated.notes,
    )
    adapter: TypeAdapter[Any] = TypeAdapter(Server)
    for name, raw in sources.read_mcp_servers(files.mcp_servers).items():
        candidate, reason = translate.mcp_server(raw)
        if candidate is None:
            plan.notes.append(f"Skipped MCP server {name!r}: {reason}.")
            continue
        try:
            plan.servers[name] = adapter.validate_python(candidate)
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"]
            plan.notes.append(f"Skipped MCP server {name!r}: {problem}.")
    return plan


def apply(plan: Plan, *, legacy: LegacyStore | None = None) -> Result:
    """Write what 1.0 does not have yet, then record the legacy fingerprint."""
    from pydantic_ai_pax.config.api_keys import save_key
    from pydantic_ai_pax.config.settings_store import SettingsStore
    from pydantic_ai_pax.mcp.store import MCPStore

    result = Result(notes=list(plan.notes))
    store = SettingsStore()
    existing = store.overrides()
    for key, value in plan.settings.items():
        if key in existing:
            continue
        try:
            store.set(key, value)
        except ValueError as exc:
            result.notes.append(f"Skipped setting {key}: {exc}")
        else:
            result.settings.append(key)

    for name, value in plan.keys.items():
        try:
            save_key(name=name, value=value, replace=False)
        except ValueError:
            continue  # Already saved under that name, or not a usable name.
        result.keys.append(name)

    mcp = MCPStore()
    known = mcp.load().servers
    for name, server in plan.servers.items():
        if name in known:
            continue
        try:
            mcp.put(name, server)
        except ValueError as exc:
            result.notes.append(f"Skipped MCP server {name!r}: {exc}")
        else:
            result.servers.append(name)

    result.names = _save_names(store, plan.names, result.notes)

    legacy = legacy or LegacyStore()
    result.preferences = legacy.set_missing(plan.preferences)
    legacy.set_meta(MIGRATED_KEY, plan.fingerprint)
    return result


def _save_names(
    store: SettingsStore, names: dict[str, str], notes: list[str]
) -> list[str]:
    """Seed the personality plugin's settings, unless the user already has some."""
    from pydantic_ai_pax.config import PluginSettings

    from code_puppy import personality

    if not names:
        return []
    try:
        personality.PersonalitySettings.model_validate(names)
    except ValidationError as exc:
        notes.append(f"Skipped puppy and owner names: {exc.errors()[0]['msg']}.")
        return []
    declaration = PluginSettings(
        id=personality.PLUGIN_ID, factory=personality.FACTORY, settings=dict(names)
    )
    try:
        store.save_plugin(declaration, overwrite=False)
    except ValueError:
        return []  # Already configured in 1.0.
    return sorted(names)


def auto() -> list[str]:
    """The startup migration: lines to show the user, or none when up to date."""
    files = sources.legacy_files()
    fingerprint = files.fingerprint()
    if not fingerprint:
        return []
    legacy = LegacyStore()
    if legacy.meta(MIGRATED_KEY) == fingerprint:
        return []
    result = apply(build_plan(files), legacy=legacy)
    if not result.changed:
        return []
    return [
        f"Brought over your {identity.DISPLAY_NAME} 0.0.x setup: {result.summary()}. "
        f"`{identity.COMMANDS[0]} migrate --dry-run` shows the details.",
        *result.notes,
    ]


def main(argv: list[str]) -> int:
    """``pup migrate``: show what carries over from 0.0.x, and apply it."""
    parser = argparse.ArgumentParser(
        prog=f"{identity.COMMANDS[0]} migrate",
        description=(
            f"Carry a {identity.DISPLAY_NAME} 0.0.x setup over to 1.0. "
            "Legacy files are never modified, and existing 1.0 values are kept."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show the plan without writing anything"
    )
    args = parser.parse_args(argv)
    files = sources.legacy_files()
    if not files.existing():
        print(
            f"No {identity.DISPLAY_NAME} 0.0.x files found in {identity.config_dir()}."
        )
        return 0
    plan = build_plan(files)
    print("Found in your 0.0.x setup:")
    print("\n".join(plan.describe()) or "  nothing to carry over")
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0
    result = apply(plan)
    print(f"Wrote: {result.summary()}.")
    for note in result.notes[len(plan.notes) :]:
        print(f"  note     {note}")
    return 0

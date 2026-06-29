"""Tests for per-plugin contribution extraction.

Covers ``plugin_list.plugin_contributions`` — that, for a given plugin, it
invokes *only* that plugin's owned collection callbacks (owner-filtered via
``_callback_owners``), parses each documented return shape into display
strings, and never raises when a callback blows up.
"""

from __future__ import annotations

import pytest

from code_puppy import callbacks
from code_puppy.plugins.plugin_list import plugin_contributions as pc


@pytest.fixture
def clean_callbacks():
    """Snapshot and restore the global callback registries."""
    saved_callbacks = {
        phase: list(funcs) for phase, funcs in callbacks._callbacks.items()
    }
    saved_owners = dict(callbacks._callback_owners)
    saved_loading = callbacks._current_loading_plugin
    try:
        yield
    finally:
        for phase in callbacks._callbacks:
            callbacks._callbacks[phase] = saved_callbacks.get(phase, [])
        callbacks._callback_owners.clear()
        callbacks._callback_owners.update(saved_owners)
        callbacks._current_loading_plugin = saved_loading


def _register(owner: str, phase: str, fn):
    """Register *fn* for *phase* owned by *owner*."""
    callbacks.set_loading_context(owner)
    try:
        callbacks.register_callback(phase, fn)
    finally:
        callbacks.clear_loading_context()
    return fn


# ── tools ──────────────────────────────────────────────────────────────────


def test_get_tools_parses_name(clean_callbacks):
    _register(
        "plugA",
        "register_tools",
        lambda: [{"name": "do_thing", "register_func": lambda a: None}],
    )
    assert pc.get_tools("plugA") == ["do_thing"]


def test_get_tools_single_dict_not_list(clean_callbacks):
    _register(
        "plugA",
        "register_tools",
        lambda: {"name": "solo", "register_func": lambda a: None},
    )
    assert pc.get_tools("plugA") == ["solo"]


# ── commands (all three shapes) ─────────────────────────────────────────────


def test_get_commands_list_of_tuples(clean_callbacks):
    _register(
        "plugA",
        "custom_command_help",
        lambda: [("foo", "Do foo"), ("bar", "Do bar")],
    )
    assert pc.get_commands("plugA") == ["/foo — Do foo", "/bar — Do bar"]


def test_get_commands_single_tuple(clean_callbacks):
    _register("plugA", "custom_command_help", lambda: ("baz", "Do baz"))
    assert pc.get_commands("plugA") == ["/baz — Do baz"]


def test_get_commands_legacy_string(clean_callbacks):
    _register(
        "plugA",
        "custom_command_help",
        lambda: ["/legacy - The legacy way"],
    )
    assert pc.get_commands("plugA") == ["/legacy — The legacy way"]


def test_get_commands_strips_leading_slash_in_name(clean_callbacks):
    _register("plugA", "custom_command_help", lambda: [("/slashed", "desc")])
    assert pc.get_commands("plugA") == ["/slashed — desc"]


# ── agents / skills / model types ───────────────────────────────────────────


def test_get_agents(clean_callbacks):
    _register("plugA", "register_agents", lambda: [{"name": "my-agent"}])
    assert pc.get_agents("plugA") == ["my-agent"]


def test_get_skills(clean_callbacks):
    _register(
        "plugA",
        "register_skills",
        lambda: [{"name": "my-skill", "skill_md": "# hi"}],
    )
    assert pc.get_skills("plugA") == ["my-skill"]


def test_get_model_types(clean_callbacks):
    _register(
        "plugA",
        "register_model_type",
        lambda: [{"type": "my_type", "handler": lambda *a: None}],
    )
    assert pc.get_model_types("plugA") == ["my_type"]


# ── providers / browser types (dict-keyed) ──────────────────────────────────


def test_get_model_providers_dict_keys(clean_callbacks):
    _register(
        "plugA",
        "register_model_providers",
        lambda: {"walmart_gemini": object},
    )
    assert pc.get_model_providers("plugA") == ["walmart_gemini"]


def test_get_browser_types_dict_keys(clean_callbacks):
    _register(
        "plugA",
        "register_browser_types",
        lambda: {"camoufox": lambda *a, **k: None},
    )
    assert pc.get_browser_types("plugA") == ["camoufox"]


# ── mcp servers (object .name or dict) ──────────────────────────────────────


def test_get_mcp_servers_object_name(clean_callbacks):
    class _Tmpl:
        name = "my-server"

    _register("plugA", "register_mcp_catalog_servers", lambda: [_Tmpl()])
    assert pc.get_mcp_servers("plugA") == ["my-server"]


def test_get_mcp_servers_dict_name(clean_callbacks):
    _register(
        "plugA",
        "register_mcp_catalog_servers",
        lambda: [{"name": "dict-server"}],
    )
    assert pc.get_mcp_servers("plugA") == ["dict-server"]


# ── advertised agent tools ──────────────────────────────────────────────────


def test_get_agent_tools_passes_none(clean_callbacks):
    seen = {}

    def _cb(agent_name=None):
        seen["arg"] = agent_name
        return ["tool_a", "tool_b"]

    _register("plugA", "register_agent_tools", _cb)
    assert pc.get_agent_tools("plugA") == ["tool_a", "tool_b"]
    assert seen["arg"] is None


# ── ownership filtering ─────────────────────────────────────────────────────


def test_only_owned_callbacks_invoked(clean_callbacks):
    _register(
        "plugA", "register_tools", lambda: [{"name": "a_tool", "register_func": id}]
    )
    _register(
        "plugB", "register_tools", lambda: [{"name": "b_tool", "register_func": id}]
    )
    assert pc.get_tools("plugA") == ["a_tool"]
    assert pc.get_tools("plugB") == ["b_tool"]


# ── safety: raising callbacks yield nothing, never crash ─────────────────────


def test_raising_callback_yields_no_items(clean_callbacks):
    def _boom():
        raise RuntimeError("kaboom")

    _register("plugA", "register_tools", _boom)
    # The raising callback contributes nothing...
    assert pc.get_tools("plugA") == []


def test_raising_callback_does_not_block_sibling(clean_callbacks):
    def _boom():
        raise RuntimeError("kaboom")

    _register("plugA", "register_tools", _boom)
    _register(
        "plugA", "register_tools", lambda: [{"name": "good", "register_func": id}]
    )
    assert pc.get_tools("plugA") == ["good"]


# ── dedupe / empties ────────────────────────────────────────────────────────


def test_dedupe_preserves_order(clean_callbacks):
    _register(
        "plugA",
        "register_tools",
        lambda: [
            {"name": "dup", "register_func": id},
            {"name": "dup", "register_func": id},
            {"name": "uniq", "register_func": id},
        ],
    )
    assert pc.get_tools("plugA") == ["dup", "uniq"]


def test_malformed_entries_skipped(clean_callbacks):
    _register(
        "plugA",
        "register_tools",
        lambda: [{"no_name": True}, "not_a_dict", {"name": "ok", "register_func": id}],
    )
    assert pc.get_tools("plugA") == ["ok"]


# ── aggregate API ───────────────────────────────────────────────────────────


def test_get_contributions_unknown_plugin_returns_empty_structure(clean_callbacks):
    result = pc.get_contributions("never_loaded_plugin")
    assert set(result.keys()) == set(pc._EXTRACTORS.keys())
    assert all(v == [] for v in result.values())


def test_get_contributions_aggregates_categories(clean_callbacks):
    _register("plugA", "register_tools", lambda: [{"name": "t", "register_func": id}])
    _register("plugA", "register_agents", lambda: [{"name": "ag"}])
    _register("plugA", "custom_command_help", lambda: [("cmd", "desc")])

    result = pc.get_contributions("plugA")
    assert result[pc.CATEGORY_TOOLS] == ["t"]
    assert result[pc.CATEGORY_AGENTS] == ["ag"]
    assert result[pc.CATEGORY_COMMANDS] == ["/cmd — desc"]
    assert result[pc.CATEGORY_SKILLS] == []


def test_get_contributions_only_target_plugin_across_categories(clean_callbacks):
    """Aggregate extraction never leaks a sibling plugin's contributions.

    ``plugB`` registers in *every* category; asking for ``plugA`` (which
    registered nothing) must come back fully empty, and asking for ``plugB``
    must return only ``plugB``'s items — proving owner filtering holds at the
    aggregate level, not just per-extractor.
    """
    _register(
        "plugB", "register_tools", lambda: [{"name": "b_tool", "register_func": id}]
    )
    _register("plugB", "register_agents", lambda: [{"name": "b_agent"}])
    _register("plugB", "register_skills", lambda: [{"name": "b_skill"}])
    _register("plugB", "custom_command_help", lambda: [("bcmd", "B command")])

    # plugA owns nothing -> every category empty.
    plug_a = pc.get_contributions("plugA")
    assert all(v == [] for v in plug_a.values())

    # plugB sees only its own items.
    plug_b = pc.get_contributions("plugB")
    assert plug_b[pc.CATEGORY_TOOLS] == ["b_tool"]
    assert plug_b[pc.CATEGORY_AGENTS] == ["b_agent"]
    assert plug_b[pc.CATEGORY_SKILLS] == ["b_skill"]
    assert plug_b[pc.CATEGORY_COMMANDS] == ["/bcmd — B command"]


# ── empty / None callback returns ───────────────────────────────────────────


def test_callback_returning_none_yields_empty(clean_callbacks):
    _register("plugA", "register_tools", lambda: None)
    assert pc.get_tools("plugA") == []


def test_callback_returning_empty_list_yields_empty(clean_callbacks):
    _register("plugA", "register_agents", lambda: [])
    assert pc.get_agents("plugA") == []


def test_command_callback_returning_none_yields_empty(clean_callbacks):
    _register("plugA", "custom_command_help", lambda: None)
    assert pc.get_commands("plugA") == []


def test_command_without_description_omits_dash(clean_callbacks):
    _register("plugA", "custom_command_help", lambda: [("bare", "")])
    assert pc.get_commands("plugA") == ["/bare"]


def test_get_contributions_empty_string_plugin_name(clean_callbacks):
    # An empty/None-ish plugin name matches no owner -> empty structure.
    result = pc.get_contributions("")
    assert set(result.keys()) == set(pc._EXTRACTORS.keys())
    assert all(v == [] for v in result.values())


# ── direct-registry attribution ─────────────────────────────────────────────


class _FakeCommandInfo:
    """Minimal stand-in for command_registry.CommandInfo."""

    def __init__(self, name, description, handler):
        self.name = name
        self.description = description
        self.handler = handler


def _handler_in(module_name):
    """Return a callable whose ``__module__`` is *module_name*."""

    def _h(command):  # pragma: no cover - never invoked, only inspected
        return True

    _h.__module__ = module_name
    return _h


def test_plugin_owner_of_module_builtin():
    assert (
        pc._plugin_owner_of_module("code_puppy.plugins.wiggum.register_callbacks")
        == "wiggum"
    )


def test_plugin_owner_of_module_project():
    assert (
        pc._plugin_owner_of_module("project_plugins.my_plug.register_callbacks")
        == "my_plug"
    )


def test_plugin_owner_of_module_user():
    assert pc._plugin_owner_of_module("user_plug.register_callbacks") == "user_plug"


def test_plugin_owner_of_module_core_does_not_match_plugin():
    # Core modules resolve to a prefix that is not a real plugin name.
    assert (
        pc._plugin_owner_of_module("code_puppy.command_line.command_handler")
        == "code_puppy"
    )


def test_plugin_owner_of_module_none():
    assert pc._plugin_owner_of_module(None) is None
    assert pc._plugin_owner_of_module("") is None


def test_registry_commands_attributed_by_handler_module(monkeypatch):
    from code_puppy.command_line import command_registry

    infos = [
        _FakeCommandInfo(
            "wiggum",
            "Loop mode",
            _handler_in("code_puppy.plugins.wiggum.register_callbacks"),
        ),
        _FakeCommandInfo(
            "other",
            "Other plugin command",
            _handler_in("code_puppy.plugins.elsewhere.register_callbacks"),
        ),
        _FakeCommandInfo(
            "core_cmd",
            "A core command",
            _handler_in("code_puppy.command_line.command_handler"),
        ),
    ]
    monkeypatch.setattr(command_registry, "get_unique_commands", lambda: infos)

    assert pc._registry_commands("wiggum") == ["/wiggum — Loop mode"]
    # Sibling plugin's command never leaks into wiggum's list.
    assert pc._registry_commands("elsewhere") == ["/other — Other plugin command"]
    # Core commands aren't attributed to any plugin.
    assert pc._registry_commands("code_puppy") == ["/core_cmd — A core command"]


def test_registry_commands_lookup_failure_yields_empty(monkeypatch):
    from code_puppy.command_line import command_registry

    def _boom():
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(command_registry, "get_unique_commands", _boom)
    assert pc._registry_commands("wiggum") == []


def test_get_commands_merges_callback_and_registry(clean_callbacks, monkeypatch):
    from code_puppy.command_line import command_registry

    _register("plugA", "custom_command_help", lambda: [("hooked", "From the hook")])
    monkeypatch.setattr(
        command_registry,
        "get_unique_commands",
        lambda: [
            _FakeCommandInfo(
                "decorated",
                "From the decorator",
                _handler_in("code_puppy.plugins.plugA.register_callbacks"),
            )
        ],
    )
    assert pc.get_commands("plugA") == [
        "/hooked — From the hook",
        "/decorated — From the decorator",
    ]


def test_get_commands_dedupes_across_callback_and_registry(
    clean_callbacks, monkeypatch
):
    from code_puppy.command_line import command_registry

    _register("plugA", "custom_command_help", lambda: [("dup", "Same command")])
    monkeypatch.setattr(
        command_registry,
        "get_unique_commands",
        lambda: [
            _FakeCommandInfo(
                "dup",
                "Same command",
                _handler_in("code_puppy.plugins.plugA.register_callbacks"),
            )
        ],
    )
    assert pc.get_commands("plugA") == ["/dup — Same command"]


def test_registry_tools_attributed_by_register_func_module(monkeypatch):
    import code_puppy.tools as tools_pkg

    fake_registry = {
        "plugA_tool": _handler_in("code_puppy.plugins.plugA.register_callbacks"),
        "core_tool": _handler_in("code_puppy.tools.file_operations"),
    }
    monkeypatch.setattr(tools_pkg, "TOOL_REGISTRY", fake_registry, raising=False)

    assert pc._registry_tools("plugA") == ["plugA_tool"]
    assert pc._registry_tools("code_puppy") == ["core_tool"]


def test_get_tools_merges_callback_and_registry(clean_callbacks, monkeypatch):
    import code_puppy.tools as tools_pkg

    _register(
        "plugA",
        "register_tools",
        lambda: [{"name": "hooked_tool", "register_func": id}],
    )
    monkeypatch.setattr(
        tools_pkg,
        "TOOL_REGISTRY",
        {"direct_tool": _handler_in("code_puppy.plugins.plugA.register_callbacks")},
        raising=False,
    )
    assert pc.get_tools("plugA") == ["hooked_tool", "direct_tool"]

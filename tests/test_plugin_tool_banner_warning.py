import logging
from unittest.mock import patch

import pytest

from code_puppy import banners
from code_puppy.banners import BannerDef
from code_puppy.tools import TOOL_REGISTRY, _banner_warned_tools, _load_plugin_tools

_NAMES = (
    "acp_banner_probe_plain",
    "acp_banner_probe_defined",
    "acp_banner_probe_raises",
)


def _noop(agent):
    return None


def _plugin(name):
    return [[{"name": name, "register_func": _noop}]]


def _warnings_for(caplog, name):
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and name in r.getMessage()
    ]


@pytest.fixture(autouse=True)
def banner_state():
    # Load built-ins first so the snapshot includes them and restoring can't drop them.
    banners._ensure_builtins()
    saved_defs = dict(banners._definitions)
    saved_registry = {n: TOOL_REGISTRY.get(n) for n in _NAMES}
    _banner_warned_tools.difference_update(_NAMES)
    yield
    banners._definitions.clear()
    banners._definitions.update(saved_defs)
    for name, func in saved_registry.items():
        if func is None:
            TOOL_REGISTRY.pop(name, None)
        else:
            TOOL_REGISTRY[name] = func
    _banner_warned_tools.difference_update(_NAMES)


def test_plugin_tool_without_banner_def_warns_and_registers(caplog):
    name = "acp_banner_probe_plain"
    with (
        caplog.at_level(logging.WARNING, logger="code_puppy.tools"),
        patch("code_puppy.tools.on_register_tools", return_value=_plugin(name)),
    ):
        _load_plugin_tools()

    assert TOOL_REGISTRY[name] is _noop
    assert len(_warnings_for(caplog, name)) == 1


def test_plugin_tool_with_banner_def_does_not_warn(caplog):
    name = "acp_banner_probe_defined"
    banners.register_banner_def(
        name, BannerDef(name=name, label="DEFINED", kind="other")
    )
    with (
        caplog.at_level(logging.WARNING, logger="code_puppy.tools"),
        patch("code_puppy.tools.on_register_tools", return_value=_plugin(name)),
    ):
        _load_plugin_tools()

    assert TOOL_REGISTRY[name] is _noop
    assert _warnings_for(caplog, name) == []


def test_repeated_loads_warn_once(caplog):
    name = "acp_banner_probe_plain"
    with (
        caplog.at_level(logging.WARNING, logger="code_puppy.tools"),
        patch("code_puppy.tools.on_register_tools", return_value=_plugin(name)),
    ):
        _load_plugin_tools()
        _load_plugin_tools()

    assert len(_warnings_for(caplog, name)) == 1


def test_banner_lookup_failure_still_registers_tool(caplog):
    name = "acp_banner_probe_raises"
    with (
        caplog.at_level(logging.WARNING, logger="code_puppy.tools"),
        patch("code_puppy.banners.has_banner_def", side_effect=RuntimeError("boom")),
        patch("code_puppy.tools.on_register_tools", return_value=_plugin(name)),
    ):
        _load_plugin_tools()

    assert TOOL_REGISTRY[name] is _noop
    assert _warnings_for(caplog, name) == []

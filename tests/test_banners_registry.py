"""Banner registration order: plugin defs win over lazily loaded builtins."""

import pytest

from code_puppy import banner_defs, banners
from code_puppy.banners import (
    BannerDef,
    get_banner_def,
    has_banner_def,
    register_banner_def,
)

PLUGIN_READ = BannerDef("read_file", "PLUGIN READ", "read", ("file_path",), "path")


@pytest.fixture
def lazy_registry(monkeypatch):
    """Empty registry with builtins not yet loaded; real builtins load on first use."""
    monkeypatch.setattr(banners, "_definitions", {})
    monkeypatch.setattr(banners, "_builtins_loaded", False)


def test_plugin_def_registered_before_lookup_overrides_builtin(lazy_registry):
    assert banners._builtins_loaded is False
    register_banner_def("read_file", PLUGIN_READ)

    assert get_banner_def("read_file") == PLUGIN_READ
    assert get_banner_def("grep") is banner_defs.BUILTIN_BANNER_DEFS["grep"]


def test_plugin_def_registered_after_lookup_overrides_builtin(lazy_registry):
    assert get_banner_def("read_file") is banner_defs.BUILTIN_BANNER_DEFS["read_file"]

    register_banner_def("read_file", PLUGIN_READ)

    assert get_banner_def("read_file") == PLUGIN_READ


def test_plugin_only_tool_is_registered_before_builtins_load(lazy_registry):
    plugin_def = BannerDef("plugin_only_tool", "PLUGIN ONLY", "other")

    register_banner_def("plugin_only_tool", plugin_def)

    assert has_banner_def("plugin_only_tool") is True
    assert get_banner_def("plugin_only_tool") == plugin_def


def test_registering_loads_builtins_once_without_recursing(lazy_registry):
    register_banner_def("plugin_only_tool", BannerDef("plugin_only_tool", "X", "other"))

    assert banners._builtins_loaded is True
    assert has_banner_def("grep") is True


def test_failed_builtin_load_is_retried_not_silently_swallowed(
    lazy_registry, monkeypatch
):
    def boom():
        raise RuntimeError("registration failed")

    monkeypatch.setattr(banner_defs, "register_builtin_banner_defs", boom)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="registration failed"):
            get_banner_def("read_file")

    monkeypatch.undo()
    monkeypatch.setattr(banners, "_definitions", {})
    monkeypatch.setattr(banners, "_builtins_loaded", False)
    assert has_banner_def("read_file")

"""Project plugin import runs the on-disk source, not a stale cache."""

import importlib.util
import marshal
import struct
import sys
from pathlib import Path

from code_puppy.plugins import (
    _ensure_project_ns,
    _load_one_project_plugin,
)


def _write_unchecked_hash_pyc(source_path: Path, body: str) -> Path:
    """Write an unchecked hash-based ``.pyc`` beside *source_path*.

    The cached bytecode carries *body* (distinct from the source file) and is
    marked unchecked so the interpreter would use it without comparing against
    the source.
    """
    code = compile(body, str(source_path), "exec")
    data = bytearray(importlib.util.MAGIC_NUMBER)
    flags = 0b01  # hash-based, unchecked
    data += struct.pack("<I", flags)
    data += b"\x00" * 8
    data += marshal.dumps(code)

    pyc_path = Path(importlib.util.cache_from_source(str(source_path)))
    pyc_path.parent.mkdir(parents=True, exist_ok=True)
    pyc_path.write_bytes(bytes(data))
    return pyc_path


def test_project_plugin_loads_from_source_not_stale_cache(tmp_path):
    plugin_name = "cache_probe_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    source_marker = tmp_path / "source_ran"
    cache_marker = tmp_path / "cache_ran"

    callbacks = plugin_dir / "register_callbacks.py"
    callbacks.write_text(
        "from pathlib import Path\n"
        f"Path(r{str(source_marker)!r}).write_text('source')\n"
    )

    _write_unchecked_hash_pyc(
        callbacks,
        f"from pathlib import Path\nPath(r{str(cache_marker)!r}).write_text('cache')\n",
    )

    module_name = f"project_plugins.{plugin_name}.register_callbacks"
    dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        sys.dont_write_bytecode = dont_write
        for name in (
            module_name,
            f"project_plugins.{plugin_name}",
        ):
            sys.modules.pop(name, None)
        parent = str(plugin_dir.parent)
        if parent in sys.path:
            sys.path.remove(parent)

    assert loaded
    assert source_marker.exists()
    assert not cache_marker.exists()


def test_project_plugin_load_writes_no_bytecode_and_touches_no_globals(tmp_path):
    """Loading runs source directly: no __pycache__ anywhere, no global
    ``sys.pycache_prefix`` mutation, and sibling imports resolve too."""
    import sys as _sys

    plugin_name = "no_bytecode_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "helper.py").write_text("VALUE = 41\n")
    (plugin_dir / "register_callbacks.py").write_text(
        "from . import helper\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"Path(r{str(tmp_path / 'pycache_at_load')!r}).write_text(str(sys.pycache_prefix))\n"
        f"Path(r{str(tmp_path / 'helper_value')!r}).write_text(str(helper.VALUE + 1))\n"
    )

    module_name = f"project_plugins.{plugin_name}.register_callbacks"
    prefix_before = _sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        for name in (
            module_name,
            f"project_plugins.{plugin_name}",
            f"project_plugins.{plugin_name}.helper",
        ):
            _sys.modules.pop(name, None)
        parent = str(plugin_dir.parent)
        if parent in _sys.path:
            _sys.path.remove(parent)

    assert loaded
    # Sibling import resolved through the source-only loader.
    assert (tmp_path / "helper_value").read_text() == "42"
    # The plugin observed an untouched global during its own import.
    assert (tmp_path / "pycache_at_load").read_text() == str(prefix_before)
    # No bytecode cache was written inside the project tree.
    assert not list(plugin_dir.rglob("__pycache__"))
    assert not list(plugin_dir.rglob("*.pyc"))


def test_project_plugin_finder_scoped_to_namespace(tmp_path):
    """The meta-path finder only serves project_plugins.* imports."""
    from code_puppy.plugins import _ProjectPluginFinder

    finder = _ProjectPluginFinder()
    plugin_dir = tmp_path / "plug"
    plugin_dir.mkdir()
    (plugin_dir / "mod.py").write_text("X = 1\n")

    spec = finder.find_spec("project_plugins.plug.mod", path=[str(plugin_dir)])
    assert spec is not None and spec.loader is not None
    assert type(spec.loader).__name__ == "_ProjectPluginLoader"

    # Anything outside the namespace is not ours to answer.
    assert finder.find_spec("os", path=[str(plugin_dir)]) is None
    assert finder.find_spec("code_puppy.plugins", path=[str(plugin_dir)]) is None

"""Project plugins load from source only; any bytecode in the tree is refused."""

import importlib.machinery
import importlib.util
import marshal
import os
import struct
import sys
from pathlib import Path

import pytest

from code_puppy.plugins import (
    _PROJECT_PLUGIN_PYCACHE,
    _ProjectPluginFinder,
    _ensure_project_ns,
    _load_one_project_plugin,
)


@pytest.fixture(autouse=True)
def _isolate_import_state():
    """Pin the process-global import state these tests plant into and mutate.

    ``_write_unchecked_hash_pyc`` places its cache via
    ``importlib.util.cache_from_source``, which honors ``sys.pycache_prefix``.
    The in-tree tripwire only sees a planted cache when the prefix is unset, so
    force it off while planting — otherwise a stray ``PYTHONPYCACHEPREFIX`` (or a
    prefix leaked by an earlier plugin-loading test) redirects the cache outside
    the plugin dir and the "refused" assertions silently invert. Also snapshot
    ``sys.path`` and ``sys.meta_path`` (the loader inserts into both) so nothing
    leaks in or out of these tests regardless of collection order.
    """
    saved_prefix = sys.pycache_prefix
    saved_path = list(sys.path)
    saved_meta_path = list(sys.meta_path)
    sys.pycache_prefix = None
    try:
        yield
    finally:
        sys.pycache_prefix = saved_prefix
        sys.path[:] = saved_path
        sys.meta_path[:] = saved_meta_path


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


def _write_sourceless_pyc(pyc_path: Path, body: str) -> None:
    """Write a valid sourceless ``.pyc`` (a bare bytecode file, no ``.py``)."""
    code = compile(body, str(pyc_path), "exec")
    data = bytearray(importlib.util.MAGIC_NUMBER)
    data += struct.pack("<I", 0)  # timestamp-based flags
    data += struct.pack("<I", 0)  # mtime
    data += struct.pack("<I", 0)  # source size
    data += marshal.dumps(code)
    pyc_path.write_bytes(bytes(data))


def _cleanup(plugin_dir: Path, plugin_name: str, extra: tuple[str, ...] = ()) -> None:
    for name in (
        f"project_plugins.{plugin_name}.register_callbacks",
        f"project_plugins.{plugin_name}",
        *extra,
    ):
        sys.modules.pop(name, None)
    parent = str(plugin_dir.parent)
    if parent in sys.path:
        sys.path.remove(parent)


def test_planted_bytecode_beside_callbacks_is_refused(tmp_path):
    """A ``register_callbacks.py`` plugin carrying a planted cache is refused."""
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

    prefix_before = sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        sys.pycache_prefix = prefix_before
        _cleanup(plugin_dir, plugin_name)

    assert not loaded
    assert not source_marker.exists()
    assert not cache_marker.exists()


def test_init_only_plugin_with_planted_sibling_bytecode_is_refused(tmp_path):
    """Repro (a): an ``__init__.py``-only plugin whose sibling has planted
    ``__pycache__`` bytecode is refused before the planted code can run."""
    plugin_name = "init_sibling_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    evil_marker = tmp_path / "evil_ran"
    helper = plugin_dir / "helper.py"
    helper.write_text("VALUE = 1\n")
    (plugin_dir / "__init__.py").write_text("from . import helper\n")

    _write_unchecked_hash_pyc(
        helper,
        "from pathlib import Path\n"
        f"Path(r{str(evil_marker)!r}).write_text('evil')\nVALUE = 1\n",
    )

    prefix_before = sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        sys.pycache_prefix = prefix_before
        _cleanup(
            plugin_dir, plugin_name, extra=(f"project_plugins.{plugin_name}.helper",)
        )

    assert not loaded
    assert not evil_marker.exists()


def test_bare_pyc_sibling_is_refused(tmp_path):
    """Repro (b): a bare ``helper.pyc`` (no ``.py``) is refused, so the
    default SourcelessFileLoader never executes the planted bytecode."""
    plugin_name = "bare_pyc_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    evil_marker = tmp_path / "bare_evil_ran"
    (plugin_dir / "__init__.py").write_text("from . import helper\n")
    _write_sourceless_pyc(
        plugin_dir / "helper.pyc",
        f"from pathlib import Path\nPath(r{str(evil_marker)!r}).write_text('evil')\n",
    )

    prefix_before = sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        sys.pycache_prefix = prefix_before
        _cleanup(
            plugin_dir, plugin_name, extra=(f"project_plugins.{plugin_name}.helper",)
        )

    assert not loaded
    assert not evil_marker.exists()


def test_clean_init_only_plugin_writes_no_bytecode(tmp_path):
    """Repro (c): a clean ``__init__.py``-only plugin with a benign sibling
    loads, resolves the sibling from source, and leaves no in-tree bytecode."""
    plugin_name = "clean_init_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "helper.py").write_text("VALUE = 41\n")
    (plugin_dir / "__init__.py").write_text(
        "from . import helper\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"Path(r{str(tmp_path / 'pycache_at_load')!r}).write_text(sys.pycache_prefix)\n"
        f"Path(r{str(tmp_path / 'helper_value')!r}).write_text(str(helper.VALUE + 1))\n"
    )

    prefix_before = sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        sys.pycache_prefix = prefix_before
        _cleanup(
            plugin_dir, plugin_name, extra=(f"project_plugins.{plugin_name}.helper",)
        )

    assert loaded
    # Sibling import resolved through the source-only loader.
    assert (tmp_path / "helper_value").read_text() == "42"
    # Bytecode was redirected out of the project tree during the load.
    assert (tmp_path / "pycache_at_load").read_text() == _PROJECT_PLUGIN_PYCACHE
    # No bytecode cache landed inside the plugin dir.
    assert not list(plugin_dir.rglob("__pycache__"))
    assert not list(plugin_dir.rglob("*.pyc"))


def test_project_plugin_finder_scoped_to_namespace(tmp_path):
    """The meta-path finder only serves project_plugins.* imports."""
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


def test_finder_refuses_planted_bytecode_within_namespace(tmp_path):
    """Within the namespace, a name backed only by bytecode raises ImportError
    instead of falling through to the default SourcelessFileLoader."""
    finder = _ProjectPluginFinder()
    plugin_dir = tmp_path / "plug"
    plugin_dir.mkdir()
    _write_sourceless_pyc(plugin_dir / "helper.pyc", "X = 1\n")

    with pytest.raises(ImportError):
        finder.find_spec("project_plugins.plug.helper", path=[str(plugin_dir)])

    # A bytecode-only name outside the namespace is still not ours to answer.
    assert finder.find_spec("plug.helper", path=[str(plugin_dir)]) is None


def test_sourceless_pyc_in_plugins_root_is_refused(tmp_path):
    """A sourceless ``.pyc`` on the plugins root (the sys.path entry) is refused.

    A trusted plugin's *top-level* ``import helper`` resolves against the plugins
    root through the default machinery, which the source-only meta-path finder
    never sees. ``_find_path_entry_binary`` covers that shared import root, so a
    loose ``helper.pyc`` there is refused before any code runs.
    """
    plugin_name = "root_pyc_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    evil_marker = tmp_path / "root_pyc_ran"
    (plugin_dir / "register_callbacks.py").write_text("import helper\n")
    # Planted directly on the plugins root, not inside the plugin dir.
    _write_sourceless_pyc(
        plugin_dir.parent / "helper.pyc",
        f"from pathlib import Path\nPath(r{str(evil_marker)!r}).write_text('evil')\n",
    )

    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        _cleanup(plugin_dir, plugin_name, extra=("helper",))

    assert not loaded
    assert not evil_marker.exists()


def test_compiled_extension_in_plugin_is_refused(tmp_path):
    """A compiled extension (``.so``/``.pyd``) beside the source is refused.

    The trust hash digests only source, so an extension is refused on its suffix
    by the tripwire — before any import machinery touches it.
    """
    plugin_name = "extension_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "register_callbacks.py").write_text("VALUE = 1\n")
    ext_suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    (plugin_dir / f"native{ext_suffix}").write_bytes(b"")

    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        _cleanup(plugin_dir, plugin_name)

    assert not loaded


def test_empty_dir_does_not_shadow_source_module(tmp_path):
    """``<name>.py`` wins over a same-named empty directory (CPython precedence).

    An empty ``state/`` dir must not shadow a trusted ``state.py`` into a
    loader-less namespace spec — the finder must serve the source module.
    """
    finder = _ProjectPluginFinder()
    plugin_dir = tmp_path / "plug"
    plugin_dir.mkdir()
    (plugin_dir / "state.py").write_text("X = 1\n")
    (plugin_dir / "state").mkdir()  # empty same-named directory

    spec = finder.find_spec("project_plugins.plug.state", path=[str(plugin_dir)])
    assert spec is not None and spec.loader is not None
    assert type(spec.loader).__name__ == "_ProjectPluginLoader"
    assert spec.origin is not None and spec.origin.endswith("state.py")


def test_extension_in_namespace_is_refused(tmp_path):
    """Within the namespace, a name backed only by a compiled extension raises.

    With ``native.<ext>`` present and no ``native.py``, the finder owns the name
    and fails closed instead of falling through to the default loader.
    """
    finder = _ProjectPluginFinder()
    plugin_dir = tmp_path / "plug"
    plugin_dir.mkdir()
    ext_suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    (plugin_dir / f"native{ext_suffix}").write_bytes(b"")

    with pytest.raises(ImportError):
        finder.find_spec("project_plugins.plug.native", path=[str(plugin_dir)])


def test_symlinked_subdir_is_refused(tmp_path):
    """A symlinked subdirectory (target outside the hashed tree) is refused.

    ``os.walk(followlinks=False)`` reports the link at its own level so the
    tripwire flags it — the trust digest never followed it.
    """
    plugin_name = "symlink_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "register_callbacks.py").write_text("VALUE = 1\n")

    outside = tmp_path / "outside_tree"
    outside.mkdir()
    try:
        os.symlink(outside, plugin_dir / "link")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unsupported on this platform: {exc}")

    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        _cleanup(plugin_dir, plugin_name)

    assert not loaded


def test_pycache_prefix_restored_after_load(tmp_path):
    """A clean load restores ``sys.pycache_prefix`` to its pre-load value.

    ``_load_one_project_plugin`` redirects the process-wide prefix during exec
    and must restore it in a ``finally`` — otherwise every unrelated import in
    the process is diverted for the rest of the session.
    """
    plugin_name = "prefix_restore_plugin"
    plugin_dir = tmp_path / ".code_puppy" / "plugins" / plugin_name
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "register_callbacks.py").write_text("VALUE = 1\n")

    prefix_snapshot = sys.pycache_prefix
    try:
        _ensure_project_ns()
        loaded = _load_one_project_plugin(plugin_dir, plugin_name)
    finally:
        _cleanup(plugin_dir, plugin_name)

    assert loaded
    assert sys.pycache_prefix == prefix_snapshot

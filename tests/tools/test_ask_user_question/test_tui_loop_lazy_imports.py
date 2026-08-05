"""Regression tests for lazy imports in ``ask_user_question.tui_loop``.

These pin the behaviour of the lazy-import helper in ``tui_loop``:
``tui_loop`` must NOT resolve
``code_puppy.callbacks.on_prompt_toolkit_style`` at module import time. Because
``tui_loop`` is loaded lazily from a worker thread inside an exception-recovery
path, a module-level ``from code_puppy.callbacks import on_prompt_toolkit_style``
can observe a partially-initialised ``code_puppy.callbacks`` and raise
``ImportError``. Deferring the lookup to call time removes that window.

If a future refactor moves the import back to module top, these tests will fail
loudly at import time and remind the next hacker why the indirection exists.
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest

_CALLBACKS = "code_puppy.callbacks"
_TUI_LOOP = "code_puppy.tools.ask_user_question.tui_loop"


@pytest.fixture
def restore_modules():
    """Snapshot and restore both modules so tests can safely stub ``callbacks``.

    Also pre-imports ``code_puppy.tools.ask_user_question`` before the stub is
    installed. Without that, a cold pytest run in which this file is collected
    first would trip over ``code_puppy.tools.__init__`` re-importing symbols
    from ``code_puppy.callbacks`` (``on_register_agent_tools``,
    ``on_register_tools``) that the stub does not carry -- the test would then
    pass or fail based on collection order rather than the invariant it claims
    to pin. Pre-importing the parent package ensures we exercise exactly the
    race the fix targets: a partially-initialised ``code_puppy.callbacks``
    observed by a fresh import of ``tui_loop`` alone.
    """
    importlib.import_module("code_puppy.tools.ask_user_question")
    saved = {name: sys.modules.get(name) for name in (_CALLBACKS, _TUI_LOOP)}
    try:
        yield
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _install_partial_callbacks_stub() -> types.ModuleType:
    """Replace ``code_puppy.callbacks`` with a stub missing the target symbol.

    Mirrors what the worker thread would see if it imported ``tui_loop`` while
    the main thread had ``code_puppy.callbacks`` only partially initialised: the
    module exists in ``sys.modules`` but ``on_prompt_toolkit_style`` is absent.
    """
    stub = types.ModuleType(_CALLBACKS)
    # Intentionally do NOT set ``on_prompt_toolkit_style`` — that is the race we
    # are pinning against.
    sys.modules[_CALLBACKS] = stub
    sys.modules.pop(_TUI_LOOP, None)
    return stub


def test_tui_loop_imports_without_on_prompt_toolkit_style(restore_modules):
    """Importing ``tui_loop`` must not require the symbol to exist yet."""
    _install_partial_callbacks_stub()

    module = importlib.import_module(_TUI_LOOP)

    # The lazy indirection is what makes the import survive the stub.
    assert hasattr(module, "_get_prompt_toolkit_style"), (
        "Regression: tui_loop should expose a lazy helper for "
        "on_prompt_toolkit_style so its module-import path does not depend on "
        "code_puppy.callbacks being fully initialised."
    )

    # And the anti-pattern must stay gone: no direct top-level binding.
    assert "on_prompt_toolkit_style" not in vars(module), (
        "Regression: tui_loop reintroduced a module-level import of "
        "on_prompt_toolkit_style. That resurrects the partially-initialised "
        "code_puppy.callbacks race the lazy helper was introduced to avoid."
    )


def test_get_prompt_toolkit_style_resolves_lazily(restore_modules):
    """The helper must resolve the real symbol on each call, not at import."""
    stub = _install_partial_callbacks_stub()

    module = importlib.import_module(_TUI_LOOP)

    # First call: symbol still missing -> AttributeError (surfaced as ImportError
    # by ``from X import Y``). Either exception type is acceptable evidence that
    # nothing was cached at import time.
    with pytest.raises((AttributeError, ImportError)):
        module._get_prompt_toolkit_style()

    # Populate the symbol after ``tui_loop`` was imported.
    sentinel = object()
    stub.on_prompt_toolkit_style = lambda: sentinel

    # Second call: helper picks up the freshly-populated symbol. Proves the
    # lookup is deferred to call time, not frozen at module load.
    assert module._get_prompt_toolkit_style() is sentinel

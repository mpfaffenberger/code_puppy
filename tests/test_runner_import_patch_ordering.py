"""Regression coverage for the cli_runner facade's pydantic-patch guarantee.

``code_puppy.cli_runner`` applies ``apply_all_patches()`` before any
pydantic-ai import (see its module docstring and the ordering comment above
``apply_all_patches()`` there). Several tests import the runner-split leaf
modules (``interactive_runner``, ``interactive_support``) directly for
cleaner mock targets; each of those files now imports ``code_puppy.cli_runner``
first precisely so that guarantee still holds for them. This module proves
the guarantee in a fresh subprocess per case (import order is a one-shot,
process-global effect that an in-process test cannot safely probe) and
documents the accepted, pre-existing gap when a leaf is imported with no
facade import at all.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _patches_loaded_after(*import_statements: str) -> bool:
    """Run ``import_statements`` in a fresh subprocess; report patch state.

    A fresh process is required because patch application and module import
    are both one-shot, process-global effects: a prior in-process import of
    ``code_puppy.cli_runner`` by this very test file (or any other collected
    module) would make every case report "already patched" regardless of
    what we're actually testing here.
    """
    script = "\n".join(
        [
            *import_statements,
            "import sys",
            "print('code_puppy.pydantic_patches' in sys.modules)",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip() == "True"


def test_facade_import_applies_patches_before_pydantic_ai():
    """Baseline: importing the facade alone applies the patches."""
    assert _patches_loaded_after("import code_puppy.cli_runner")


def test_facade_first_then_leaf_import_keeps_patches_applied():
    """The fix applied to the four retargeted tests: facade import first,
    then the direct leaf import, still yields patched pydantic-ai.
    """
    assert _patches_loaded_after(
        "import code_puppy.cli_runner",
        "import code_puppy.interactive_runner",
    )
    assert _patches_loaded_after(
        "import code_puppy.cli_runner",
        "import code_puppy.interactive_support",
    )


def test_bare_leaf_import_without_facade_does_not_apply_patches():
    """Documents the accepted, known gap: a leaf import with *no* facade
    import first does not get patched pydantic-ai. This is why the fixed
    test files import the facade first rather than relying on the leaf
    alone; this test exists so that gap can never silently disappear or
    silently get worse without someone noticing the assertion flip.
    """
    assert not _patches_loaded_after("import code_puppy.interactive_runner")
    assert not _patches_loaded_after("import code_puppy.interactive_support")

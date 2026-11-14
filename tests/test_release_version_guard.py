"""The publish guard keeps 1.0 release candidates away from `uvx code-puppy` users."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "check_release_version.py"
)
_spec = importlib.util.spec_from_file_location("check_release_version", _SCRIPT)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


@pytest.mark.parametrize(
    ("branch", "version"),
    [
        ("main", "0.0.970"),
        ("main", "0.1.0"),
        ("v1", "1.0.0rc1"),
        ("v1", "1.0.0rc27"),
        ("v1", "1.0.1rc1"),
    ],
)
def test_allowed(branch: str, version: str) -> None:
    assert guard.release_problem(branch, version) is None


@pytest.mark.parametrize(
    ("branch", "version", "fragment"),
    [
        # What `uv version --bump patch` produces from 1.0.0rc1.
        ("v1", "1.0.1", "stable release"),
        ("v1", "1.0.0", "stable release"),
        ("v1", "0.0.970rc1", "older than"),
        ("main", "1.0.0", "1.x release"),
        ("main", "1.0.1", "1.x release"),
        ("main", "1.0.0rc2", "pre-release"),
        ("main", "0.0.970rc1", "pre-release"),
        ("feature/x", "0.0.970", "does not publish"),
        ("v1", "not-a-version", "not a valid"),
    ],
)
def test_refused(branch: str, version: str, fragment: str) -> None:
    problem = guard.release_problem(branch, version)
    assert problem is not None and fragment in problem


def test_main_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert guard.main(["prog", "v1", "1.0.0rc2"]) == 0
    assert guard.main(["prog", "v1", "1.0.1"]) == 1
    assert guard.main(["prog"]) == 2
    assert "Refusing to publish" in capsys.readouterr().out

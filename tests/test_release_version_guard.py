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


RELEASABLE = """
[project]
dependencies = ["pydantic-ai-pax==0.70.0", "packaging>=24.0"]
"""


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(RELEASABLE, encoding="utf-8")

    assert guard.main(["prog", "v1", "1.0.0rc2"], pyproject=pyproject) == 0
    assert guard.main(["prog", "v1", "1.0.1"], pyproject=pyproject) == 1
    assert guard.main(["prog"], pyproject=pyproject) == 2
    assert "Refusing to publish" in capsys.readouterr().out


def test_a_build_against_unreleased_runtime_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`[tool.uv.sources]` never reaches PyPI, so the upload would depend on the wrong runtime."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = ["pydantic-ai-pax"]\n'
        "[tool.uv.sources]\n"
        'pydantic-ai-pax = { git = "https://github.com/pydantic/pydantic-ai", rev = "abc" }\n',
        encoding="utf-8",
    )

    assert guard.main(["prog", "v1", "1.0.0rc2"], pyproject=pyproject) == 1
    assert (
        "pydantic-ai-pax come from `[tool.uv.sources]`, not PyPI"
        in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    "requirement",
    [
        "pydantic-ai-pax",
        "pydantic-ai-pax>=0.70.0",
        "pydantic_ai_pax==0.70.*",
        "pydantic-ai-pax @ git+https://github.com/pydantic/pydantic-ai",
        # The alias package: loose, it could resolve to the pre-rename runtime.
        "pydantic-clai2",
    ],
)
def test_a_loose_runtime_pin_is_refused(requirement: str) -> None:
    problem = guard.dependency_problem({"project": {"dependencies": [requirement]}})
    assert problem is not None and "is not an exact pin" in problem


@pytest.mark.parametrize(
    "pyproject",
    [
        {"project": {"dependencies": ["pydantic-ai-pax==0.72.0", "packaging>=24.0"]}},
        {
            "project": {
                "dependencies": ["pydantic-ai-pax==0.72.0", "pydantic-clai2==0.72.0"]
            }
        },
        # 0.0.x on `main` has no runtime to pin.
        {"project": {"dependencies": ["rich>=13"]}},
        {},
    ],
)
def test_released_dependencies_are_allowed(pyproject: dict[str, object]) -> None:
    assert guard.dependency_problem(pyproject) is None

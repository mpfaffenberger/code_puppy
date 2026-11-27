"""The publish guard: only `main` publishes, and only stable versions from 1.0.0."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

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
        # What `uv version --bump stable` makes of 1.0.0rc1: the cutover.
        ("main", "1.0.0"),
        ("main", "1.0.1"),
        ("main", "1.2.0"),
        ("main", "2.0.0"),
    ],
)
def test_allowed(branch: str, version: str) -> None:
    assert guard.release_problem(branch, version) is None


@pytest.mark.parametrize(
    ("branch", "version", "fragment"),
    [
        ("main", "1.0.0rc2", "pre-release"),
        ("main", "1.0.1.dev1", "pre-release"),
        ("main", "0.0.970", "older than 1.0.0"),
        # The RC branch is retired.
        ("v1", "1.0.0rc2", "does not publish"),
        ("feature/x", "1.0.1", "does not publish"),
        ("main", "not-a-version", "not a valid"),
    ],
)
def test_refused(branch: str, version: str, fragment: str) -> None:
    problem = guard.release_problem(branch, version)
    assert problem is not None and fragment in problem


RELEASABLE = """
[project]
dependencies = ["pydantic-ai-pax==0.70.0", "packaging>=24.0"]
"""


@pytest.mark.parametrize(
    ("version", "bump"),
    [
        ("1.0.0rc1", "stable"),
        ("1.1.0b2", "stable"),
        ("1.0.1.dev3", "stable"),
        # A pre-release with a local or post segment is still one.
        ("1.0.0rc1+build.1", "stable"),
        ("1.0.0rc1.post1", "stable"),
        ("1.0.0", "patch"),
        ("1.0.0.post1", "patch"),
    ],
)
def test_the_bump_finalises_a_pre_release(
    version: str, bump: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert guard.bump_for(version) == bump
    assert guard.main(["prog", "--bump-for", version]) == 0
    assert capsys.readouterr().out == f"{bump}\n"


def test_the_project_being_released_passes_the_dependency_guard() -> None:
    """The real manifest, checked on every PR rather than first in the publish job."""
    pyproject = tomllib.loads(guard.PYPROJECT.read_text(encoding="utf-8"))
    assert guard.dependency_problem(pyproject) is None
    names = {Requirement(text).name for text in pyproject["project"]["dependencies"]}
    assert "pydantic-ai-pax" in names
    # Importing through the alias package runs pax twice; see former_name.py.
    assert "pydantic-clai2" not in names


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(RELEASABLE, encoding="utf-8")

    assert guard.main(["prog", "main", "1.0.0"], pyproject=pyproject) == 0
    assert guard.main(["prog", "main", "1.0.1rc1"], pyproject=pyproject) == 1
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

    assert guard.main(["prog", "main", "1.0.1"], pyproject=pyproject) == 1
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
        {"project": {"dependencies": ["rich>=13"]}},
        {},
    ],
)
def test_released_dependencies_are_allowed(pyproject: dict[str, object]) -> None:
    assert guard.dependency_problem(pyproject) is None

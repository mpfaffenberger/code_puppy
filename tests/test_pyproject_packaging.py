"""Packaging invariants for ``pyproject.toml``.

Two problems this pins down:

* ``dev-dependencies`` is **not** a PEP 621 ``[project]`` key. Hatchling
  tolerates unknown keys, but strict validators (and future build backends)
  reject them. It was also a dead duplicate of ``[dependency-groups] dev``,
  kept in sync by hand.
* the model catalogs were mapped into wheel *shared-data* as well as being
  included in the package, so every byte shipped twice -- 548 KB of
  duplicated JSON per wheel -- for a location nothing reads.
"""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

#: Keys PEP 621 defines for ``[project]``. Anything else there is invalid.
PEP_621_PROJECT_KEYS = {
    "name",
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "license-files",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "scripts",
    "gui-scripts",
    "entry-points",
    "dependencies",
    "optional-dependencies",
    "dynamic",
}


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_project_table_has_only_pep_621_keys(pyproject):
    unknown = sorted(set(pyproject["project"]) - PEP_621_PROJECT_KEYS)
    assert not unknown, f"invalid [project] keys: {unknown}"


def test_dev_dependencies_are_declared_once(pyproject):
    """One canonical home for the dev group: ``[dependency-groups]``."""
    assert "dev-dependencies" not in pyproject["project"]

    dev_group = pyproject.get("dependency-groups", {}).get("dev")
    assert dev_group, "the dev dependency group must exist"
    for requirement in ("pytest", "pytest-asyncio", "ruff"):
        assert any(requirement in entry for entry in dev_group), (
            f"{requirement} must stay in [dependency-groups] dev"
        )


def test_model_catalogs_are_not_shipped_twice(pyproject):
    """The catalogs live inside the package; shared-data duplicated them."""
    hatch = pyproject.get("tool", {}).get("hatch", {}).get("build", {})
    shared_data = hatch.get("targets", {}).get("wheel", {}).get("shared-data", {})

    packages = hatch.get("packages", [])
    for source in shared_data:
        for package in packages:
            prefix = package.rstrip("/") + "/"
            assert not source.startswith(prefix), (
                f"{source} is already shipped inside the {package} package; "
                "mapping it into shared-data as well duplicates it in the wheel"
            )


def test_sdist_still_ships_the_catalogs(pyproject):
    """Removing the wheel mapping must not drop them from the sdist."""
    hatch = pyproject.get("tool", {}).get("hatch", {}).get("build", {})
    included = {
        entry["path"]
        for entry in hatch.get("targets", {}).get("sdist", {}).get("include", [])
    }
    assert "code_puppy/models.json" in included
    assert "code_puppy/models_dev_api.json" in included

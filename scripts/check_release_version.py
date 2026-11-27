"""Refuse to publish a version that does not belong on the branch being released,
or one whose dependencies PyPI cannot supply.

Only ``main`` publishes, and only stable versions at or above ``1.0.0``: the
1.0 release candidates are over, and ``uvx code-puppy`` resolves to whatever
``main`` ships. A pre-release, or a version older than ``1.0.0``, is refused.

Between runtime releases ``main`` may be built against a commit of pydantic-ai
``main`` through ``[tool.uv.sources]``. Those sources are not part of the
published metadata, so such a build would reach PyPI depending on whatever
release happens to be newest. The guard refuses that too.

It also picks the bump that releases the version in git, by the same rules:
a pre-release is finalised (``1.0.0rc1`` → ``1.0.0``), a stable one patched.

Usage:

* ``python scripts/check_release_version.py <branch> <version>``
* ``python scripts/check_release_version.py --bump-for <version>``
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

RELEASE_BRANCH = "main"
FIRST_RELEASE = Version("1.0.0")
RUNTIME = ("pydantic-ai-pax", "pydantic-clai2")
"""Pinned exactly. pax carries the pins of everything else in the runtime.

``pydantic-clai2`` is its deprecated alias package since the rename, and was
the runtime itself before it: a loose requirement could resolve to an old one.
"""
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def release_problem(branch: str, version: str) -> str | None:
    """Return why ``version`` must not be published from ``branch``, or ``None``."""
    try:
        parsed = Version(version)
    except InvalidVersion:
        return f"{version!r} is not a valid PEP 440 version"
    if branch != RELEASE_BRANCH:
        return f"branch {branch!r} does not publish releases"
    if parsed.is_prerelease:
        return f"{version} is a pre-release; {RELEASE_BRANCH} publishes stable only"
    if parsed < FIRST_RELEASE:
        return f"{version} is older than {FIRST_RELEASE}, the 1.0 rewrite"
    return None


def bump_for(version: str) -> str:
    """The ``uv version --bump`` that releases ``version``.

    ``--bump patch`` would turn ``1.0.0rc1`` into ``1.0.1``, skipping ``1.0.0``;
    ``--bump stable`` refuses a version that is already stable.
    """
    return "stable" if Version(version).is_prerelease else "patch"


def _pinned_exactly(requirement: Requirement) -> bool:
    specifiers = list(requirement.specifier)
    return (
        requirement.url is None
        and len(specifiers) == 1
        and specifiers[0].operator == "=="
        and not specifiers[0].version.endswith(".*")
    )


def dependency_problem(pyproject: Mapping[str, Any]) -> str | None:
    """Return why this project's dependencies cannot be published, or ``None``."""
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    if sources:
        return (
            f"{', '.join(sorted(sources))} come from `[tool.uv.sources]`, not PyPI; "
            "a release can only depend on released packages"
        )
    for text in pyproject.get("project", {}).get("dependencies", []):
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        if name in RUNTIME and not _pinned_exactly(requirement):
            return f"`{text}` is not an exact pin; use `{name}==X.Y.Z`"
    return None


def main(argv: list[str], *, pyproject: Path = PYPROJECT) -> int:
    if len(argv) == 3 and argv[1] == "--bump-for":
        print(bump_for(argv[2]))
        return 0
    if len(argv) != 3:
        print(__doc__)
        return 2
    problem = release_problem(argv[1], argv[2]) or dependency_problem(
        tomllib.loads(pyproject.read_text(encoding="utf-8"))
    )
    if problem:
        print(f"Refusing to publish: {problem}")
        return 1
    print(f"OK: {argv[2]} may be published from {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

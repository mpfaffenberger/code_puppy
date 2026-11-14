"""Refuse to publish a version that does not belong on the branch being released.

During the 1.0 release-candidate period two lines publish from this repository:

* ``main`` ships stable ``0.0.x`` patches.
* ``v1`` ships ``1.0.0rcN`` pre-releases.

Installers skip pre-releases while a stable release exists, so ``uvx code-puppy``
keeps resolving to ``0.0.x``. That only holds while no stable ``1.x`` reaches
PyPI early. ``uv version --bump patch`` turns ``1.0.0rc1`` into a stable
``1.0.1``, so the wrong bump on the wrong branch would hand the rewrite to every
user. This guard fails the publish job before the upload when that happens.

Usage: ``python scripts/check_release_version.py <branch> <version>``
"""

from __future__ import annotations

import sys

from packaging.version import InvalidVersion, Version

STABLE_BRANCH = "main"
RC_BRANCH = "v1"
FIRST_REWRITE_RELEASE = Version("1.0.0rc1")


def release_problem(branch: str, version: str) -> str | None:
    """Return why ``version`` must not be published from ``branch``, or ``None``."""
    try:
        parsed = Version(version)
    except InvalidVersion:
        return f"{version!r} is not a valid PEP 440 version"
    if branch == RC_BRANCH:
        if not parsed.is_prerelease:
            return (
                f"{version} is a stable release; {RC_BRANCH} may only publish "
                "pre-releases (bump with `uv version --bump rc`)"
            )
        if parsed < FIRST_REWRITE_RELEASE:
            return f"{version} is older than {FIRST_REWRITE_RELEASE}"
        return None
    if branch == STABLE_BRANCH:
        if parsed.is_prerelease:
            return f"{version} is a pre-release; {STABLE_BRANCH} publishes stable only"
        if parsed >= FIRST_REWRITE_RELEASE:
            return (
                f"{version} is a 1.x release; {STABLE_BRANCH} stays on 0.0.x until "
                "the 1.0 cutover (see docs/upgrade/code_puppy_1_0_rewrite_plan.md)"
            )
        return None
    return f"branch {branch!r} does not publish releases"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    problem = release_problem(argv[1], argv[2])
    if problem:
        print(f"Refusing to publish: {problem}")
        return 1
    print(f"OK: {argv[2]} may be published from {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

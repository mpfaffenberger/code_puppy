"""Computer-use packaging stays opt-in and delegates platform rules to plugins."""

import tomllib
from pathlib import Path

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def _read_toml(name):
    with (ROOT / name).open("rb") as stream:
        return tomllib.load(stream)


def test_computer_use_extra_delegates_to_published_plugin():
    project = _read_toml("pyproject.toml")["project"]
    base = next(
        Requirement(value)
        for value in project["dependencies"]
        if Requirement(value).name == "code-puppy-core-plugins"
    )
    extra = project["optional-dependencies"]["computer-use"]
    assert len(extra) == 1
    delegated = Requirement(extra[0])
    assert delegated.name == base.name
    assert delegated.extras == {"computer-use"}
    assert not base.extras  # Plain installations do not request desktop SDKs.
    for requirement in (base, delegated):
        assert Version("0.0.77") in requirement.specifier
        assert Version("0.0.76") not in requirement.specifier


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_locked_extra_selects_platform_dependencies(platform):
    packages = {item["name"]: item for item in _read_toml("uv.lock")["package"]}
    plugin = packages["code-puppy-core-plugins"]
    assert Version(plugin["version"]) >= Version("0.0.77")
    assert packages["code-puppy"]["optional-dependencies"]["computer-use"] == [
        {"name": "code-puppy-core-plugins", "extra": ["computer-use"]}
    ]
    dependencies = plugin["optional-dependencies"]["computer-use"]
    active = {
        item["name"]
        for item in dependencies
        if "marker" not in item
        or Marker(item["marker"]).evaluate({"sys_platform": platform})
    }
    windows = {"pywinauto", "windows-capture"}
    macos = {
        "pyobjc-framework-applicationservices",
        "pyobjc-framework-cocoa",
        "pyobjc-framework-quartz",
    }
    assert active & windows == (windows if platform == "win32" else set())
    assert active & macos == (macos if platform == "darwin" else set())
    assert not {item["name"] for item in plugin.get("dependencies", [])} & (
        windows | macos
    )

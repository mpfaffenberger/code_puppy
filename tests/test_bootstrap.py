from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from code_puppy import bootstrap, bootstrap_profiles

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_env(**overrides):
    base = {
        "python_executable": sys.executable,
        "python_version": "3.12.0",
        "platform_system": "Linux",
        "platform_release": "6.0",
        "platform_machine": "x86_64",
        "is_android": False,
        "is_termux": False,
        "is_windows": False,
        "is_macos": False,
        "is_linux": True,
        "has_uv": True,
        "has_rust": True,
        "has_clang": True,
        "has_ripgrep": True,
        "has_git": True,
    }
    base.update(overrides)
    return base


# --- pre-install / runtime isolation -------------------------------------


def test_import_does_not_pull_runtime():
    # Importing the planner must not drag in Code Puppy's heavy runtime or
    # provider dependency stack, so launchers can inspect the environment
    # before those are installed.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import code_puppy.bootstrap, sys; "
                "heavy = [m for m in "
                "('pydantic_ai', 'httpx', 'openai', 'anthropic', 'rich', "
                "'prompt_toolkit', 'playwright') if m in sys.modules]; "
                "print(heavy)"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    )
    assert result.stdout.strip() == "[]"


def test_source_checkout_invocation_runs(tmp_path):
    # Simulate running from a fresh source checkout before installation:
    # `python -m code_puppy.bootstrap` must work without the Code Puppy
    # runtime/provider stack (code_puppy/__init__.py only imports `packaging`).
    result = subprocess.run(
        [sys.executable, "-m", "code_puppy.bootstrap", "plan", "--json"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    )
    payload = json.loads(result.stdout)
    assert payload["package_spec"].startswith("code-puppy")
    assert payload["profile"] == "lean"


# --- detection ------------------------------------------------------------


def test_detect_environment_termux(monkeypatch):
    monkeypatch.setenv("TERMUX_VERSION", "0.119")
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    environment = bootstrap_profiles.detect_environment()
    assert environment["is_termux"] is True
    assert environment["is_android"] is True


def test_detect_environment_has_expected_keys():
    environment = bootstrap_profiles.detect_environment()
    for key in ("python_executable", "is_termux", "has_uv", "has_rust"):
        assert key in environment


# --- profiles & platform filtering ---------------------------------------


def test_default_profile_is_lean(monkeypatch):
    monkeypatch.setattr(bootstrap_profiles, "detect_environment", _fake_env)
    plan = bootstrap_profiles.build_install_plan()
    assert plan["profile"] == "lean"
    assert plan["extras"] == []
    assert plan["package_spec"] == "code-puppy"


def test_full_profile_excludes_darwin_only_extra_off_macos(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(is_android=True, is_termux=True, is_linux=False),
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile="full")
    assert plan["extras"] == ["bedrock", "durable"]  # no computer-use on Android
    assert "computer-use" not in plan["detached_extras"]
    assert plan["package_spec"] == "code-puppy[bedrock,durable]"


def test_full_profile_includes_darwin_only_extra_on_macos(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(is_macos=True, is_linux=False, platform_system="Darwin"),
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile="full")
    assert plan["extras"] == ["bedrock", "computer-use", "durable"]
    assert plan["package_spec"] == "code-puppy[bedrock,computer-use,durable]"


def test_lean_detached_extras_are_platform_applicable(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(is_android=True, is_termux=True, is_linux=False),
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile="lean")
    assert plan["detached_extras"] == ["bedrock", "durable"]


def test_unknown_profile_rejected():
    with pytest.raises(ValueError, match="unknown install profile"):
        bootstrap_profiles.build_install_plan(requested_profile="not-a-real-profile")


def test_every_generated_extra_exists_and_is_applicable(monkeypatch):
    # Invariant: the planner never prescribes an extra that is absent from
    # pyproject or inapplicable to the detected platform.
    for is_macos in (True, False):
        monkeypatch.setattr(
            bootstrap_profiles,
            "detect_environment",
            lambda is_macos=is_macos: _fake_env(
                is_macos=is_macos, is_linux=not is_macos
            ),
        )
        plan = bootstrap_profiles.build_install_plan(requested_profile="full")
        for extra in plan["extras"] + plan["detached_extras"]:
            assert extra in bootstrap_profiles._OPTIONAL_EXTRAS
            if extra in bootstrap_profiles._DARWIN_ONLY_EXTRAS:
                assert is_macos


# --- command matrix -------------------------------------------------------


@pytest.mark.parametrize("profile", ["lean", "full"])
@pytest.mark.parametrize("has_uv", [True, False])
def test_command_matrix(monkeypatch, profile, has_uv):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(has_uv=has_uv),
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile=profile)
    if has_uv:
        assert plan["install_command"].startswith("uv tool install --refresh ")
    else:
        assert plan["install_command"].startswith("python -m pip install ")
    # Every install command targets a real code-puppy spec.
    assert "code-puppy" in plan["install_command"]


# --- Termux system-package honesty ---------------------------------------


def test_suggested_system_packages_empty_off_android(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(has_ripgrep=False, has_rust=False, has_clang=False),
    )
    plan = bootstrap_profiles.build_install_plan()
    assert plan["suggested_system_packages"] == []


def test_required_build_tools_on_android(monkeypatch):
    # rust/clang are REQUIRED on Termux: mandatory deps ship Rust/C native
    # extensions with no Termux-compatible wheels and compile on-device.
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(
            is_android=True,
            is_termux=True,
            is_linux=False,
            has_ripgrep=False,
            has_rust=False,
            has_clang=False,
        ),
    )
    plan = bootstrap_profiles.build_install_plan()
    pkgs = {p["package"]: p["kind"] for p in plan["suggested_system_packages"]}
    assert pkgs["rust"] == "required"
    assert pkgs["clang"] == "required"
    assert pkgs["ripgrep"] == "optional"  # ripgrep stays optional
    assert "proot" not in pkgs  # proot is never prescribed
    assert "libjpeg-turbo" not in pkgs  # not a hard build requirement for Pillow
    # Android install note surfaces the on-device compile cost.
    assert any("compile on-device" in n for n in plan["notes"])


def test_suggested_system_packages_only_missing(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: _fake_env(
            is_android=True,
            is_termux=True,
            is_linux=False,
            has_ripgrep=True,  # present -> not suggested
            has_rust=False,
            has_clang=True,  # present -> not suggested
        ),
    )
    plan = bootstrap_profiles.build_install_plan()
    assert [p["package"] for p in plan["suggested_system_packages"]] == ["rust"]


# --- CLI ------------------------------------------------------------------


def test_cli_detect_json(capsys):
    assert bootstrap.main(["detect", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "python_executable" in payload
    assert "is_termux" in payload


def test_cli_plan_defaults_to_lean_json(capsys):
    assert bootstrap.main(["plan", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "lean"
    assert payload["package_spec"].startswith("code-puppy")


def test_cli_plan_human_output(capsys):
    assert bootstrap.main(["plan"]) == 0
    output = capsys.readouterr().out
    assert "Profile:" in output
    assert "Install:" in output
    assert "Run:" in output


def test_cli_rejects_unknown_profile(capsys):
    with pytest.raises(SystemExit):
        bootstrap.main(["plan", "--profile", "nope"])

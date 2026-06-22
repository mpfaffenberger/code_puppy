from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from code_puppy import bootstrap, bootstrap_profiles


def test_bootstrap_import_does_not_pull_cli_runner():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import code_puppy.bootstrap; print('code_puppy.cli_runner' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_detect_environment_termux(monkeypatch):
    monkeypatch.setenv("TERMUX_VERSION", "0.119")
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    environment = bootstrap_profiles.detect_environment()
    assert environment["is_termux"] is True
    assert environment["is_android"] is True


def test_auto_profile_prefers_android_termux(monkeypatch):
    monkeypatch.setenv("TERMUX_VERSION", "0.119")
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    plan = bootstrap_profiles.build_install_plan(requested_profile="auto")
    assert plan["profile"] == "android-termux-lean"
    assert plan["extras"] == []
    assert "browser automation extras detached" in plan["degraded_capabilities"]


def test_build_install_plan_applies_manifest_overrides(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "profile": "android-termux-lean",
                "extras_add": ["browser", "search"],
                "extras_remove": ["search"],
                "notes": ["cloud picked a browser-friendly lane"],
            }
        )
    )
    plan = bootstrap_profiles.build_install_plan(
        requested_profile="android-termux-lean",
        manifest_file=str(manifest_path),
    )
    assert plan["extras"] == ["browser"]
    assert plan["manifest_applied"] is True
    assert "cloud picked a browser-friendly lane" in plan["notes"]
    assert plan["package_spec"] == "code-puppy[browser]"


def test_build_install_plan_rejects_profile_mismatch(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"profile": "desktop-browser"}))
    with pytest.raises(ValueError, match="does not match"):
        bootstrap_profiles.build_install_plan(
            requested_profile="android-termux-lean",
            manifest_file=str(manifest_path),
        )


def test_cli_detect_json(capsys):
    exit_code = bootstrap.main(["detect", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "python_executable" in payload
    assert "is_termux" in payload


def test_cli_plan_defaults_to_auto_json(capsys):
    exit_code = bootstrap.main(["plan", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] in bootstrap_profiles.available_profiles()
    assert payload["package_spec"].startswith("code-puppy")


def test_build_install_plan_rejects_unknown_profile():
    with pytest.raises(ValueError, match="unknown install profile"):
        bootstrap_profiles.build_install_plan(requested_profile="not-a-real-profile")


def test_build_install_plan_rejects_multiple_manifest_sources(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}")
    with pytest.raises(ValueError, match="choose manifest_json or manifest_file"):
        bootstrap_profiles.build_install_plan(
            requested_profile="core",
            manifest_json="{}",
            manifest_file=str(manifest_path),
        )


def test_build_install_plan_falls_back_to_pip_without_uv(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: {
            "has_uv": False,
            "has_uvx": False,
            "has_proot": True,
            "has_ripgrep": True,
            "has_rust": True,
            "has_clang": True,
            "is_android": False,
            "is_termux": False,
            "is_linux": True,
            "is_macos": False,
            "is_windows": False,
        },
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile="core")
    assert plan["install_command"] == "python -m pip install code-puppy"
    assert plan["reattach_command"] == "python -m pip install --upgrade code-puppy"


def test_build_install_plan_reports_missing_android_system_packages(monkeypatch):
    monkeypatch.setattr(
        bootstrap_profiles,
        "detect_environment",
        lambda: {
            "has_uv": True,
            "has_uvx": True,
            "has_proot": False,
            "has_ripgrep": False,
            "has_rust": False,
            "has_clang": False,
            "is_android": True,
            "is_termux": True,
            "is_linux": True,
            "is_macos": False,
            "is_windows": False,
        },
    )
    plan = bootstrap_profiles.build_install_plan(requested_profile="auto")
    assert plan["profile"] == "android-termux-lean"
    assert plan["missing_system_packages"] == ["rust", "clang", "ripgrep", "proot"]


def test_cli_plan_human_output(capsys):
    exit_code = bootstrap.main(["plan"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Profile:" in output
    assert "Install:" in output
    assert "Run:" in output


def test_cli_plan_rejects_bad_manifest_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["plan", "--manifest-json", "[]"])
    assert exc_info.value.code == 2
    assert "bootstrap manifest must be a JSON object" in capsys.readouterr().err

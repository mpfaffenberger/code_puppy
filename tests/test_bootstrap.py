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
                "extras_add": ["images", "search"],
                "extras_remove": ["search"],
                "notes": ["cloud picked a camera-friendly lane"],
            }
        )
    )
    plan = bootstrap_profiles.build_install_plan(
        requested_profile="android-termux-lean",
        manifest_file=str(manifest_path),
    )
    assert plan["extras"] == ["images"]
    assert plan["manifest_applied"] is True
    assert "cloud picked a camera-friendly lane" in plan["notes"]
    assert plan["package_spec"] == "code-puppy[images]"


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


def test_cli_plan_rejects_bad_manifest_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["plan", "--manifest-json", "[]"])
    assert exc_info.value.code == 2
    assert "bootstrap manifest must be a JSON object" in capsys.readouterr().err

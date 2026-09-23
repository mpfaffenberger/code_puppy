"""Focused tests for the project presentation-maker plugin."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_DIR = Path(__file__).parents[1]
TOOLS_PATH = PLUGIN_DIR / "tools.py"

pydantic_ai_stub = types.ModuleType("pydantic_ai")
pydantic_ai_stub.RunContext = object
sys.modules.setdefault("pydantic_ai", pydantic_ai_stub)

code_puppy_stub = types.ModuleType("code_puppy")
code_puppy_stub.__path__ = []
code_puppy_tools_stub = types.ModuleType("code_puppy.tools")
code_puppy_tools_stub.__path__ = []
common_stub = types.ModuleType("code_puppy.tools.common")
common_stub.get_working_directory = os.getcwd
sys.modules.setdefault("code_puppy", code_puppy_stub)
sys.modules.setdefault("code_puppy.tools", code_puppy_tools_stub)
sys.modules.setdefault("code_puppy.tools.common", common_stub)

SPEC = importlib.util.spec_from_file_location("presentation_maker_tools", TOOLS_PATH)
assert SPEC is not None and SPEC.loader is not None
tools = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tools
SPEC.loader.exec_module(tools)


def test_prepare_spec_resolves_image_inside_workspace(tmp_path, monkeypatch):
    image = tmp_path / "figure.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(tools, "get_working_directory", lambda: str(tmp_path))

    spec = tools.PresentationSpec.model_validate(
        {
            "slides": [
                {
                    "elements": [
                        {
                            "type": "image",
                            "path": "figure.png",
                            "x": 1,
                            "y": 1,
                            "w": 2,
                            "h": 2,
                        }
                    ]
                }
            ]
        }
    )

    payload = tools._prepare_spec(spec)

    assert payload["slides"][0]["elements"][0]["path"] == str(image)


def test_output_path_cannot_escape_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "get_working_directory", lambda: str(tmp_path))

    with pytest.raises(ValueError, match="inside the working directory"):
        tools._resolve_workspace_path("../outside.pptx")


def test_build_returns_setup_command_when_dependency_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "get_working_directory", lambda: str(tmp_path))
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(tools, "_runtime_directory", lambda: tmp_path / "runtime")

    result = tools.build_presentation_file({"slides": [{"title": "Test"}]}, "deck.pptx")

    assert result.success is False
    assert result.setup_command is not None
    assert "npm install" in result.setup_command


def test_build_invokes_renderer_and_reports_output(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "node_modules" / "pptxgenjs").mkdir(parents=True)
    (runtime / "node_modules" / "pptxgenjs" / "package.json").write_text("{}")
    monkeypatch.setattr(tools, "get_working_directory", lambda: str(tmp_path))
    monkeypatch.setattr(tools, "_runtime_directory", lambda: runtime)
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/node")

    def fake_run(command, **kwargs):
        Path(command[3]).write_bytes(b"pptx")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)

    result = tools.build_presentation_file(
        {"slides": [{"title": "One"}, {"title": "Two"}]}, "deck.pptx"
    )

    assert result.success is True
    assert result.slide_count == 2
    assert result.file_size_bytes == 4


def test_preview_dependency_check_requires_both_packages(tmp_path):
    modules = tmp_path / "node_modules"
    for package in ("pdfjs-dist", "@napi-rs/canvas"):
        package_dir = modules / package
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text("{}")

    assert tools._preview_dependencies_available(tmp_path) is True
    (modules / "pdfjs-dist" / "package.json").unlink()
    assert tools._preview_dependencies_available(tmp_path) is False


def test_render_uses_powerpoint_and_collects_pngs(tmp_path, monkeypatch):
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"pptx")
    monkeypatch.setattr(tools, "get_working_directory", lambda: str(tmp_path))
    monkeypatch.setattr(tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        tools,
        "_powerpoint_command",
        lambda source, target: ["powerpoint", str(source), str(target)],
    )

    def fake_run(command, **kwargs):
        export_dir = Path(command[2])
        export_dir.mkdir(parents=True)
        (export_dir / "Slide1.png").write_bytes(b"png")
        (export_dir / "Slide2.png").write_bytes(b"png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)

    result = tools.render_presentation_file("deck.pptx")

    assert result.success is True
    assert result.slide_count == 2
    assert [Path(path).name for path in result.preview_paths] == [
        "Slide1.png",
        "Slide2.png",
    ]

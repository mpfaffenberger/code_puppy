"""Tool implementations for building and rendering PowerPoint decks."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai import RunContext

from code_puppy.tools.common import get_working_directory

PLUGIN_DIR = Path(__file__).parent
RUNTIME_DIR = PLUGIN_DIR / ".state" / "node"
RENDERER = PLUGIN_DIR / "renderer.mjs"
MACOS_RENDERER = PLUGIN_DIR / "render_powerpoint.js"
WINDOWS_RENDERER = PLUGIN_DIR / "render_powerpoint.ps1"
PDF_RENDERER = PLUGIN_DIR / "render_pdf.mjs"


class PresentationElement(BaseModel):
    """A native PowerPoint element accepted by the JavaScript renderer."""

    model_config = ConfigDict(extra="allow")

    type: Literal["text", "image", "table", "chart", "shape", "line"]
    text: str | list[dict[str, Any]] | None = None
    path: str | None = None
    rows: list[Any] | None = None
    data: list[dict[str, Any]] | None = None
    chartType: str | None = None
    shape: str | None = None
    options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_required_content(self) -> "PresentationElement":
        required = {
            "text": (self.text, "text"),
            "image": (self.path, "path"),
            "table": (self.rows, "rows"),
            "chart": (self.data, "data"),
            "shape": (self.shape, "shape"),
        }
        if self.type in required:
            value, field_name = required[self.type]
            if value is None:
                raise ValueError(f"{self.type} elements require '{field_name}'")
        if self.type == "chart" and not self.chartType:
            raise ValueError("chart elements require 'chartType'")
        return self


class SlideSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    titleOptions: dict[str, Any] | None = None
    background: str | dict[str, Any] | None = None
    elements: list[PresentationElement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PresentationSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    layout: Literal["LAYOUT_WIDE", "LAYOUT_STANDARD"] = "LAYOUT_WIDE"
    author: str = "Code Puppy Presentation Maker"
    company: str = ""
    subject: str = ""
    language: str = "en-US"
    theme: dict[str, Any] = Field(default_factory=dict)
    slides: list[SlideSpec] = Field(min_length=1, max_length=200)


class PresentationToolResult(BaseModel):
    success: bool
    presentation_path: str | None = None
    preview_paths: list[str] = Field(default_factory=list)
    slide_count: int | None = None
    file_size_bytes: int | None = None
    error: str | None = None
    setup_command: str | None = None


def _workspace_root() -> Path:
    return Path(get_working_directory()).resolve()


def _resolve_workspace_path(path_value: str, *, suffix: str | None = None) -> Path:
    requested = Path(path_value).expanduser()
    candidate = (
        requested.resolve()
        if requested.is_absolute()
        else (_workspace_root() / requested).resolve()
    )
    if suffix and not candidate.suffix:
        candidate = candidate.with_suffix(suffix)
    try:
        candidate.relative_to(_workspace_root())
    except ValueError as exc:
        raise ValueError(
            "Presentation paths must stay inside the working directory"
        ) from exc
    return candidate


def _runtime_directory() -> Path:
    configured = os.environ.get("CODE_PUPPY_PRESENTATION_RUNTIME")
    return Path(configured).expanduser().resolve() if configured else RUNTIME_DIR


def _setup_command() -> str:
    return (
        f'npm install --prefix "{_runtime_directory()}" --no-save '
        '"pptxgenjs@3.12.0" "pdfjs-dist@3.11.174" '
        '"@napi-rs/canvas@0.1.68"'
    )


def _prepare_spec(spec: PresentationSpec) -> dict[str, Any]:
    payload = spec.model_dump(exclude_none=True)
    for slide in payload["slides"]:
        for element in slide.get("elements", []):
            if element["type"] != "image":
                continue
            image_path = _resolve_workspace_path(element["path"])
            if not image_path.is_file():
                raise ValueError(f"Image file not found: {element['path']}")
            element["path"] = str(image_path)
    return payload


def _pptxgen_available(runtime_dir: Path) -> bool:
    package_dir = runtime_dir / "node_modules" / "pptxgenjs"
    return (package_dir / "package.json").is_file()


def _preview_dependencies_available(runtime_dir: Path) -> bool:
    modules = runtime_dir / "node_modules"
    return all(
        (modules / package / "package.json").is_file()
        for package in ("pdfjs-dist", "@napi-rs/canvas")
    )


def build_presentation_file(
    spec_data: dict[str, Any], output_path: str, timeout: int = 180
) -> PresentationToolResult:
    """Validate a deck spec and render it to an editable PPTX file."""
    try:
        spec = PresentationSpec.model_validate(spec_data)
        payload = _prepare_spec(spec)
        destination = _resolve_workspace_path(output_path, suffix=".pptx")
        if destination.suffix.lower() != ".pptx":
            raise ValueError("The output file must use the .pptx extension")

        node = shutil.which("node")
        if node is None:
            return PresentationToolResult(
                success=False,
                error="Node.js is required to generate PowerPoint files.",
            )

        runtime_dir = _runtime_directory()
        if not _pptxgen_available(runtime_dir):
            return PresentationToolResult(
                success=False,
                error="The presentation renderer dependency is not installed.",
                setup_command=_setup_command(),
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="code-puppy-presentation-") as tmp:
            spec_path = Path(tmp) / "deck-spec.json"
            spec_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    node,
                    str(RENDERER),
                    str(spec_path),
                    str(destination),
                    str(runtime_dir),
                ],
                cwd=_workspace_root(),
                capture_output=True,
                text=True,
                timeout=max(1, min(timeout, 600)),
                check=False,
            )

        if result.returncode != 0:
            details = (
                result.stderr or result.stdout or "Unknown renderer error"
            ).strip()
            return PresentationToolResult(
                success=False,
                presentation_path=str(destination),
                error=f"PowerPoint generation failed: {details[-2000:]}",
            )
        if not destination.is_file():
            return PresentationToolResult(
                success=False,
                error="The renderer completed without producing a PPTX file.",
            )

        return PresentationToolResult(
            success=True,
            presentation_path=str(destination),
            slide_count=len(spec.slides),
            file_size_bytes=destination.stat().st_size,
        )
    except (ValidationError, ValueError, OSError, subprocess.SubprocessError) as exc:
        return PresentationToolResult(success=False, error=str(exc))


def _powerpoint_command(source: Path, export_target: Path) -> list[str]:
    system = platform.system()
    if system == "Darwin":
        if not Path("/Applications/Microsoft PowerPoint.app").is_dir():
            raise RuntimeError("Microsoft PowerPoint is not installed in /Applications")
        osascript = shutil.which("osascript")
        if osascript is None:
            raise RuntimeError("macOS AppleScript support is unavailable")
        return [
            osascript,
            "-l",
            "JavaScript",
            str(MACOS_RENDERER),
            str(source),
            str(export_target),
        ]
    if system == "Windows":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            raise RuntimeError(
                "PowerShell is required to automate Microsoft PowerPoint"
            )
        return [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WINDOWS_RENDERER),
            "-InputPptx",
            str(source),
            "-OutputPath",
            str(export_target),
        ]
    raise RuntimeError(
        "PowerPoint rendering requires Microsoft PowerPoint on macOS or Windows"
    )


def render_presentation_file(
    presentation_path: str,
    output_directory: str | None = None,
    timeout: int = 180,
) -> PresentationToolResult:
    """Open a PPTX in Microsoft PowerPoint and export every slide as PNG."""
    try:
        source = _resolve_workspace_path(presentation_path)
        if not source.is_file():
            raise ValueError(f"Presentation not found: {presentation_path}")
        if source.suffix.lower() != ".pptx":
            raise ValueError("Only .pptx files can be rendered")

        if output_directory:
            preview_dir = _resolve_workspace_path(output_directory)
        else:
            preview_dir = source.with_name(f"{source.stem}_preview")
        preview_dir.mkdir(parents=True, exist_ok=True)
        run_dir = preview_dir / f"render-{uuid.uuid4().hex}"
        run_dir.mkdir()

        system = platform.system()
        office_export: Path | None = None
        if system == "Darwin":
            runtime_dir = _runtime_directory()
            if not _preview_dependencies_available(runtime_dir):
                return PresentationToolResult(
                    success=False,
                    presentation_path=str(source),
                    error="The PowerPoint preview dependencies are not installed.",
                    setup_command=_setup_command(),
                )
            office_temp = (
                Path.home()
                / "Library"
                / "Group Containers"
                / "UBF8T346G9.Office"
                / "TemporaryItems"
            )
            if not office_temp.is_dir():
                raise RuntimeError(
                    "Microsoft Office temporary directory is unavailable"
                )
            office_export = office_temp / f"code-puppy-{uuid.uuid4().hex}.pdf"
            export_target = office_export
        else:
            export_target = run_dir / "slides"

        command = _powerpoint_command(source, export_target)
        try:
            result = subprocess.run(
                command,
                cwd=_workspace_root(),
                capture_output=True,
                text=True,
                timeout=max(1, min(timeout, 600)),
                check=False,
            )
            if result.returncode != 0:
                details = (
                    result.stderr or result.stdout or "Unknown PowerPoint error"
                ).strip()
                return PresentationToolResult(
                    success=False,
                    presentation_path=str(source),
                    error=(
                        "Microsoft PowerPoint could not render the deck: "
                        f"{details[-2000:]}"
                    ),
                )

            if system == "Darwin":
                if office_export is None or not office_export.is_file():
                    raise RuntimeError(
                        "Microsoft PowerPoint completed without exporting a PDF"
                    )
                conversion = subprocess.run(
                    [
                        shutil.which("node") or "node",
                        str(PDF_RENDERER),
                        str(office_export),
                        str(run_dir),
                        str(runtime_dir),
                    ],
                    cwd=_workspace_root(),
                    capture_output=True,
                    text=True,
                    timeout=max(1, min(timeout, 600)),
                    check=False,
                )
                if conversion.returncode != 0:
                    details = (
                        conversion.stderr
                        or conversion.stdout
                        or "Unknown PDF conversion error"
                    ).strip()
                    raise RuntimeError(
                        f"PowerPoint preview conversion failed: {details[-2000:]}"
                    )
        finally:
            if office_export is not None:
                office_export.unlink(missing_ok=True)

        preview_paths = sorted(
            str(path)
            for path in run_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".png"
        )
        if not preview_paths:
            return PresentationToolResult(
                success=False,
                presentation_path=str(source),
                error="Microsoft PowerPoint completed without exporting slide images.",
            )
        return PresentationToolResult(
            success=True,
            presentation_path=str(source),
            preview_paths=preview_paths,
            slide_count=len(preview_paths),
        )
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return PresentationToolResult(
            success=False,
            presentation_path=presentation_path,
            error=str(exc),
        )


def register_build_presentation(agent):
    """Register the structured PPTX generation tool."""

    @agent.tool
    async def build_presentation(
        context: RunContext,
        spec: dict[str, Any],
        output_path: str,
        timeout: int = 180,
    ) -> PresentationToolResult:
        """Build an editable Microsoft PowerPoint file from a slide specification.

        The specification must contain at least one slide. Supported element
        types are text, image, table, chart, shape, and line. Coordinates use
        inches, as expected by PptxGenJS. Image paths and the output path must
        stay inside the active working directory.
        """
        return build_presentation_file(spec, output_path, timeout)

    return build_presentation


def register_render_presentation(agent):
    """Register Microsoft PowerPoint rendering for visual inspection."""

    @agent.tool
    async def render_presentation(
        context: RunContext,
        presentation_path: str,
        output_directory: str | None = None,
        timeout: int = 180,
    ) -> PresentationToolResult:
        """Open a PPTX in Microsoft PowerPoint and export each slide as PNG.

        This uses AppleScript on macOS and the PowerPoint COM API on Windows.
        It never uses LibreOffice. Inspect every returned image with
        load_image_for_analysis before delivering the deck.
        """
        return render_presentation_file(
            presentation_path, output_directory=output_directory, timeout=timeout
        )

    return render_presentation

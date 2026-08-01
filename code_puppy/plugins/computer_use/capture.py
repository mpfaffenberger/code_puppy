"""Typed ScreenCaptureKit bridge through a small cached Swift helper."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from code_puppy.config import CONFIG_DIR

from .backend_types import ComputerUseError
from .geometry import CaptureGeometry, Rect

_BUILD_LOCK = threading.Lock()
_SOURCE = Path(__file__).with_name("NativeCapture.swift")
_CACHE_DIR = Path(CONFIG_DIR) / "computer_use"
_EXECUTABLE = _CACHE_DIR / "native-capture"
_HASH_FILE = _CACHE_DIR / "native-capture.sha256"


def _source_hash() -> str:
    return hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _ensure_helper() -> Path:
    expected_hash = _source_hash()
    with _BUILD_LOCK:
        if (
            _EXECUTABLE.is_file()
            and os.access(_EXECUTABLE, os.X_OK)
            and _HASH_FILE.is_file()
            and _HASH_FILE.read_text().strip() == expected_hash
        ):
            return _EXECUTABLE
        _CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        command = [
            "/usr/bin/xcrun",
            "swiftc",
            "-O",
            "-parse-as-library",
            "-framework",
            "AppKit",
            "-framework",
            "ScreenCaptureKit",
            str(_SOURCE),
            "-o",
            str(_EXECUTABLE),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise ComputerUseError(
                "Failed to build the native ScreenCaptureKit helper. Install "
                f"Xcode Command Line Tools. {result.stderr.strip()}"
            )
        os.chmod(_EXECUTABLE, 0o700)
        _HASH_FILE.write_text(expected_hash)
        os.chmod(_HASH_FILE, 0o600)
    return _EXECUTABLE


def capture_window(app_name: str, target: Path) -> dict[str, Any]:
    helper = _ensure_helper()
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(helper), app_name, str(target)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ComputerUseError(message or "Native window capture failed.")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ComputerUseError("Native capture returned invalid metadata.") from exc
    bounds = payload["window_bounds_points"]
    geometry = CaptureGeometry(
        window_points=Rect(
            float(bounds["x"]),
            float(bounds["y"]),
            float(bounds["width"]),
            float(bounds["height"]),
        ),
        image_width_pixels=int(payload["screenshot_size_pixels"]["width"]),
        image_height_pixels=int(payload["screenshot_size_pixels"]["height"]),
        backing_scale=float(payload["backing_scale"]),
    )
    return {
        "success": True,
        "path": str(target),
        "application": str(payload["application"]),
        "bundle_id": str(payload["bundle_id"]),
        "pid": int(payload["pid"]),
        "window_id": int(payload["window_id"]),
        "window_title": str(payload["window_title"]),
        "geometry": geometry,
    }

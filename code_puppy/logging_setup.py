"""Backend logging configuration utilities.

Provides date-based file logging with weekday in filename, stdout logging,
and retention cleanup for backend log files.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from code_puppy.config import STATE_DIR

_BACKEND_FILE_RE = re.compile(
    r"^backend-(monday|tuesday|wednesday|thursday|friday|saturday|sunday)-(\d{4}-\d{2}-\d{2})\.log$"
)
_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%H:%M:%S"


class DailyBackendFileHandler(logging.Handler):
    """File handler that switches to a new date-based file at midnight.

    Filename format:
      backend-<weekday>-YYYY-MM-DD.log
    """

    def __init__(self, log_dir: Path, retention_days: int, encoding: str = "utf-8"):
        super().__init__()
        self.log_dir = log_dir
        self.retention_days = max(0, retention_days)
        self.encoding = encoding
        self.terminator = "\n"
        self._stream: Any = None
        self._active_date: date | None = None
        self._active_path: Path | None = None

    def _path_for_date(self, d: date) -> Path:
        weekday = d.strftime("%A").lower()
        return self.log_dir / f"backend-{weekday}-{d.isoformat()}.log"

    def _rotate_if_needed(self, now: datetime) -> None:
        today = now.date()
        if self._active_date == today and self._stream is not None:
            return

        self._close_stream()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._active_path = self._path_for_date(today)
        self._stream = self._active_path.open("a", encoding=self.encoding)
        self._active_date = today

        # Run cleanup after opening the current day's stream.
        cleanup_backend_log_files(
            log_dir=self.log_dir,
            retention_days=self.retention_days,
            now=now,
        )

    def _close_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.flush()
            self._stream.close()
        finally:
            self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = datetime.now()
            self._rotate_if_needed(now)
            if self._stream is None:
                return
            msg = self.format(record)
            self._stream.write(msg + self.terminator)
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self._close_stream()
        finally:
            super().close()


def _resolve_log_level(level: int | None = None) -> int:
    if level is not None:
        return level
    raw = (
        (os.getenv("BACKEND_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "INFO")
        .strip()
        .upper()
    )
    return getattr(logging, raw, logging.INFO)


def _resolve_log_dir(log_dir: str | Path | None = None) -> Path:
    if log_dir is not None:
        return Path(log_dir)
    raw = os.getenv("BACKEND_LOG_DIR")
    if raw:
        return Path(raw)
    return Path(STATE_DIR) / "logs"


def _resolve_retention_days(retention_days: int | None = None) -> int:
    if retention_days is not None:
        return max(0, retention_days)
    raw = os.getenv("BACKEND_LOG_RETENTION_DAYS", "7").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 7


def cleanup_backend_log_files(
    *,
    log_dir: str | Path,
    retention_days: int,
    now: datetime | None = None,
) -> list[Path]:
    """Delete backend log files older than retention_days.

    Returns list of removed file paths.
    """
    current = now or datetime.now()
    keep_days = max(1, retention_days)
    cutoff_date = current.date() - timedelta(days=keep_days - 1)
    base = Path(log_dir)
    if not base.exists():
        return []

    removed: list[Path] = []
    for path in base.glob("backend-*.log"):
        match = _BACKEND_FILE_RE.match(path.name)
        if not match:
            continue
        file_date_raw = match.group(2)
        try:
            file_date = date.fromisoformat(file_date_raw)
        except ValueError:
            continue
        if file_date < cutoff_date:
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                # Non-fatal; logging setup should never crash app startup.
                continue
    return removed


def configure_backend_logging(
    *,
    level: int | None = None,
    log_dir: str | Path | None = None,
    retention_days: int | None = None,
) -> int:
    """Configure root logger with stdout + daily backend file logging.

    Safe to call multiple times: it removes/replaces previously installed
    backend handlers to avoid duplicates.

    Returns the resolved integer log level used for backend logging.
    """
    resolved_level = _resolve_log_level(level)
    resolved_log_dir = _resolve_log_dir(log_dir)
    resolved_retention = _resolve_retention_days(retention_days)

    root = logging.getLogger()
    root.setLevel(resolved_level)

    # Remove previous backend-managed handlers to avoid duplicates.
    for handler in list(root.handlers):
        if getattr(handler, "_code_puppy_backend_logging", False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)
    setattr(stream_handler, "_code_puppy_backend_logging", True)
    setattr(stream_handler, "_code_puppy_backend_logging_kind", "stream")
    root.addHandler(stream_handler)

    try:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = DailyBackendFileHandler(
            log_dir=resolved_log_dir,
            retention_days=resolved_retention,
        )
        file_handler.setLevel(resolved_level)
        file_handler.setFormatter(formatter)
        setattr(file_handler, "_code_puppy_backend_logging", True)
        setattr(file_handler, "_code_puppy_backend_logging_kind", "file")
        root.addHandler(file_handler)

        # Also run cleanup at configuration time.
        cleanup_backend_log_files(
            log_dir=resolved_log_dir,
            retention_days=resolved_retention,
        )
    except Exception as exc:
        print(
            f"[code_puppy.logging_setup] backend file logging disabled: {exc}",
            file=sys.stderr,
        )
        root.warning(
            "Backend file logging disabled; continuing with stdout logging only.",
            exc_info=True,
        )

    return resolved_level

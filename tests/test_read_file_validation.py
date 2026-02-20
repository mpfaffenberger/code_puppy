"""Tests for start_line and num_lines validation in _read_file."""

import os
import tempfile
from unittest.mock import MagicMock

from code_puppy.tools.file_operations import _read_file


def _make_context():
    return MagicMock()


def test_start_line_zero_returns_error():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        f.flush()
        try:
            result = _read_file(_make_context(), f.name, start_line=0, num_lines=1)
            assert result.error is not None
            assert "start_line must be >= 1" in result.error
        finally:
            os.unlink(f.name)


def test_start_line_negative_returns_error():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\n")
        f.flush()
        try:
            result = _read_file(_make_context(), f.name, start_line=-5, num_lines=1)
            assert result.error is not None
            assert "start_line must be >= 1" in result.error
        finally:
            os.unlink(f.name)


def test_num_lines_zero_returns_error():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\n")
        f.flush()
        try:
            result = _read_file(_make_context(), f.name, start_line=1, num_lines=0)
            assert result.error is not None
            assert "num_lines must be >= 1" in result.error
        finally:
            os.unlink(f.name)


def test_num_lines_negative_returns_error():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\n")
        f.flush()
        try:
            result = _read_file(_make_context(), f.name, start_line=1, num_lines=-3)
            assert result.error is not None
            assert "num_lines must be >= 1" in result.error
        finally:
            os.unlink(f.name)


def test_valid_start_line_still_works():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        f.flush()
        try:
            result = _read_file(_make_context(), f.name, start_line=2, num_lines=1)
            assert result.error is None
            assert "line2" in result.content
        finally:
            os.unlink(f.name)

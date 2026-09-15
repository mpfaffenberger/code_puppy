"""Tests for AGENTS.md encoding detection in ``_builder``.

Regression for the Windows crash: ``echo hi > AGENTS.md`` in PowerShell
writes UTF-16 LE with a BOM. A plain ``utf-8-sig`` read raised
``UnicodeDecodeError`` and killed the agent run.
"""

from unittest.mock import patch

import pytest

from code_puppy.agents import _builder
from code_puppy.agents._builder import _read_rules_text, load_puppy_rules


@pytest.mark.parametrize(
    "encoding",
    ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"],
)
def test_read_rules_text_decodes_bom_encodings(tmp_path, encoding):
    """Decode BOM-prefixed UTF-16/UTF-32 files without a crash."""
    path = tmp_path / "AGENTS.md"
    path.write_bytes("\ufeffhello rules".encode(encoding))
    assert _read_rules_text(path) == "hello rules"


def test_read_rules_text_decodes_powershell_redirect(tmp_path):
    """Reproduce the exact PowerShell ``echo test > AGENTS.md`` bytes."""
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"\xff\xfe" + "test\r\n".encode("utf-16-le"))
    assert _read_rules_text(path) == "test\r\n"


def test_read_rules_text_decodes_utf8_with_bom(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"\xef\xbb\xbfplain utf8 sig")
    assert _read_rules_text(path) == "plain utf8 sig"


def test_read_rules_text_decodes_plain_utf8(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_text("no bom here", encoding="utf-8")
    assert _read_rules_text(path) == "no bom here"


def test_read_rules_text_replaces_invalid_bytes(tmp_path):
    """Garbage bytes must not raise. Bad bytes become U+FFFD."""
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"ok \x80\x81 bad")
    result = _read_rules_text(path)
    assert result is not None
    assert result.startswith("ok ")
    assert "\ufffd" in result


def test_read_rules_text_returns_none_for_missing_file(tmp_path):
    assert _read_rules_text(tmp_path / "nope.md") is None


def test_load_puppy_rules_survives_utf16_agents_md(tmp_path, monkeypatch):
    """End-to-end: a UTF-16 project AGENTS.md must load, not crash."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_bytes(
        b"\xff\xfe" + "utf16 project rules".encode("utf-16-le")
    )
    empty_config = tmp_path / "empty_config"
    empty_config.mkdir()
    with patch.object(_builder, "CONFIG_DIR", str(empty_config)):
        rules = load_puppy_rules()
    assert rules is not None
    assert "utf16 project rules" in rules

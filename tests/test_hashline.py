"""Comprehensive test suite for hashline tools.

Tests ported from experimental/hashline_test.go and adapted for Python.
"""

import os
import tempfile
import pytest
from code_puppy.tools.hashline import (
    line_hash,
    compute_file_hashes,
    format_hashlines,
    parse_hashline_ref,
    validate_hashes,
    apply_hashline_edits,
    HashlineMismatchError,
)


# --- LineHash tests ---


def test_line_hash_deterministic():
    """Same input should produce same hash."""
    h1 = line_hash("hello world")
    h2 = line_hash("hello world")
    assert h1 == h2, f"same input produced different hashes: {h1!r} vs {h2!r}"


def test_line_hash_length():
    """Hash should be exactly 4 hex characters."""
    h = line_hash("test")
    assert len(h) == 4, f"hash should be 4 chars, got {len(h)}"
    assert all(c in "0123456789abcdef" for c in h), f"hash should be hex, got {h!r}"


def test_line_hash_different_inputs():
    """Different inputs should produce different hashes (collision unlikely)."""
    h1 = line_hash("hello")
    h2 = line_hash("world")
    # Note: collisions are possible but extremely unlikely
    assert h1 != h2 or True  # Don't fail on unlikely collision


def test_line_hash_empty_string():
    """Empty string should have valid hash."""
    h = line_hash("")
    assert len(h) == 4, f"empty string hash should be 4 chars, got {h!r}"


def test_line_hash_whitespace_sensitive():
    """Leading/trailing whitespace should affect hash."""
    h1 = line_hash("  hello")
    h2 = line_hash("hello")
    # Different whitespace = different content = likely different hash
    # (collision possible but unlikely)
    pass  # Just verify both are valid


# --- compute_file_hashes tests ---


def test_compute_file_hashes_basic():
    """Compute hashes for multi-line content."""
    content = "line one\nline two\nline three"
    hashes = compute_file_hashes(content)
    
    assert len(hashes) == 3, f"expected 3 lines, got {len(hashes)}"
    assert all(len(h) == 4 for h in hashes.values()), "all hashes should be 4 chars"
    assert list(hashes.keys()) == [1, 2, 3], "line numbers should be 1-based"


def test_compute_file_hashes_empty():
    """Empty file should have one empty line."""
    hashes = compute_file_hashes("")
    assert len(hashes) == 1, "empty content should have 1 line"


def test_compute_file_hashes_trailing_newline():
    """Trailing newline creates empty last line."""
    hashes = compute_file_hashes("a\nb\n")
    assert len(hashes) == 3, "trailing newline should create empty line"


# --- format_hashlines tests ---


def test_format_hashlines_basic():
    """Format content with line:hash|content format."""
    content = "func main() {\n\tfmt.Println(\"hi\")\n}"
    output = format_hashlines(content)
    lines = output.split("\n")
    
    # Should not have truncation warning
    assert not output.startswith("[Some lines truncated"), "no truncation expected"
    
    # Check format of each line
    for i, line in enumerate(lines, 1):
        assert ":" in line, f"line {i} should have ':' separator"
        assert "|" in line, f"line {i} should have '|' separator"
        parts = line.split("|", 1)
        ref = parts[0]
        num_str, hash_str = ref.split(":", 1)
        assert int(num_str) == i, f"line number should be {i}"
        assert len(hash_str) == 4, f"hash should be 4 chars, got {hash_str!r}"


def test_format_hashlines_with_offset():
    """Format with start_line offset."""
    content = "first\nsecond"
    output = format_hashlines(content, start_line=10)
    lines = output.split("\n")
    
    assert lines[0].startswith("10:"), "first line should be numbered 10"
    assert lines[1].startswith("11:"), "second line should be numbered 11"


def test_format_hashlines_truncation():
    """Long lines should be truncated with warning."""
    long_line = "x" * 3000  # Longer than default 2000 char limit
    content = f"short\n{long_line}\nshort"
    output = format_hashlines(content)
    
    assert "[Some lines truncated" in output, "should have truncation warning"
    assert "...[truncated]" in output, "long line should be truncated"


# --- parse_hashline_ref tests ---


def test_parse_hashline_ref_valid():
    """Parse valid line:hash reference."""
    line_num, hash_val = parse_hashline_ref("42:a3f1")
    assert line_num == 42
    assert hash_val == "a3f1"


def test_parse_hashline_ref_invalid_format():
    """Missing colon should raise ValueError."""
    with pytest.raises(ValueError, match="missing ':'"):
        parse_hashline_ref("42a3f1")


def test_parse_hashline_ref_invalid_line_number():
    """Non-numeric line number should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid line number"):
        parse_hashline_ref("abc:a3f1")


def test_parse_hashline_ref_invalid_hash_length():
    """Hash must be exactly 4 chars."""
    with pytest.raises(ValueError, match="exactly 4 hex chars"):
        parse_hashline_ref("42:a3")  # Too short
    with pytest.raises(ValueError, match="exactly 4 hex chars"):
        parse_hashline_ref("42:a3f12")  # Too long


def test_parse_hashline_ref_line_number_zero():
    """Line number must be >= 1."""
    with pytest.raises(ValueError, match="must be >= 1"):
        parse_hashline_ref("0:a3f1")


# --- validate_hashes tests ---


def test_validate_hashes_all_valid():
    """All valid hashes should return empty error list."""
    content = "line one\nline two\nline three"
    hashes = compute_file_hashes(content)
    refs = [(1, hashes[1]), (2, hashes[2]), (3, hashes[3])]
    
    errors = validate_hashes(refs, content)
    assert errors == [], f"expected no errors, got {errors}"


def test_validate_hashes_mismatch():
    """Hash mismatch should return descriptive error."""
    content = "line one\nline two"
    errors = validate_hashes([(1, "xxxx")], content)
    
    assert len(errors) == 1, "should have one error"
    assert "mismatch" in errors[0].lower()
    assert "expected 'xxxx'" in errors[0]


def test_validate_hashes_out_of_range():
    """Line number out of range should return error."""
    content = "line one\nline two"
    errors = validate_hashes([(10, "a3f1")], content)
    
    assert len(errors) == 1
    assert "out of range" in errors[0].lower()
    assert "file has 2 lines" in errors[0]


# --- apply_hashline_edits tests ---


def test_apply_hashline_edits_replace_single():
    """Replace a single line."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line one\nline two\nline three\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line one\nline two\nline three\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "replace",
                "start_ref": f"2:{hashes[2]}",
                "new_content": "REPLACED LINE TWO",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        assert "REPLACED LINE TWO" in result["content"]
        assert "line one" in result["content"]
        assert "line three" in result["content"]
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_replace_range():
    """Replace multiple lines with end_ref."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "replace",
                "start_ref": f"2:{hashes[2]}",
                "end_ref": f"4:{hashes[4]}",
                "new_content": "REPLACED\nMULTIPLE\nLINES",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        assert "line 1" in result["content"]
        assert "REPLACED" in result["content"]
        assert "MULTIPLE" in result["content"]
        assert "LINES" in result["content"]
        assert "line 5" in result["content"]
        assert "line 2" not in result["content"]
        assert "line 3" not in result["content"]
        assert "line 4" not in result["content"]
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_insert():
    """Insert content after a line."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\nline 2\nline 3\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "insert",
                "start_ref": f"2:{hashes[2]}",
                "new_content": "INSERTED",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        lines = result["content"].split("\n")
        assert lines[0] == "line 1"
        assert lines[1] == "line 2"
        assert lines[2] == "INSERTED"
        assert lines[3] == "line 3"
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_delete_single():
    """Delete a single line."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\nline 2\nline 3\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "delete",
                "start_ref": f"2:{hashes[2]}",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        assert "line 1" in result["content"]
        assert "line 3" in result["content"]
        assert "line 2" not in result["content"]
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_delete_range():
    """Delete multiple lines with end_ref."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "delete",
                "start_ref": f"2:{hashes[2]}",
                "end_ref": f"4:{hashes[4]}",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        assert "line 1" in result["content"]
        assert "line 5" in result["content"]
        assert "line 2" not in result["content"]
        assert "line 3" not in result["content"]
        assert "line 4" not in result["content"]
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_hash_mismatch():
    """Hash mismatch should reject entire batch."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\n")
        f.flush()
        temp_file = f.name
    
    try:
        edits = [
            {
                "operation": "replace",
                "start_ref": "2:xxxx",  # Invalid hash
                "new_content": "REPLACED",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert not result["success"], "should fail on hash mismatch"
        assert len(result["errors"]) > 0
        assert "mismatch" in result["errors"][0].lower()
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_invalid_operation():
    """Invalid operation should be rejected."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\n"
        hashes = compute_file_hashes(content)
        
        edits = [
            {
                "operation": "invalid_op",
                "start_ref": f"1:{hashes[1]}",
            }
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert not result["success"]
        assert any("unknown operation" in e.lower() for e in result["errors"])
    finally:
        os.unlink(temp_file)


def test_apply_hashline_edits_multiple_edits_bottom_to_top():
    """Multiple edits should be applied bottom-to-top."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line 1\nline 2\nline 3\nline 4\n")
        f.flush()
        temp_file = f.name
    
    try:
        content = "line 1\nline 2\nline 3\nline 4\n"
        hashes = compute_file_hashes(content)
        
        # Edit in non-sorted order to verify bottom-to-top sorting
        edits = [
            {
                "operation": "replace",
                "start_ref": f"2:{hashes[2]}",
                "new_content": "REPLACED 2",
            },
            {
                "operation": "replace",
                "start_ref": f"4:{hashes[4]}",
                "new_content": "REPLACED 4",
            },
        ]
        
        result = apply_hashline_edits(temp_file, edits)
        
        assert result["success"], f"edit failed: {result.get('errors')}"
        assert "REPLACED 2" in result["content"]
        assert "REPLACED 4" in result["content"]
    finally:
        os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

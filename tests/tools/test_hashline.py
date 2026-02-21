"""Comprehensive tests for code_puppy.tools.hashline."""

from __future__ import annotations

import hashlib
import textwrap

import pytest

from code_puppy.tools.hashline import (
    _CACHE_MAX,
    HashlineMismatchError,
    _hashline_cache,
    apply_hashline_edits,
    cache_file_hashes,
    compute_file_hashes,
    format_hashlines,
    get_cached_hashes,
    invalidate_cache,
    line_hash,
    parse_hashline_ref,
    validate_hashes,
)

# ── helpers ───────────────────────────────────────────────────────────────

SAMPLE_CONTENT = textwrap.dedent("""\
    def hello():
        return "world"

    def goodbye():
        return "moon"
""")
"""Five-line sample with a trailing newline."""


def _expected_hash(text: str) -> str:
    """Mirror the production algorithm so tests stay in sync."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:2]


def _write(tmp_path, content: str, name: str = "f.py") -> str:
    """Write *content* to a temp file, return its path as a string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_ref(content: str, line: int) -> str:
    """Build a valid hashline ref like '2:ab' from *content*."""
    hashes = compute_file_hashes(content)
    return f"{line}:{hashes[line]}"


# ── 1. line_hash ──────────────────────────────────────────────────────────


class TestLineHash:
    def test_deterministic(self):
        assert line_hash("hello") == line_hash("hello")

    def test_two_char_hex(self):
        h = line_hash("anything")
        assert len(h) == 2
        int(h, 16)  # must be valid hex – raises ValueError otherwise

    def test_different_inputs_differ(self):
        # Not *guaranteed* for all inputs (2-char = 256 buckets) but these
        # specific strings are known to differ.
        assert line_hash("alpha") != line_hash("beta")

    def test_empty_string(self):
        h = line_hash("")
        assert len(h) == 2

    def test_matches_sha256_prefix(self):
        raw = "test line"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:2]
        assert line_hash(raw) == expected


# ── 2. compute_file_hashes ────────────────────────────────────────────────


class TestComputeFileHashes:
    def test_one_based_keys(self):
        hashes = compute_file_hashes("a\nb\nc")
        assert set(hashes.keys()) == {1, 2, 3}

    def test_correct_hashes(self):
        hashes = compute_file_hashes("a\nb")
        assert hashes[1] == _expected_hash("a")
        assert hashes[2] == _expected_hash("b")

    def test_single_line_no_newline(self):
        hashes = compute_file_hashes("only")
        assert hashes == {1: _expected_hash("only")}

    def test_empty_content(self):
        assert compute_file_hashes("") == {}

    def test_trailing_newline_not_extra_line(self):
        # "a\n" splits to ["a"] – only 1 line
        hashes = compute_file_hashes("a\n")
        assert len(hashes) == 1


# ── 3. format_hashlines ──────────────────────────────────────────────────


class TestFormatHashlines:
    def test_basic_format(self):
        out = format_hashlines("foo\nbar")
        lines = out.splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("1:")
        assert "|foo" in lines[0]
        assert lines[1].startswith("2:")
        assert "|bar" in lines[1]

    def test_empty_line_in_middle(self):
        out = format_hashlines("a\n\nb")
        lines = out.splitlines()
        assert len(lines) == 3
        # Middle line is empty content but still has hash prefix
        assert lines[1].startswith("2:")
        assert lines[1].endswith("|")

    def test_single_line(self):
        out = format_hashlines("only")
        assert out.startswith("1:")
        assert "|only" in out
        assert "\n" not in out

    def test_roundtrip_hash_matches(self):
        """Hash embedded in formatted output must match compute_file_hashes."""
        content = "x\ny\nz"
        formatted = format_hashlines(content)
        hashes = compute_file_hashes(content)
        for line in formatted.splitlines():
            ref_part, _sep, _content = line.partition("|")
            line_num, h = ref_part.split(":")
            assert hashes[int(line_num)] == h


# ── 4. parse_hashline_ref ────────────────────────────────────────────────


class TestParseHashlineRef:
    def test_valid(self):
        assert parse_hashline_ref("2:f1") == (2, "f1")
        assert parse_hashline_ref("100:ab") == (100, "ab")

    def test_missing_colon(self):
        with pytest.raises(ValueError, match="missing ':'"):
            parse_hashline_ref("2f1")

    def test_bad_line_number(self):
        with pytest.raises(ValueError, match="Invalid line number"):
            parse_hashline_ref("abc:f1")

    def test_zero_line_number(self):
        with pytest.raises(ValueError, match=">= 1"):
            parse_hashline_ref("0:ab")

    def test_negative_line_number(self):
        with pytest.raises(ValueError, match=">= 1"):
            parse_hashline_ref("-1:ab")

    def test_wrong_hash_length_short(self):
        with pytest.raises(ValueError, match="exactly 2 hex chars"):
            parse_hashline_ref("1:a")

    def test_wrong_hash_length_long(self):
        with pytest.raises(ValueError, match="exactly 2 hex chars"):
            parse_hashline_ref("1:abc")


# ── 5. validate_hashes ───────────────────────────────────────────────────


class TestValidateHashes:
    def test_all_valid(self):
        content = "one\ntwo\nthree"
        hashes = compute_file_hashes(content)
        refs = [(ln, h) for ln, h in hashes.items()]
        assert validate_hashes(refs, content) == []

    def test_mismatch_detected(self):
        content = "one\ntwo"
        errors = validate_hashes([(1, "zz")], content)
        assert len(errors) == 1
        assert "expected hash 'zz'" in errors[0]

    def test_out_of_range(self):
        content = "one\ntwo"
        errors = validate_hashes([(99, "ab")], content)
        assert len(errors) == 1
        assert "out of range" in errors[0]

    def test_mixed_valid_and_invalid(self):
        content = "a\nb"
        hashes = compute_file_hashes(content)
        refs = [(1, hashes[1]), (2, "zz")]  # first valid, second bad
        errors = validate_hashes(refs, content)
        assert len(errors) == 1


# ── 6. HashlineMismatchError ─────────────────────────────────────────────


class TestHashlineMismatchError:
    def test_attributes(self):
        err = HashlineMismatchError(
            line=5, expected_hash="ab", actual_hash="cd", actual_content="hello"
        )
        assert err.line == 5
        assert err.expected_hash == "ab"
        assert err.actual_hash == "cd"
        assert err.actual_content == "hello"

    def test_message(self):
        err = HashlineMismatchError(
            line=3, expected_hash="ab", actual_hash="cd", actual_content="x"
        )
        msg = str(err)
        assert "Line 3" in msg
        assert "'ab'" in msg
        assert "'cd'" in msg

    def test_is_exception(self):
        assert issubclass(HashlineMismatchError, Exception)


# ── 7. LRU cache ─────────────────────────────────────────────────────────


class TestLRUCache:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Ensure every test starts with an empty cache."""
        _hashline_cache.clear()
        yield
        _hashline_cache.clear()

    def test_store_and_retrieve(self):
        hashes = {1: "ab", 2: "cd"}
        cache_file_hashes("/tmp/a.py", hashes)
        assert get_cached_hashes("/tmp/a.py") == hashes

    def test_miss_returns_none(self):
        assert get_cached_hashes("/nope") is None

    def test_invalidate(self):
        cache_file_hashes("/tmp/b.py", {1: "ee"})
        invalidate_cache("/tmp/b.py")
        assert get_cached_hashes("/tmp/b.py") is None

    def test_invalidate_missing_key_is_noop(self):
        invalidate_cache("/does/not/exist")  # should not raise

    def test_overwrite_existing_key(self):
        cache_file_hashes("/tmp/c.py", {1: "aa"})
        cache_file_hashes("/tmp/c.py", {1: "bb"})
        assert get_cached_hashes("/tmp/c.py") == {1: "bb"}

    def test_eviction_at_max_capacity(self):
        # Fill to max
        for i in range(_CACHE_MAX):
            cache_file_hashes(f"/f/{i}", {1: f"{i:02x}"[:2]})

        # The first entry should still be present
        assert get_cached_hashes("/f/0") is not None

        # Adding one more should evict the oldest (which is now /f/1
        # because /f/0 was just accessed by the get above, moving it to end)
        cache_file_hashes("/f/overflow", {1: "zz"})
        assert len(_hashline_cache) == _CACHE_MAX
        # /f/1 was the LRU item after we accessed /f/0
        assert get_cached_hashes("/f/1") is None


# ── 8. apply_hashline_edits ──────────────────────────────────────────────


class TestApplyHashlineEdits:
    """Integration tests that hit the filesystem via tmp_path."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _hashline_cache.clear()
        yield
        _hashline_cache.clear()

    # -- replace single line -------------------------------------------

    def test_replace_single_line(self, tmp_path):
        content = "aaa\nbbb\nccc\n"
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 2)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": ref, "new_content": "BBB"},
            ],
        )

        assert result["success"] is True
        assert "BBB" in result["content"]
        assert "bbb" not in result["content"]
        # File on disk should match
        assert open(fp).read() == result["content"]

    # -- replace_range -------------------------------------------------

    def test_replace_range(self, tmp_path):
        content = "line1\nline2\nline3\nline4\nline5\n"
        fp = _write(tmp_path, content)
        start = _make_ref(content, 2)
        end = _make_ref(content, 4)

        result = apply_hashline_edits(
            fp,
            [
                {
                    "operation": "replace_range",
                    "start_ref": start,
                    "end_ref": end,
                    "new_content": "REPLACED",
                },
            ],
        )

        assert result["success"] is True
        lines = result["content"].splitlines()
        assert lines == ["line1", "REPLACED", "line5"]

    # -- insert_after --------------------------------------------------

    def test_insert_after(self, tmp_path):
        content = "first\nsecond\nthird\n"
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 1)

        result = apply_hashline_edits(
            fp,
            [
                {
                    "operation": "insert_after",
                    "start_ref": ref,
                    "new_content": "inserted",
                },
            ],
        )

        assert result["success"] is True
        lines = result["content"].splitlines()
        assert lines == ["first", "inserted", "second", "third"]

    # -- delete single line --------------------------------------------

    def test_delete_single_line(self, tmp_path):
        content = "keep\nremove\nkeep2\n"
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 2)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "delete", "start_ref": ref, "new_content": ""},
            ],
        )

        assert result["success"] is True
        assert result["content"].splitlines() == ["keep", "keep2"]

    # -- delete_range --------------------------------------------------

    def test_delete_range(self, tmp_path):
        content = "a\nb\nc\nd\ne\n"
        fp = _write(tmp_path, content)
        start = _make_ref(content, 2)
        end = _make_ref(content, 4)

        result = apply_hashline_edits(
            fp,
            [
                {
                    "operation": "delete_range",
                    "start_ref": start,
                    "end_ref": end,
                    "new_content": "",
                },
            ],
        )

        assert result["success"] is True
        assert result["content"].splitlines() == ["a", "e"]

    # -- staleness rejection -------------------------------------------

    def test_stale_hash_rejected(self, tmp_path):
        original = "aaa\nbbb\nccc\n"
        fp = _write(tmp_path, original)
        ref = _make_ref(original, 2)  # hash computed against "bbb"

        # Mutate the file *after* computing the ref
        (tmp_path / "f.py").write_text("aaa\nXXX\nccc\n", encoding="utf-8")

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": ref, "new_content": "new"},
            ],
        )

        assert result["success"] is False
        assert len(result["errors"]) >= 1
        assert "expected hash" in result["errors"][0]

    # -- overlapping edits → error -------------------------------------

    def test_overlapping_edits_rejected(self, tmp_path):
        content = "a\nb\nc\nd\n"
        fp = _write(tmp_path, content)

        result = apply_hashline_edits(
            fp,
            [
                {
                    "operation": "replace",
                    "start_ref": _make_ref(content, 2),
                    "new_content": "X",
                },
                {
                    "operation": "replace",
                    "start_ref": _make_ref(content, 2),
                    "new_content": "Y",
                },
            ],
        )

        assert result["success"] is False
        assert any("overlaps" in e.lower() for e in result["errors"])

    # -- out-of-range line → error -------------------------------------

    def test_out_of_range_line(self, tmp_path):
        content = "one\ntwo\n"
        fp = _write(tmp_path, content)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": "99:ab", "new_content": "nope"},
            ],
        )

        assert result["success"] is False
        assert any("out of range" in e for e in result["errors"])

    # -- file not found → error ----------------------------------------

    def test_file_not_found(self, tmp_path):
        result = apply_hashline_edits(
            str(tmp_path / "ghost.py"),
            [{"operation": "replace", "start_ref": "1:ab", "new_content": "x"}],
        )

        assert result["success"] is False
        assert len(result["errors"]) >= 1

    # -- trailing newline preserved ------------------------------------

    def test_preserves_trailing_newline(self, tmp_path):
        content = "aaa\nbbb\n"
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 1)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": ref, "new_content": "AAA"},
            ],
        )

        assert result["success"] is True
        assert result["content"].endswith("\n")

    def test_no_trailing_newline_when_original_lacks_it(self, tmp_path):
        content = "aaa\nbbb"  # no trailing newline
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 1)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": ref, "new_content": "AAA"},
            ],
        )

        assert result["success"] is True
        assert not result["content"].endswith("\n")

    # -- unknown operation → error -------------------------------------

    def test_unknown_operation(self, tmp_path):
        content = "a\nb\n"
        fp = _write(tmp_path, content)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "yeet", "start_ref": "1:ab", "new_content": "x"},
            ],
        )

        assert result["success"] is False
        assert any("unknown operation" in e for e in result["errors"])

    # -- multi-line new_content ----------------------------------------

    def test_replace_with_multiple_lines(self, tmp_path):
        content = "a\nb\nc\n"
        fp = _write(tmp_path, content)
        ref = _make_ref(content, 2)

        result = apply_hashline_edits(
            fp,
            [
                {"operation": "replace", "start_ref": ref, "new_content": "x\ny\nz"},
            ],
        )

        assert result["success"] is True
        assert result["content"].splitlines() == ["a", "x", "y", "z", "c"]

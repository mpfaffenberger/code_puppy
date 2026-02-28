"""Tests for code_puppy/command_line/attachments.py — targeting 100% coverage."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.attachments import (
    MAX_PATH_LENGTH,
    AttachmentParsingError,
    PromptLinkAttachment,
    _candidate_paths,
    _detect_path_tokens,
    _DetectedPath,
    _determine_media_type,
    _is_probable_path,
    _is_supported_extension,
    _load_binary,
    _normalise_path,
    _parse_link,
    _strip_attachment_token,
    _tokenise,
    _unescape_dragged_path,
    parse_prompt_attachments,
)


# ---------------------------------------------------------------------------
# _is_probable_path
# ---------------------------------------------------------------------------
class TestIsProbablePath:
    def test_empty(self):
        assert _is_probable_path("") is False

    def test_too_long(self):
        assert _is_probable_path("a" * (MAX_PATH_LENGTH + 1)) is False

    def test_hash_prefix(self):
        assert _is_probable_path("#comment") is False

    def test_absolute_unix(self):
        assert _is_probable_path("/tmp/foo.png") is True

    def test_tilde(self):
        assert _is_probable_path("~/pic.png") is True

    def test_dot_slash(self):
        assert _is_probable_path("./pic.png") is True

    def test_dot_dot_slash(self):
        assert _is_probable_path("../pic.png") is True

    def test_windows_drive(self):
        assert _is_probable_path("C:foo") is True

    def test_contains_sep(self):
        assert _is_probable_path(f"a{os.sep}b") is True

    def test_contains_quote(self):
        assert _is_probable_path('a"b') is True

    def test_plain_word(self):
        # No sep, no quote, no special prefix
        assert _is_probable_path("hello") is False


# ---------------------------------------------------------------------------
# _unescape_dragged_path
# ---------------------------------------------------------------------------
def test_unescape_dragged_path():
    assert _unescape_dragged_path(r"my\ file.png") == "my file.png"
    assert _unescape_dragged_path("noescape") == "noescape"


# ---------------------------------------------------------------------------
# _normalise_path
# ---------------------------------------------------------------------------
def test_normalise_path_expands_user():
    p = _normalise_path("~/foo.png")
    assert p.is_absolute()
    assert "foo.png" in str(p)


def test_normalise_path_invalid():
    with patch(
        "code_puppy.command_line.attachments.Path.absolute",
        side_effect=ValueError("bad"),
    ):
        with pytest.raises(AttachmentParsingError, match="Invalid path"):
            _normalise_path("some_token")


# ---------------------------------------------------------------------------
# _determine_media_type
# ---------------------------------------------------------------------------
def test_determine_media_type_known():
    assert "image" in _determine_media_type(Path("pic.png"))


def test_determine_media_type_unknown_image_ext():
    # .webp might not be in mimetypes on all systems, but is in our set
    # Use a definitely-unknown extension that's also in our accepted set
    with patch(
        "code_puppy.command_line.attachments.mimetypes.guess_type",
        return_value=(None, None),
    ):
        # suffix in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS -> "image/png"
        assert _determine_media_type(Path("pic.bmp")) == "image/png"


def test_determine_media_type_totally_unknown():
    with patch(
        "code_puppy.command_line.attachments.mimetypes.guess_type",
        return_value=(None, None),
    ):
        assert _determine_media_type(Path("file.xyz123")) == "application/octet-stream"


# ---------------------------------------------------------------------------
# _load_binary
# ---------------------------------------------------------------------------
def test_load_binary_not_found(tmp_path):
    with pytest.raises(AttachmentParsingError, match="not found"):
        _load_binary(tmp_path / "nope.png")


def test_load_binary_permission_error(tmp_path):
    f = tmp_path / "secret.png"
    f.write_bytes(b"x")
    with patch.object(Path, "read_bytes", side_effect=PermissionError("no")):
        with pytest.raises(AttachmentParsingError, match="permission denied"):
            _load_binary(f)


def test_load_binary_os_error(tmp_path):
    f = tmp_path / "bad.png"
    f.write_bytes(b"x")
    with patch.object(Path, "read_bytes", side_effect=OSError("disk")):
        with pytest.raises(AttachmentParsingError, match="Failed to read"):
            _load_binary(f)


def test_load_binary_success(tmp_path):
    f = tmp_path / "ok.png"
    f.write_bytes(b"hello")
    assert _load_binary(f) == b"hello"


# ---------------------------------------------------------------------------
# _tokenise
# ---------------------------------------------------------------------------
def test_tokenise_empty():
    assert list(_tokenise("")) == []


def test_tokenise_normal():
    tokens = list(_tokenise("hello world"))
    assert tokens == ["hello", "world"]


def test_tokenise_fallback_on_bad_quotes():
    # Unmatched quote triggers fallback
    tokens = list(_tokenise('hello "world'))
    assert len(tokens) >= 2


@patch("code_puppy.command_line.attachments.os.name", "nt")
def test_tokenise_windows_mode():
    tokens = list(_tokenise("hello world"))
    assert tokens == ["hello", "world"]


# ---------------------------------------------------------------------------
# _strip_attachment_token
# ---------------------------------------------------------------------------
def test_strip_attachment_token():
    assert _strip_attachment_token("  (file.png),  ") == "file.png"


# ---------------------------------------------------------------------------
# _candidate_paths
# ---------------------------------------------------------------------------
def test_candidate_paths():
    tokens = ["my", "long", "path"]
    results = list(_candidate_paths(tokens, 0, max_span=3))
    assert results[0] == ("my", 1)
    assert results[1] == ("my long", 2)
    assert results[2] == ("my long path", 3)


# ---------------------------------------------------------------------------
# _is_supported_extension
# ---------------------------------------------------------------------------
def test_is_supported_extension():
    assert _is_supported_extension(Path("a.png")) is True
    assert _is_supported_extension(Path("a.PNG")) is True
    assert _is_supported_extension(Path("a.txt")) is False


# ---------------------------------------------------------------------------
# _parse_link
# ---------------------------------------------------------------------------
def test_parse_link_always_none():
    assert _parse_link("https://example.com/pic.png") is None


# ---------------------------------------------------------------------------
# _DetectedPath.has_path
# ---------------------------------------------------------------------------
def test_detected_path_has_path():
    d = _DetectedPath(placeholder="x", path=Path("x"), start_index=0, consumed_until=1)
    assert d.has_path() is True

    d2 = _DetectedPath(placeholder="x", path=None, start_index=0, consumed_until=1)
    assert d2.has_path() is False

    d3 = _DetectedPath(
        placeholder="x",
        path=Path("x"),
        start_index=0,
        consumed_until=1,
        unsupported=True,
    )
    assert d3.has_path() is False


# ---------------------------------------------------------------------------
# _detect_path_tokens
# ---------------------------------------------------------------------------
class TestDetectPathTokens:
    def test_empty_prompt(self):
        detections, warnings = _detect_path_tokens("")
        assert detections == []
        assert warnings == []

    def test_no_paths(self):
        detections, warnings = _detect_path_tokens("just some text")
        assert detections == []

    def test_existing_supported_file(self, tmp_path):
        f = tmp_path / "pic.png"
        f.write_bytes(b"img")
        detections, warnings = _detect_path_tokens(str(f))
        assert len(detections) == 1
        assert detections[0].path is not None
        assert not detections[0].unsupported

    def test_existing_unsupported_ext(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"a,b")
        detections, warnings = _detect_path_tokens(str(f))
        assert len(detections) == 1
        assert detections[0].unsupported is True

    def test_nonexistent_path_skipped(self):
        detections, _ = _detect_path_tokens("/nonexistent/path/to/file.png")
        assert detections == []

    def test_path_normalise_error(self):
        # Token that looks like a path but triggers normalise error
        with patch(
            "code_puppy.command_line.attachments._normalise_path",
            side_effect=AttachmentParsingError("bad"),
        ):
            detections, warnings = _detect_path_tokens("/some/path")
            assert len(warnings) == 1

    def test_os_error_on_exists(self, tmp_path):
        """path.exists() raises OSError -> skip token."""
        with patch("pathlib.Path.exists", side_effect=OSError("ENAMETOOLONG")):
            detections, _ = _detect_path_tokens("/some/path.png")
            assert detections == []

    def test_stripped_token_too_long(self):
        """Token that passes _is_probable_path but stripped version > MAX_PATH_LENGTH."""
        long_token = "/" + "a" * (MAX_PATH_LENGTH + 1)
        detections, _ = _detect_path_tokens(long_token)
        assert detections == []

    def test_multi_token_path(self, tmp_path):
        """Path with spaces reconstructed from multiple tokens."""
        d = tmp_path / "my dir"
        d.mkdir()
        f = d / "pic.png"
        f.write_bytes(b"img")
        # Use the path with escaped space
        prompt = str(f).replace(" ", r"\ ")
        detections, _ = _detect_path_tokens(prompt)
        assert any(not d.unsupported for d in detections)

    def test_candidate_path_normalise_error_in_span(self, tmp_path):
        """_normalise_path fails during candidate span search -> break."""
        # A path that doesn't exist triggers span search; if normalise fails in span, break
        original_normalise = _normalise_path
        call_count = [0]

        def patched(token):
            call_count[0] += 1
            if call_count[0] > 1:
                raise AttachmentParsingError("bad span")
            return original_normalise(token)

        with patch(
            "code_puppy.command_line.attachments._normalise_path", side_effect=patched
        ):
            detections, _ = _detect_path_tokens("/nonexistent/foo bar baz")
            # Should not crash

    def test_candidate_path_os_error_in_span(self):
        """OSError during span exists() check -> continue."""
        call_count = [0]

        def patched_exists(self):
            call_count[0] += 1
            if call_count[0] > 1:
                raise OSError("bad")
            return False

        with patch.object(Path, "exists", patched_exists):
            detections, _ = _detect_path_tokens("/nonexistent/foo bar")

    def test_candidate_span_not_probable_path(self):
        """Joined tokens where _is_probable_path returns False for the join."""
        # First token looks like path, second doesn't form a probable path when joined
        # This is tricky - we just need to hit the `continue` in the span loop
        detections, _ = _detect_path_tokens("/nonexistent/file.png hello")
        assert detections == []

    def test_candidate_span_too_long(self):
        """Joined candidate exceeds MAX_PATH_LENGTH -> continue."""
        long_part = "a" * (MAX_PATH_LENGTH - 5)
        detections, _ = _detect_path_tokens(f"/x/{long_part} extra")
        assert detections == []

    def test_link_attachment_detection(self):
        """When _parse_link returns a link, it's added as detection."""
        mock_link = PromptLinkAttachment(
            placeholder="http://x.com/img.png", url_part=MagicMock()
        )
        with patch(
            "code_puppy.command_line.attachments._parse_link", return_value=mock_link
        ):
            detections, _ = _detect_path_tokens("http://x.com/img.png")
            assert len(detections) == 1
            assert detections[0].link is mock_link

    def test_stripped_token_exceeds_max_in_main_loop(self):
        """Stripped token > MAX_PATH_LENGTH in main loop (line 222-223).

        This is a defensive guard after _is_probable_path. We mock _is_probable_path
        to return True for a long token to reach the guard.
        """
        long_path = "/" + "a" * (MAX_PATH_LENGTH + 1)
        orig = _is_probable_path

        def patched(token):
            if len(token) > MAX_PATH_LENGTH:
                return True  # bypass the length check in _is_probable_path
            return orig(token)

        with patch(
            "code_puppy.command_line.attachments._is_probable_path", side_effect=patched
        ):
            detections, _ = _detect_path_tokens(long_path)
            assert detections == []

    def test_multi_token_span_found_existing_file(self, tmp_path):
        """Multi-token path where span search finds an existing file (lines 274-277, 285-287)."""
        d = tmp_path / "my dir"
        d.mkdir()
        f = d / "pic.png"
        f.write_bytes(b"imgdata")
        # Use space-separated tokens (not escaped) so shlex splits them
        # The first token alone won't exist, but joined tokens will
        part1 = str(tmp_path / "my")
        part2 = "dir/pic.png"
        prompt = f"{part1} {part2}"
        detections, _ = _detect_path_tokens(prompt)
        # Should find the file via span search
        supported = [d for d in detections if not d.unsupported]
        assert len(supported) == 1

    def test_candidate_span_max_path_in_loop(self):
        """candidate_path_token > MAX_PATH_LENGTH inside span loop (line 265).

        Mock _is_probable_path to allow long tokens through so we hit the
        defensive MAX_PATH_LENGTH guard inside the span loop.
        """
        long_suffix = "a" * (MAX_PATH_LENGTH + 1)
        prompt = f"/nonexistent/start {long_suffix}"
        # _is_probable_path normally rejects long tokens, so mock it
        orig = _is_probable_path

        def patched(token):
            if len(token) > MAX_PATH_LENGTH:
                return True
            return orig(token)

        with patch(
            "code_puppy.command_line.attachments._is_probable_path", side_effect=patched
        ):
            detections, _ = _detect_path_tokens(prompt)


# ---------------------------------------------------------------------------
# parse_prompt_attachments (integration)
# ---------------------------------------------------------------------------
class TestParsePromptAttachments:
    def test_no_attachments(self):
        result = parse_prompt_attachments("hello world")
        assert result.prompt == "hello world"
        assert result.attachments == []
        assert result.link_attachments == []
        assert result.warnings == []

    def test_with_image_file(self, tmp_path):
        f = tmp_path / "pic.png"
        f.write_bytes(b"\x89PNG")
        result = parse_prompt_attachments(f"describe {f}")
        assert len(result.attachments) == 1
        assert result.attachments[0].content.data == b"\x89PNG"
        # The file path token should be removed from prompt
        assert str(f) not in result.prompt

    def test_only_attachment_gets_default_prompt(self, tmp_path):
        f = tmp_path / "pic.png"
        f.write_bytes(b"data")
        result = parse_prompt_attachments(str(f))
        assert result.prompt == "Describe the attached files in detail."

    def test_unsupported_extension_kept_in_prompt(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"a,b")
        result = parse_prompt_attachments(f"analyze {f}")
        assert result.attachments == []
        # Unsupported files are NOT stripped from the prompt (spans only skip supported)

    def test_unreadable_file_silently_skipped(self, tmp_path):
        f = tmp_path / "pic.png"
        f.write_bytes(b"x")
        with patch(
            "code_puppy.command_line.attachments._load_binary",
            side_effect=AttachmentParsingError("nope"),
        ):
            result = parse_prompt_attachments(str(f))
            assert result.attachments == []

    def test_link_attachment_in_detections(self):
        """If _parse_link returned something, it'd be in link_attachments."""
        mock_link = PromptLinkAttachment(placeholder="http://x", url_part=MagicMock())
        fake_detection = _DetectedPath(
            placeholder="http://x",
            path=None,
            start_index=0,
            consumed_until=1,
            link=mock_link,
        )
        with patch(
            "code_puppy.command_line.attachments._detect_path_tokens",
            return_value=([fake_detection], []),
        ):
            result = parse_prompt_attachments("http://x")
            assert len(result.link_attachments) == 1

    def test_detection_with_path_none_no_link_skipped(self):
        """Detection with path=None and no link -> skip."""
        fake_detection = _DetectedPath(
            placeholder="x",
            path=None,
            start_index=0,
            consumed_until=1,
        )
        with patch(
            "code_puppy.command_line.attachments._detect_path_tokens",
            return_value=([fake_detection], []),
        ):
            result = parse_prompt_attachments("x")
            assert result.attachments == []

    def test_warnings_from_detection(self):
        with patch(
            "code_puppy.command_line.attachments._detect_path_tokens",
            return_value=([], ["some warning"]),
        ):
            result = parse_prompt_attachments("hello")
            assert "some warning" in result.warnings

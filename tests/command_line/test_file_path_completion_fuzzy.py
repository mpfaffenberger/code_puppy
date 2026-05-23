"""Tests for the pi-style fuzzy @file completion in file_path_completion.py."""

import os
import tempfile
from unittest.mock import MagicMock

from prompt_toolkit.document import Document

from code_puppy.command_line import file_index
from code_puppy.command_line.file_path_completion import (
    FilePathCompleter,
    _looks_like_path_navigation,
    _score,
)


# ----------------------------------------------------------------- unit: scorer


class TestScore:
    def test_empty_query_matches_everything(self):
        assert _score("foo.py", "src/foo.py", "") == 1

    def test_exact_basename_match_wins(self):
        assert _score("foo.py", "src/foo.py", "foo.py") == 100

    def test_basename_prefix(self):
        assert _score("foo.py", "src/foo.py", "foo") == 80

    def test_basename_substring(self):
        assert _score("myfooutil.py", "src/myfooutil.py", "foo") == 50

    def test_path_substring_only(self):
        # "src" is not in basename, but is in full path
        assert _score("util.py", "src/util.py", "src") == 30

    def test_no_match(self):
        assert _score("foo.py", "src/foo.py", "zzz") == 0

    def test_ordering_invariants(self):
        # exact > prefix > basename-contains > path-contains > nothing
        scores = [
            _score("query.py", "a/query.py", "query"),
            _score("queryX.py", "a/queryX.py", "query"),
            _score("xqueryx.py", "a/xqueryx.py", "query"),
            _score("util.py", "query/util.py", "query"),
            _score("util.py", "a/util.py", "query"),
        ]
        # Strictly descending
        assert scores == sorted(scores, reverse=True)
        assert scores[-1] == 0


# ----------------------------------------------------- unit: nav detection


class TestPathNavigationDetection:
    def test_empty_is_nav(self):
        assert _looks_like_path_navigation("")

    def test_trailing_slash_is_nav(self):
        assert _looks_like_path_navigation("foo/")

    def test_absolute_is_nav(self):
        assert _looks_like_path_navigation("/etc")

    def test_tilde_is_nav(self):
        assert _looks_like_path_navigation("~/code")

    def test_dot_relative_is_nav(self):
        assert _looks_like_path_navigation("./x")
        assert _looks_like_path_navigation("../x")
        assert _looks_like_path_navigation(".env")  # dotfile

    def test_embedded_slash_is_nav(self):
        # "dir/partial" — user is drilling, glob is better
        assert _looks_like_path_navigation("src/fo")

    def test_plain_token_is_fuzzy(self):
        assert not _looks_like_path_navigation("foo")
        assert not _looks_like_path_navigation("MyComp")


# ----------------------------------------------- integration: fuzzy ranking


def _completions(completer, text):
    doc = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(doc, MagicMock()))


class TestFuzzyCompletion:
    def setup_method(self):
        self.completer = FilePathCompleter(symbol="@")

    def teardown_method(self):
        # Reset the global index so we don't pollute other tests that expect
        # a fresh, cwd-driven glob fallback.
        file_index.set_index_for_testing("", [])

    def test_fuzzy_uses_file_index_for_plain_token(self):
        # Seed an index with files outside cwd so glob fallback can't satisfy it.
        file_index.set_index_for_testing(
            "/some/proj",
            [
                "src/widgets/button.py",
                "src/widgets/modal.py",
                "src/utils/helpers.py",
                "tests/test_button.py",
                "README.md",
            ],
        )
        results = _completions(self.completer, "@button")
        texts = [c.text for c in results]
        assert "src/widgets/button.py" in texts
        assert "tests/test_button.py" in texts
        # exact-basename "button.py" doesn't exist, so the prefix-match wins;
        # but either way the unrelated ones shouldn't be at the top.
        assert results[0].text in {"src/widgets/button.py", "tests/test_button.py"}

    def test_fuzzy_ranking_prefers_basename_match(self):
        file_index.set_index_for_testing(
            "/some/proj",
            [
                "deeply/nested/path/with/foo/somefile.py",  # path-contains only
                "src/foo.py",  # exact basename
                "src/foobar.py",  # prefix match
                "src/myfoo.py",  # contains match
            ],
        )
        results = _completions(self.completer, "@foo")
        texts = [c.text for c in results]
        # foo.py (exact=100) beats foobar.py (prefix=80) beats myfoo.py (contains=50)
        # beats the path-only one (30).
        assert texts.index("src/foo.py") < texts.index("src/foobar.py")
        assert texts.index("src/foobar.py") < texts.index("src/myfoo.py")
        assert texts.index("src/myfoo.py") < texts.index(
            "deeply/nested/path/with/foo/somefile.py"
        )

    def test_fuzzy_caps_results(self):
        # 50 files all matching — ensure we don't drown the user.
        paths = [f"src/foo_{i:03}.py" for i in range(50)]
        file_index.set_index_for_testing("/some/proj", paths)
        results = _completions(self.completer, "@foo")
        assert len(results) <= 20

    def test_fuzzy_falls_back_to_glob_on_empty_index(self):
        # Empty index → should glob in cwd, matching old behavior.
        file_index.set_index_for_testing("/nope", [])
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "hello.py"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                # Force the index to "match cwd" so we don't reindex async
                # away from our seeded empty state.
                file_index.set_index_for_testing(os.path.abspath(td), [])
                results = _completions(self.completer, "@hel")
                assert any("hello.py" in c.text for c in results)
            finally:
                os.chdir(old_cwd)

    def test_path_navigation_skips_fuzzy(self):
        # Seed the index with a tempting match, but trailing slash should
        # force glob mode and ignore the index entirely.
        file_index.set_index_for_testing("/some/proj", ["should_not_appear_in_glob.py"])
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "real.py"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                results = _completions(self.completer, "@")  # empty -> nav
                texts = [c.text for c in results]
                assert any("real.py" in t for t in texts)
                assert not any("should_not_appear" in t for t in texts)
            finally:
                os.chdir(old_cwd)

    def test_no_symbol_no_completions(self):
        results = _completions(self.completer, "just typing prose")
        assert results == []

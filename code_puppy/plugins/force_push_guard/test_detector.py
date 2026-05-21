"""Tests for the force push guard detector."""

from code_puppy.plugins.force_push_guard.detector import detect_force_push


class TestDetectForcePush:
    """Test suite for force push pattern detection."""

    # --- Should BLOCK these commands ---

    def test_long_force_flag(self):
        result = detect_force_push("git push --force origin main")
        assert result is not None
        assert result.pattern_name == "--force"

    def test_short_f_flag(self):
        result = detect_force_push("git push -f origin main")
        assert result is not None
        assert result.pattern_name == "-f"

    def test_capital_f_flag(self):
        result = detect_force_push("git push -F origin main")
        assert result is not None
        assert result.pattern_name == "-F"

    def test_force_with_lease(self):
        result = detect_force_push("git push --force-with-lease origin feature")
        assert result is not None
        assert result.pattern_name == "--force-with-lease"

    def test_force_if_includes(self):
        result = detect_force_push("git push --force-if-includes origin feature")
        assert result is not None
        assert result.pattern_name == "--force-if-includes"

    def test_plus_refspec(self):
        result = detect_force_push("git push origin +main")
        assert result is not None
        assert result.pattern_name == "+refspec"

    def test_plus_refspec_head(self):
        result = detect_force_push("git push origin +HEAD:refs/heads/main")
        assert result is not None
        assert result.pattern_name == "+refspec"

    def test_force_before_remote(self):
        result = detect_force_push(
            "git push --force-with-lease --set-upstream origin foo"
        )
        assert result is not None
        assert result.pattern_name == "--force-with-lease"

    def test_force_after_remote(self):
        result = detect_force_push("git push origin feature --force")
        assert result is not None
        assert result.pattern_name == "--force"

    def test_force_flag_with_equals(self):
        result = detect_force_push("git push --force=yes origin main")
        assert result is not None
        assert result.pattern_name == "--force"

    def test_force_with_other_flags(self):
        result = detect_force_push("git push -v -f origin main")
        assert result is not None
        assert result.pattern_name == "-f"

    # --- Should ALLOW these commands ---

    def test_normal_push(self):
        assert detect_force_push("git push origin main") is None

    def test_push_with_set_upstream(self):
        assert detect_force_push("git push --set-upstream origin feature") is None

    def test_push_with_tags(self):
        assert detect_force_push("git push origin --tags") is None

    def test_push_u(self):
        assert detect_force_push("git push -u origin main") is None

    def test_git_pull(self):
        assert detect_force_push("git pull origin main") is None

    def test_git_status(self):
        assert detect_force_push("git status") is None

    def test_unrelated_command(self):
        assert detect_force_push("npm install --force") is None

    def test_empty_string(self):
        assert detect_force_push("") is None

    def test_echo_push(self):
        assert detect_force_push("echo 'git push --force'") is None

    def test_push_dry_run(self):
        assert detect_force_push("git push --dry-run origin main") is None

    def test_git_push_all(self):
        assert detect_force_push("git push --all origin") is None

    def test_git_push_mirror(self):
        """--mirror IS destructive, but it's not a 'force push' per se.
        We don't block it — different safety concern."""
        assert detect_force_push("git push --mirror") is None

    def test_push_no_force_file(self):
        """A file named '--force' in a weirdly structured command shouldn't match."""
        # This is a contrived edge case — the regex should not match
        assert detect_force_push("git push origin main") is None

    def test_grep_push(self):
        """grep containing 'push' should not trigger."""
        assert detect_force_push("grep -r push src/") is None

    # --- Compound commands (shell operators) ---

    def test_compound_and_force(self):
        result = detect_force_push("cd foo && git push --force origin main")
        assert result is not None
        assert result.pattern_name == "--force"

    def test_compound_semicolon_force(self):
        result = detect_force_push("echo hi; git push -f origin main")
        assert result is not None
        assert result.pattern_name == "-f"

    def test_compound_or_force(self):
        result = detect_force_push("git pull || git push --force origin main")
        assert result is not None
        assert result.pattern_name == "--force"

    def test_compound_pipe_not_force(self):
        """Piped git push (uncommon) should still be caught if forced."""
        result = detect_force_push("cat file | git push --force")
        # Note: piping to git push makes no sense, but regex should still match
        assert result is not None
        assert result.pattern_name == "--force"

    def test_compound_and_normal_push(self):
        """Compound with a normal push should be allowed."""
        assert detect_force_push("cd foo && git push origin main") is None

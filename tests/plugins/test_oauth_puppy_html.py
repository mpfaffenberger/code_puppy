"""Tests for the shared OAuth result pages."""

from code_puppy.plugins.oauth_puppy_html import (
    oauth_failure_html,
    oauth_success_html,
)


def test_success_page_is_calm_and_self_contained() -> None:
    html = oauth_success_html("ChatGPT", "Ready to use.")

    assert "You're connected" in html
    assert "Ready to use." in html
    assert "Code Puppy · ChatGPT" in html
    assert html.count('class="mark"') == 1
    assert "http://" not in html
    assert "https://" not in html
    assert "artillery" not in html
    assert "confetti" not in html
    assert "setTimeout" in html


def test_failure_page_has_a_useful_next_step() -> None:
    html = oauth_failure_html("Claude Code", "The request expired.")

    assert "Couldn't connect" in html
    assert "The request expired." in html
    assert "Return to Code Puppy and try signing in again." in html
    assert "setTimeout" not in html


def test_dynamic_content_is_escaped() -> None:
    html = oauth_failure_html("<b>OAuth</b>", "<script>alert('nope')</script>")

    assert "&lt;b&gt;OAuth&lt;/b&gt;" in html
    assert "&lt;script&gt;alert(&#x27;nope&#x27;)&lt;/script&gt;" in html
    assert "<script>alert" not in html


def test_blank_content_uses_fallback_copy() -> None:
    success = oauth_success_html("  ")
    failure = oauth_failure_html("", "  ")

    assert "Code Puppy · OAuth" in success
    assert "Authentication is complete." in success
    assert "Authentication could not be completed." in failure


def test_page_includes_accessibility_and_mobile_metadata() -> None:
    html = oauth_success_html("ChatGPT")

    assert 'name="viewport"' in html
    assert 'role="status"' in html
    assert 'lang="en"' in html
    assert "prefers-color-scheme: dark" in html

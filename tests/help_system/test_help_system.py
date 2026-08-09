"""Tests for the help system."""

import pytest

from code_puppy.help_system import HelpProvider
from code_puppy.help_system.search_engine import (
    format_search_results,
    match_score,
    search_help,
)
from code_puppy.help_system.tutorial_engine import TutorialEngine


@pytest.fixture
def help_provider():
    return HelpProvider()


@pytest.fixture
def tutorial_engine():
    return TutorialEngine()


class TestHelpProvider:
    def test_main_help_displays(self, help_provider):
        output = help_provider.show_main_help()
        assert "Code Puppy Help System" in output
        assert "Built-in Commands" in output

    def test_command_help(self, help_provider):
        output = help_provider.get_command_help("/agent")
        assert "/agent" in output
        assert "agent-name" in output

    def test_command_help_not_found(self, help_provider):
        output = help_provider.get_command_help("/nonexistent")
        assert "not found" in output.lower() or "Unknown command" in output

    def test_category_help(self, help_provider):
        output = help_provider.get_category_help("commands")
        assert "commands" in output.lower()

    def test_category_help_not_found(self, help_provider):
        output = help_provider.get_category_help("nonexistent")
        assert "No results found" in output or "search" in output.lower()

    def test_show_categories(self, help_provider):
        output = help_provider.show_categories()
        assert "commands" in output.lower()
        assert "session" in output.lower()

    def test_search(self, help_provider):
        output = help_provider.search("model")
        assert "model" in output.lower()
        assert "/model" in output

    def test_suggestion(self, help_provider):
        suggestion = help_provider.get_suggestion("/hlpe")
        assert suggestion is not None
        assert "/help" in suggestion

    def test_suggestion_no_match(self, help_provider):
        suggestion = help_provider.get_suggestion("/xyz123")
        assert suggestion is None

    def test_context_tip(self, help_provider):
        tip = help_provider.get_context_tip("model_selection")
        assert tip is not None
        assert "Tip:" in tip


class TestSearchEngine:
    def test_match_score_exact(self):
        score = match_score("model", "model")
        assert score == 1.0

    def test_match_score_partial(self):
        score = match_score("mod", "model")
        assert score > 0.5

    def test_match_score_fuzzy(self):
        score = match_score("modl", "model")
        assert score > 0.3

    def test_search_help(self):
        results = search_help("model", {})
        assert isinstance(results, list)

    def test_format_search_results(self):
        results = [("commands", "/model", "Select model")]
        output = format_search_results(results, "model")
        assert "model" in output.lower()
        assert "/model" in output

    def test_format_search_results_empty(self):
        output = format_search_results([], "test")
        assert "No results found" in output


class TestTutorialEngine:
    def test_list_tutorials(self, tutorial_engine):
        output = tutorial_engine.list_tutorials()
        assert "basics" in output
        assert "agents" in output

    def test_get_tutorial(self, tutorial_engine):
        tutorial = tutorial_engine.get_tutorial("basics")
        assert tutorial is not None
        assert "title" in tutorial
        assert "steps" in tutorial

    def test_get_tutorial_not_found(self, tutorial_engine):
        tutorial = tutorial_engine.get_tutorial("nonexistent")
        assert tutorial is None

    def test_format_tutorial(self, tutorial_engine):
        output = tutorial_engine.format_tutorial("basics")
        assert "Introduction to Code Puppy" in output
        assert "Step 1/" in output

    def test_format_tutorial_not_found(self, tutorial_engine):
        output = tutorial_engine.format_tutorial("nonexistent")
        assert "not found" in output.lower()

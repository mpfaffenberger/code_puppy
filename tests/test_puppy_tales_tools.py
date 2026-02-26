"""Tests for puppy_tales_tools module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.plugins.walmart_specific.puppy_tales_tools import (
    PuppyTalesListOutput,
    PuppyTalesSaveOutput,
    PuppyTalesStory,
    _generate_story_id,
    _get_stories_dir,
    _get_system_username,
    _slugify,
    puppy_tales_list_stories,
    puppy_tales_save_story,
)


# =============================================================================
# Helpers
# =============================================================================


class TestSlugify:
    def test_basic_slugify(self):
        assert _slugify("My Cool Project") == "my-cool-project"

    def test_special_characters(self):
        assert _slugify("Hello! World?") == "hello-world"

    def test_multiple_spaces(self):
        assert _slugify("Too   Many   Spaces") == "too-many-spaces"

    def test_leading_trailing_hyphens(self):
        assert _slugify("---test---") == "test"

    def test_empty_string(self):
        assert _slugify("") == "untitled"

    def test_truncates_long_slugs(self):
        long_name = "a" * 100
        assert len(_slugify(long_name)) == 50


class TestGenerateStoryId:
    def test_format(self):
        story_id = _generate_story_id()
        assert story_id.startswith("PUPPY-")
        parts = story_id.split("-")
        assert len(parts) == 3
        assert parts[0] == "PUPPY"
        assert parts[1].isdigit()  # Year
        assert len(parts[2]) == 4  # Random hex

    def test_uniqueness(self):
        ids = [_generate_story_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique


class TestGetSystemUsername:
    def test_returns_string_or_none(self):
        result = _get_system_username()
        assert result is None or isinstance(result, str)

    def test_returns_non_empty_string_on_normal_system(self):
        # On most systems this should return something
        result = _get_system_username()
        if result is not None:
            assert len(result) > 0


class TestGetStoriesDir:
    def test_creates_directory(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            stories_dir = _get_stories_dir()
            assert stories_dir.exists()
            assert stories_dir.is_dir()
            assert stories_dir == tmp_path / ".code_puppy" / "stories"


# =============================================================================
# Save Story
# =============================================================================


class TestPuppyTalesSaveStory:
    def test_successful_save(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="Auto Report Generator",
                project_purpose="Needed faster insights for weekly store reviews",
                problem_solved="Manual report creation took hours",
                before_code_puppy="Copy-paste from multiple sources",
                after_code_puppy="One command generates everything",
                time_saved="3 hours per week",
                lessons_learned="Break complex tasks into smaller steps",
                category="reports & dashboards",
            )

        assert result.success is True
        assert result.story_id is not None
        assert result.story_id.startswith("PUPPY-")
        assert result.file_path is not None
        assert Path(result.file_path).exists()

        # Verify the saved content
        saved_data = json.loads(Path(result.file_path).read_text())
        assert saved_data["project_name"] == "Auto Report Generator"
        assert saved_data["project_purpose"] == "Needed faster insights for weekly store reviews"
        assert saved_data["category"] == "reports & dashboards"
        assert "submitted_at" in saved_data

    def test_invalid_category_defaults_to_other(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="Test",
                project_purpose="Test purpose",
                problem_solved="Test",
                before_code_puppy="Test",
                after_code_puppy="Test",
                time_saved="1 hour",
                lessons_learned="Test",
                category="invalid category",
            )

        assert result.success is True
        saved_data = json.loads(Path(result.file_path).read_text())
        assert saved_data["category"] == "other"

    def test_strips_whitespace(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="  Trimmed Name  ",
                project_purpose="  Trimmed Purpose  ",
                problem_solved="  Trimmed Problem  ",
                before_code_puppy="Before",
                after_code_puppy="After",
                time_saved="1 hour",
                lessons_learned="Tips",
                category="other",
            )

        saved_data = json.loads(Path(result.file_path).read_text())
        assert saved_data["project_name"] == "Trimmed Name"
        assert saved_data["project_purpose"] == "Trimmed Purpose"
        assert saved_data["problem_solved"] == "Trimmed Problem"

    def test_saves_project_metrics(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="Metrics Test",
                project_purpose="Testing metrics capture",
                problem_solved="Testing metrics",
                before_code_puppy="Before",
                after_code_puppy="After",
                time_saved="2 hours",
                lessons_learned="Tips",
                category="process automation",
                project_type="Python",
                lines_of_code=1234,
                git_commits=56,
                complexity="medium",
            )

        assert result.success is True
        saved_data = json.loads(Path(result.file_path).read_text())
        assert saved_data["project_type"] == "Python"
        assert saved_data["lines_of_code"] == 1234
        assert saved_data["git_commits"] == 56
        assert saved_data["complexity"] == "medium"

    def test_saves_author_profile_and_guessed_category(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="Profile Test",
                project_purpose="Testing profile capture",
                problem_solved="Testing profile",
                before_code_puppy="Before",
                after_code_puppy="After",
                time_saved="1 hour",
                lessons_learned="Tips",
                category="data cleanup",
                author_name="Mary",
                author_role="Fork Lift Operator",
                author_department="Stores",
                author_location="Store #1234",
                collaborators=["Bob", "Alice"],
                guessed_category="Process Automation",
            )

        assert result.success is True
        saved_data = json.loads(Path(result.file_path).read_text())
        assert saved_data["author_name"] == "Mary"
        assert saved_data["author_role"] == "Fork Lift Operator"
        assert saved_data["author_department"] == "Stores"
        assert saved_data["author_location"] == "Store #1234"
        assert saved_data["collaborators"] == ["Bob", "Alice"]
        assert saved_data["guessed_category"] == "process automation"  # lowercased
        assert saved_data["category"] == "data cleanup"  # user's actual choice


# =============================================================================
# List Stories
# =============================================================================


    def test_auto_captures_system_username(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_save_story(
                project_name="Username Test",
                project_purpose="Testing auto username",
                problem_solved="Testing auto username",
                before_code_puppy="Before",
                after_code_puppy="After",
                time_saved="1 hour",
                lessons_learned="Tips",
                category="other",
            )

        assert result.success is True
        saved_data = json.loads(Path(result.file_path).read_text())
        # submitted_by should be auto-populated (may be None in some test envs)
        assert "submitted_by" in saved_data
        # If we got a username, it should be a non-empty string
        if saved_data["submitted_by"] is not None:
            assert isinstance(saved_data["submitted_by"], str)
            assert len(saved_data["submitted_by"]) > 0


class TestPuppyTalesListStories:
    def test_empty_directory(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            result = puppy_tales_list_stories()

        assert result.success is True
        assert result.count == 0
        assert result.stories == []

    def test_lists_saved_stories(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            # Save a couple of stories
            puppy_tales_save_story(
                project_name="Story One",
                project_purpose="Purpose 1",
                problem_solved="Problem 1",
                before_code_puppy="Before 1",
                after_code_puppy="After 1",
                time_saved="1 hour",
                lessons_learned="Tip 1",
                category="other",
            )
            puppy_tales_save_story(
                project_name="Story Two",
                project_purpose="Purpose 2",
                problem_solved="Problem 2",
                before_code_puppy="Before 2",
                after_code_puppy="After 2",
                time_saved="2 hours",
                lessons_learned="Tip 2",
                category="data cleanup",
            )

            result = puppy_tales_list_stories()

        assert result.success is True
        assert result.count == 2
        assert len(result.stories) == 2

    def test_skips_malformed_files(self, tmp_path):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_tales_tools.Path.home",
            return_value=tmp_path,
        ):
            # Create stories dir and add a malformed file
            stories_dir = tmp_path / ".code_puppy" / "stories"
            stories_dir.mkdir(parents=True)
            (stories_dir / "bad-file.json").write_text("not valid json")

            # Save a valid story
            puppy_tales_save_story(
                project_name="Valid Story",
                project_purpose="Valid purpose",
                problem_solved="Problem",
                before_code_puppy="Before",
                after_code_puppy="After",
                time_saved="1 hour",
                lessons_learned="Tip",
                category="other",
            )

            result = puppy_tales_list_stories()

        assert result.success is True
        assert result.count == 1  # Only the valid story


# =============================================================================
# Story Schema
# =============================================================================


class TestPuppyTalesStorySchema:
    def test_valid_story(self):
        story = PuppyTalesStory(
            story_id="PUPPY-2026-ABCD",
            slug="my-project",
            project_name="My Project",
            project_purpose="Wanted better insights",
            problem_solved="Big problem",
            before_code_puppy="Manual work",
            after_code_puppy="Automated",
            time_saved="5 hours",
            lessons_learned="Great tips",
            category="process automation",
            submitted_at="2026-01-01T00:00:00Z",
        )
        assert story.story_id == "PUPPY-2026-ABCD"
        assert story.category == "process automation"
        assert story.project_purpose == "Wanted better insights"

    def test_valid_story_with_metrics(self):
        story = PuppyTalesStory(
            story_id="PUPPY-2026-ABCD",
            slug="my-project",
            project_name="My Project",
            project_purpose="Needed faster reporting",
            problem_solved="Big problem",
            before_code_puppy="Manual work",
            after_code_puppy="Automated",
            time_saved="5 hours",
            lessons_learned="Great tips",
            category="process automation",
            project_type="Python",
            lines_of_code=1500,
            git_commits=42,
            complexity="medium",
            submitted_at="2026-01-01T00:00:00Z",
        )
        assert story.project_type == "Python"
        assert story.lines_of_code == 1500
        assert story.git_commits == 42
        assert story.complexity == "medium"

    def test_invalid_category_rejected(self):
        with pytest.raises(ValueError):
            PuppyTalesStory(
                story_id="PUPPY-2026-ABCD",
                slug="test",
                project_name="Test",
                project_purpose="Test purpose",
                problem_solved="Test",
                before_code_puppy="Test",
                after_code_puppy="Test",
                time_saved="1h",
                lessons_learned="Test",
                category="invalid",  # Not in allowed list
                submitted_at="2026-01-01T00:00:00Z",
            )

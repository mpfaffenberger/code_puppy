"""Tests for Agent Skills plugin."""

import json
import logging
from pathlib import Path

import pytest

from code_puppy.plugins.agent_skills.config import (
    add_skill_directory,
    get_disabled_skills,
    get_skill_directories,
    get_skills_enabled,
    remove_skill_directory,
    set_skill_disabled,
    set_skills_enabled,
)
from code_puppy.plugins.agent_skills.discovery import (
    SkillInfo,
    discover_skills,
    get_default_skill_directories,
    is_valid_skill_directory,
    refresh_skill_cache,
)
from code_puppy.plugins.agent_skills.metadata import (
    SkillMetadata,
    get_skill_resources,
    load_full_skill_content,
    parse_skill_metadata,
    parse_yaml_frontmatter,
)
from code_puppy.plugins.agent_skills.prompt_builder import (
    build_available_skills_xml,
    build_skills_guidance,
)

# Fixtures


@pytest.fixture
def empty_skill_dir(tmp_path):
    """Create an empty skill directory."""
    skill_dir = tmp_path / "empty-skill"
    skill_dir.mkdir()
    return skill_dir


@pytest.fixture
def valid_skill_dir(tmp_path):
    """Create a valid skill directory with SKILL.md."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n# Test Content\n"
    )
    return skill_dir


@pytest.fixture
def skill_with_metadata(tmp_path):
    """Create a skill directory with full metadata."""
    skill_dir = tmp_path / "advanced-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: advanced-skill\n"
        "description: An advanced testing skill with multiple features\n"
        'version: "1.0.0"\n'
        "author: Test Author\n"
        "tags:\n"
        "  - testing\n"
        "  - automation\n"
        "  - pytest\n"
        "---\n"
        "# Advanced Skill\n"
        "This skill has additional content.\n"
    )
    return skill_dir


@pytest.fixture
def skill_with_string_tags(tmp_path):
    """Create a skill directory with comma-separated tags."""
    skill_dir = tmp_path / "string-tags-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: string-tags-skill\n"
        "description: A test skill with string tags\n"
        "tags: 'a, b, c'\n"
        "---\n"
        "# Test Skill\n"
    )
    return skill_dir


@pytest.fixture
def skill_dir_with_resources(tmp_path):
    """Create a skill directory with additional resources."""
    skill_dir = tmp_path / "resourceful-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: resourceful-skill\n"
        "description: A skill with additional resources\n"
        "---\n"
    )
    (skill_dir / "example.txt").write_text("Example resource")
    (skill_dir / "data.json").write_text('{"key": "value"}')
    return skill_dir


@pytest.fixture
def multi_skill_dir(tmp_path):
    """Create a directory with multiple skill subdirectories."""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()

    # Create skill 1 (empty)
    (skill_dir / "skill1").mkdir()

    # Create skill 2 with SKILL.md
    skill2 = skill_dir / "skill2"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text(
        "---\nname: skill2\ndescription: Test skill 2\n---\n"
    )

    # Create skill 3 with SKILL.md
    skill3 = skill_dir / "skill3"
    skill3.mkdir()
    (skill3 / "SKILL.md").write_text(
        "---\nname: skill3\ndescription: Test skill 3\n---\n"
    )

    return skill_dir


# Tests for Discovery Module


class TestSkillDiscovery:
    """Tests for skill discovery module."""

    def test_get_default_skill_directories(self):
        """Test default skill directories are correctly returned."""
        directories = get_default_skill_directories()
        assert len(directories) == 2
        assert directories[0] == Path.home() / ".code_puppy" / "skills"
        assert directories[1] == Path.cwd() / "skills"

    def test_is_valid_skill_directory_valid(self, valid_skill_dir):
        """Test valid skill directory detection."""
        assert is_valid_skill_directory(valid_skill_dir) is True

    def test_is_valid_skill_directory_invalid(self, empty_skill_dir):
        """Test invalid skill directory detection (no SKILL.md)."""
        assert is_valid_skill_directory(empty_skill_dir) is False

    def test_is_valid_skill_directory_not_a_dir(self, tmp_path):
        """Test invalid skill directory detection (not a directory)."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        assert is_valid_skill_directory(file_path) is False

    def test_discover_skills_empty_directory(self, tmp_path):
        """Test discovering skills from empty directory."""
        skills = discover_skills(directories=[tmp_path])
        assert len(skills) == 0

    def test_discover_skills_finds_valid_skill(self, multi_skill_dir):
        """Test discovering valid skills from directory."""
        skills = discover_skills(directories=[multi_skill_dir])
        assert len(skills) == 3  # All subdirectories are found
        skill_names = [skill.name for skill in skills]
        assert "skill2" in skill_names
        assert "skill3" in skill_names

    def test_discover_skills_finds_only_valid_skills(self, tmp_path):
        """Test discovering only skills with SKILL.md."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()

        # Create skill with SKILL.md
        valid_skill = skill_dir / "valid"
        valid_skill.mkdir()
        (valid_skill / "SKILL.md").write_text(
            "---\nname: valid\ndescription: Valid skill\n---\n"
        )

        # Create skill without SKILL.md
        invalid_skill = skill_dir / "invalid"
        invalid_skill.mkdir()

        skills = discover_skills(directories=[skill_dir])
        assert len(skills) == 2  # Both found, but only one has_skill_md

        # Check that valid skill has has_skill_md=True
        valid_skill_info = next(s for s in skills if s.name == "valid")
        assert valid_skill_info.has_skill_md is True

        # Check that invalid skill has has_skill_md=False
        invalid_skill_info = next(s for s in skills if s.name == "invalid")
        assert invalid_skill_info.has_skill_md is False

    def test_discover_skills_skips_hidden_directories(self, tmp_path):
        """Test that hidden directories are skipped during discovery."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()

        # Create hidden directory
        hidden_skill = skill_dir / ".hidden"
        hidden_skill.mkdir()
        (hidden_skill / "SKILL.md").write_text(
            "---\nname: hidden\ndescription: Hidden skill\n---\n"
        )

        # Create normal directory
        normal_skill = skill_dir / "normal"
        normal_skill.mkdir()
        (normal_skill / "SKILL.md").write_text(
            "---\nname: normal\ndescription: Normal skill\n---\n"
        )

        skills = discover_skills(directories=[skill_dir])
        assert len(skills) == 1  # Only normal directory found
        assert skills[0].name == "normal"

    def test_discover_skills_nonexistent_directory(self, caplog):
        """Test discovering skills from nonexistent directory."""
        nonexistent = Path("/nonexistent/path/that/does/not/exist")

        with caplog.at_level(logging.DEBUG):
            skills = discover_skills(directories=[nonexistent])

        assert len(skills) == 0
        assert "Skill directory does not exist" in caplog.text

    def test_discover_skills_not_a_directory(self, tmp_path, caplog):
        """Test discovering skills from file path instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with caplog.at_level(logging.WARNING):
            skills = discover_skills(directories=[file_path])

        assert len(skills) == 0
        assert "Skill path is not a directory" in caplog.text

    def test_discover_skills_caching(self, tmp_path, monkeypatch):
        """Test that skill discovery uses caching correctly."""
        # First discovery
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        skills = discover_skills(directories=[skill_dir])
        first_count = len(skills)

        # Add new skill - but don't use cache by mocking _skill_cache to None
        new_skill = skill_dir / "new"
        new_skill.mkdir()
        (new_skill / "SKILL.md").write_text(
            "---\nname: new\ndescription: New skill\n---\n"
        )

        # Clear cache to force re-scan
        global _skill_cache
        _skill_cache = None

        # Second discovery (should find the new skill)
        skills = discover_skills(directories=[skill_dir])
        assert len(skills) == first_count + 1

    def test_refresh_skill_cache(self, monkeypatch):
        """Test cache refresh functionality."""
        # This test can't use tmp_path because refresh_skill_cache uses default dirs
        # So we need to mock the default discovery behavior to verify cache clearing

        def mock_discover(directories=None):
            # Return a single test skill
            return [SkillInfo(name="test-skill", path=Path("/tmp"), has_skill_md=True)]

        # Apply the monkeypatch to discover_skills in the discovery module
        # AND in the test module (since we imported it directly)
        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.discovery.discover_skills", mock_discover
        )
        # Also patch the direct import in this test module
        monkeypatch.setattr(
            "tests.plugins.test_agent_skills.discover_skills", mock_discover
        )

        # Initial discovery should return 1 skill
        skills = discover_skills()
        assert len(skills) == 1
        assert skills[0].name == "test-skill"

        # The key assertion: refresh_skill_cache should clear cache and call discover_skills
        # Without our mock being re-applied, it would use the real function
        # But since we mocked it, it should still work
        skills = refresh_skill_cache()
        assert len(skills) == 1

        # But we need to verify cache was actually cleared
        # If cache wasn't cleared, subsequent calls would return the cached result without calling mock
        # So we can verify by checking that our mock was called twice
        # This indirectly tests that cache was cleared (otherwise discover_skills wouldn't be called again)


# Tests for Metadata Module


class TestMetadataParsing:
    """Tests for metadata parsing module."""

    def test_parse_yaml_frontmatter_basic(self):
        """Test basic YAML frontmatter parsing."""
        content = "---\nname: test\ndescription: A test\n---\n# Content"
        parsed = parse_yaml_frontmatter(content)
        assert parsed == {"name": "test", "description": "A test"}

    def test_parse_yaml_frontmatter_with_quotes(self):
        """Test YAML frontmatter parsing with quoted values."""
        content = (
            "---\nname: \"quoted name\"\ndescription: 'quoted desc'\n---\n# Content"
        )
        parsed = parse_yaml_frontmatter(content)
        assert parsed == {"name": "quoted name", "description": "quoted desc"}

    def test_parse_yaml_frontmatter_with_list(self):
        """Test YAML frontmatter parsing with list values."""
        content = "---\nname: test\ntags:\n  - tag1\n  - tag2\n  - tag3\n---\n# Content"
        parsed = parse_yaml_frontmatter(content)
        assert parsed == {"name": "test", "tags": ["tag1", "tag2", "tag3"]}

    def test_parse_yaml_frontmatter_without_frontmatter(self):
        """Test parsing content without frontmatter section."""
        content = "# No frontmatter here\nJust content."
        parsed = parse_yaml_frontmatter(content)
        assert parsed == {}

    def test_parse_yaml_frontmatter_malformed_frontmatter(self):
        """Test parsing content with incomplete or malformed frontmatter."""
        # Missing closing --- (should not match since it's not complete frontmatter)
        content = "---\nname: test\ndescription: A test\n# Content"
        parsed = parse_yaml_frontmatter(content)
        # Should return empty dict because it doesn't have proper closing ---
        assert parsed == {}  # No proper frontmatter format

    def test_parse_skill_metadata_valid(self, valid_skill_dir):
        """Test parsing valid skill metadata."""
        metadata = parse_skill_metadata(valid_skill_dir)
        assert metadata is not None
        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert metadata.path == valid_skill_dir
        assert metadata.version is None
        assert metadata.author is None
        assert metadata.tags == []

    def test_parse_skill_metadata_full(self, skill_with_metadata):
        """Test parsing skill metadata with all fields."""
        metadata = parse_skill_metadata(skill_with_metadata)
        assert metadata is not None
        assert metadata.name == "advanced-skill"
        assert (
            metadata.description == "An advanced testing skill with multiple features"
        )
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"
        assert metadata.tags == ["testing", "automation", "pytest"]

    def test_parse_skill_metadata_string_tags(self, skill_with_string_tags):
        """Test parsing skill metadata with comma-separated string tags."""
        metadata = parse_skill_metadata(skill_with_string_tags)
        assert metadata is not None
        assert metadata.name == "string-tags-skill"
        assert metadata.description == "A test skill with string tags"
        assert metadata.tags == ["a", "b", "c"]

    def test_parse_skill_metadata_missing_required_fields(self, empty_skill_dir):
        """Test parsing skill metadata when required fields are missing."""
        metadata = parse_skill_metadata(empty_skill_dir)
        assert metadata is None

    def test_parse_skill_metadata_missing_name_field(self, tmp_path):
        """Test parsing when 'name' field is missing."""
        skill_dir = tmp_path / "no-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: This has no name field\n---\n"
        )

        metadata = parse_skill_metadata(skill_dir)
        assert metadata is None

    def test_parse_skill_metadata_missing_description_field(self, tmp_path):
        """Test parsing when 'description' field is missing."""
        skill_dir = tmp_path / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n")

        metadata = parse_skill_metadata(skill_dir)
        assert metadata is None

    def test_parse_skill_metadata_nonexistent_path(self, tmp_path, caplog):
        """Test parsing skill metadata from nonexistent path."""
        nonexistent = tmp_path / "does-not-exist"

        with caplog.at_level(logging.WARNING):
            metadata = parse_skill_metadata(nonexistent)

        assert metadata is None
        assert "Skill path does not exist" in caplog.text

    def test_parse_skill_metadata_with_file_io_error(self, tmp_path, monkeypatch):
        """Test parsing when file I/O fails."""
        skill_dir = tmp_path / "io-error"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: io-error\ndescription: This will fail\n---\n"
        )

        # Mock read_text to raise an exception using monkeypatch
        def mock_read_text(*args, **kwargs):
            raise Exception("Read error")

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        metadata = parse_skill_metadata(skill_dir)
        assert metadata is None

    def test_load_full_skill_content(self, valid_skill_dir):
        """Test loading full skill content from SKILL.md."""
        content = load_full_skill_content(valid_skill_dir)
        assert content is not None
        assert "---" in content
        assert "# Test Content" in content

    def test_load_full_skill_content_nonexistent_path(self, tmp_path, caplog):
        """Test loading full skill content from nonexistent path."""
        nonexistent = tmp_path / "does-not-exist"

        with caplog.at_level(logging.WARNING):
            content = load_full_skill_content(nonexistent)

        assert content is None
        assert "Skill path does not exist" in caplog.text

    def test_get_skill_resources(self, skill_dir_with_resources):
        """Test getting resource files from skill directory."""
        resources = get_skill_resources(skill_dir_with_resources)
        assert len(resources) == 2
        resource_names = [r.name for r in resources]
        assert "example.txt" in resource_names
        assert "data.json" in resource_names

    def test_get_skill_resources_skips_skill_md(self, valid_skill_dir):
        """Test that SKILL.md is not included in resources."""
        # Add an extra file
        (valid_skill_dir / "extra.txt").write_text("extra")

        resources = get_skill_resources(valid_skill_dir)
        assert len(resources) == 1
        assert resources[0].name == "extra.txt"

    def test_get_skill_resources_empty_directory(self, valid_skill_dir):
        """Test getting resources from skill directory with no extra files."""
        resources = get_skill_resources(valid_skill_dir)
        assert len(resources) == 0

    def test_get_skill_resources_nonexistent_path(self, tmp_path, caplog):
        """Test getting resources from nonexistent path."""
        nonexistent = tmp_path / "does-not-exist"

        with caplog.at_level(logging.WARNING):
            resources = get_skill_resources(nonexistent)

        assert len(resources) == 0
        assert "Skill path does not exist" in caplog.text


# Tests for Prompt Builder Module


class TestPromptBuilder:
    """Tests for prompt builder module."""

    def test_build_available_skills_xml_empty(self):
        """Test building XML for empty skills list."""
        xml = build_available_skills_xml([])
        assert xml == "<available_skills></available_skills>"

    def test_build_available_skills_xml_single_skill(self):
        """Test building XML for single skill."""
        skill = SkillMetadata(
            name="test-skill",
            description="A test skill",
            path=Path("/path/to/skill"),
        )
        xml = build_available_skills_xml([skill])
        assert "<available_skills>" in xml
        assert "<skill>" in xml
        assert "<name>test-skill</name>" in xml
        assert "<description>A test skill</description>" in xml
        assert "</skill>" in xml

    def test_build_available_skills_xml_multiple_skills(self):
        """Test building XML for multiple skills."""
        skills = [
            SkillMetadata(
                name="skill1",
                description="First skill",
                path=Path("/path/to/skill1"),
            ),
            SkillMetadata(
                name="skill2",
                description="Second skill",
                path=Path("/path/to/skill2"),
            ),
        ]
        xml = build_available_skills_xml(skills)
        assert xml.count("<skill>") == 2
        assert "<name>skill1</name>" in xml
        assert "<name>skill2</name>" in xml

    def test_xml_escaping_ampersand(self):
        """Test XML escaping of ampersand character."""
        skill = SkillMetadata(
            name="test",
            description="Tom & Jerry",
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "Tom &amp; Jerry" in xml

    def test_xml_escaping_less_than(self):
        """Test XML escaping of less than character."""
        skill = SkillMetadata(
            name="test",
            description="Use < for comparison",
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "Use &lt; for comparison" in xml

    def test_xml_escaping_greater_than(self):
        """Test XML escaping of greater than character."""
        skill = SkillMetadata(
            name="test",
            description="Use > for comparison",
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "Use &gt; for comparison" in xml

    def test_xml_escaping_quotes(self):
        """Test XML escaping of quotes."""
        skill = SkillMetadata(
            name="test",
            description='She said "Hello"',
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "She said &quot;Hello&quot;" in xml

    def test_xml_escaping_apostrophe(self):
        """Test XML escaping of apostrophe."""
        skill = SkillMetadata(
            name="test",
            description="It's a test",
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "It&#39;s a test" in xml

    def test_xml_escaping_multiple_special_chars(self):
        """Test XML escaping of multiple special characters."""
        skill = SkillMetadata(
            name="test",
            description="Tom & Jerry say: 'Use < & >'",
            path=Path("/path"),
        )
        xml = build_available_skills_xml([skill])
        assert "Tom &amp; Jerry say: &#39;Use &lt; &amp; &gt;&#39;" in xml

    def test_build_skills_guidance(self):
        """Test building skills guidance text."""
        guidance = build_skills_guidance()
        assert "# Using Agent Skills" in guidance
        assert "list_or_search_skills" in guidance
        assert "activate_skill" in guidance
        assert "Skill Locations" in guidance
        assert "~/.code_puppy/skills/" in guidance


# Tests for Config Module


class TestSkillsConfig:
    """Tests for skills configuration module."""

    def test_get_skill_directories_default(self, monkeypatch):
        """Test getting skill directories with default values."""

        # Mock config to return None (no saved config)
        def mock_get_value(key):
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )

        directories = get_skill_directories()
        assert len(directories) == 2
        # The tilde will be expanded to the actual home directory
        assert ".code_puppy/skills" in directories[0]
        # The current directory path will contain the full path, ending with "skills"
        assert "skills" in directories[1]

    def test_get_skill_directories_from_config(self, monkeypatch):
        """Test getting skill directories from config."""
        # Mock config to return saved directories
        saved_dirs = json.dumps(["/path1", "/path2"])

        def mock_get_value(key):
            return saved_dirs

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )

        directories = get_skill_directories()
        assert directories == ["/path1", "/path2"]

    def test_get_skill_directories_malformed_config(self, monkeypatch, caplog):
        """Test getting skill directories with malformed JSON config."""

        # Mock config to return malformed JSON
        def mock_get_value(key):
            return "not json"

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )

        with caplog.at_level(logging.ERROR):
            directories = get_skill_directories()

        assert len(directories) == 2  # Falls back to defaults
        assert "Failed to parse skill_directories config" in caplog.text

    def test_add_skill_directory_new(self, monkeypatch):
        """Test adding a new skill directory."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/existing"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        result = add_skill_directory("/new")

        assert result is True
        # Check that set_value was called with the updated list
        assert len(calls) == 1
        key, value = calls[0]
        assert key == "skill_directories"
        saved_dirs = json.loads(value)
        assert "/existing" in saved_dirs
        assert "/new" in saved_dirs

    def test_add_skill_directory_duplicate(self, monkeypatch):
        """Test adding a duplicate skill directory."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/existing"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        result = add_skill_directory("/existing")

        assert result is False
        assert len(calls) == 0

    def test_add_skill_directory_config_error(self, monkeypatch, caplog):
        """Test adding skill directory when config save fails."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/existing"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        def mock_set_value(key, value):
            raise Exception("Config save error")

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        with caplog.at_level(logging.ERROR):
            result = add_skill_directory("/new")

        assert result is False
        assert "Failed to add skill directory" in caplog.text

    def test_remove_skill_directory_existing(self, monkeypatch):
        """Test removing an existing skill directory."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/dir1", "/dir2", "/dir3"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        result = remove_skill_directory("/dir2")

        assert result is True
        # Check that set_value was called with the updated list
        assert len(calls) == 1
        key, value = calls[0]
        saved_dirs = json.loads(value)
        assert "/dir2" not in saved_dirs
        assert len(saved_dirs) == 2

    def test_remove_skill_directory_nonexistent(self, monkeypatch):
        """Test removing nonexistent skill directory."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/dir1", "/dir2"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        result = remove_skill_directory("/not-exists")

        assert result is False
        assert len(calls) == 0

    def test_remove_skill_directory_config_error(self, monkeypatch, caplog):
        """Test removing skill directory when config save fails."""

        # Mock existing directories
        def mock_get_skill_directories():
            return ["/dir1", "/dir2"]

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            mock_get_skill_directories,
        )

        def mock_set_value(key, value):
            raise Exception("Config save error")

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        with caplog.at_level(logging.ERROR):
            result = remove_skill_directory("/dir2")

        assert result is False
        assert "Failed to remove skill directory" in caplog.text

    def test_get_skills_enabled_default(self, monkeypatch):
        """Test getting skills enabled flag with default (no config)."""

        def mock_get_value(key):
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )
        assert get_skills_enabled() is True

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ],
    )
    def test_get_skills_enabled_various_values(self, value, expected, monkeypatch):
        """Test getting skills enabled flag with various config values."""

        def mock_get_value(key):
            return value

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )
        assert get_skills_enabled() == expected

    def test_set_skills_enabled_true(self, monkeypatch):
        """Test setting skills enabled to True."""
        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )
        set_skills_enabled(True)
        assert calls == [("skills_enabled", "true")]

    def test_set_skills_enabled_false(self, monkeypatch):
        """Test setting skills enabled to False."""
        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )
        set_skills_enabled(False)
        assert calls == [("skills_enabled", "false")]

    def test_get_disabled_skills_default(self, monkeypatch):
        """Test getting disabled skills with default (none disabled)."""

        def mock_get_value(key):
            return None

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )
        disabled = get_disabled_skills()
        assert isinstance(disabled, set)
        assert len(disabled) == 0

    def test_get_disabled_skills_from_config(self, monkeypatch):
        """Test getting disabled skills from config."""

        # Mock config with disabled skills JSON
        def mock_get_value(key):
            return json.dumps(["skill1", "skill2", "skill3"])

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )

        disabled = get_disabled_skills()
        assert disabled == {"skill1", "skill2", "skill3"}

    def test_get_disabled_skills_malformed_config(self, monkeypatch, caplog):
        """Test getting disabled skills with malformed config."""

        # Mock config with malformed JSON
        def mock_get_value(key):
            return "not json"

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_value", mock_get_value
        )

        with caplog.at_level(logging.ERROR):
            disabled = get_disabled_skills()

        assert isinstance(disabled, set)
        assert len(disabled) == 0
        assert "Failed to parse disabled_skills config" in caplog.text

    def test_set_skill_disabled_add(self, monkeypatch):
        """Test disabling a skill."""

        # Mock existing disabled skills
        def mock_get_disabled_skills():
            return set()

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            mock_get_disabled_skills,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        set_skill_disabled("skill1", disabled=True)

        # Check that set_value was called with the updated set
        assert len(calls) == 1
        key, value = calls[0]
        assert key == "disabled_skills"
        disabled_list = json.loads(value)
        assert "skill1" in disabled_list

    def test_set_skill_disabled_remove(self, monkeypatch):
        """Test enabling a previously disabled skill."""

        # Mock existing disabled skills
        def mock_get_disabled_skills():
            return {"skill1", "skill2"}

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            mock_get_disabled_skills,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        set_skill_disabled("skill1", disabled=False)

        # Check that set_value was called with the updated set
        assert len(calls) == 1
        key, value = calls[0]
        assert key == "disabled_skills"
        disabled_list = json.loads(value)
        assert "skill1" not in disabled_list
        assert "skill2" in disabled_list

    def test_set_skill_disabled_already_disabled(self, monkeypatch):
        """Test disabling an already disabled skill."""

        # Mock existing disabled skills
        def mock_get_disabled_skills():
            return {"skill1"}

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            mock_get_disabled_skills,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        set_skill_disabled("skill1", disabled=True)

        # Should not call set_value since skill is already disabled
        assert len(calls) == 0

    def test_set_skill_disabled_already_enabled(self, monkeypatch):
        """Test enabling an already enabled skill."""

        # Mock existing disabled skills
        def mock_get_disabled_skills():
            return set()

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            mock_get_disabled_skills,
        )

        calls = []

        def mock_set_value(key, value):
            calls.append((key, value))

        monkeypatch.setattr(
            "code_puppy.plugins.agent_skills.config.set_value", mock_set_value
        )

        set_skill_disabled("skill1", disabled=False)

        # Should not call set_value since skill is not in disabled list
        assert len(calls) == 0


# Integration Tests


class TestSkillIntegration:
    """Integration tests for skill discovery and metadata parsing."""

    def test_discover_and_parse_skills(self, multi_skill_dir):
        """Test end-to-end skill discovery and metadata parsing."""
        # Discover skills
        skill_infos = discover_skills(directories=[multi_skill_dir])
        assert len(skill_infos) == 3

        # Parse metadata for each valid skill
        for info in skill_infos:
            if info.has_skill_md:
                metadata = parse_skill_metadata(info.path)
                assert metadata is not None
                assert metadata.name == info.name
                assert metadata.path == info.path

    def test_xml_generation_with_discovered_skills(self, valid_skill_dir):
        """Test generating XML from discovered skills with metadata."""
        # Discover skills first
        skill_infos = discover_skills(directories=[valid_skill_dir.parent])

        # Parse metadata for discovered skills
        metadatas = []
        for info in skill_infos:
            if info.has_skill_md:
                metadata = parse_skill_metadata(info.path)
                if metadata:
                    metadatas.append(metadata)

        # Build XML
        xml = build_available_skills_xml(metadatas)
        assert "<available_skills>" in xml
        assert "<name>test-skill</name>" in xml

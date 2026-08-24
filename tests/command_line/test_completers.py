import os
import sys
from unittest.mock import patch

import pytest
from prompt_toolkit.document import Document

from code_puppy.command_line.completers import (
    AgentCompleter,
    CDCompleter,
    SetCompleter,
)
from code_puppy.command_line.file_path_completion import FilePathCompleter

# Skip some path-format sensitive tests on Windows where backslashes are expected
IS_WINDOWS = os.name == "nt" or sys.platform.startswith("win")


def setup_files(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "file1.txt").write_text("content1")
    (d / "file2.py").write_text("content2")
    (tmp_path / "file3.txt").write_text("hi")
    (tmp_path / ".hiddenfile").write_text("sneaky")
    return d


def test_fork_agent_completion_owns_at_slot():
    document = Document(text="/fork @qa", cursor_position=len("/fork @qa"))

    with patch(
        "code_puppy.command_line.pin_command_completion.load_agent_names",
        return_value=["code-puppy", "qa-kitten"],
    ):
        agents = list(
            AgentCompleter(trigger="/fork", prefix="@").get_completions(document, None)
        )

    files = list(FilePathCompleter(symbol="@").get_completions(document, None))
    assert [completion.text for completion in agents] == ["qa-kitten"]
    assert agents[0].start_position == -2
    assert files == []


def test_fork_agent_completion_requires_at_prefix():
    document = Document(text="/fork qa", cursor_position=len("/fork qa"))
    completions = AgentCompleter(trigger="/fork", prefix="@").get_completions(
        document, None
    )
    assert list(completions) == []


def test_fork_model_completion_with_prefix():
    """Test that ModelNameCompleter works with @ prefix in /fork context."""
    from code_puppy.command_line.model_picker_completion import ModelNameCompleter

    document = Document(
        text="/fork @code-puppy @codex", cursor_position=len("/fork @code-puppy @codex")
    )

    with (
        patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={
                "codex-gpt-5.6-luna": {},
                "gpt-4o": {},
                "claude-sonnet": {},
            },
        ),
        patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="gpt-4o",
        ),
    ):
        models = list(
            ModelNameCompleter(trigger="/fork", prefix="@").get_completions(
                document, None
            )
        )

    # Should only match codex models
    assert len(models) == 1
    assert models[0].text == "codex-gpt-5.6-luna"
    # start_position should be -5 (length of "codex")
    assert models[0].start_position == -5


def test_fork_model_completion_requires_at_prefix():
    """Test that ModelNameCompleter with prefix requires @ in /fork context."""
    from code_puppy.command_line.model_picker_completion import ModelNameCompleter

    document = Document(
        text="/fork @code-puppy gpt", cursor_position=len("/fork @code-puppy gpt")
    )

    with patch(
        "code_puppy.command_line.model_picker_completion._load_models_config",
        return_value={"gpt-4o": {}},
    ):
        models = list(
            ModelNameCompleter(trigger="/fork", prefix="@").get_completions(
                document, None
            )
        )

    # No @ prefix before "gpt", so no completions
    assert models == []


def test_fork_model_completion_no_prefix_still_works():
    """Test that ModelNameCompleter without prefix still works for /model."""
    from code_puppy.command_line.model_picker_completion import ModelNameCompleter

    document = Document(text="/model gpt", cursor_position=len("/model gpt"))

    with (
        patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4o": {}, "claude-sonnet": {}},
        ),
        patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="claude-sonnet",
        ),
    ):
        models = list(
            ModelNameCompleter(trigger="/model").get_completions(document, None)
        )

    assert len(models) == 1
    assert models[0].text == "gpt-4o"


def test_fork_parse_args_with_model():
    """Test fork arg parsing extracts both agent and model."""
    from code_puppy_core_plugins.fork.register_callbacks import _parse_fork_args

    # Both agent and model
    agent, model, prompt = _parse_fork_args("@code-puppy @gpt-5 fizzbuzz")
    assert agent == "code-puppy"
    assert model == "gpt-5"
    assert prompt == "fizzbuzz"

    # Only agent
    agent, model, prompt = _parse_fork_args("@code-puppy fizzbuzz")
    assert agent == "code-puppy"
    assert model is None
    assert prompt == "fizzbuzz"

    # Neither
    agent, model, prompt = _parse_fork_args("just a prompt")
    assert agent is None
    assert model is None
    assert prompt == "just a prompt"

    # Empty after @model
    agent, model, prompt = _parse_fork_args("@agent @model")
    assert agent == "agent"
    assert model == "model"
    assert prompt == ""


def test_no_symbol(tmp_path):
    completer = FilePathCompleter(symbol="@")
    doc = Document(text="no_completion_here", cursor_position=7)
    completions = list(completer.get_completions(doc, None))
    assert completions == []


def test_completion_directory_listing(tmp_path):
    d = setup_files(tmp_path)
    completer = FilePathCompleter(symbol="@")
    # Set cwd so dir lookup matches. Fix cursor position off by one.
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        text = f"test @{d.name}/"
        doc = Document(text=text, cursor_position=len(text))
        completions = list(completer.get_completions(doc, None))
        # termflow completions carry plain-string displays.
        filenames = {str(c.display) for c in completions}
        assert "file1.txt" in filenames
        assert "file2.py" in filenames
    finally:
        os.chdir(cwd)


def test_completion_with_hidden_file(tmp_path):
    # Should show hidden files if user types starting with .
    setup_files(tmp_path)
    completer = FilePathCompleter(symbol="@")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        doc = Document(text="@.", cursor_position=2)
        completions = list(completer.get_completions(doc, None))
        assert any(".hiddenfile" in c.text for c in completions)
    finally:
        os.chdir(cwd)


def test_completion_handles_permissionerror(monkeypatch):
    # Patch os.listdir to explode!
    completer = FilePathCompleter(symbol="@")

    def explode(path):
        raise PermissionError

    monkeypatch.setattr(os, "listdir", explode)
    doc = Document(text="@", cursor_position=1)
    # Should not raise:
    list(completer.get_completions(doc, None))


def test_set_completer_on_non_trigger():
    completer = SetCompleter()
    doc = Document(text="not_a_set_command")
    assert list(completer.get_completions(doc, None)) == []


def test_set_completer_exact_trigger(monkeypatch):
    completer = SetCompleter()
    doc = Document(text="/set", cursor_position=len("/set"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    assert completions[0].text == "/set "  # Check the actual text to be inserted
    assert completions[0].display_meta == "set config key"


def test_set_completer_on_set_trigger(monkeypatch):
    # Simulate config keys
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_config_keys",
        lambda: ["foo", "bar"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_value",
        lambda key: "woo" if key == "foo" else None,
    )
    completer = SetCompleter()
    doc = Document(text="/set ", cursor_position=len("/set "))
    completions = list(completer.get_completions(doc, None))
    completion_texts = sorted([c.text for c in completions])
    completion_metas = sorted(
        [c.display_meta for c in completions]
    )  # Corrected display_meta access

    # The completer now provides 'key = value' as text, not '/set key = value'
    assert completion_texts == sorted(["bar = ", "foo = woo"])
    # Display meta should be empty now
    assert len(completion_metas) == 2
    for meta in completion_metas:
        assert meta == ""


def test_set_completer_partial_key(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_config_keys",
        lambda: ["long_key_name", "other_key", "model"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_value",
        lambda key: "value_for_" + key if key == "long_key_name" else None,
    )
    completer = SetCompleter()

    doc = Document(text="/set long_k", cursor_position=len("/set long_k"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    # `text` for partial key completion should be the key itself and its value part
    assert completions[0].text == "long_key_name = value_for_long_key_name"
    # Display meta should be empty now
    assert completions[0].display_meta == ""

    doc = Document(text="/set oth", cursor_position=len("/set oth"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    assert completions[0].text == "other_key = "
    # Display meta should be empty now
    assert completions[0].display_meta == ""


def test_set_completer_excludes_model_settings_only_keys(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_config_keys",
        lambda: [
            "openai_reasoning_effort",
            "openai_verbosity",
            "temperature",
        ],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_value",
        lambda key: "high",
    )
    completer = SetCompleter()

    completions = list(completer.get_completions(Document(text="/set openai_"), None))
    assert completions == []

    completions = list(completer.get_completions(Document(text="/set temp"), None))
    assert [completion.text for completion in completions] == ["temperature = high"]


def test_set_completer_excludes_model_key(monkeypatch):
    # Ensure 'model' is a config key but SetCompleter doesn't offer it
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_config_keys",
        lambda: ["api_key", "model", "temperature"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_value",
        lambda key: "test_value",
    )
    completer = SetCompleter()

    # Test with full "model" typed
    doc = Document(text="/set model", cursor_position=len("/set model"))
    completions = list(completer.get_completions(doc, None))
    assert completions == [], (
        "SetCompleter should not complete for 'model' key directly"
    )

    # Test with partial "mo" that would match "model"
    doc = Document(text="/set mo", cursor_position=len("/set mo"))
    completions = list(completer.get_completions(doc, None))
    assert completions == [], (
        "SetCompleter should not complete for 'model' key even partially"
    )

    # Ensure other keys are still completed
    doc = Document(text="/set api", cursor_position=len("/set api"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    assert completions[0].text == "api_key = test_value"


def test_set_completer_excludes_puppy_token(monkeypatch):
    # Ensure 'puppy_token' is a config key but SetCompleter doesn't offer it
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_config_keys",
        lambda: ["puppy_token", "user_name", "temp_dir"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.completers.get_value",
        lambda key: "sensitive_token_value" if key == "puppy_token" else "normal_value",
    )
    completer = SetCompleter()

    # Test with full "puppy_token" typed
    doc = Document(text="/set puppy_token", cursor_position=len("/set puppy_token"))
    completions = list(completer.get_completions(doc, None))
    assert completions == [], (
        "SetCompleter should not complete for 'puppy_token' key directly"
    )

    # Test with partial "puppy" that would match "puppy_token"
    doc = Document(text="/set puppy", cursor_position=len("/set puppy"))
    completions = list(completer.get_completions(doc, None))
    assert completions == [], (
        "SetCompleter should not complete for 'puppy_token' key even partially"
    )

    # Ensure other keys are still completed
    doc = Document(text="/set user", cursor_position=len("/set user"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    assert completions[0].text == "user_name = normal_value"


def test_set_completer_no_match(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_config_keys", lambda: ["actual_key"])
    completer = SetCompleter()
    doc = Document(text="/set non_existent", cursor_position=len("/set non_existent"))
    completions = list(completer.get_completions(doc, None))
    assert completions == []


def test_cd_completer_on_non_trigger():
    completer = CDCompleter()
    doc = Document(text="something_else")
    assert list(completer.get_completions(doc, None)) == []


@pytest.fixture
def setup_cd_test_dirs(tmp_path):
    # Current working directory structure
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2_long_name").mkdir()
    (tmp_path / "another_dir").mkdir()
    (tmp_path / "file_not_dir.txt").write_text("hello")

    # Home directory structure for testing '~' expansion
    mock_home_path = tmp_path / "mock_home" / "user"
    mock_home_path.mkdir(parents=True, exist_ok=True)
    (mock_home_path / "Documents").mkdir()
    (mock_home_path / "Downloads").mkdir()
    (mock_home_path / "Desktop").mkdir()
    return tmp_path, mock_home_path


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_initial_trigger(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(text="/cd ", cursor_position=len("/cd "))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    displays = sorted(
        [
            str(c.display) if isinstance(c.display, list) else str(c.display)
            for c in completions
        ]
    )

    # mock_home is also created at the root of tmp_path by the fixture
    assert texts == sorted(["another_dir/", "dir1/", "dir2_long_name/", "mock_home/"])
    assert displays == sorted(
        ["another_dir/", "dir1/", "dir2_long_name/", "mock_home/"]
    )
    assert not any("file_not_dir.txt" in t for t in texts)


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_partial_name(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(text="/cd di", cursor_position=len("/cd di"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    assert texts == sorted(["dir1/", "dir2_long_name/"])
    assert "another_dir/" not in texts


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_sub_directory(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    # Create a subdirectory with content
    sub_dir = tmp_path / "dir1" / "sub1"
    sub_dir.mkdir(parents=True)
    (tmp_path / "dir1" / "sub2_another").mkdir()

    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(text="/cd dir1/", cursor_position=len("/cd dir1/"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    # Completions should be relative to the 'base' typed in the command, which is 'dir1/'
    # So, the 'text' part of completion should be 'dir1/sub1/' and 'dir1/sub2_another/'
    assert texts == sorted(["dir1/sub1/", "dir1/sub2_another/"])
    displays = sorted([str(c.display) for c in completions])
    assert displays == sorted(["sub1/", "sub2_another/"])


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_partial_sub_directory(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    sub_dir = tmp_path / "dir1" / "sub_alpha"
    sub_dir.mkdir(parents=True)
    (tmp_path / "dir1" / "sub_beta").mkdir()

    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(text="/cd dir1/sub_a", cursor_position=len("/cd dir1/sub_a"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    assert texts == ["dir1/sub_alpha/"]
    displays = sorted([str(c.display) for c in completions])
    assert displays == ["sub_alpha/"]


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_home_directory_expansion(setup_cd_test_dirs, monkeypatch):
    _, mock_home_path = setup_cd_test_dirs
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: p.replace("~", str(mock_home_path))
    )
    # We don't chdir here, as ~ expansion should work irrespective of cwd

    completer = CDCompleter()
    doc = Document(text="/cd ~/", cursor_position=len("/cd ~/"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    displays = sorted([str(c.display) for c in completions])

    # The 'text' should include the '~/' prefix as that's what the user typed as base
    assert texts == sorted(["~/Desktop/", "~/Documents/", "~/Downloads/"])
    assert displays == sorted(["Desktop/", "Documents/", "Downloads/"])


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_home_directory_expansion_bare_tilde(
    setup_cd_test_dirs, monkeypatch
):
    _, mock_home_path = setup_cd_test_dirs
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: p.replace("~", str(mock_home_path))
    )

    completer = CDCompleter()
    doc = Document(text="/cd ~", cursor_position=len("/cd ~"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])

    assert texts == sorted(["~/Desktop/", "~/Documents/", "~/Downloads/"])
    assert "~/user/" not in texts


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_home_directory_expansion_partial(setup_cd_test_dirs, monkeypatch):
    _, mock_home_path = setup_cd_test_dirs
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: p.replace("~", str(mock_home_path))
    )

    completer = CDCompleter()
    doc = Document(text="/cd ~/Do", cursor_position=len("/cd ~/Do"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    displays = sorted([str(c.display) for c in completions])

    assert texts == sorted(["~/Documents/", "~/Downloads/"])
    assert displays == sorted(["Documents/", "Downloads/"])
    assert "~/Desktop/" not in texts


def test_cd_completer_non_existent_base(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(
        text="/cd non_existent_dir/", cursor_position=len("/cd non_existent_dir/")
    )
    completions = list(completer.get_completions(doc, None))
    assert completions == []


@pytest.mark.skipif(IS_WINDOWS, reason="Path separator expectations differ on Windows")
def test_cd_completer_root_path_keeps_absolute_prefix():
    completer = CDCompleter()
    with patch(
        "code_puppy.command_line.completers.list_directory",
        return_value=(["usr", "tmp"], []),
    ):
        doc = Document(text="/cd /", cursor_position=len("/cd /"))
        completions = list(completer.get_completions(doc, None))

    texts = sorted([c.text for c in completions])
    assert texts == sorted(["/usr/", "/tmp/"])


def test_cd_completer_permission_error_silently_handled(monkeypatch):
    completer = CDCompleter()
    # Patch the utility function used by CDCompleter
    with patch(
        "code_puppy.command_line.completers.list_directory",
        side_effect=PermissionError,
    ) as mock_list_dir:
        doc = Document(text="/cd somedir/", cursor_position=len("/cd somedir/"))
        completions = list(completer.get_completions(doc, None))
        assert completions == []
        mock_list_dir.assert_called_once()

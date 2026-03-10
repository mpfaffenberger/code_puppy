import asyncio
import contextlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import TransformationInput

from code_puppy.command_line.prompt_toolkit_completion import (
    AttachmentPlaceholderProcessor,
    CDCompleter,
    FilePathCompleter,
    PromptSubmission,
    SetCompleter,
    clear_active_prompt_surface,
    get_active_prompt_surface_kind,
    get_prompt_with_active_model,
    get_input_with_combined_completion,
    has_active_prompt_surface,
    is_shell_prompt_suspended,
    prompt_for_submission,
    render_submitted_prompt_echo,
    register_active_prompt_surface,
    set_shell_prompt_suspended,
)
from code_puppy.command_line.interactive_runtime import (
    PromptRuntimeState,
    clear_active_interactive_runtime,
    register_active_interactive_runtime,
)

# Skip some path-format sensitive tests on Windows where backslashes are expected
IS_WINDOWS = os.name == "nt" or sys.platform.startswith("win")


@pytest.fixture
def active_runtime():
    runtime = PromptRuntimeState()
    register_active_interactive_runtime(runtime)
    yield runtime
    clear_active_interactive_runtime(runtime)


def setup_files(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "file1.txt").write_text("content1")
    (d / "file2.py").write_text("content2")
    (tmp_path / "file3.txt").write_text("hi")
    (tmp_path / ".hiddenfile").write_text("sneaky")
    return d


def test_no_symbol(tmp_path):
    completer = FilePathCompleter(symbol="@")
    doc = Document(text="no_completion_here", cursor_position=7)
    completions = list(completer.get_completions(doc, None))
    assert completions == []


def test_completion_basic(tmp_path, monkeypatch):
    setup_files(tmp_path)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        completer = FilePathCompleter(symbol="@")
        doc = Document(text="run @fi", cursor_position=7)
        completions = list(completer.get_completions(doc, None))
        # Should see file3.txt from the base dir, but NOT .hiddenfile
        values = {c.text for c in completions}
        assert any("file3.txt" in v for v in values)
        assert not any(".hiddenfile" in v for v in values)
    finally:
        os.chdir(cwd)


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
        # In modern prompt_toolkit, display is a FormattedText: a list of (style, text) tuples
        filenames = {
            c.display[0][1] if hasattr(c.display, "__getitem__") else str(c.display)
            for c in completions
        }
        assert "file1.txt" in filenames
        assert "file2.py" in filenames
    finally:
        os.chdir(cwd)


def test_completion_symbol_in_middle(tmp_path):
    setup_files(tmp_path)
    completer = FilePathCompleter(symbol="@")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        doc = Document(text="echo @fi then something", cursor_position=7)
        completions = list(completer.get_completions(doc, None))
        assert any("file3.txt" in c.text for c in completions)
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
    # display_meta can be FormattedText, so access its content
    assert completions[0].display_meta[0][1] == "set config key"


def test_set_completer_on_set_trigger(monkeypatch):
    # Simulate config keys
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
        lambda: ["foo", "bar"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_value",
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
        assert isinstance(meta, FormattedText)
        assert len(meta) == 1
        assert meta[0][1] == ""


def test_set_completer_partial_key(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
        lambda: ["long_key_name", "other_key", "model"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_value",
        lambda key: "value_for_" + key if key == "long_key_name" else None,
    )
    completer = SetCompleter()

    doc = Document(text="/set long_k", cursor_position=len("/set long_k"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    # `text` for partial key completion should be the key itself and its value part
    assert completions[0].text == "long_key_name = value_for_long_key_name"
    # Display meta should be empty now
    assert isinstance(completions[0].display_meta, FormattedText)
    assert len(completions[0].display_meta) == 1
    assert completions[0].display_meta[0][1] == ""

    doc = Document(text="/set oth", cursor_position=len("/set oth"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 1
    assert completions[0].text == "other_key = "
    # Display meta should be empty now
    assert isinstance(completions[0].display_meta, FormattedText)
    assert len(completions[0].display_meta) == 1
    assert completions[0].display_meta[0][1] == ""


def test_set_completer_excludes_model_key(monkeypatch):
    # Ensure 'model' is a config key but SetCompleter doesn't offer it
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
        lambda: ["api_key", "model", "temperature"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_value",
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


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_submitted_prompt_echo(mock_create_output, mock_print_formatted_text):
    mock_output = MagicMock()
    mock_create_output.return_value = mock_output

    render_submitted_prompt_echo("queued task")

    mock_create_output.assert_called_once()
    mock_print_formatted_text.assert_called_once()
    rendered = mock_print_formatted_text.call_args.args[0]
    assert any("queued task" in text for _style, text in rendered)


@patch("code_puppy.command_line.prompt_toolkit_completion.print_formatted_text")
@patch("prompt_toolkit.output.defaults.create_output")
def test_render_submitted_prompt_echo_uses_prompt_app_when_available(
    mock_create_output, mock_print_formatted_text, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)

    render_submitted_prompt_echo("queued task")

    session.app.print_text.assert_called_once()
    mock_create_output.assert_called_once()
    mock_print_formatted_text.assert_not_called()


def test_set_completer_excludes_puppy_token(monkeypatch):
    # Ensure 'puppy_token' is a config key but SetCompleter doesn't offer it
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_config_keys",
        lambda: ["puppy_token", "user_name", "temp_dir"],
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_value",
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
            "".join(item[1] for item in c.display)
            if isinstance(c.display, list)
            else str(c.display)
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
    displays = sorted(["".join(item[1] for item in c.display) for c in completions])
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
    displays = sorted(["".join(item[1] for item in c.display) for c in completions])
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
    displays = sorted(["".join(item[1] for item in c.display) for c in completions])

    # The 'text' should include the '~/' prefix as that's what the user typed as base
    assert texts == sorted(["~/Desktop/", "~/Documents/", "~/Downloads/"])
    assert displays == sorted(["Desktop/", "Documents/", "Downloads/"])


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
    displays = sorted(["".join(item[1] for item in c.display) for c in completions])

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


def test_cd_completer_permission_error_silently_handled(monkeypatch):
    completer = CDCompleter()
    # Patch the utility function used by CDCompleter
    with patch(
        "code_puppy.command_line.prompt_toolkit_completion.list_directory",
        side_effect=PermissionError,
    ) as mock_list_dir:
        doc = Document(text="/cd somedir/", cursor_position=len("/cd somedir/"))
        completions = list(completer.get_completions(doc, None))
        assert completions == []
        mock_list_dir.assert_called_once()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion.FileHistory")
@patch("code_puppy.command_line.prompt_toolkit_completion.merge_completers")
async def test_get_input_with_combined_completion_defaults(
    mock_merge_completers, mock_file_history, mock_prompt_session_cls
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test input")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_merge_completers.return_value = MagicMock()  # Mocked merged completer

    result = await get_input_with_combined_completion()

    mock_prompt_session_cls.assert_called_once()
    assert (
        mock_prompt_session_cls.call_args[1]["completer"]
        == mock_merge_completers.return_value
    )
    assert mock_prompt_session_cls.call_args[1]["history"] is None
    assert mock_prompt_session_cls.call_args[1]["complete_while_typing"] is True
    assert "key_bindings" in mock_prompt_session_cls.call_args[1]
    assert "input_processors" in mock_prompt_session_cls.call_args[1]
    assert isinstance(
        mock_prompt_session_cls.call_args[1]["input_processors"][0],
        AttachmentPlaceholderProcessor,
    )

    mock_session_instance.prompt_async.assert_called_once()
    # Check default prompt string was converted to FormattedText
    assert isinstance(mock_session_instance.prompt_async.call_args[0][0], FormattedText)
    assert mock_session_instance.prompt_async.call_args[0][0] == FormattedText(
        [(None, ">>> ")]
    )
    assert "style" in mock_session_instance.prompt_async.call_args[1]

    # NOTE: update_model_in_input is no longer called from the prompt layer.
    # Instead, /model commands are handled by the command handler.
    # The prompt layer now just returns the input as-is.
    assert result == "test input"
    mock_file_history.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion.SafeFileHistory")
async def test_get_input_with_combined_completion_with_history(
    mock_safe_file_history, mock_prompt_session_cls
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="input with history")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_history_instance = MagicMock()
    mock_safe_file_history.return_value = mock_history_instance

    history_path = "~/.my_test_history"
    result = await get_input_with_combined_completion(history_file=history_path)

    mock_safe_file_history.assert_called_once_with(history_path)
    assert mock_prompt_session_cls.call_args[1]["history"] == mock_history_instance
    # NOTE: update_model_in_input is no longer called from the prompt layer.
    assert result == "input with history"


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_with_combined_completion_custom_prompt(
    mock_prompt_session_cls,
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="custom prompt input")
    mock_prompt_session_cls.return_value = mock_session_instance

    # Test with string prompt
    custom_prompt_str = "Custom> "
    await get_input_with_combined_completion(prompt_str=custom_prompt_str)
    assert mock_session_instance.prompt_async.call_args[0][0] == FormattedText(
        [(None, custom_prompt_str)]
    )

    # Test with FormattedText prompt
    custom_prompt_ft = FormattedText([("class:test", "Formatted>")])
    await get_input_with_combined_completion(prompt_str=custom_prompt_ft)
    assert mock_session_instance.prompt_async.call_args[0][0] == custom_prompt_ft


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_with_combined_completion_no_model_update(
    mock_prompt_session_cls,
):
    raw_input = "raw user input"
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value=raw_input)
    mock_prompt_session_cls.return_value = mock_session_instance

    result = await get_input_with_combined_completion()
    # NOTE: update_model_in_input is no longer called from the prompt layer.
    # The prompt layer now just returns the input as-is.
    assert result == raw_input


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.patch_stdout")
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_prompt_for_submission_uses_non_raw_patch_stdout(
    mock_prompt_session_cls, mock_patch_stdout
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test input")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_patch_stdout.return_value.__enter__ = MagicMock()
    mock_patch_stdout.return_value.__exit__ = MagicMock(return_value=False)

    result = await prompt_for_submission()

    assert result == PromptSubmission(action="submit", text="test input")
    mock_patch_stdout.assert_called_once_with()


# To test key bindings, we need to inspect the KeyBindings object passed to PromptSession
# We can get it from the mock_prompt_session_cls.call_args


@pytest.mark.xfail(
    reason="Alt+M binding representation varies across prompt_toolkit versions; current implementation may not expose Keys.Escape + 'm' tuple.",
    strict=False,
)
@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_key_binding_alt_m(mock_prompt_session_cls):
    # We don't need the function to run fully, just to set up PromptSession
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    # Find the Alt+M binding (Escape, 'm')
    alt_m_handler = None
    for binding in bindings.bindings:
        if (
            len(binding.keys) == 2
            and binding.keys[0] == Keys.Escape
            and binding.keys[1] == "m"
        ):
            alt_m_handler = binding.handler
            break
    assert alt_m_handler is not None, "Alt+M keybinding not found"


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_key_binding_escape(mock_prompt_session_cls):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test")
    mock_prompt_session_cls.return_value = mock_session_instance

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    found_escape_handler = None
    for binding_obj in bindings.bindings:
        if binding_obj.keys == (Keys.Escape,):
            found_escape_handler = binding_obj.handler
            break

    assert found_escape_handler is not None, "Standalone Escape keybinding not found"

    mock_event = MagicMock()
    mock_event.app = MagicMock()
    mock_event.app.exit.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        found_escape_handler(mock_event)
    mock_event.app.exit.assert_called_once_with(exception=KeyboardInterrupt)


def test_prompt_runtime_registry_round_trip(active_runtime):
    session = MagicMock()
    session.app = MagicMock()

    clear_active_prompt_surface()
    register_active_prompt_surface("main", session)

    assert has_active_prompt_surface() is True
    assert get_active_prompt_surface_kind() == "main"
    assert is_shell_prompt_suspended() is False

    session.app.invalidate.reset_mock()
    set_shell_prompt_suspended(True)
    assert is_shell_prompt_suspended() is True
    session.app.invalidate.assert_called_once()

    set_shell_prompt_suspended(False)
    clear_active_prompt_surface(session)
    assert has_active_prompt_surface() is False
    assert get_active_prompt_surface_kind() is None
    assert is_shell_prompt_suspended() is False


def test_spinner_invalidation_yields_to_recent_prompt_redraw(monkeypatch, active_runtime):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)
    session.app.invalidate.reset_mock()

    samples = iter([10.0, 10.02, 10.12])
    monkeypatch.setattr(
        "code_puppy.command_line.interactive_runtime.time.monotonic",
        lambda: next(samples),
    )

    active_runtime.invalidate_prompt()
    session.app.invalidate.assert_called_once()

    session.app.invalidate.reset_mock()
    active_runtime.invalidate_prompt_for_spinner()
    session.app.invalidate.assert_not_called()

    active_runtime.invalidate_prompt_for_spinner()
    session.app.invalidate.assert_called_once()


def test_get_prompt_with_active_model_omits_shell_status(monkeypatch, active_runtime):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    set_shell_prompt_suspended(True)

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with patch(
        "code_puppy.agents.agent_manager.get_current_agent",
        return_value=agent,
    ):
        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "shell running" not in rendered
    clear_active_prompt_surface()


def test_get_prompt_with_active_model_shows_thinking_status(monkeypatch, active_runtime):
    clear_active_prompt_surface()
    session = MagicMock()
    session.app = MagicMock()
    register_active_prompt_surface("main", session)
    active_runtime.running = True
    active_runtime.prompt_status_started_at = 0.0

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_puppy_name",
        lambda: "Buddy",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_active_model",
        lambda: "gpt-test",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.os.getcwd",
        lambda: "/tmp/demo",
    )
    monkeypatch.setattr(
        "code_puppy.command_line.interactive_runtime.time.monotonic",
        lambda: 0.18,
    )

    agent = MagicMock()
    agent.display_name = "code-puppy"
    agent.get_model_name.return_value = "gpt-test"

    with (
        patch(
            "code_puppy.agents.agent_manager.get_current_agent",
            return_value=agent,
        ),
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.SpinnerBase.get_context_info",
            return_value="Tokens: 1,650/272,000 (0.6% used)",
        ),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
    ):
        rendered = "".join(text for _style, text in get_prompt_with_active_model())

    assert "Buddy is thinking..." in rendered
    assert "(  🐶  ) " in rendered
    assert "Tokens: 1,650/272,000 (0.6% used)" in rendered
    assert rendered.index("Buddy is thinking...") < rendered.index("─" * 80)
    clear_active_prompt_surface()
@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_get_input_registers_active_prompt_surface(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()

    async def fake_prompt_async(*args, **kwargs):
        assert has_active_prompt_surface() is True
        assert get_active_prompt_surface_kind() == "main"
        set_shell_prompt_suspended(True)
        assert is_shell_prompt_suspended() is True
        set_shell_prompt_suspended(False)
        return "test input"

    session.prompt_async = AsyncMock(side_effect=fake_prompt_async)
    mock_prompt_session_cls.return_value = session

    result = await get_input_with_combined_completion()

    assert result == "test input"
    assert has_active_prompt_surface() is False
    assert is_shell_prompt_suspended() is False


@pytest.mark.asyncio
async def test_prompt_runtime_refreshes_spinner_while_running(active_runtime):
    session = MagicMock()
    session.app = MagicMock()
    active_runtime.register_prompt_surface(session)

    worker = asyncio.create_task(asyncio.sleep(1))
    active_runtime.mark_running(worker)
    session.app.invalidate.reset_mock()

    try:
        await asyncio.sleep(0.12)
        assert session.app.invalidate.called
        assert active_runtime.prompt_status_task is not None
    finally:
        active_runtime.mark_idle()
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    await asyncio.sleep(0)
    assert active_runtime.prompt_status_task is None


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_ctrl_x_interrupts_shell_when_prompt_is_suspended(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()
    session.prompt_async = AsyncMock(return_value="done")
    mock_prompt_session_cls.return_value = session

    await get_input_with_combined_completion()

    bindings = mock_prompt_session_cls.call_args[1]["key_bindings"]
    ctrl_x_handler = next(
        binding.handler
        for binding in bindings.bindings
        if binding.keys == (Keys.ControlX,)
    )

    register_active_prompt_surface("main", session)
    set_shell_prompt_suspended(True)

    mock_event = MagicMock()
    mock_event.app = MagicMock()

    with patch(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes",
        return_value=1,
    ) as mock_kill:
        with patch("code_puppy.messaging.emit_warning"):
            ctrl_x_handler(mock_event)

    mock_kill.assert_called_once()
    mock_event.app.exit.assert_not_called()
    clear_active_prompt_surface()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
async def test_prompt_for_submission_returns_inline_queue_action(
    mock_prompt_session_cls, active_runtime
):
    session = MagicMock()
    session.app = MagicMock()
    session.default_buffer = MagicMock()
    session.prompt_async = AsyncMock(
        return_value=PromptSubmission(action="queue", text="queued task")
    )
    mock_prompt_session_cls.return_value = session

    result = await prompt_for_submission()

    assert result == PromptSubmission(action="queue", text="queued task")


@pytest.mark.asyncio
async def test_attachment_placeholder_processor_renders_images(tmp_path: Path) -> None:
    image_path = tmp_path / "fluffy pupper.png"
    image_path.write_bytes(b"png")

    processor = AttachmentPlaceholderProcessor()
    document_text = f"describe {image_path} now"
    document = Document(text=document_text, cursor_position=len(document_text))

    fragments = [("", document_text)]
    buffer = Buffer(document=document)
    control = BufferControl(buffer=buffer)
    transformation_input = TransformationInput(
        buffer_control=control,
        document=document,
        lineno=0,
        source_to_display=lambda i: i,
        fragments=fragments,
        width=len(document_text),
        height=1,
    )

    transformed = processor.apply_transformation(transformation_input)
    rendered_text = "".join(text for _style, text in transformed.fragments)

    assert "[png image]" in rendered_text
    assert "fluffy pupper" not in rendered_text

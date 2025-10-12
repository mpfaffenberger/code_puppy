import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.keys import Keys

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import TransformationInput

from code_puppy.command_line.prompt_toolkit_completion import (
    AttachmentPlaceholderProcessor,
    CDCompleter,
    FilePathCompleter,
    SetCompleter,
    get_input_with_combined_completion,
)


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


def test_cd_completer_partial_name(setup_cd_test_dirs, monkeypatch):
    tmp_path, _ = setup_cd_test_dirs
    monkeypatch.chdir(tmp_path)
    completer = CDCompleter()
    doc = Document(text="/cd di", cursor_position=len("/cd di"))
    completions = list(completer.get_completions(doc, None))
    texts = sorted([c.text for c in completions])
    assert texts == sorted(["dir1/", "dir2_long_name/"])
    assert "another_dir/" not in texts


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
@patch("code_puppy.command_line.prompt_toolkit_completion.update_model_in_input")
@patch("code_puppy.command_line.prompt_toolkit_completion.merge_completers")
async def test_get_input_with_combined_completion_defaults(
    mock_merge_completers, mock_update_model, mock_file_history, mock_prompt_session_cls
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="test input")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_update_model.return_value = "processed input"
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

    mock_update_model.assert_called_once_with("test input")
    assert result == "processed input"
    mock_file_history.assert_not_called()


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion.FileHistory")
@patch("code_puppy.command_line.prompt_toolkit_completion.update_model_in_input")
async def test_get_input_with_combined_completion_with_history(
    mock_update_model, mock_file_history, mock_prompt_session_cls
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="input with history")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_update_model.return_value = "processed history input"
    mock_history_instance = MagicMock()
    mock_file_history.return_value = mock_history_instance

    history_path = "~/.my_test_history"
    result = await get_input_with_combined_completion(history_file=history_path)

    mock_file_history.assert_called_once_with(history_path)
    assert mock_prompt_session_cls.call_args[1]["history"] == mock_history_instance
    mock_update_model.assert_called_once_with("input with history")
    assert result == "processed history input"


@pytest.mark.asyncio
@patch("code_puppy.command_line.prompt_toolkit_completion.PromptSession")
@patch("code_puppy.command_line.prompt_toolkit_completion.update_model_in_input")
async def test_get_input_with_combined_completion_custom_prompt(
    mock_update_model, mock_prompt_session_cls
):
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value="custom prompt input")
    mock_prompt_session_cls.return_value = mock_session_instance
    mock_update_model.return_value = "processed custom prompt"

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
@patch(
    "code_puppy.command_line.prompt_toolkit_completion.update_model_in_input",
    return_value=None,
)  # Simulate no model update
async def test_get_input_with_combined_completion_no_model_update(
    mock_update_model_no_change, mock_prompt_session_cls
):
    raw_input = "raw user input"
    mock_session_instance = MagicMock()
    mock_session_instance.prompt_async = AsyncMock(return_value=raw_input)
    mock_prompt_session_cls.return_value = mock_session_instance

    result = await get_input_with_combined_completion()
    mock_update_model_no_change.assert_called_once_with(raw_input)
    assert result == raw_input


# To test key bindings, we need to inspect the KeyBindings object passed to PromptSession
# We can get it from the mock_prompt_session_cls.call_args


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

    mock_event = MagicMock()
    mock_event.app.current_buffer = MagicMock()
    alt_m_handler(mock_event)
    mock_event.app.current_buffer.insert_text.assert_called_once_with("\n")


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


@pytest.mark.asyncio
async def test_attachment_placeholder_processor_handles_links() -> None:
    processor = AttachmentPlaceholderProcessor()
    document_text = "check https://example.com/pic.png"
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

    assert "[link]" in rendered_text
    assert "https://example.com/pic.png" not in rendered_text

import os
from prompt_toolkit.document import Document

from code_puppy.command_line.prompt_toolkit_completion import FilePathCompleter, SetCompleter, CDCompleter, get_prompt_with_active_model


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

def test_set_completer_on_set_trigger(monkeypatch):
    # Simulate config keys
    monkeypatch.setattr("code_puppy.config.get_config_keys", lambda: ["foo", "bar"])
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "woo" if key == "foo" else None)
    completer = SetCompleter()
    doc = Document(text='~set ')
    completions = list(completer.get_completions(doc, None))
    completion_texts = [c.text for c in completions]
    assert completion_texts

def test_cd_completer_on_non_trigger():
    completer = CDCompleter()
    doc = Document(text="something_else")
    assert list(completer.get_completions(doc, None)) == []

def test_get_prompt_with_active_model(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_puppy_name", lambda: 'Biscuit')
    monkeypatch.setattr("code_puppy.command_line.model_picker_completion.get_active_model", lambda: 'TestModel')
    monkeypatch.setattr("os.getcwd", lambda: '/home/user/test')
    monkeypatch.setattr("os.path.expanduser", lambda x: x.replace('~', '/home/user'))
    formatted = get_prompt_with_active_model()
    text = ''.join(fragment[1] for fragment in formatted)
    assert 'biscuit' in text.lower()
    assert '[b]' in text.lower()   # Model abbreviation, update if prompt changes
    assert "/test" in text
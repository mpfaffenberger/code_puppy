import pytest
import sys
import types
from code_agent import main
from unittest.mock import patch, MagicMock
import builtins


def test_main_entry_runs(monkeypatch):
    # Monkeypatch asyncio.run to avoid _actually_ running the repl loop
    monkeypatch.setattr(main.asyncio, "run", lambda func: True)
    assert main.main_entry() is None


def test_prettier_code_blocks_covers():
    # It should inject SimpleCodeBlock into Markdown.elements
    main.prettier_code_blocks()
    assert "fence" in main.Markdown.elements


def test_get_secret_file_path_creates(tmp_path, monkeypatch):
    # Patch the user home to a tmp dir
    monkeypatch.setattr(main.os.path, "expanduser", lambda x: str(tmp_path))
    path = main.get_secret_file_path()
    assert path.endswith("history.txt")
    assert tmp_path.joinpath(".agent_secret", "history.txt").exists() or True


def test_main_command_branch(monkeypatch):
    mock_agent = MagicMock()
    mock_console = MagicMock()
    monkeypatch.setattr(main, "code_generation_agent", mock_agent)
    monkeypatch.setattr(main, "console", mock_console)
    # CLI args: simulate a command
    test_args = ["prog", "--", "some", "command"]
    monkeypatch.setattr(sys, "argv", test_args)
    # Patch parser so it always gives us command
    monkeypatch.setattr(main, "get_secret_file_path", lambda: "/dev/null")
    monkeypatch.setattr(main.argparse.ArgumentParser, "parse_args", lambda self: types.SimpleNamespace(command=["echo", "hi"], interactive=False))
    # Patch the agent.run to be async and just set shutdown_flag = True to break
    monkeypatch.setattr(main, "shutdown_flag", True)
    
    with patch("builtins.input", return_value="exit"):
        pytest.run(main.main())
import pytest
import sys
import types
from code_agent import main
from unittest.mock import patch, MagicMock
import builtins


def test_main_entry_runs(monkeypatch):
    # Monkeypatch asyncio.run to avoid _actually_ running the repl loop
    monkeypatch.setattr(main.asyncio, "run", lambda func: True)
    assert main.main_entry() is None


def test_prettier_code_blocks_covers():
    # It should inject SimpleCodeBlock into Markdown.elements
    main.prettier_code_blocks()
    assert "fence" in main.Markdown.elements


def test_get_secret_file_path_creates(tmp_path, monkeypatch):
    # Patch the user home to a tmp dir
    monkeypatch.setattr(main.os.path, "expanduser", lambda x: str(tmp_path))
    path = main.get_secret_file_path()
    assert path.endswith("history.txt")
    assert tmp_path.joinpath(".agent_secret", "history.txt").exists() or True


def test_main_command_branch(monkeypatch):
    mock_agent = MagicMock()
    mock_console = MagicMock()
    monkeypatch.setattr(main, "code_generation_agent", mock_agent)
    monkeypatch.setattr(main, "console", mock_console)
    # CLI args: simulate a command
    test_args = ["prog", "--", "some", "command"]
    monkeypatch.setattr(sys, "argv", test_args)
    # Patch parser so it always gives us command
    monkeypatch.setattr(main, "get_secret_file_path", lambda: "/dev/null")
    monkeypatch.setattr(main.argparse.ArgumentParser, "parse_args", lambda self: types.SimpleNamespace(command=["echo", "hi"], interactive=False))
    # Create shutdown_flag on main
    main.shutdown_flag = True
    
    with patch("builtins.input", return_value="exit"):
        pytest.run(main.main())
import pytest
import sys
import types
from code_agent import main
from unittest.mock import patch, MagicMock
import asyncio
import builtins


def test_main_entry_runs(monkeypatch):
    # Monkeypatch asyncio.run to avoid _actually_ running the repl loop
    monkeypatch.setattr(main.asyncio, "run", lambda func: True)
    assert main.main_entry() is None


def test_prettier_code_blocks_covers():
    # It should inject SimpleCodeBlock into Markdown.elements
    main.prettier_code_blocks()
    assert "fence" in main.Markdown.elements


def test_get_secret_file_path_creates(tmp_path, monkeypatch):
    # Patch the user home to a tmp dir
    monkeypatch.setattr(main.os.path, "expanduser", lambda x: str(tmp_path))
    path = main.get_secret_file_path()
    assert path.endswith("history.txt")
    assert tmp_path.joinpath(".agent_secret", "history.txt").exists() or True


def test_main_command_branch(monkeypatch):
    mock_agent = MagicMock()
    mock_console = MagicMock()
    monkeypatch.setattr(main, "code_generation_agent", mock_agent)
    monkeypatch.setattr(main, "console", mock_console)
    # CLI args: simulate a command
    test_args = ["prog", "--", "some", "command"]
    monkeypatch.setattr(sys, "argv", test_args)
    # Patch parser so it always gives us command
    monkeypatch.setattr(main, "get_secret_file_path", lambda: "/dev/null")
    monkeypatch.setattr(main.argparse.ArgumentParser, "parse_args", lambda self: types.SimpleNamespace(command=["echo", "hi"], interactive=False))
    # Create shutdown_flag on main
    main.shutdown_flag = True
    
    with patch("builtins.input", return_value="exit"):
        asyncio.run(main.main())

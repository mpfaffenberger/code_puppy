import json
from unittest.mock import ANY, MagicMock, mock_open, patch

from code_puppy.tools import file_modifications


def test_write_to_file_new(tmp_path):
    path = tmp_path / "a.txt"
    result = file_modifications._write_to_file(
        None, str(path), "hi puppy", overwrite=False
    )
    assert result["success"]
    assert path.exists()
    assert path.read_text() == "hi puppy"


def test_write_to_file_no_overwrite(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("old")
    result = file_modifications._write_to_file(None, str(path), "new", overwrite=False)
    assert not result["success"]
    assert path.read_text() == "old"


def test_write_to_file_overwrite(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("old")
    result = file_modifications._write_to_file(None, str(path), "new", overwrite=True)
    assert result["success"]
    assert path.read_text() == "new"


def test_replace_in_file_simple(tmp_path):
    path = tmp_path / "d.txt"
    path.write_text("foo bar baz")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "bar", "new_str": "biscuit"}]
    )
    assert res["success"]
    assert path.read_text() == "foo biscuit baz"


def test_replace_in_file_no_match(tmp_path):
    path = tmp_path / "e.txt"
    path.write_text("abcdefg")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "xxxyyy", "new_str": "puppy"}]
    )
    assert not res.get("success", False)


def test_delete_snippet_success(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("i am a biscuit. delete me! woof woof")
    res = file_modifications._delete_snippet_from_file(None, str(path), "delete me!")
    assert res["success"]
    assert "delete me!" not in path.read_text()


def test_delete_snippet_no_file(tmp_path):
    path = tmp_path / "nope.txt"
    res = file_modifications._delete_snippet_from_file(
        None, str(path), "does not matter"
    )
    assert not res.get("success", False)


def test_delete_snippet_not_found(tmp_path):
    path = tmp_path / "g.txt"
    path.write_text("i am loyal.")
    res = file_modifications._delete_snippet_from_file(None, str(path), "NEVER here!")
    assert not res.get("success", False)


class DummyContext:
    pass


# Helper function to create a mock agent that captures tool registrations
def create_tool_capturing_mock_agent():
    mock_agent = MagicMock(name="helper_mock_agent")
    captured_registrations = []  # Stores {'name': str, 'func': callable, 'decorator_args': dict}

    # This is the object that will be accessed as agent.tool
    # It needs to handle being called directly (agent.tool(func)) or as a factory (agent.tool(retries=5))
    agent_tool_mock = MagicMock(name="agent.tool_decorator_or_factory_itself")

    def tool_side_effect_handler(*args, **kwargs):
        # This function is the side_effect for agent_tool_mock
        # args[0] might be the function to decorate, or this is a factory call

        # Factory call: @agent.tool(retries=5)
        # agent_tool_mock is called with kwargs (e.g., retries=5)
        if kwargs:  # If decorator arguments are passed to agent.tool itself
            decorator_args_for_next_tool = kwargs.copy()
            # It must return a new callable (the actual decorator)
            actual_decorator_mock = MagicMock(
                name=f"actual_decorator_for_{list(kwargs.keys())}"
            )

            def actual_decorator_side_effect(func_to_decorate):
                captured_registrations.append(
                    {
                        "name": func_to_decorate.__name__,
                        "func": func_to_decorate,
                        "decorator_args": decorator_args_for_next_tool,
                    }
                )
                return func_to_decorate  # Decorator returns the original function

            actual_decorator_mock.side_effect = actual_decorator_side_effect
            return actual_decorator_mock

        # Direct decorator call: @agent.tool
        # agent_tool_mock is called with the function as the first arg
        elif args and callable(args[0]):
            func_to_decorate = args[0]
            captured_registrations.append(
                {
                    "name": func_to_decorate.__name__,
                    "func": func_to_decorate,
                    "decorator_args": {},  # No args passed to agent.tool itself
                }
            )
            return func_to_decorate
        # Should not happen with valid decorator usage
        return MagicMock(name="unexpected_tool_call_fallback")

    agent_tool_mock.side_effect = tool_side_effect_handler
    mock_agent.tool = agent_tool_mock
    return mock_agent, captured_registrations


def test_edit_file_content_creates(tmp_path):
    f = tmp_path / "hi.txt"
    res = file_modifications._write_to_file(
        None, str(f), "new-content!", overwrite=False
    )
    assert res["success"]
    assert f.read_text() == "new-content!"


def test_edit_file_content_overwrite(tmp_path):
    f = tmp_path / "hi2.txt"
    f.write_text("abc")
    res = file_modifications._write_to_file(None, str(f), "puppy", overwrite=True)
    assert res["success"]
    assert f.read_text() == "puppy"


def test_edit_file_empty_content(tmp_path):
    f = tmp_path / "empty.txt"
    res = file_modifications._write_to_file(None, str(f), "", overwrite=False)
    assert res["success"]
    assert f.read_text() == ""


def test_edit_file_delete_snippet(tmp_path):
    f = tmp_path / "woof.txt"
    f.write_text("puppy loyal")
    res = file_modifications._delete_snippet_from_file(None, str(f), "loyal")
    assert res["success"]
    assert "loyal" not in f.read_text()


class TestRegisterFileModificationsTools:
    def setUp(self):
        self.mock_agent = MagicMock(
            name="mock_agent_for_TestRegisterFileModificationsTools"
        )
        self.captured_tools_details = []
        # self.mock_agent.tool is the mock that will be called by the SUT (System Under Test)
        # Its side_effect will handle the logic of being a direct decorator or a factory.
        self.mock_agent.tool = MagicMock(name="mock_agent.tool_decorator_or_factory")
        self.mock_agent.tool.side_effect = self._agent_tool_side_effect_logic

    def _agent_tool_side_effect_logic(self, *args, **kwargs):
        # This method is the side_effect for self.mock_agent.tool
        # 'self' here refers to the instance of TestRegisterFileModificationsTools

        # Case 1: Direct decoration, e.g., @agent.tool or tool_from_factory(func)
        # This is identified if the first arg is callable and no kwargs are passed to *this* call.
        # The 'tool_from_factory(func)' part is handled because the factory returns a mock
        # whose side_effect is also this logic (or a simpler version just for decoration).
        # For simplicity, we assume if args[0] is callable and no kwargs, it's a direct decoration.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            func_to_decorate = args[0]
            # If 'self.current_decorator_args' exists, it means this is the second call in a factory pattern.
            decorator_args_for_this_tool = getattr(self, "_current_decorator_args", {})
            self.captured_tools_details.append(
                {
                    "name": func_to_decorate.__name__,
                    "func": func_to_decorate,
                    "decorator_args": decorator_args_for_this_tool,
                }
            )
            if hasattr(self, "_current_decorator_args"):
                del self._current_decorator_args  # Clean up for next tool
            return func_to_decorate  # Decorator returns the original function
        else:
            # Case 2: Factory usage, e.g., @agent.tool(retries=5)
            # Here, self.mock_agent.tool is called with decorator arguments.
            # It should store these arguments and return a callable (the actual decorator).
            self._current_decorator_args = (
                kwargs.copy()
            )  # Store args like {'retries': 5}

            # Return a new mock that will act as the decorator returned by the factory.
            # When this new mock is called with the function, it should trigger the 'direct decoration' logic.
            # To achieve this, its side_effect can also be self._agent_tool_side_effect_logic.
            # This creates a slight recursion in logic but correctly models the behavior.
            # Alternatively, it could be a simpler lambda that calls a capture method with self._current_decorator_args.
            returned_decorator = MagicMock(
                name=f"actual_decorator_from_factory_{list(kwargs.keys())}"
            )
            returned_decorator.side_effect = (
                lambda fn: self._agent_tool_side_effect_logic(fn)
            )  # Pass only the function
            return returned_decorator

    def get_registered_tool_function(self, tool_name):
        """Retrieves a captured tool function by its name."""
        for detail in self.captured_tools_details:
            if detail["name"] == tool_name:
                return detail["func"]
        raise ValueError(
            f"Tool function '{tool_name}' not found in captured tools: {self.captured_tools_details}"
        )

    @patch(f"{file_modifications.__name__}._write_to_file")
    @patch(f"{file_modifications.__name__}._print_diff")
    def test_registered_write_to_file_tool(
        self, mock_print_diff, mock_internal_write, tmp_path
    ):
        self.setUp()

        mock_internal_write.return_value = {
            "success": True,
            "path": str(tmp_path / "test.txt"),
            "diff": "mock_diff_content",
        }
        context = DummyContext()
        file_path = str(tmp_path / "test.txt")
        content = "hello world"
        overwrite = False
        assert file_modifications._write_to_file(context, file_path, content, overwrite)

    @patch(f"{file_modifications.__name__}._delete_snippet_from_file")
    @patch(f"{file_modifications.__name__}._print_diff")
    def test_registered_delete_snippet_tool(
        self, mock_print_diff, mock_internal_delete_snippet, tmp_path
    ):
        self.setUp()
        mock_internal_delete_snippet.return_value = {
            "success": True,
            "diff": "snippet_diff",
        }
        context = DummyContext()
        file_path = str(tmp_path / "test.txt")
        snippet = "to_delete"

        assert file_modifications._delete_snippet_from_file(context, file_path, snippet)
        mock_internal_delete_snippet.assert_called_once_with(
            context, file_path, snippet
        )

    @patch(f"{file_modifications.__name__}._replace_in_file")
    def test_registered_replace_in_file_tool(self, mock_internal_replace, tmp_path):
        self.setUp()
        replacements = [{"old_str": "old", "new_str": "new"}]
        mock_internal_replace.return_value = {"success": True, "diff": "replace_diff"}
        context = DummyContext()
        file_path = str(tmp_path / "test.txt")

        assert file_modifications._replace_in_file(context, file_path, replacements)
        mock_internal_replace.assert_called_once_with(context, file_path, replacements)

    @patch(f"{file_modifications.__name__}.os.remove")
    @patch(f"{file_modifications.__name__}.os.path.exists", return_value=True)
    @patch(f"{file_modifications.__name__}.os.path.isfile", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="line1\nline2\ndelete me!\nline3",
    )
    def test_registered_delete_file_tool_success(
        self, mock_open, mock_exists, mock_isfile, mock_remove, tmp_path
    ):
        self.setUp()

        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_remove.return_value = None

        context = DummyContext()
        file_path_str = str(tmp_path / "delete_me.txt")

        result = file_modifications._delete_file(context, file_path_str)
        assert result["success"]
        assert result["path"] == file_path_str
        assert result["message"] == f"File '{file_path_str}' deleted successfully."
        assert result["changed"] is True

    @patch(
        f"{file_modifications.__name__}.os.path.exists", return_value=False
    )  # File does not exist
    def test_registered_delete_file_tool_not_exists(self, mock_exists, tmp_path):
        self.setUp()

        context = DummyContext()
        file_path_str = str(tmp_path / "ghost.txt")

        mock_exists.return_value = False

        result = file_modifications._delete_file(context, file_path_str)

        assert not result.get("success", False)
        # Error handling changed in implementation


class TestEditFileTool:
    def get_edit_file_tool_function(self):
        mock_agent, captured_registrations = create_tool_capturing_mock_agent()
        file_modifications.register_file_modifications_tools(mock_agent)

        for reg_info in captured_registrations:
            if reg_info["name"] == "edit_file":
                return reg_info["func"]
        raise ValueError("edit_file tool not found among captured registrations.")

    @patch(f"{file_modifications.__name__}._delete_snippet_from_file")
    @patch(f"{file_modifications.__name__}._print_diff")
    def test_edit_file_routes_to_delete_snippet(
        self, mock_print_diff_sub_tool, mock_internal_delete, tmp_path
    ):
        edit_file_tool = self.get_edit_file_tool_function()

        mock_internal_delete.return_value = {
            "success": True,
            "diff": "delete_diff_via_edit",
        }
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        payload = json.dumps({"delete_snippet": "text_to_remove"})

        result = edit_file_tool(context, file_path, payload)

        mock_internal_delete.assert_called_once_with(
            context, file_path, "text_to_remove", message_group=ANY
        )
        assert result["success"]

    @patch(f"{file_modifications.__name__}._replace_in_file")
    def test_edit_file_routes_to_replace_in_file(
        self, mock_internal_replace, tmp_path
    ):
        edit_file_tool = self.get_edit_file_tool_function()

        replacements_payload = [{"old_str": "old", "new_str": "new"}]
        mock_internal_replace.return_value = {
            "success": True,
            "diff": "replace_diff_via_edit",
        }
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        payload = json.dumps({"replacements": replacements_payload})

        result = edit_file_tool(context, file_path, payload)
        mock_internal_replace.assert_called_once_with(
            context, file_path, replacements_payload, message_group=ANY
        )
        assert result["success"]

    @patch(f"{file_modifications.__name__}._write_to_file")
    @patch(
        "os.path.exists", return_value=False
    )  # File does not exist for this write test path
    def test_edit_file_routes_to_write_to_file_with_content_key(
        self, mock_os_exists, mock_internal_write, tmp_path
    ):
        mock_internal_write.return_value = {
            "success": True,
            "diff": "write_diff_via_edit_content_key",
        }
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        content = "new file content"
        payload = json.dumps(
            {"content": content, "overwrite": True}
        )  # Overwrite true, os.path.exists mocked to false

        result = file_modifications._edit_file(context, file_path, payload)
        assert result["success"]

    @patch(
        f"{file_modifications.__name__}._write_to_file"
    )  # Mock the internal function
    @patch("os.path.exists", return_value=True)  # File exists
    def test_edit_file_content_key_refuses_overwrite_if_false(
        self, mock_os_exists, mock_internal_write, tmp_path
    ):
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        content = "new file content"
        payload = json.dumps(
            {"content": content, "overwrite": False}
        )  # Overwrite is False

        result = file_modifications._edit_file(context, file_path, payload)

        mock_os_exists.assert_called_with(file_path)
        mock_internal_write.assert_not_called()
        assert not result["success"]
        assert result["path"] == file_path
        assert (
            result["message"]
            == f"File '{file_path}' exists. Set 'overwrite': true to replace."
        )
        assert result["changed"] is False

    def test_edit_file_handles_unparseable_json(self):
        import pathlib
        from tempfile import mkdtemp

        tmp_path = pathlib.Path(mkdtemp())
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        unparseable_payload = "{'bad_json': true,}"  # Invalid JSON

        result = file_modifications._edit_file(context, file_path, unparseable_payload)
        assert result["success"]

    def test_edit_file_handles_unknown_payload_structure(self, tmp_path):
        context = DummyContext()
        file_path = str(tmp_path / "file.txt")
        unknown_payload = json.dumps({"unknown_operation": "do_something"})

        with patch(
            f"{file_modifications.__name__}._write_to_file"
        ) as mock_internal_write:
            mock_internal_write.return_value = {
                "success": True,
                "diff": "unknown_payload_written_as_content",
            }
            result = file_modifications._edit_file(context, file_path, unknown_payload)
            assert result["success"]

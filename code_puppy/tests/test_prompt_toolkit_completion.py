import unittest
from prompt_toolkit.document import Document
from code_puppy.command_line.prompt_toolkit_completion import FilePathCompleter


class TestFilePathCompleter(unittest.TestCase):
    def setUp(self):
        self.completer = FilePathCompleter("@")

    def test_no_symbol_in_text(self):
        document = Document(text="No symbol here", cursor_position=14)
        completions = list(self.completer.get_completions(document, None))
        self.assertEqual(completions, [])

    def test_symbol_with_partial_path(self):
        document = Document(
            text="Look at this: @code_puppy/com",
            cursor_position=len("Look at this: @code_puppy/com"),
        )
        completions = list(self.completer.get_completions(document, None))
        expected_completions = [c.text for c in completions]
        self.assertTrue(
            any(
                path.startswith("code_puppy/command_line")
                for path in expected_completions
            )
        )

    def test_hidden_files_completion(self):
        document = Document(
            text="@.", cursor_position=2
        )  # Assuming this is the home or current folder
        completions = list(self.completer.get_completions(document, None))
        hidden_files = [c.text for c in completions if c.text.startswith(".")]
        self.assertGreater(len(hidden_files), 0)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest

from code_puppy.tui.models.command_history import HistoryFileReader


class TestHistoryFileReader(unittest.TestCase):
    def setUp(self):
        # Create a temporary file for testing
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file_path = self.temp_file.name

        # Sample content with multiple commands
        sample_content = """
# 2023-01-01T12:00:00
First command

# 2023-01-01T13:00:00
Second command
with multiple lines

# 2023-01-01T14:00:00
Third command
"""
        # Write sample content to the temporary file
        with open(self.temp_file_path, "w") as f:
            f.write(sample_content)

        # Initialize reader with the temp file
        self.reader = HistoryFileReader(self.temp_file_path)

    def tearDown(self):
        # Clean up the temporary file
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)

    def test_read_history(self):
        # Test reading history entries
        entries = self.reader.read_history()

        # Check that we have the correct number of entries
        self.assertEqual(len(entries), 3)

        # Check that entries are in reverse chronological order (newest first)
        self.assertEqual(entries[0]["timestamp"], "2023-01-01T14:00:00")
        self.assertEqual(entries[0]["command"], "Third command")

        self.assertEqual(entries[1]["timestamp"], "2023-01-01T13:00:00")
        self.assertEqual(entries[1]["command"], "Second command\nwith multiple lines")

        self.assertEqual(entries[2]["timestamp"], "2023-01-01T12:00:00")
        self.assertEqual(entries[2]["command"], "First command")

    def test_read_history_with_limit(self):
        # Test reading history with a limit
        entries = self.reader.read_history(max_entries=2)

        # Check that we only get the specified number of entries
        self.assertEqual(len(entries), 2)

        # Check that we get the most recent entries
        self.assertEqual(entries[0]["timestamp"], "2023-01-01T14:00:00")
        self.assertEqual(entries[1]["timestamp"], "2023-01-01T13:00:00")

    def test_read_history_empty_file(self):
        # Create an empty file
        empty_file = tempfile.NamedTemporaryFile(delete=False)
        empty_file_path = empty_file.name
        empty_file.close()

        try:
            # Create reader with empty file
            empty_reader = HistoryFileReader(empty_file_path)

            # Should return empty list
            entries = empty_reader.read_history()
            self.assertEqual(len(entries), 0)
        finally:
            # Clean up
            if os.path.exists(empty_file_path):
                os.unlink(empty_file_path)

    def test_read_history_nonexistent_file(self):
        # Create reader with non-existent file
        nonexistent_reader = HistoryFileReader("/nonexistent/file/path")

        # Should return empty list, not raise an exception
        entries = nonexistent_reader.read_history()
        self.assertEqual(len(entries), 0)

    def test_format_timestamp(self):
        # Test default formatting
        formatted = self.reader.format_timestamp("2023-01-01T12:34:56")
        self.assertEqual(formatted, "12:34:56")

        # Test custom format
        formatted = self.reader.format_timestamp("2023-01-01T12:34:56", "%H:%M")
        self.assertEqual(formatted, "12:34")

        # Test invalid timestamp
        formatted = self.reader.format_timestamp("invalid")
        self.assertEqual(formatted, "invalid")


if __name__ == "__main__":
    unittest.main()

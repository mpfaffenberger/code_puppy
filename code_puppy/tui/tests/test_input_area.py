import unittest
from code_puppy.tui.components.input_area import InputArea


class TestInputArea(unittest.TestCase):
    def setUp(self):
        self.input_area = InputArea()

    def test_compose(self):
        # Should yield widgets without error
        widgets = list(self.input_area.compose())
        self.assertGreaterEqual(len(widgets), 3)


if __name__ == "__main__":
    unittest.main()

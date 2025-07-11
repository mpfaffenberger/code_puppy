import unittest
from code_puppy.tui.components.sidebar import Sidebar


class TestSidebar(unittest.TestCase):
    def setUp(self):
        self.sidebar = Sidebar()

    def test_compose(self):
        widgets = list(self.sidebar.compose())
        self.assertGreaterEqual(len(widgets), 2)


if __name__ == "__main__":
    unittest.main()

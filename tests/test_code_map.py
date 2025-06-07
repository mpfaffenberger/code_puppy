import os
from code_puppy.tools.code_map import make_code_map
from rich.tree import Tree


def test_make_code_map_tools_dir():
    # Use the tools directory itself!
    tools_dir = os.path.join(os.path.dirname(__file__), "../code_puppy/tools")
    tree = make_code_map(tools_dir)
    assert isinstance(tree, Tree)

    # Should have at least one file node (file child)
    # Helper to unwrap label recursively
    def unwrap_label(label):
        while hasattr(label, "label"):
            label = label.label
        return getattr(label, "plain", str(label))

    labels = [unwrap_label(child.label) for child in tree.children]
    assert any(".py" in lbl for lbl in labels), f"Children: {labels}"

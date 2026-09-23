"""Keep streaming parse diagnostics from flooding Speculative Puppy's terminal."""

import ast
import importlib
import warnings

from code_puppy.agents import agent_speculative_puppy


def test_only_generated_invalid_escape_warnings_are_suppressed():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.reload(agent_speculative_puppy)

        for _ in range(3):
            ast.parse(r'pattern = "\("')
        assert not captured

        ast.parse(r'pattern = "\("', filename="project_file.py")
        warnings.warn("another syntax warning", SyntaxWarning)
        warnings.warn("runtime warning", RuntimeWarning)

    assert len(captured) == 3
    assert "invalid escape sequence" in str(captured[0].message)
    assert str(captured[1].message) == "another syntax warning"
    assert captured[2].category is RuntimeWarning

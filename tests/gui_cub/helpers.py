"""Helper functions for desktop automation tests."""

from typing import Any, Dict


def validate_result_type(result, expected_type):
    """Validate that a result matches expected Pydantic type."""
    assert isinstance(result, expected_type), (
        f"Expected {expected_type}, got {type(result)}"
    )
    assert hasattr(result, "success"), "Result must have 'success' field"
    assert isinstance(result.success, bool), "'success' must be boolean"


def validate_tool_schema(schema: Dict[str, Any]):
    """Validate that a tool schema is well-formed."""
    # Check required top-level keys
    assert "type" in schema, "Schema must have 'type'"
    assert "properties" in schema, "Schema must have 'properties'"

    # Check each parameter
    for param_name, param_def in schema.get("properties", {}).items():
        assert "type" in param_def or "anyOf" in param_def, (
            f"Parameter '{param_name}' must have 'type' or 'anyOf'"
        )
        # Description is recommended but not required
        if "description" not in param_def:
            print(f"Warning: Parameter '{param_name}' has no description")


def extract_schema_from_tool(tool_func):
    """Extract JSON schema from a tool function."""
    # This depends on how pydantic-ai exposes schemas
    # May need to inspect function annotations
    if hasattr(tool_func, "__annotations__"):
        return tool_func.__annotations__
    return None


def assert_valid_coordinates(x, y, max_x=10000, max_y=10000):
    """Assert that coordinates are valid."""
    assert isinstance(x, int), "x must be integer"
    assert isinstance(y, int), "y must be integer"
    assert 0 <= x <= max_x, f"x must be 0-{max_x}"
    assert 0 <= y <= max_y, f"y must be 0-{max_y}"


def assert_valid_color_tuple(color):
    """Assert that a color tuple is valid RGB."""
    assert isinstance(color, tuple), "Color must be tuple"
    assert len(color) == 3, "Color must have 3 values (RGB)"
    for val in color:
        assert isinstance(val, int), "Color values must be integers"
        assert 0 <= val <= 255, "Color values must be 0-255"

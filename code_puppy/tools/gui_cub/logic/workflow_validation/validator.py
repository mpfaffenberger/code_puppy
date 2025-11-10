"""Pure workflow parameter validation logic.

This module provides pure functions for validating workflow parameters,
including type checking, required field validation, and type conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationError:
    """Validation error details."""

    parameter_name: str
    error_type: str  # "missing_required", "type_mismatch", "conversion_failed"
    message: str
    expected_type: str | None = None
    actual_value: Any = None


def validate_required_parameter(
    param_name: str,
    value: Any | None,
    default: Any | None,
    required: bool,
) -> tuple[bool, Any, ValidationError | None]:
    """
    Validate required parameter presence.

    Args:
        param_name: Parameter name
        value: Provided value (may be None)
        default: Default value if not provided
        required: Whether parameter is required

    Returns:
        Tuple of (is_valid, resolved_value, error)

    Examples:
        >>> validate_required_parameter("name", None, None, True)
        (False, None, ValidationError(...))
        >>> validate_required_parameter("name", "test", None, True)
        (True, "test", None)
        >>> validate_required_parameter("name", None, "default", False)
        (True, "default", None)
    """
    if value is None:
        if required and default is None:
            return (
                False,
                None,
                ValidationError(
                    parameter_name=param_name,
                    error_type="missing_required",
                    message=f"Missing required parameter: {param_name}",
                ),
            )
        # Use default if available
        return (True, default, None)

    return (True, value, None)


def convert_string_to_boolean(value: str) -> bool | None:
    """
    Convert string to boolean.

    Args:
        value: String value ("true", "false", "yes", "no", "1", "0")

    Returns:
        Boolean value or None if cannot convert

    Examples:
        >>> convert_string_to_boolean("true")
        True
        >>> convert_string_to_boolean("FALSE")
        False
        >>> convert_string_to_boolean("yes")
        True
        >>> convert_string_to_boolean("invalid")
        None
    """
    value_lower = value.lower()
    if value_lower in ("true", "yes", "1"):
        return True
    elif value_lower in ("false", "no", "0"):
        return False
    return None


def convert_to_number(value: Any) -> int | float:
    """
    Convert value to number (int or float).

    Args:
        value: Value to convert

    Returns:
        Converted number

    Raises:
        ValueError: If conversion fails

    Examples:
        >>> convert_to_number("42")
        42
        >>> convert_to_number("3.14")
        3.14
        >>> convert_to_number(100)
        100
    """
    if isinstance(value, (int, float)):
        return value

    value_str = str(value)
    if "." in value_str:
        return float(value_str)
    return int(value_str)


def convert_to_type(
    value: Any,
    expected_type: str,
    param_name: str,
) -> tuple[bool, Any, ValidationError | None]:
    """
    Convert value to expected type with validation.

    Args:
        value: Value to convert
        expected_type: Expected type ("string", "number", "boolean", "array", "object")
        param_name: Parameter name (for error messages)

    Returns:
        Tuple of (is_valid, converted_value, error)

    Examples:
        >>> convert_to_type("42", "number", "count")
        (True, 42, None)
        >>> convert_to_type("true", "boolean", "enabled")
        (True, True, None)
        >>> convert_to_type([1, 2], "string", "data")
        (True, "[1, 2]", None)
    """
    if value is None:
        return (True, None, None)

    try:
        if expected_type == "string":
            # Auto-convert to string
            return (True, str(value), None)

        elif expected_type == "number":
            if isinstance(value, (int, float)):
                return (True, value, None)
            converted = convert_to_number(value)
            return (True, converted, None)

        elif expected_type == "boolean":
            if isinstance(value, bool):
                return (True, value, None)
            if isinstance(value, str):
                converted = convert_string_to_boolean(value)
                if converted is not None:
                    return (True, converted, None)
                return (
                    False,
                    None,
                    ValidationError(
                        parameter_name=param_name,
                        error_type="conversion_failed",
                        message=f"Parameter '{param_name}' must be boolean, got '{value}'",
                        expected_type="boolean",
                        actual_value=value,
                    ),
                )
            # Try bool() conversion
            return (True, bool(value), None)

        elif expected_type == "array":
            if not isinstance(value, list):
                return (
                    False,
                    None,
                    ValidationError(
                        parameter_name=param_name,
                        error_type="type_mismatch",
                        message=f"Parameter '{param_name}' must be array, got {type(value).__name__}",
                        expected_type="array",
                        actual_value=value,
                    ),
                )
            return (True, value, None)

        elif expected_type == "object":
            if not isinstance(value, dict):
                return (
                    False,
                    None,
                    ValidationError(
                        parameter_name=param_name,
                        error_type="type_mismatch",
                        message=f"Parameter '{param_name}' must be object, got {type(value).__name__}",
                        expected_type="object",
                        actual_value=value,
                    ),
                )
            return (True, value, None)

        else:
            # Unknown type, pass through
            return (True, value, None)

    except (ValueError, TypeError) as e:
        return (
            False,
            None,
            ValidationError(
                parameter_name=param_name,
                error_type="conversion_failed",
                message=f"Failed to convert '{param_name}' to {expected_type}: {e}",
                expected_type=expected_type,
                actual_value=value,
            ),
        )


def validate_parameter_type(
    param_name: str,
    value: Any,
    expected_type: str,
) -> tuple[bool, Any, ValidationError | None]:
    """
    Validate and convert parameter to expected type.

    Combines type checking and conversion in one step.

    Args:
        param_name: Parameter name
        value: Value to validate
        expected_type: Expected type

    Returns:
        Tuple of (is_valid, converted_value, error)
    """
    return convert_to_type(value, expected_type, param_name)


def validate_all_parameters(
    parameter_specs: list[dict[str, Any]],
    provided_values: dict[str, Any],
) -> tuple[dict[str, Any], list[ValidationError]]:
    """
    Validate all parameters against specifications.

    Args:
        parameter_specs: List of parameter specifications with keys:
            - name (str): Parameter name
            - type (str): Expected type
            - required (bool): Whether required
            - default (Any, optional): Default value
        provided_values: Dict of provided parameter values

    Returns:
        Tuple of (validated_params, errors)
        If errors list is empty, validation succeeded.

    Examples:
        >>> specs = [{"name": "count", "type": "number", "required": True}]
        >>> validate_all_parameters(specs, {"count": "42"})
        ({'count': 42}, [])
        >>> validate_all_parameters(specs, {})
        ({}, [ValidationError(...)])
    """
    validated = {}
    errors = []

    for spec in parameter_specs:
        param_name = spec["name"]
        param_type = spec.get("type", "string")
        required = spec.get("required", False)
        default = spec.get("default")

        value = provided_values.get(param_name)

        # Check required
        is_valid, resolved_value, error = validate_required_parameter(
            param_name, value, default, required
        )

        if not is_valid:
            errors.append(error)
            continue

        # Type validation/conversion
        if resolved_value is not None:
            is_valid, converted_value, error = convert_to_type(
                resolved_value, param_type, param_name
            )

            if not is_valid:
                errors.append(error)
                continue

            validated[param_name] = converted_value

    return validated, errors

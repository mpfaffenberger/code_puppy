"""Test suite for GUI-Cub workflow management."""

import pytest

from code_puppy.tools.gui_cub.workflows import (
    WorkflowOutput,
    WorkflowParameter,
    parse_workflow_outputs,
    parse_workflow_parameters,
    validate_workflow_parameters,
)


class TestWorkflowParameter:
    """Test WorkflowParameter model."""

    def test_basic_parameter(self):
        """Test basic parameter creation."""
        param = WorkflowParameter(name="username", type="string")

        assert param.name == "username"
        assert param.type == "string"
        assert param.required is True
        assert param.default is None
        assert param.sensitive is False

    def test_optional_parameter_with_default(self):
        """Test parameter with default value."""
        param = WorkflowParameter(
            name="timeout", type="number", default=30, required=False
        )

        assert param.name == "timeout"
        assert param.default == 30
        assert param.required is False

    def test_sensitive_parameter(self):
        """Test sensitive parameter flag."""
        param = WorkflowParameter(
            name="password", type="string", sensitive=True, description="User password"
        )

        assert param.sensitive is True
        assert param.description == "User password"

    def test_parameter_with_example(self):
        """Test parameter with example value."""
        param = WorkflowParameter(
            name="email", type="string", example="user@example.com"
        )

        assert param.example == "user@example.com"


class TestWorkflowOutput:
    """Test WorkflowOutput model."""

    def test_basic_output(self):
        """Test basic output creation."""
        output = WorkflowOutput(name="result", description="Operation result")

        assert output.name == "result"
        assert output.description == "Operation result"
        assert output.extraction_method == "manual"

    def test_output_with_extraction_method(self):
        """Test output with specific extraction method."""
        output = WorkflowOutput(
            name="status_text",
            description="Status message from UI",
            extraction_method="ocr",
        )

        assert output.extraction_method == "ocr"


class TestParseWorkflowParameters:
    """Test parse_workflow_parameters function."""

    def test_parse_single_parameter(self):
        """Test parsing single parameter."""
        workflow_data = {
            "parameters": [{"name": "username", "type": "string", "required": True}]
        }

        params = parse_workflow_parameters(workflow_data)

        assert len(params) == 1
        assert params[0].name == "username"
        assert params[0].type == "string"

    def test_parse_multiple_parameters(self):
        """Test parsing multiple parameters."""
        workflow_data = {
            "parameters": [
                {"name": "username", "type": "string"},
                {"name": "timeout", "type": "number", "default": 30},
                {"name": "debug", "type": "boolean", "default": False},
            ]
        }

        params = parse_workflow_parameters(workflow_data)

        assert len(params) == 3
        assert params[0].name == "username"
        assert params[1].name == "timeout"
        assert params[1].default == 30
        assert params[2].name == "debug"
        assert params[2].default is False

    def test_parse_no_parameters(self):
        """Test parsing workflow with no parameters."""
        workflow_data = {}

        params = parse_workflow_parameters(workflow_data)

        assert len(params) == 0

    def test_parse_empty_parameters_list(self):
        """Test parsing empty parameters list."""
        workflow_data = {"parameters": []}

        params = parse_workflow_parameters(workflow_data)

        assert len(params) == 0


class TestParseWorkflowOutputs:
    """Test parse_workflow_outputs function."""

    def test_parse_single_output(self):
        """Test parsing single output."""
        workflow_data = {
            "outputs": [
                {
                    "name": "result",
                    "description": "Operation result",
                    "extraction_method": "manual",
                }
            ]
        }

        outputs = parse_workflow_outputs(workflow_data)

        assert len(outputs) == 1
        assert outputs[0].name == "result"
        assert outputs[0].extraction_method == "manual"

    def test_parse_multiple_outputs(self):
        """Test parsing multiple outputs."""
        workflow_data = {
            "outputs": [
                {"name": "status", "extraction_method": "ocr"},
                {"name": "screenshot", "extraction_method": "screenshot"},
            ]
        }

        outputs = parse_workflow_outputs(workflow_data)

        assert len(outputs) == 2
        assert outputs[0].extraction_method == "ocr"
        assert outputs[1].extraction_method == "screenshot"

    def test_parse_no_outputs(self):
        """Test parsing workflow with no outputs."""
        workflow_data = {}

        outputs = parse_workflow_outputs(workflow_data)

        assert len(outputs) == 0


class TestValidateWorkflowParameters:
    """Test validate_workflow_parameters function."""

    def test_validate_required_parameter_provided(self):
        """Test validation passes when required parameter is provided."""
        params = [WorkflowParameter(name="username", type="string", required=True)]
        provided = {"username": "john_doe"}

        validated = validate_workflow_parameters(params, provided)

        assert validated["username"] == "john_doe"

    def test_validate_required_parameter_missing_raises_error(self):
        """Test validation fails when required parameter is missing."""
        params = [WorkflowParameter(name="username", type="string", required=True)]
        provided = {}

        with pytest.raises(ValueError, match="Missing required parameter: username"):
            validate_workflow_parameters(params, provided)

    def test_validate_optional_parameter_with_default(self):
        """Test optional parameter uses default when not provided."""
        params = [
            WorkflowParameter(name="timeout", type="number", required=False, default=30)
        ]
        provided = {}

        validated = validate_workflow_parameters(params, provided)

        assert validated["timeout"] == 30

    def test_validate_optional_parameter_override_default(self):
        """Test optional parameter can override default."""
        params = [
            WorkflowParameter(name="timeout", type="number", required=False, default=30)
        ]
        provided = {"timeout": 60}

        validated = validate_workflow_parameters(params, provided)

        assert validated["timeout"] == 60

    def test_validate_string_type(self):
        """Test string type validation and auto-conversion."""
        params = [WorkflowParameter(name="name", type="string")]

        # String input
        validated = validate_workflow_parameters(params, {"name": "test"})
        assert validated["name"] == "test"

        # Auto-convert number to string
        validated = validate_workflow_parameters(params, {"name": 123})
        assert validated["name"] == "123"

    def test_validate_number_type_int(self):
        """Test number type validation with integers."""
        params = [WorkflowParameter(name="count", type="number")]

        validated = validate_workflow_parameters(params, {"count": 42})
        assert validated["count"] == 42

    def test_validate_number_type_float(self):
        """Test number type validation with floats."""
        params = [WorkflowParameter(name="ratio", type="number")]

        validated = validate_workflow_parameters(params, {"ratio": 3.14})
        assert validated["ratio"] == 3.14

    def test_validate_number_type_string_conversion(self):
        """Test number type converts from string."""
        params = [WorkflowParameter(name="timeout", type="number")]

        # Integer string
        validated = validate_workflow_parameters(params, {"timeout": "30"})
        assert validated["timeout"] == 30

        # Float string
        validated = validate_workflow_parameters(params, {"timeout": "30.5"})
        assert validated["timeout"] == 30.5

    def test_validate_number_type_invalid_raises_error(self):
        """Test number type validation fails on invalid input."""
        params = [WorkflowParameter(name="count", type="number")]

        with pytest.raises(TypeError, match="must be number"):
            validate_workflow_parameters(params, {"count": "not_a_number"})

    def test_validate_boolean_type_true(self):
        """Test boolean type validation with true values."""
        params = [WorkflowParameter(name="debug", type="boolean")]

        # Boolean input
        validated = validate_workflow_parameters(params, {"debug": True})
        assert validated["debug"] is True

        # String "true"
        validated = validate_workflow_parameters(params, {"debug": "true"})
        assert validated["debug"] is True

        # String "yes"
        validated = validate_workflow_parameters(params, {"debug": "yes"})
        assert validated["debug"] is True

        # String "1"
        validated = validate_workflow_parameters(params, {"debug": "1"})
        assert validated["debug"] is True

    def test_validate_boolean_type_false(self):
        """Test boolean type validation with false values."""
        params = [WorkflowParameter(name="debug", type="boolean")]

        # Boolean input
        validated = validate_workflow_parameters(params, {"debug": False})
        assert validated["debug"] is False

        # String "false"
        validated = validate_workflow_parameters(params, {"debug": "false"})
        assert validated["debug"] is False

        # String "no"
        validated = validate_workflow_parameters(params, {"debug": "no"})
        assert validated["debug"] is False

        # String "0"
        validated = validate_workflow_parameters(params, {"debug": "0"})
        assert validated["debug"] is False

    def test_validate_boolean_type_invalid_raises_error(self):
        """Test boolean type validation fails on invalid string."""
        params = [WorkflowParameter(name="debug", type="boolean")]

        with pytest.raises(TypeError, match="must be boolean"):
            validate_workflow_parameters(params, {"debug": "maybe"})

    def test_validate_array_type(self):
        """Test array type validation."""
        params = [WorkflowParameter(name="items", type="array")]

        validated = validate_workflow_parameters(params, {"items": [1, 2, 3]})
        assert validated["items"] == [1, 2, 3]

    def test_validate_array_type_invalid_raises_error(self):
        """Test array type validation fails on non-list."""
        params = [WorkflowParameter(name="items", type="array")]

        with pytest.raises(TypeError, match="must be array"):
            validate_workflow_parameters(params, {"items": "not_a_list"})

    def test_validate_object_type(self):
        """Test object type validation."""
        params = [WorkflowParameter(name="config", type="object")]

        validated = validate_workflow_parameters(params, {"config": {"key": "value"}})
        assert validated["config"] == {"key": "value"}

    def test_validate_object_type_invalid_raises_error(self):
        """Test object type validation fails on non-dict."""
        params = [WorkflowParameter(name="config", type="object")]

        with pytest.raises(TypeError, match="must be object"):
            validate_workflow_parameters(params, {"config": "not_an_object"})

    def test_validate_multiple_parameters_mixed_types(self):
        """Test validation with multiple parameters of different types."""
        params = [
            WorkflowParameter(name="username", type="string", required=True),
            WorkflowParameter(name="timeout", type="number", default=30),
            WorkflowParameter(name="debug", type="boolean", default=False),
            WorkflowParameter(name="tags", type="array", required=False),
        ]

        provided = {"username": "john", "timeout": 60, "debug": True}

        validated = validate_workflow_parameters(params, provided)

        assert validated["username"] == "john"
        assert validated["timeout"] == 60
        assert validated["debug"] is True
        assert "tags" not in validated  # Not provided, no default

    def test_validate_ignores_extra_parameters(self):
        """Test that extra provided parameters don't cause errors."""
        params = [WorkflowParameter(name="username", type="string")]

        provided = {"username": "john", "extra_param": "ignored"}

        validated = validate_workflow_parameters(params, provided)

        # Should only validate defined parameters
        assert validated == {"username": "john"}

    def test_validate_required_parameter_with_default(self):
        """Test required parameter can still have a default."""
        params = [
            WorkflowParameter(
                name="mode", type="string", required=True, default="production"
            )
        ]

        # Not provided - should use default
        validated = validate_workflow_parameters(params, {})
        assert validated["mode"] == "production"

        # Provided - should use provided value
        validated = validate_workflow_parameters(params, {"mode": "development"})
        assert validated["mode"] == "development"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
